#!/usr/bin/env python3
"""Sample N random pages per document; flag transformation defects via API."""
from __future__ import annotations

import argparse
import json
import random
import re
import urllib.request
from pathlib import Path

API = "http://localhost:8000/api"
JAMMED = re.compile(r"[A-Za-z]{25,}")
BOLD_SUB = re.compile(r"<li>\s*<strong>\s*\([0-9a-zA-Z]+\)", re.I)


def get(path: str):
    with urllib.request.urlopen(API + path, timeout=60) as r:
        return json.loads(r.read().decode())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=10)
    ap.add_argument("--seed", type=int, default=661395)
    ap.add_argument("--limit-docs", type=int, default=0)
    ap.add_argument("--source", choices=["acts", "ordinance", "all"], default="acts")
    ap.add_argument("-o", type=Path, default=Path("/tmp/crx_page_sample.json"))
    args = ap.parse_args()
    random.seed(args.seed)

    docs = get("/documents")
    if args.source == "acts":
        docs = [d for d in docs if d.get("source_type") == "acts_corpus"]
    elif args.source == "ordinance":
        docs = [d for d in docs if d.get("source_type") != "acts_corpus"]
    if args.limit_docs:
        docs = docs[: args.limit_docs]

    findings = []
    page_stats = {
        "checked": 0,
        "empty": 0,
        "thin": 0,
        "jammed": 0,
        "bold_sub": 0,
        "page_bleed": 0,
        "no_sections_mid": 0,
        "ok_docs": 0,
    }

    for doc in docs:
        pages = doc.get("total_pages") or 0
        if pages < 1:
            continue
        n = min(args.pages, pages)
        picks = {1, pages}
        while len(picks) < n:
            picks.add(random.randint(1, pages))
        sample = sorted(picks)[:n]
        doc_issues = []
        for p in sample:
            page_stats["checked"] += 1
            try:
                secs = get(f"/documents/{doc['id']}/sections/by-page/{p}")
            except Exception as e:  # noqa: BLE001
                doc_issues.append({"page": p, "issue": "api_error", "detail": str(e)[:120]})
                continue
            if not secs:
                if 2 < p < pages - 1:
                    page_stats["no_sections_mid"] += 1
                    doc_issues.append({"page": p, "issue": "no_sections"})
                continue
            for s in secs:
                html = s.get("html_content") or s.get("html") or ""
                plain = s.get("plain_text") or ""
                code = s.get("code")
                if not html and not plain:
                    page_stats["empty"] += 1
                    doc_issues.append({"page": p, "code": code, "issue": "empty_content"})
                    continue
                if len(plain or html) < 15:
                    page_stats["thin"] += 1
                    doc_issues.append(
                        {"page": p, "code": code, "issue": "thin_content", "len": len(plain or html)}
                    )
                for m in JAMMED.findall(plain or ""):
                    if "http" in m.lower():
                        continue
                    page_stats["jammed"] += 1
                    doc_issues.append(
                        {"page": p, "code": code, "issue": "jammed_word", "word": m[:60]}
                    )
                    break
                if BOLD_SUB.search(html or ""):
                    page_stats["bold_sub"] += 1
                    doc_issues.append(
                        {"page": p, "code": code, "issue": "bold_subsection_marker"}
                    )
                lines = [ln.strip() for ln in (plain or "").splitlines() if ln.strip()]
                if lines and re.fullmatch(r"\d{1,3}", lines[-1]):
                    page_stats["page_bleed"] += 1
                    doc_issues.append(
                        {
                            "page": p,
                            "code": code,
                            "issue": "page_number_bleed",
                            "val": lines[-1],
                        }
                    )
        if not doc_issues:
            page_stats["ok_docs"] += 1
        findings.append(
            {
                "name": doc["name"],
                "id": doc["id"],
                "pages": pages,
                "sampled": sample,
                "n_issues": len(doc_issues),
                "issues": doc_issues[:20],
                "health_fail": (doc.get("health") or {}).get("failing_invariants") or [],
                "fn_miss": (doc.get("health") or {}).get("footnote_missing"),
            }
        )

    findings.sort(
        key=lambda x: (-x["n_issues"], -len(x["health_fail"]), -(x["fn_miss"] or 0))
    )
    out = {
        "page_stats": page_stats,
        "docs_with_issues": sum(1 for f in findings if f["n_issues"]),
        "docs_clean": sum(1 for f in findings if not f["n_issues"]),
        "worst": findings[:25],
        "findings": findings,
    }
    args.o.write_text(json.dumps(out, indent=2))
    print(json.dumps({"stats": page_stats, "docs_with_issues": out["docs_with_issues"], "docs_clean": out["docs_clean"], "out": str(args.o)}, indent=2))
    print("--- worst ---")
    for f in findings[:15]:
        print(
            f"{f['n_issues']:3} issues | inv={f['health_fail']} fn_miss={f['fn_miss']} | {f['name'][:70]}"
        )
        for i in f["issues"][:4]:
            print("   ", i)


if __name__ == "__main__":
    main()
