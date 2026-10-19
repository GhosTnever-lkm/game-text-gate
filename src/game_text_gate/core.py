from __future__ import annotations

import ast
import csv
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class InputError(Exception):
    """An input file or option is invalid."""


def display_path(path: str | Path) -> str:
    """Return a useful workspace-relative label without leaking machine directories."""
    raw = str(path).replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        return PurePosixPath(raw).name or "."
    candidate = Path(raw)
    try:
        return candidate.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except (OSError, ValueError):
        return candidate.name or "."


@dataclass(frozen=True)
class Entry:
    key: str
    text: str
    line: int | None
    token_variants: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Finding:
    rule_id: str
    level: str
    message: str
    file: str
    line: int | None = None
    key: str | None = None
    details: dict[str, Any] | None = None


LOCALE_HEADER = re.compile(r"^(.+?)\s*\(([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)*)\)$")
SIMPLE_BRACE = re.compile(r"(?<![\\{])\{([A-Za-z_][A-Za-z0-9_]*|\d+)\}(?!})")
PRINTF = re.compile(
    r"%(?:(?P<map>\([A-Za-z_][A-Za-z0-9_]*\))|(?P<position>\d+\$))?"
    r"[-+#0 ]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[hlLzjt]*[diouxXeEfFgGaAcsp]"
)
TAG = re.compile(r"</?([A-Za-z][A-Za-z0-9]*)(?:\s+[^<>]*?)?\s*/?>")
BBTAG = re.compile(r"\[(/?)([A-Za-z][A-Za-z0-9]*)(?:=[^\[\]]*)?\]")
ICU_TYPED = re.compile(r"(?<![\\{])\{([A-Za-z_][A-Za-z0-9_]*|\d+)\s*,\s*(plural|select|selectordinal|number|date|time)\s*,")
SUPPORTED_TAGS = {"b", "i", "u", "s", "color", "size", "sprite", "quad", "br", "url", "font", "material", "outline", "shadow"}


def _read_text(path: Path, max_bytes: int) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise InputError(f"Cannot read {display_path(path)}: {exc.strerror or exc.__class__.__name__}") from exc
    if len(data) > max_bytes:
        raise InputError(f"{display_path(path)}: file size {len(data)} exceeds limit {max_bytes} bytes")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError(f"{display_path(path)}: input must be UTF-8 (decode error at byte {exc.start})") from exc


def _csv_entries(path: Path, locale: str, key_column: str | None, text_column: str | None, max_bytes: int, max_entries: int) -> tuple[list[Entry], list[Finding]]:
    text = _read_text(path, max_bytes)
    try:
        reader = csv.DictReader(text.splitlines(keepends=True), strict=True)
        headers = reader.fieldnames
        if not headers:
            raise InputError(f"{display_path(path)}: CSV is empty or has no header")
        if len(set(headers)) != len(headers):
            raise InputError(f"{display_path(path)}: duplicate CSV column names")
        key_name = key_column or next((h for h in headers if h.casefold() in {"key", "keys", "id", "msgctxt"}), headers[0])
        if key_name not in headers:
            raise InputError(f"{display_path(path)}: key column {key_name!r} not found; columns: {headers}")
        value_name = text_column
        if value_name is None:
            for header in headers:
                match = LOCALE_HEADER.fullmatch(header.strip())
                if match and match.group(2).casefold().replace("_", "-") == locale.casefold().replace("_", "-"):
                    value_name = header
                    break
        if value_name is None:
            candidates = [h for h in headers if h != key_name and h.casefold() not in {"id", "shared comments", "comments", "context"} and not h.startswith("_")]
            if len(candidates) == 1:
                value_name = candidates[0]
        if not value_name or value_name not in headers:
            raise InputError(f"{display_path(path)}: set --text-column or provide one locale column; columns: {headers}")
        entries: list[Entry] = []
        findings: list[Finding] = []
        seen: dict[str, int | None] = {}
        for row in reader:
            line = reader.line_num
            if len(entries) + len(findings) >= max_entries:
                raise InputError(f"{display_path(path)}: row count exceeds limit {max_entries}")
            if None in row:
                findings.append(Finding("malformed_row", "error", "CSV row has more values than the header", display_path(path), line))
            if any(value is None for value in row.values()):
                findings.append(Finding("malformed_row", "error", "CSV row has fewer values than the header", display_path(path), line))
            key = (row.get(key_name) or "").strip()
            value = row.get(value_name)
            if not key:
                findings.append(Finding("empty_key", "error", f"Empty key in column {key_name}", display_path(path), line))
                continue
            if key in seen:
                findings.append(Finding("duplicate_key", "error", f"Duplicate key {key!r}; first seen at line {seen[key]}", display_path(path), line, key))
                continue
            seen[key] = line
            entries.append(Entry(key, value or "", line))
        return entries, findings
    except csv.Error as exc:
        raise InputError(f"{display_path(path)}: malformed CSV: {exc}") from exc


