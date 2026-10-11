from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import Finding, InputError, compare, load_entries
from .report import escape_control_characters, make_report, to_json, to_markdown, to_sarif


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Check game localization exports without uploading or rewriting them.")
    result.add_argument("--source", required=True, type=Path, help="Source locale file (CSV, PO, or JSON)")
    result.add_argument("--target", required=True, type=Path, help="Target locale file (CSV, PO, or JSON)")
    result.add_argument("--source-locale", default="en", help="Source locale identifier (default: en)")
    result.add_argument("--target-locale", default="", help="Target locale identifier; used to choose CSV locale columns")
    result.add_argument("--format", choices=("auto", "csv", "po", "json"), default="auto", help="Input format (default: infer from file extension)")
    result.add_argument("--key-column", help="CSV key column; auto-detected from Key/keys/Id otherwise")
    result.add_argument("--source-column", help="CSV source text column; auto-detected when possible")
    result.add_argument("--target-column", help="CSV target text column; auto-detected when possible")
    result.add_argument("--report", choices=("text", "json", "markdown", "sarif"), default="text")
    result.add_argument("--output", type=Path, help="Write report to this path instead of stdout")
    result.add_argument("--fail-on", choices=("error", "warning"), default="error", help="Exit 1 at this severity or above")
    result.add_argument("--max-file-size", type=int, default=10 * 1024 * 1024, help="Maximum input bytes per file (default: 10 MiB)")
    result.add_argument("--max-entries", type=int, default=100_000, help="Maximum rows or entries per file")
    result.add_argument("--version", action="version", version=f"GameText Gate {__version__}")
    return result


def _fmt(path: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    suffix = path.suffix.casefold()
    return {".csv": "csv", ".po": "po", ".json": "json"}.get(suffix, "")


def _load_args(path: Path, fmt: str, locale: str, column: str | None, args) -> tuple[list, list[Finding]]:
    detected = _fmt(path, fmt)
    if not detected:
        raise InputError(f"Cannot infer input format from {path.suffix!r}; pass --format")
    return load_entries(path, detected, locale, args.key_column, column, args.max_file_size, args.max_entries)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.max_file_size <= 0 or args.max_entries <= 0:
        print("ERROR: size and entry limits must be positive", file=sys.stderr)
        return 2
    try:
        source, source_findings = _load_args(args.source, args.format, args.source_locale, args.source_column, args)
        target_locale = args.target_locale or args.target.stem
        target, target_findings = _load_args(args.target, args.format, target_locale, args.target_column, args)
        findings = source_findings + target_findings + compare(source, target, args.source, args.target)
    except InputError as exc:
        print(f"ERROR: {escape_control_characters(str(exc))}", file=sys.stderr)
        return 2

    report = make_report(findings, str(args.source), str(args.target), __version__)
    if args.report == "json":
        output = to_json(report)
    elif args.report == "markdown":
        output = to_markdown(report)
    elif args.report == "sarif":
        output = to_sarif(report)
    else:
        output = (to_markdown(report) if findings else "GameText Gate: no findings.\n")
    try:
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8", newline="\n")
        else:
            sys.stdout.write(output)
    except OSError as exc:
        print(f"ERROR: cannot write report: {exc}", file=sys.stderr)
        return 2

    threshold = {"error": {"error"}, "warning": {"error", "warning"}}[args.fail_on]
    return 1 if any(f.level in threshold for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
