#!/usr/bin/env python3
"""
Lightweight docs lint for harness planning artifacts.
"""

from pathlib import Path
import sys


REQUIRED_DOCS = [
    "index.md",
    "harness-team-implementation-plan-v2.md",
    "harness-implementation-task-sequence.md",
]


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    docs_dir = repo_root / "docs"
    errors: list[str] = []

    for doc_name in REQUIRED_DOCS:
        doc_path = docs_dir / doc_name
        if not doc_path.exists():
            errors.append(f"missing required docs file: {doc_path}")

    index_path = docs_dir / "index.md"
    if index_path.exists():
        index_text = index_path.read_text()
        for doc_name in REQUIRED_DOCS[1:]:
            if doc_name not in index_text:
                errors.append(f"docs/index.md missing link entry for {doc_name}")

    for md_path in sorted(docs_dir.glob("*.md")):
        head = "\n".join(md_path.read_text().splitlines()[:20]).lower()
        if "last updated:" not in head:
            errors.append(f"{md_path} missing 'Last updated:' header in first 20 lines")

    if errors:
        print("docs lint failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("docs lint passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