def _json_entries(path: Path, max_bytes: int, max_entries: int) -> tuple[list[Entry], list[Finding]]:
    text = _read_text(path, max_bytes)
    try:
        def object_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise InputError(f"{display_path(path)}: duplicate JSON object key {key!r}")
                result[key] = value
            return result
        root = json.loads(text, object_pairs_hook=object_pairs)
    except json.JSONDecodeError as exc:
        raise InputError(f"{display_path(path)}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}") from exc
    except RecursionError as exc:
        raise InputError(f"{display_path(path)}: JSON nesting exceeds the parser's supported depth") from exc
    entries: list[Entry] = []
    findings: list[Finding] = []

    pending: list[tuple[Any, list[str]]] = [(root, [])]
    while pending:
        value, parts = pending.pop()
        if len(entries) + len(findings) >= max_entries:
            raise InputError(f"{display_path(path)}: entry count exceeds limit {max_entries}")
        if isinstance(value, str):
            if not parts:
                findings.append(Finding("empty_key", "error", "Root JSON string has no key", display_path(path)))
                continue
            key = "/" + "/".join(p.replace("~", "~0").replace("/", "~1") for p in parts)
            entries.append(Entry(key, value, None))
        elif isinstance(value, dict):
            for key, child in reversed(list(value.items())):
                pending.append((child, parts + [str(key)]))
        elif isinstance(value, list):
            for index in range(len(value) - 1, -1, -1):
                pending.append((value[index], parts + [str(index)]))
        else:
            findings.append(Finding("unsupported_json_value", "note", f"Ignoring non-string JSON leaf at {'/'.join(parts) or '/'}", display_path(path)))
    return entries, findings


