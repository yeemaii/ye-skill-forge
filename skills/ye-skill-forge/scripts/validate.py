#!/usr/bin/env python3
"""Validate a skill package's file structure and metadata."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.skill_utils import validate_skill
from core.cli import configure_console


def main():
    configure_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_path", help="Path to the skill directory")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    args = parser.parse_args()

    findings = validate_skill(args.skill_path)
    if args.json:
        print(json.dumps(findings, ensure_ascii=True, indent=2))
    else:
        print(f"Structural validation: {args.skill_path}")
        for finding in findings:
            print(f"[{finding['severity'].upper()}] {finding['code']}: {finding['message']}")

    has_errors = any(item["severity"] == "error" for item in findings)
    has_warnings = any(item["severity"] == "warning" for item in findings)
    return 1 if has_errors or (args.strict and has_warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
