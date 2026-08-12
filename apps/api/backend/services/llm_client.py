"""OpenAI-compatible chat client for the AI fix loop.

Deliberately thin: one call shape (chat completions with optional vision parts),
configured entirely from the environment so the portal runs fine without it.

Two sources feed one model registry (dropdown id -> endpoint spec):

    OPENPATHS_API_KEY    bearer token (never logged, never echoed in errors)
    OPENPATHS_BASE_URL   e.g. https://openpaths.io/v1
    OPENPATHS_MODELS     comma-separated allow-list; every entry becomes a
                         registry model on the OpenPaths gateway
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
from typing import Any, Dict, List, Tuple

import httpx2 as httpx

REQUEST_TIMEOUT_SECONDS = 180.0
_ENV_KEY = "OPENPATHS_API_KEY"
_ENV_BASE_URL = "OPENPATHS_BASE_URL"
_ENV_MODELS = "OPENPATHS_MODELS"
_ENV_MODEL = "OPENPATHS_MODEL"
_ENV_EXTRA = "LLM_EXTRA_PROVIDERS"


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


def _registry() -> Dict[str, Dict[str, Any]]:
    """Dropdown id -> {base_url, model, api_key, extra}, in dropdown order."""
    entries: Dict[str, Dict[str, Any]] = {}

    api_key = (os.environ.get(_ENV_KEY) or "").strip()
    base_url = (os.environ.get(_ENV_BASE_URL) or "").strip()
    if api_key and base_url:
        for name in _models_from_env():
            entries[name] = {
                "base_url": base_url,
                "model": name,
                "api_key": api_key,
                "extra": {},
            }

    raw = (os.environ.get(_ENV_EXTRA) or "").strip()
    if raw:
        try:
            extra_providers = json.loads(raw)
        except ValueError as error:
            raise LLMNotConfigured(f"{_ENV_EXTRA} is not valid JSON: {error}")
        if not isinstance(extra_providers, dict):
            raise LLMNotConfigured(f"{_ENV_EXTRA} must be a JSON object")
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
            }

    if not entries:
        raise LLMNotConfigured(
            "AI fixes are not configured; set OPENPATHS_API_KEY, "
            f"OPENPATHS_BASE_URL and OPENPATHS_MODELS (and/or {_ENV_EXTRA})"
        )
    return entries


def configured() -> bool:
    try:
        _registry()
    except LLMNotConfigured:
        return False
    return True


def available_models() -> List[str]:
    """The configured allow-list. The first entry is the default."""
    return list(_registry().keys())


def default_model() -> str:
    return available_models()[0]


def resolve_model(requested: str | None) -> str:
    """Validate a UI-chosen model against the allow-list; None means default."""
    models = available_models()
    if requested is None or not requested.strip():
        return models[0]
    requested = requested.strip()
    if requested not in models:
        raise ValueError(
            f"unknown model {requested!r}; configured models: {', '.join(models)}"
        )
    return requested


def request_spec(
    model: str | None,
) -> Tuple[str, str, Dict[str, Any]]:
    """(url, api_key, payload base) for a dropdown model id."""
    entry = _registry()[resolve_model(model)]
    url = entry["base_url"].rstrip("/") + "/chat/completions"
    payload: Dict[str, Any] = {"model": entry["model"], **entry["extra"]}
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
