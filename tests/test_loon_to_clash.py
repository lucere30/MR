import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

spec = importlib.util.spec_from_file_location("clash", Path(__file__).resolve().parents[1] / "scripts/loon_to_clash.py")
clash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clash)


class ClashTests(unittest.TestCase):
    def test_plain_rules_keep_original_order_duplicates_and_format(self):
        text = "DOMAIN,b.example\nDOMAIN,a.example\nDOMAIN,b.example\nUSER-AGENT,*YouTube*\n"
        self.assertEqual(clash.convert(text, "sample"), "payload:\n" + "".join("  - " + line + "\n" for line in text.splitlines()))

    def test_bom_crlf_blank_lines_comments_and_missing_final_newline(self):
        text = "\ufeff# heading\r\n   \r\n\t\n  # comment\r\n DOMAIN,a.example  \r\nDOMAIN,b.example"
        self.assertEqual(yaml.safe_load(clash.convert(text, "sample")), {"payload": ["DOMAIN,a.example", "DOMAIN,b.example"]})

    def test_yaml_special_characters_keep_the_full_rule_string(self):
        rules = ['URL-REGEX,^https://example.com/a: b', 'URL-REGEX,hello #world', 'DOMAIN,"example.com"', 'null', 'true', '123', '*alias', '!!python/object:evil']
        output = clash.convert("\n".join(rules), "sample")
        self.assertEqual(yaml.safe_load(output), {"payload": rules})

    def test_empty_input_is_not_published_and_old_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "lq", root / "cat"
            source.mkdir()
            output.mkdir()
            (output / "old.yaml").write_text("keep")
            (source / "a.list").write_text("DOMAIN,a.example")
            clash.generate(source, output)
            first = (output / "a.yaml").read_bytes()
            (source / "z.txt").write_text("# empty\n \r\n")
            with self.assertRaises(ValueError):
                clash.generate(source, output)
            self.assertEqual((output / "a.yaml").read_bytes(), first)
            self.assertEqual((output / "old.yaml").read_text(), "keep")

    def test_duplicate_output_stems_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for suffix in ("txt", "list"):
                (root / f"same.{suffix}").write_text("DOMAIN,a.example")
            with self.assertRaises(ValueError):
                clash.generate(root, root / "out")
            self.assertFalse((root / "out").exists())


if __name__ == "__main__":
    unittest.main()