def _po_entries(path: Path, max_bytes: int, max_entries: int) -> tuple[list[Entry], list[Finding]]:
    """Read a practical gettext PO subset, including continuations and plurals."""
    text = _read_text(path, max_bytes)
    entries: list[Entry] = []
    findings: list[Finding] = []
    current: dict[str, Any] = {}
    active: str | None = None
    start_line: int | None = None
    seen_keys: set[str] = set()

    def finish() -> None:
        nonlocal current, active, start_line
        if not current:
            return
        msgid = current.get("msgid", "")
        if msgid == "" and current.get("msgctxt") is None:
            current, active, start_line = {}, None, None  # PO header, not a translation row.
            return
        context = current.get("msgctxt")
        key = f"{context}\x04{msgid}" if context is not None else msgid
        translations = list(current.get("msgstr_plural", {}).values()) if current.get("msgstr_plural") else [current.get("msgstr", "")]
        token_variants = tuple(translations)
        nonempty_translations = tuple(item for item in translations if item != "")
        value = "\n".join(nonempty_translations)
        if key in seen_keys:
            findings.append(Finding("duplicate_key", "error", f"Duplicate PO key {key!r}", display_path(path), start_line, key))
        else:
            entries.append(Entry(key, value, start_line, token_variants or ("",)))
            seen_keys.add(key)
        current, active, start_line = {}, None, None

    directive = re.compile(r"^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+(.*)$")
    for line_number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            if not stripped:
                finish()
            continue
        match = directive.match(stripped)
        if match:
            field, literal = match.groups()
            if field == "msgid" and "msgid" in current:
                finish()
            if start_line is None:
                start_line = line_number
            try:
                value = ast.literal_eval(literal)
            except (ValueError, SyntaxError) as exc:
                findings.append(Finding("malformed_po_string", "error", f"Invalid quoted PO string: {exc}", display_path(path), line_number))
                current = {}
                active = None
                continue
            if not isinstance(value, str):
                findings.append(Finding("malformed_po_string", "error", "PO value must be a quoted string", display_path(path), line_number))
                continue
            if field.startswith("msgstr["):
                index = int(field[field.index("[") + 1:-1])
                current.setdefault("msgstr_plural", {})[index] = value
                active = f"msgstr_plural:{index}"
            else:
                current[field] = value
                active = field
            if len(entries) >= max_entries:
                raise InputError(f"{display_path(path)}: entry count exceeds limit {max_entries}")
            continue
        if stripped.startswith('"') and active:
            try:
                continuation = ast.literal_eval(stripped)
            except (ValueError, SyntaxError) as exc:
                findings.append(Finding("malformed_po_string", "error", f"Invalid PO continuation: {exc}", display_path(path), line_number))
                continue
            if not isinstance(continuation, str):
                findings.append(Finding("malformed_po_string", "error", "PO continuation must be quoted", display_path(path), line_number))
                continue
            if active.startswith("msgstr_plural:"):
                index = int(active.split(":", 1)[1])
                current["msgstr_plural"][index] += continuation
            else:
                current[active] += continuation
            continue
        findings.append(Finding("malformed_po_entry", "error", "Unrecognized PO syntax", display_path(path), line_number))
    finish()
    return entries, findings


def load_entries(path: Path, fmt: str, locale: str, key_column: str | None = None, text_column: str | None = None,
                 max_bytes: int = 10 * 1024 * 1024, max_entries: int = 100_000) -> tuple[list[Entry], list[Finding]]:
    fmt = fmt.lower()
    if fmt in {"csv", "unity-csv", "godot-csv"}:
        return _csv_entries(path, locale, key_column, text_column, max_bytes, max_entries)
    if fmt in {"po", "unreal-po"}:
        return _po_entries(path, max_bytes, max_entries)
    if fmt == "json":
        return _json_entries(path, max_bytes, max_entries)
    raise InputError(f"Unsupported format {fmt!r}; use csv, po, or json")


def extract_tokens(text: str) -> Counter[tuple[str, str]]:
    """Extract a conservative subset of runtime placeholders and markup tokens."""
    tokens: Counter[tuple[str, str]] = Counter()
    # Escaped literal forms do not represent runtime formatting tokens.
    protected = re.sub(r"\\[{}\[\]]|\{\{|\}\}|%%", " ", text)
    for match in SIMPLE_BRACE.finditer(protected):
        tokens[("brace", match.group(1))] += 1
    for match in PRINTF.finditer(protected):
        raw = match.group(0)
        tokens[("printf", raw)] += 1
    for match in ICU_TYPED.finditer(protected):
        tokens[("icu-unsupported", f"{match.group(1)}:{match.group(2)}")] += 1
        tokens[("brace", match.group(1))] -= 1
        if tokens[("brace", match.group(1))] <= 0:
            del tokens[("brace", match.group(1))]
    # Only compare a conservative engine-markup allowlist; ordinary HTML-looking text is ignored.
    for match in TAG.finditer(protected):
        tag = match.group(1).lower()
        if tag in SUPPORTED_TAGS:
            kind = "self" if match.group(0).endswith("/>") else ("close" if match.group(0).startswith("</") else "open")
            tokens[("unity-tag", f"{kind}:{tag}")] += 1
    for match in BBTAG.finditer(protected):
        tag = match.group(2).lower()
        if tag in SUPPORTED_TAGS:
            kind = "close" if match.group(1) else "open"
            tokens[("bbcode-tag", f"{kind}:{tag}")] += 1
    return tokens


