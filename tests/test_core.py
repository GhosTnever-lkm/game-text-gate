import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from game_text_gate.cli import main
from game_text_gate.core import Finding, InputError, compare, extract_tokens, load_entries
from game_text_gate.report import make_report, to_json, to_markdown, to_sarif


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, content):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_unity_csv_selects_locale_column(self):
        path = self.write("table.csv", 'Key,English (en),French (fr)\nHELLO,Hello,Bonjour\n')
        entries, findings = load_entries(path, "csv", "fr")
        self.assertEqual([(e.key, e.text) for e in entries], [("HELLO", "Bonjour")])
        self.assertEqual(findings, [])

    def test_godot_csv_text_column_and_duplicate_key(self):
        path = self.write("fr.csv", 'keys,values\nHELLO,Bonjour\nHELLO,Salut\n')
        entries, findings = load_entries(path, "godot-csv", "fr", text_column="values")
        self.assertEqual(len(entries), 1)
        self.assertEqual([f.rule_id for f in findings], ["duplicate_key"])

    def test_csv_short_row_is_reported(self):
        path = self.write("bad.csv", 'key,en\na\n')
        _, findings = load_entries(path, "csv", "en")
        self.assertIn("malformed_row", [f.rule_id for f in findings])

    def test_csv_entry_limit(self):
        path = self.write("many.csv", 'key,en\na,A\nb,B\n')
        with self.assertRaisesRegex(InputError, "row count exceeds limit"):
            load_entries(path, "csv", "en", max_entries=1)

    def test_json_flattens_nested_keys_and_rejects_duplicate_object_keys(self):
        path = self.write("source.json", '{"menu":{"play":"Play"}}')
        entries, _ = load_entries(path, "json", "en")
        self.assertEqual(entries[0].key, "/menu/play")
        bad = self.write("duplicate.json", '{"a":"one","a":"two"}')
        with self.assertRaisesRegex(InputError, "duplicate JSON object key"):
            load_entries(bad, "json", "en")

    def test_po_handles_multiline_and_plural_values(self):
        path = self.write("fr.po", 'msgid "items"\nmsgid_plural "items"\nmsgstr[0] "un"\nmsgstr[1] "plusieurs"\n\nmsgid "long"\nmsgstr "ligne "\n"continuee"\n')
        entries, findings = load_entries(path, "po", "fr")
        self.assertEqual({e.key: e.text for e in entries}, {"items": "un\nplusieurs", "long": "ligne continuee"})
        self.assertEqual(findings, [])

    def test_po_context_is_part_of_key_identity(self):
        path = self.write("contexts.po", 'msgctxt "button"\nmsgid "Open"\nmsgstr "Открыть"\n\nmsgctxt "door"\nmsgid "Open"\nmsgstr "Открыт"\n')
        entries, findings = load_entries(path, "po", "ru")
        self.assertEqual([e.key for e in entries], ["button" + chr(4) + "Open", "door" + chr(4) + "Open"])
        self.assertEqual(findings, [])

    def test_placeholder_and_markup_mismatches(self):
        source = self.write("en.json", '{"greet":"Hello {player}, <b>%s</b>"}')
        target = self.write("fr.json", '{"greet":"Bonjour <b>{player}</b>"}')
        src, sf = load_entries(source, "json", "en")
        dst, tf = load_entries(target, "json", "fr")
        findings = sf + tf + compare(src, dst, source, target)
        self.assertIn("missing_token", [f.rule_id for f in findings])
        self.assertEqual(extract_tokens("{{literal}} \\{escaped\\} %%"), {})

    def test_icu_is_reported_as_unsupported_note(self):
        tokens = extract_tokens("{count, plural, one {one} other {many}}")
        self.assertIn(("icu-unsupported", "count:plural"), tokens)
        self.assertNotIn(("brace", "count"), tokens)

    def test_sarif_serializes_valid_json(self):
        report = make_report([Finding("missing_key", "error", "Missing key", str(self.root / "fr.csv"), 3, "TITLE")], "en.csv", "fr.csv", "0.1.0")
        sarif = json.loads(to_sarif(report))
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertEqual(sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"], "fr.csv")

    def test_markdown_escapes_untrusted_paths_and_keys(self):
        report = make_report(
            [Finding("duplicate_key", "error", "Untrusted | message `", "locales/evil|`file\nnext.csv", key="key|`next\nrow")],
            "locales/en|`source.csv",
            "locales/fr.csv",
            "0.1.9",
        )
        rendered = to_markdown(report)
        self.assertIn("locales/en&#124;&#96;source.csv", rendered)
        self.assertIn("evil&#124;&#96;file next.csv", rendered)
        self.assertIn("key&#124;&#96;next row", rendered)
        self.assertNotIn("evil|`file\nnext.csv", rendered)
        self.assertNotIn("key|`next\nrow", rendered)

    def test_reports_escape_bidi_controls_visually_and_json_roundtrips(self):
        key = "menu\u202e\u2028line\u2029end\u0085[ERROR]"
        report = make_report(
            [Finding("missing_token", "error", "Placeholder missing", "locales/fr.json", key=key)],
            "locales/en.json",
            "locales/fr.json",
            "0.1.11",
        )
        markdown = to_markdown(report)
        json_text = to_json(report)
        sarif_text = to_sarif(report)

        for rendered in (markdown, json_text, sarif_text):
            for invisible in ("\u202e", "\u2028", "\u2029", "\u0085"):
                self.assertNotIn(invisible, rendered)
        self.assertIn("&#92;u202e", markdown)
        self.assertIn("2028", markdown)
        self.assertIn(r"\u202e", json_text)
        self.assertIn(r"\u2028", json_text)
        self.assertIn(r"\u202e", sarif_text)
        self.assertIn(r"\u2028", sarif_text)
        self.assertEqual(json.loads(json_text)["findings"][0]["key"], key)
        self.assertEqual(
            json.loads(sarif_text)["runs"][0]["results"][0]["properties"]["key"],
            key,
        )

    def test_cli_input_error_escapes_bidi_and_newline_in_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "missing\n\u202e\u2028line\u2029end.json"
            target = Path(tmp) / "target.json"
            target.write_text('{"key":"value"}', encoding="utf-8")
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                result = main(["--source", str(source), "--target", str(target)])
        text = error.getvalue()
        self.assertEqual(result, 2)
        for invisible in ("\u202e", "\u2028", "\u2029"):
            self.assertNotIn(invisible, text)
        self.assertIn(r"missing\n\u202e\u2028line\u2029end.json", text)


if __name__ == "__main__":
    unittest.main()
