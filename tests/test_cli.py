import json
import tempfile
import unittest
from pathlib import Path

from game_text_gate.cli import main


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "en.json"
        self.target = self.root / "fr.json"
        self.source.write_text('{"greet":"Hello {name}"}', encoding="utf-8")

    def test_clean_pair_returns_zero_and_writes_json(self):
        self.target.write_text('{"greet":"Bonjour {name}"}', encoding="utf-8")
        report = self.root / "report.json"
        code = main(["--source", str(self.source), "--target", str(self.target), "--report", "json", "--output", str(report)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["summary"]["error"], 0)

    def test_findings_return_one_and_warning_threshold_is_strict(self):
        self.target.write_text('{"other":"Salut"}', encoding="utf-8")
        args = ["--source", str(self.source), "--target", str(self.target), "--report", "json", "--output", str(self.root / "out.json")]
        self.assertEqual(main(args), 1)
        self.assertEqual(main(args + ["--fail-on", "warning"]), 1)

    def test_bad_input_returns_two(self):
        self.target.write_text("{broken", encoding="utf-8")
        self.assertEqual(main(["--source", str(self.source), "--target", str(self.target)]), 2)


if __name__ == "__main__":
    unittest.main()