def compare(source: list[Entry], target: list[Entry], source_path: Path, target_path: Path) -> list[Finding]:
    findings: list[Finding] = []
    source_map = {entry.key: entry for entry in source}
    target_map = {entry.key: entry for entry in target}
    for key in sorted(source_map.keys() - target_map.keys()):
        findings.append(Finding("missing_key", "error", f"Target is missing source key {key!r}", display_path(target_path), key=key))
    for key in sorted(target_map.keys() - source_map.keys()):
        findings.append(Finding("extra_key", "warning", f"Target contains unknown key {key!r}", display_path(target_path), target_map[key].line, key))
    for key in sorted(source_map.keys() & target_map.keys()):
        source_entry, target_entry = source_map[key], target_map[key]
        if not target_entry.text.strip():
            findings.append(Finding("empty_translation", "warning", f"Translation for {key!r} is empty", display_path(target_path), target_entry.line, key))
        source_variants = source_entry.token_variants or (source_entry.text,)
        target_variants = target_entry.token_variants or (target_entry.text,)
        source_tokens = _variant_token_bounds(source_variants, maximum=True)
        target_min_tokens = _variant_token_bounds(target_variants, maximum=False)
        target_max_tokens = _variant_token_bounds(target_variants, maximum=True)
        for rule_id, token, count in _variant_counter_delta(source_tokens, target_min_tokens, target_max_tokens):
            level = "note" if rule_id == "unsupported_syntax" else "error"
            findings.append(Finding(rule_id, level, f"{token} occurs {count} time(s) in source/target mismatch for {key!r}", display_path(target_path), target_entry.line, key,
                                    {"token": token, "count": count, "source_file": display_path(source_path)}))
    return findings


def _counter_delta(source: Counter[tuple[str, str]], target: Counter[tuple[str, str]]):
    for kind, value in sorted(source.keys() | target.keys()):
        missing = source[(kind, value)] - target[(kind, value)]
        extra = target[(kind, value)] - source[(kind, value)]
        if missing > 0:
            yield ("unsupported_syntax" if kind == "icu-unsupported" else "missing_token", f"{kind}:{value}", missing)
        if extra > 0:
            yield ("unsupported_syntax" if kind == "icu-unsupported" else "extra_token", f"{kind}:{value}", extra)


def _variant_token_bounds(variants: tuple[str, ...], *, maximum: bool) -> Counter[tuple[str, str]]:
    """Return token counts present at the maximum or minimum across PO plural forms."""
    counters = [extract_tokens(text) for text in variants]
    keys = set().union(*(counter.keys() for counter in counters))
    bound = max if maximum else min
    return Counter({key: bound(counter[key] for counter in counters) for key in keys})


def _variant_counter_delta(
    source_max: Counter[tuple[str, str]],
    target_min: Counter[tuple[str, str]],
    target_max: Counter[tuple[str, str]],
):
    """Require each target plural form to retain source tokens, without comparing form counts."""
    for kind, value in sorted(source_max.keys() | target_min.keys() | target_max.keys()):
        missing = source_max[(kind, value)] - target_min[(kind, value)]
        extra = target_max[(kind, value)] - source_max[(kind, value)]
        if missing > 0:
            yield ("unsupported_syntax" if kind == "icu-unsupported" else "missing_token", f"{kind}:{value}", missing)
        if extra > 0:
            yield ("unsupported_syntax" if kind == "icu-unsupported" else "extra_token", f"{kind}:{value}", extra)


def finding_dict(finding: Finding) -> dict[str, Any]:
    result = asdict(finding)
    result["file"] = display_path(result["file"])
    details = result.get("details")
    if isinstance(details, dict) and isinstance(details.get("source_file"), str):
        details["source_file"] = display_path(details["source_file"])
    return {key: value for key, value in result.items() if value is not None}
