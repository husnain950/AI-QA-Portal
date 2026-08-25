"""OpenAI-compatible chat client for the AI fix loop.

Deliberately thin: one call shape (chat completions with optional vision parts),
configured entirely from the environment so the portal runs fine without it.

Two sources feed one model registry (dropdown id -> endpoint spec):

    OPENPATHS_API_KEY    bearer token (never logged, never echoed in errors)
    OPENPATHS_BASE_URL   e.g. https://openpaths.io/v1
    OPENPATHS_MODELS     optional prefer/allow list. When unset, the dropdown is
                         filled from GET {BASE_URL}/models (top chat models fit
                         for legal PDF→JSON fixing). When set, those ids are
                         kept in order and enriched with catalog metadata.
    OPENPATHS_MODEL      legacy single-model form, still honoured

    LLM_EXTRA_PROVIDERS  one JSON object for models on OTHER endpoints, e.g.
                         self-hosted deployments:
                         {"kimi": {"base_url": "https://.../v1",
                                   "model": "<endpoint model name>",
                                   "env_key": "<api key>",
                                   "extra": {"reasoning_effort": "low"}}}
                         ``extra`` is merged into the request payload.
                         ``api_key`` is accepted as a synonym for ``env_key``.

The first registry entry is the default model. Everything is read at call
time, not import time, so tests can monkeypatch the environment and a missing
key fails the request rather than the process.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx2 as httpx

REQUEST_TIMEOUT_SECONDS = 180.0
CATALOG_TIMEOUT_SECONDS = 20.0
CATALOG_CACHE_TTL_SECONDS = 300.0
DROPDOWN_LIMIT = 10

_ENV_KEY = "OPENPATHS_API_KEY"
_ENV_BASE_URL = "OPENPATHS_BASE_URL"
_ENV_MODELS = "OPENPATHS_MODELS"
_ENV_MODEL = "OPENPATHS_MODEL"
_ENV_EXTRA = "LLM_EXTRA_PROVIDERS"

# Specialty / non-chat ids we never offer for AI fix.
_EXCLUDE_ID = re.compile(
    r"(embed|tts|stt|whisper|transcribe|speech|music|realtime|voice|"
    r"image|video|diffusion|seedance|sora|veo|kling|flux|dall-e|"
    r"meshy|trellis|hailuo|lyria|wan$|chronos|pocket-tts)",
    re.IGNORECASE,
)
# Prefer first-party gateway ids over mirrored vendor routes.
_MIRROR_PREFIX = re.compile(r"^(or|fireworks|together|nvidia|cursor|alibaba|zai)/")

# Families that work well for careful legal transcription + optional vision.
_FAMILY_BOOST = (
    (re.compile(r"^claude-sonnet", re.I), 120),
    (re.compile(r"^claude-opus", re.I), 90),
    (re.compile(r"^claude-haiku", re.I), 70),
    (re.compile(r"^gpt-5", re.I), 110),
    (re.compile(r"^gpt-4o", re.I), 100),
    (re.compile(r"^o[34]", re.I), 85),
    (re.compile(r"^gemini-", re.I), 95),
    (re.compile(r"^kimi", re.I), 105),
    (re.compile(r"^grok-4", re.I), 80),
    (re.compile(r"^glm-4\.6v", re.I), 75),
    (re.compile(r"^deepseek.*vision", re.I), 70),
    (re.compile(r"^openpaths/auto", re.I), 60),
    (re.compile(r"^mistral-", re.I), 55),
    (re.compile(r"^qwen", re.I), 50),
)

_catalog_cache: Dict[str, Any] = {"fetched_at": 0.0, "by_id": {}}


class LLMNotConfigured(Exception):
    """The gateway env vars are absent; the feature is off, not broken."""


class LLMError(Exception):
    """The gateway was reachable but the call failed."""


def _models_from_env() -> List[str]:
    raw = os.environ.get(_ENV_MODELS) or os.environ.get(_ENV_MODEL) or ""
    seen: List[str] = []
    for name in raw.split(","):
        name = name.strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def _openpaths_credentials() -> Tuple[str, str]:
    api_key = (os.environ.get(_ENV_KEY) or "").strip()
    base_url = (os.environ.get(_ENV_BASE_URL) or "").strip()
    return api_key, base_url


def _extra_providers() -> Dict[str, Dict[str, Any]]:
    raw = (os.environ.get(_ENV_EXTRA) or "").strip()
    if not raw:
        return {}
    try:
        extra_providers = json.loads(raw)
    except ValueError as error:
        raise LLMNotConfigured(f"{_ENV_EXTRA} is not valid JSON: {error}")
    if not isinstance(extra_providers, dict):
        raise LLMNotConfigured(f"{_ENV_EXTRA} must be a JSON object")
    entries: Dict[str, Dict[str, Any]] = {}
    for name, spec in extra_providers.items():
        if not isinstance(spec, dict) or not spec.get("base_url"):
            raise LLMNotConfigured(
                f"{_ENV_EXTRA} entry {name!r} needs at least a base_url"
            )
        entries[str(name)] = {
            "base_url": str(spec["base_url"]),
            "model": str(spec.get("model") or name),
            "api_key": str(spec.get("api_key") or spec.get("env_key") or ""),
            "extra": spec.get("extra") or {},
            "vision": bool(spec.get("vision", False)),
            "label": str(spec.get("label") or _humanize_id(str(name))),
            "input_price_per_1m": _as_float(spec.get("input_price_per_1m")),
            "output_price_per_1m": _as_float(spec.get("output_price_per_1m")),
        }
    return entries


def _as_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _humanize_id(model_id: str) -> str:
    """Turn a gateway id into a short label for the dropdown."""
    short = model_id.split("/")[-1]
    short = re.sub(r"-\d{8}$", "", short)
    # claude-sonnet-4-5 → claude-sonnet-4.5
    short = re.sub(r"(?<=\d)-(?=\d)", ".", short)
    parts = short.replace("_", "-").split("-")
    out: List[str] = []
    for part in parts:
        lower = part.lower()
        if lower in {"gpt", "glm", "tts", "stt", "pdf"}:
            out.append(part.upper())
        elif lower == "kimi":
            out.append("Kimi")
        elif re.fullmatch(r"\d+(\.\d+)*", part):
            out.append(part)
        elif re.fullmatch(r"[a-z]+\d+(\.\d+)*", lower):
            # e.g. k2.5, v4 → keep compact
            out.append(part[0].upper() + part[1:])
        else:
            out.append(part[:1].upper() + part[1:])
    return " ".join(out)


def _family_key(model_id: str) -> str:
    """Collapse versioned ids so we keep one entry per product family."""
    short = model_id.split("/")[-1].lower()
    short = re.sub(r"-\d{8}$", "", short)
    short = re.sub(r"-(latest|preview|exp|highspeed)$", "", short)
    for prefix in (
        "claude-sonnet",
        "claude-opus",
        "claude-haiku",
        "claude-fable",
        "gpt-5",
        "gpt-4o",
        "gemini",
        "kimi",
        "grok-4",
        "glm-4.6v",
        "deepseek",
        "mistral",
        "openpaths/auto",
    ):
        bare = prefix.split("/")[-1]
        if short.startswith(bare) or model_id.lower().startswith(prefix):
            return prefix
    # Strip trailing version tokens: gpt-5.4-mini → gpt-5
    return re.split(r"[-.](?=\d)", short, maxsplit=1)[0]


def _is_chat_model(entry: Dict[str, Any]) -> bool:
    pricing = entry.get("pricing") or {}
    if "input_per_1m_tokens" not in pricing or "output_per_1m_tokens" not in pricing:
        return False
    model_id = str(entry.get("id") or "")
    if not model_id or _EXCLUDE_ID.search(model_id):
        return False
    return True


def _score_model(entry: Dict[str, Any]) -> float:
    model_id = str(entry["id"])
    caps = entry.get("capabilities") or {}
    pricing = entry.get("pricing") or {}
    score = 0.0
    if caps.get("vision"):
        score += 100
    if caps.get("tools"):
        score += 8
    for pattern, boost in _FAMILY_BOOST:
        if pattern.search(model_id):
            score += boost
            break
    else:
        score += 10
    if _MIRROR_PREFIX.match(model_id):
        score -= 40
    if model_id.endswith("-latest"):
        score += 6
    # Prefer mid-range pricing; penalize extreme cost.
    try:
        inp = float(pricing.get("input_per_1m_tokens") or 0)
        out = float(pricing.get("output_per_1m_tokens") or 0)
        if inp + out > 40:
            score -= 25
        elif inp + out > 20:
            score -= 8
        if 0 < inp + out < 1:
            score += 4
    except (TypeError, ValueError):
        pass
    # Prefer shorter canonical ids over dated snapshots when scores tie.
    score -= min(len(model_id), 40) * 0.05
    return score


def _catalog_entry_to_info(entry: Dict[str, Any]) -> Dict[str, Any]:
    pricing = entry.get("pricing") or {}
    caps = entry.get("capabilities") or {}
    model_id = str(entry["id"])
    return {
        "id": model_id,
        "label": _humanize_id(model_id),
        "vision": bool(caps.get("vision")),
        "input_price_per_1m": _as_float(pricing.get("input_per_1m_tokens")),
        "output_price_per_1m": _as_float(pricing.get("output_per_1m_tokens")),
    }


def _select_top_models(catalog: Dict[str, Dict[str, Any]], *, limit: int = DROPDOWN_LIMIT) -> List[Dict[str, Any]]:
    """Pick up to ``limit`` chat models suited to AI fix work; always keep Kimi."""
    candidates = [entry for entry in catalog.values() if _is_chat_model(entry)]
    candidates.sort(key=_score_model, reverse=True)

    selected: List[Dict[str, Any]] = []
    seen_families: set[str] = set()
    for entry in candidates:
        family = _family_key(str(entry["id"]))
        if family in seen_families:
            continue
        selected.append(_catalog_entry_to_info(entry))
        seen_families.add(family)
        if len(selected) >= limit:
            break

    # Guarantee a Kimi option when the catalog (or an alias) has one.
    if not any("kimi" in m["id"].lower() for m in selected):
        kimi_hits = [
            entry
            for entry in candidates
            if "kimi" in str(entry.get("id") or "").lower()
        ]
        if kimi_hits:
            kimi_hits.sort(key=_score_model, reverse=True)
            info = _catalog_entry_to_info(kimi_hits[0])
            if len(selected) >= limit:
                selected[-1] = info
            else:
                selected.append(info)

    return selected[:limit]


def clear_catalog_cache() -> None:
    """Test helper: drop the in-process /models cache."""
    _catalog_cache["fetched_at"] = 0.0
    _catalog_cache["by_id"] = {}


async def fetch_openpaths_catalog(*, force: bool = False) -> Dict[str, Dict[str, Any]]:
    """GET {BASE_URL}/models; cached briefly. Returns id -> raw catalog row."""
    api_key, base_url = _openpaths_credentials()
    if not api_key or not base_url:
        return {}

    now = time.monotonic()
    if (
        not force
        and _catalog_cache["by_id"]
        and now - float(_catalog_cache["fetched_at"]) < CATALOG_CACHE_TTL_SECONDS
    ):
        return dict(_catalog_cache["by_id"])

    url = base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=CATALOG_TIMEOUT_SECONDS) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as error:
        raise LLMError(f"models catalog request failed: {type(error).__name__}: {error}")

    if response.status_code != 200:
        body = response.text[:500]
        raise LLMError(f"models catalog returned HTTP {response.status_code}: {body}")

    try:
        payload = response.json()
        rows = payload.get("data", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise TypeError("expected a list of models")
    except (ValueError, TypeError) as error:
        raise LLMError(f"models catalog was not list-shaped: {error}")

    by_id: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("id"):
            by_id[str(row["id"])] = row

    _catalog_cache["fetched_at"] = now
    _catalog_cache["by_id"] = by_id
    return dict(by_id)


def _info_from_spec(model_id: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": model_id,
        "label": str(spec.get("label") or _humanize_id(model_id)),
        "vision": bool(spec.get("vision", False)),
        "input_price_per_1m": _as_float(spec.get("input_price_per_1m")),
        "output_price_per_1m": _as_float(spec.get("output_price_per_1m")),
    }


async def list_model_infos() -> List[Dict[str, Any]]:
    """Rich dropdown rows: id, label, vision, pricing. First entry is default."""
    api_key, base_url = _openpaths_credentials()
    prefer = _models_from_env()
    extras = _extra_providers()
    infos: List[Dict[str, Any]] = []
    seen: set[str] = set()

    catalog: Dict[str, Dict[str, Any]] = {}
    if api_key and base_url:
        try:
            catalog = await fetch_openpaths_catalog()
        except LLMError:
            # Fall back to env allow-list / extras if the catalog is down.
            catalog = {}

    if prefer:
        for name in prefer:
            if name in seen:
                continue
            if name in catalog:
                infos.append(_catalog_entry_to_info(catalog[name]))
            else:
                infos.append(
                    {
                        "id": name,
                        "label": _humanize_id(name),
                        "vision": False,
                        "input_price_per_1m": None,
                        "output_price_per_1m": None,
                    }
                )
            seen.add(name)
    elif catalog:
        for info in _select_top_models(catalog):
            if info["id"] not in seen:
                infos.append(info)
                seen.add(info["id"])

    for name, spec in extras.items():
        if name in seen:
            # Extra provider overrides routing; keep metadata if richer.
            continue
        infos.append(_info_from_spec(name, spec))
        seen.add(name)

    if not infos:
        raise LLMNotConfigured(
            "AI fixes are not configured; set OPENPATHS_API_KEY and "
            f"OPENPATHS_BASE_URL (and/or {_ENV_EXTRA})"
        )
    return infos


def _sync_registry_fallback() -> Dict[str, Dict[str, Any]]:
    """Sync path used when only env allow-list / extras are configured (tests)."""
    entries: Dict[str, Dict[str, Any]] = {}
    api_key, base_url = _openpaths_credentials()
    if api_key and base_url:
        for name in _models_from_env():
            entries[name] = {
                "base_url": base_url,
                "model": name,
                "api_key": api_key,
                "extra": {},
                "vision": False,
                "label": _humanize_id(name),
                "input_price_per_1m": None,
                "output_price_per_1m": None,
            }
    for name, spec in _extra_providers().items():
        entries[name] = {
            "base_url": spec["base_url"],
            "model": spec["model"],
            "api_key": spec["api_key"],
            "extra": spec["extra"],
            "vision": bool(spec.get("vision", False)),
            "label": spec.get("label") or _humanize_id(name),
            "input_price_per_1m": spec.get("input_price_per_1m"),
            "output_price_per_1m": spec.get("output_price_per_1m"),
        }
    if not entries:
        api_key, base_url = _openpaths_credentials()
        if api_key and base_url:
            # Models come from the live catalog; sync registry stays empty.
            return entries
        raise LLMNotConfigured(
            "AI fixes are not configured; set OPENPATHS_API_KEY and "
            f"OPENPATHS_BASE_URL (and/or {_ENV_EXTRA})"
        )
    return entries


def configured() -> bool:
    try:
        if (os.environ.get(_ENV_EXTRA) or "").strip():
            _extra_providers()  # invalid JSON disables the feature
        api_key, base_url = _openpaths_credentials()
        if api_key and base_url:
            return True
        return bool(_extra_providers())
    except LLMNotConfigured:
        return False


def available_models() -> List[str]:
    """Sync allow-list (env + extras). Prefer ``list_model_infos`` for the UI."""
    return list(_sync_registry_fallback().keys())


def default_model() -> str:
    models = available_models()
    if models:
        return models[0]
    cached = list((_catalog_cache.get("by_id") or {}).keys())
    if cached:
        return cached[0]
    raise LLMNotConfigured("no models configured")


def resolve_model(requested: str | None) -> str:
    """Validate a UI-chosen model against env/extras/catalog-cache; None = default."""
    models = available_models()
    cached_ids = set((_catalog_cache.get("by_id") or {}).keys())
    known = list(dict.fromkeys([*models, *sorted(cached_ids)]))
    api_key, base_url = _openpaths_credentials()
    openpaths_ready = bool(api_key and base_url)
    if requested is None or not str(requested).strip():
        if known:
            return known[0]
        raise LLMNotConfigured("no models configured")
    requested = requested.strip()
    if requested in known or requested in cached_ids:
        return requested
    # Dynamic catalog mode: any OpenPaths id is routable once credentials exist.
    if openpaths_ready and not _models_from_env():
        return requested
    raise ValueError(
        f"unknown model {requested!r}; configured models: {', '.join(known) or '(none)'}"
    )


async def resolve_model_async(requested: str | None) -> str:
    """Validate against the live dropdown (catalog + extras)."""
    infos = await list_model_infos()
    ids = [row["id"] for row in infos]
    if requested is None or not str(requested).strip():
        return ids[0]
    requested = requested.strip()
    if requested not in ids:
        raise ValueError(
            f"unknown model {requested!r}; configured models: {', '.join(ids)}"
        )
    return requested


def model_supports_vision(model: str | None) -> bool:
    """Whether PDF page images should be attached for this dropdown id."""
    if not model:
        return False
    cached = (_catalog_cache.get("by_id") or {}).get(model)
    if isinstance(cached, dict):
        caps = cached.get("capabilities") or {}
        if "vision" in caps:
            return bool(caps.get("vision"))
    try:
        extras = _extra_providers()
    except LLMNotConfigured:
        extras = {}
    if model in extras:
        return bool(extras[model].get("vision", False))
    # Env-only OpenPaths ids without catalog metadata: assume vision so we
    # keep today's behaviour (AI fix always sends page images).
    return True


def request_spec(
    model: str | None,
) -> Tuple[str, str, Dict[str, Any]]:
    """(url, api_key, payload base) for a dropdown model id."""
    resolved = resolve_model(model)
    registry = _sync_registry_fallback()
    if resolved in registry:
        entry = registry[resolved]
    else:
        # Catalog-selected OpenPaths id (not in OPENPATHS_MODELS).
        api_key, base_url = _openpaths_credentials()
        if not api_key or not base_url:
            raise ValueError(f"unknown model {resolved!r}")
        extras = {}
        try:
            extras = _extra_providers()
        except LLMNotConfigured:
            pass
        if resolved in extras:
            entry = extras[resolved]
        else:
            entry = {
                "base_url": base_url,
                "model": resolved,
                "api_key": api_key,
                "extra": {},
            }
    url = entry["base_url"].rstrip("/") + "/chat/completions"
    payload: Dict[str, Any] = {"model": entry["model"], **(entry.get("extra") or {})}
    return url, entry["api_key"], payload


async def chat(
    messages: List[Dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.0,
) -> str:
    """Send a chat-completions request and return the assistant message text."""
    url, api_key, payload = request_spec(model)
    payload.update(messages=messages, temperature=temperature)

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as error:
        # The exception text can embed the URL but never the Authorization header.
        raise LLMError(f"gateway request failed: {type(error).__name__}: {error}")

    if response.status_code != 200:
        body = response.text[:500]
        raise LLMError(f"gateway returned HTTP {response.status_code}: {body}")

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMError(
            "gateway response was not chat-completions shaped: "
            + json.dumps(response.text[:300])
        )
    if not isinstance(content, str) or not content.strip():
        raise LLMError("gateway returned an empty completion")
    return content
