import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("converter", Path(__file__).resolve().parents[1] / "scripts/loon_to_singbox.py")
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)


class ConversionTests(unittest.TestCase):
    def test_matching_fields_and_deduplication(self):
        data, report = converter.convert("\ufeff# comment\r\nDOMAIN,example.com\nDOMAIN,example.com\nDOMAIN-SUFFIX,.example.org\nDOMAIN-KEYWORD,video\nIP-CIDR,192.0.2.3/24,no-resolve\nIP-CIDR6,2001:db8::1/32,no-resolve\n", "sample.list")
        self.assertEqual(data, {"version": 2, "rules": [
            {"domain": ["example.com"]}, {"domain_keyword": ["video"]},
            {"domain_suffix": [".example.org"]}, {"ip_cidr": ["192.0.2.0/24", "2001:db8::/32"]},
        ]})
        self.assertEqual(report["converted_lines"], 6)
        self.assertEqual(report["unique_entries"], 5)
        self.assertEqual(report["no_resolve_lines"], 2)

    def test_unrepresentable_rules_are_reported_verbatim(self):
        data, report = converter.convert("DOMAIN,example.com\nUSER-AGENT,*YouTube*\nURL-REGEX,^https?://example.com/a{1,2}\n", "sample")
        self.assertEqual(len(data["rules"]), 1)
        self.assertEqual([item["line"] for item in report["skipped"]], [2, 3])
        self.assertTrue(report["skipped"][1]["rule"].endswith("{1,2}"))

    def test_invalid_rules_fail_instead_of_silent_loss(self):
        for line in ["GEOIP,CN", "DOMAIN", "DOMAIN,", "DOMAIN,a.com,DIRECT", "IP-CIDR,not-an-ip", "IP-CIDR,2001:db8::/32", "IP-CIDR6,192.0.2.0/24", "IP-CIDR,192.0.2.0/24,unknown", "USER-AGENT,*", "# empty"]:
            with self.subTest(line=line), self.assertRaises(ValueError):
                converter.convert(line, "sample")

    def test_generation_is_deterministic_and_preserves_old_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "lq", root / "singbox"
            source.mkdir()
            output.mkdir()
            (source / "proxy.list").write_text("DOMAIN,a.example\n")
            (output / "old.json").write_text("{}")
            (output / "README.md").write_text("keep")
            report = output / "reports/conversion-report.json"
            converter.generate(source, output, report)
            first = (output / "proxy.json").read_bytes()
            converter.generate(source, output, report)
            self.assertEqual(first, (output / "proxy.json").read_bytes())
            self.assertEqual((output / "old.json").read_text(), "{}")
            self.assertTrue((output / "README.md").exists())
            self.assertEqual(len(json.loads(report.read_text())["files"]), 1)
            (source / "broken.list").write_text("DOMAIN,a.example,PROXY")
            with self.assertRaises(ValueError):
                converter.generate(source, output, report)
            self.assertEqual(first, (output / "proxy.json").read_bytes())

    def test_duplicate_stems_fail_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for suffix in ["list", "txt"]:
                (root / f"same.{suffix}").write_text("DOMAIN,a.example")
            with self.assertRaises(ValueError):
                converter.generate(root, root / "out", root / "report.json")
            self.assertFalse((root / "out").exists())


if __name__ == "__main__":
    unittest.main()
