from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import Finding, display_path, finding_dict

SARIF_LEVEL = {"error": "error", "warning": "warning", "note": "note"}


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
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def _markdown_cell(value: Any) -> str:
    """Keep untrusted keys and filenames on one safe Markdown table cell."""
    escaped: list[str] = []
    for char in str(value if value is not None else "—"):
        codepoint = ord(char)
        if char in "\r\n\t":
            escaped.append(" ")
        elif codepoint < 0x20 or codepoint == 0x7F:
            escaped.append(f"&#{codepoint};")
        elif char == "&":
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
    return json.dumps(sarif, ensure_ascii=False, indent=2) + "\n"
