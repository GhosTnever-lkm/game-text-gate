import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
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

    def test_shareable_reports_omit_absolute_parent_paths(self):
        self.target.write_text('{"greet":"Bonjour"}', encoding="utf-8")
        for output_format in ("json", "markdown", "sarif"):
            with self.subTest(output_format=output_format):
                report_path = self.root / f"report-{output_format}.txt"
                code = main(["--source", str(self.source), "--target", str(self.target),
                             "--report", output_format, "--output", str(report_path)])
                self.assertEqual(code, 1)
                rendered = report_path.read_text(encoding="utf-8")
                self.assertNotIn(str(self.root), rendered)
                if output_format == "json":
                    report = json.loads(rendered)
                    self.assertEqual((report["source"], report["target"]), ("en.json", "fr.json"))
                    self.assertNotIn(str(self.root), json.dumps(report))

    def test_bad_input_returns_two_without_absolute_parent_path(self):
        self.target.write_text("{broken", encoding="utf-8")
        error = io.StringIO()
        with redirect_stderr(error):
            result = main(["--source", str(self.source), "--target", str(self.target)])
        self.assertEqual(result, 2)
        self.assertNotIn(str(self.root), error.getvalue())
        self.assertIn("fr.json", error.getvalue())


if __name__ == "__main__":
    unittest.main()
