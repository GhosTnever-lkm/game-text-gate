from __future__ import annotations

import json
from typing import Any

from .core import Finding, finding_dict

SARIF_LEVEL = {"error": "error", "warning": "warning", "note": "note"}


def make_report(findings: list[Finding], source: str, target: str, version: str) -> dict[str, Any]:
    return {
        "tool": "GameText Gate",
        "version": version,
        "source": source,
        "target": target,
        "summary": {level: sum(f.level == level for f in findings) for level in ("error", "warning", "note")},
        "findings": [finding_dict(finding) for finding in findings],
    }


def to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def to_markdown(report: dict[str, Any]) -> str:
    lines = ["# GameText Gate report", "", f"- Source: `{report['source']}`", f"- Target: `{report['target']}`",
             f"- Findings: {report['summary']['error']} errors, {report['summary']['warning']} warnings, {report['summary']['note']} notes", ""]
    if not report["findings"]:
        return "\n".join(lines + ["No findings.", ""])
    lines += ["| Level | Rule | File | Line | Key | Message |", "|:--|:--|:--|--:|:--|:--|"]
    for finding in report["findings"]:
        def cell(value: Any) -> str:
            return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")
        lines.append("| " + " | ".join(cell(finding.get(key) if finding.get(key) is not None else "—") for key in ("level", "rule_id", "file", "line", "key", "message")) + " |")
    return "\n".join(lines) + "\n"


def to_sarif(report: dict[str, Any]) -> str:
    rules: dict[str, dict[str, str]] = {}
    results = []
    for finding in report["findings"]:
        rule_id = finding["rule_id"]
        rules.setdefault(rule_id, {"id": rule_id, "name": rule_id.replace("_", " ").title()})
        location: dict[str, Any] = {"artifactLocation": {"uri": finding["file"]}}
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
