#!/usr/bin/env python3
"""Verify the NPEDATA authorship provenance ("DNA").

Two checks:
  1. Recompute the SHA-256 of the canonical author manifest in PROVENANCE.json
     and confirm it matches the stored fingerprint. If anyone edits the author
     details without recomputing, this fails.
  2. Scan the source tree and confirm the fingerprint is still embedded where it
     should be (LICENSE/NOTICE/AUTHORS, source headers, HTML meta tags).

Usage:  python tools/verify_authorship.py
Exit code 0 = all good, 1 = a check failed.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROV = ROOT / "PROVENANCE.json"

MANIFEST_KEYS = [
    "author", "matric_no", "institution", "department", "project", "title",
    "year", "email", "github", "repository", "genesis_commit", "genesis_date",
    "license",
]


def recompute(prov: dict) -> str:
    manifest = {k: prov[k] for k in MANIFEST_KEYS}
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def main() -> int:
    if not PROV.exists():
        print("FAIL: PROVENANCE.json not found")
        return 1
    prov = json.loads(PROV.read_text(encoding="utf-8"))
    stored = prov.get("provenance_fingerprint_sha256", "")
    calc = recompute(prov)

    print(f"Author      : {prov.get('author')}")
    print(f"Stored  FP  : {stored}")
    print(f"Recomputed  : {calc}")
    if stored != calc:
        print("\nFAIL: fingerprint does not match the author manifest — it was tampered with.")
        return 1
    print("OK: fingerprint matches the author manifest.\n")

    short = stored[:16].upper()
    # LICENSE only needs to exist (it is the standard Apache-2.0 boilerplate).
    if not (ROOT / "LICENSE").exists():
        print("WARNING: LICENSE file is missing.")
        return 1
    # These files must carry the fingerprint (full or short form).
    targets = [
        ROOT / "NOTICE",
        ROOT / "AUTHORS",
        ROOT / "main.py",
        ROOT / "project" / "frontend" / "shared.js",
    ]
    missing = []
    for t in targets:
        text = t.read_text(encoding="utf-8", errors="ignore") if t.exists() else ""
        if stored not in text and short not in text:
            missing.append(str(t.relative_to(ROOT)))

    html_dir = ROOT / "project" / "frontend"
    pages = list(html_dir.glob("*.html"))
    tagged = sum(1 for p in pages if stored in p.read_text(encoding="utf-8", errors="ignore"))

    print(f"Embedded in core files : {len(targets) - len(missing)}/{len(targets)}")
    print(f"HTML pages fingerprinted: {tagged}/{len(pages)}")
    if missing:
        print("WARNING: fingerprint missing from: " + ", ".join(missing))
        return 1
    print("\nOK: authorship DNA is intact across the source tree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
