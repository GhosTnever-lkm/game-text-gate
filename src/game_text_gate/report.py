from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from .core import Finding, display_path, finding_dict

SARIF_LEVEL = {"error": "error", "warning": "warning", "note": "note"}


def escape_control_characters(value: str, *, whitespace_as_space: bool = False) -> str:
    """Render control/format characters visibly before reports reach a viewer."""
    escaped: list[str] = []
    whitespace = {"\r": r"\r", "\n": r"\n", "\t": r"\t"}
    for char in value:
        if char in whitespace:
            escaped.append(" " if whitespace_as_space else whitespace[char])
        elif unicodedata.category(char).startswith("C") or unicodedata.category(char) in {"Zl", "Zp"}:
            codepoint = ord(char)
            if codepoint <= 0xFF:
                escaped.append(f"\\x{codepoint:02x}")
            elif codepoint <= 0xFFFF:
                escaped.append(f"\\u{codepoint:04x}")
            else:
                escaped.append(f"\\U{codepoint:08x}")
        else:
            escaped.append(char)
    return "".join(escaped)


def _escape_json_controls(serialized: str) -> str:
    """Escape formatting controls in JSON text while preserving decoded data."""
    result: list[str] = []
    for char in serialized:
        if char in "\r\n\t":
            result.append(char)  # JSON formatting whitespace, not source data.
        elif unicodedata.category(char).startswith("C") or unicodedata.category(char) in {"Zl", "Zp"}:
            codepoint = ord(char)
            if codepoint <= 0xFFFF:
                result.append(f"\\u{codepoint:04x}")
            else:
                value = codepoint - 0x10000
                high = 0xD800 + (value >> 10)
                low = 0xDC00 + (value & 0x3FF)
                result.extend((f"\\u{high:04x}", f"\\u{low:04x}"))
        else:
            result.append(char)
    return "".join(result)


def make_report(findings: list[Finding], source: str, target: str, version: str) -> dict[str, Any]:
    return {
        "tool": "GameText Gate",
        "version": version,
        "source": display_path(source),
        "target": display_path(target),
        "summary": {level: sum(f.level == level for f in findings) for level in ("error", "warning", "note")},
        "findings": [finding_dict(finding) for finding in findings],
    }


def to_json(report: dict[str, Any]) -> str:
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    return _escape_json_controls(serialized) + "\n"


def _markdown_cell(value: Any) -> str:
    """Keep untrusted keys and filenames on one safe Markdown table cell."""
    escaped: list[str] = []
    visible = escape_control_characters(str(value if value is not None else "—"), whitespace_as_space=True)
    for char in visible:
        codepoint = ord(char)
        if char == "&":
            escaped.append("&amp;")
        elif char == "<":
            escaped.append("&lt;")
        elif char == ">":
            escaped.append("&gt;")
        elif char in "|`\\*_{}[]!#~":
            escaped.append(f"&#{codepoint};")
        else:
            escaped.append(char)
    return "".join(escaped)


def to_markdown(report: dict[str, Any]) -> str:
    lines = ["# GameText Gate report", "", f"- Source: {_markdown_cell(report['source'])}", f"- Target: {_markdown_cell(report['target'])}",
             f"- Findings: {report['summary']['error']} errors, {report['summary']['warning']} warnings, {report['summary']['note']} notes", ""]
    if not report["findings"]:
        return "\n".join(lines + ["No findings.", ""])
    lines += ["| Level | Rule | File | Line | Key | Message |", "|:--|:--|:--|--:|:--|:--|"]
    for finding in report["findings"]:
        lines.append("| " + " | ".join(
            _markdown_cell(finding.get(key) if finding.get(key) is not None else "—")
            for key in ("level", "rule_id", "file", "line", "key", "message")
        ) + " |")
    return "\n".join(lines) + "\n"


def to_sarif(report: dict[str, Any]) -> str:
    rules: dict[str, dict[str, str]] = {}
    results = []
    working_directory = Path.cwd().resolve()
    for finding in report["findings"]:
        rule_id = finding["rule_id"]
        rules.setdefault(rule_id, {"id": rule_id, "name": rule_id.replace("_", " ").title()})
        path = Path(finding["file"])
        try:
            uri = path.resolve().relative_to(working_directory).as_posix()
        except (OSError, ValueError):
            uri = path.resolve().as_uri()
        location: dict[str, Any] = {"artifactLocation": {"uri": uri}}
        if finding.get("line"):
            location["region"] = {"startLine": finding["line"]}
        result: dict[str, Any] = {
            "ruleId": rule_id,
            "level": SARIF_LEVEL[finding["level"]],
            "message": {"text": finding["message"]},
            "locations": [{"physicalLocation": location}],
        }
        if finding.get("key"):
            result["properties"] = {"key": finding["key"]}
        results.append(result)
    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "GameText Gate", "version": report["version"], "rules": list(rules.values())}},
            "results": results,
        }],
    }
    serialized = json.dumps(sarif, ensure_ascii=False, indent=2)
    return _escape_json_controls(serialized) + "\n"
