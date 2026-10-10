import json
import tempfile
import unittest
from pathlib import Path

from game_text_gate.core import InputError, compare, extract_tokens, load_entries
from game_text_gate.report import make_report, to_sarif


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
        report = make_report([], "en.csv", "fr.csv", "0.1.0")
        sarif = json.loads(to_sarif(report))
        self.assertEqual(sarif["version"], "2.1.0")


if __name__ == "__main__":
    unittest.main()
