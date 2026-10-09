import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from configdiff.core.diff_engine import compare_text
from configdiff.core.file_io import read_text_file


class DiffEngineTests(unittest.TestCase):
    def test_equal_and_empty(self):
        for value in ("", "A\nB\n", "设备名称：核心交换机\n"):
            result = compare_text(value, value)
            self.assertTrue(result.identical)
            self.assertEqual(result.change_positions, ())

    def test_empty_side(self):
        self.assertEqual(compare_text("", "A\nB\n").additions, 2)
        self.assertEqual(compare_text("A\nB\n", "").deletions, 2)

    def test_middle_insertion_keeps_following_lines(self):
        result = compare_text("A\nB\nC\nD\n", "A\nX\nB\nC\nD\n")
        self.assertEqual((result.additions, result.deletions, result.modifications), (1, 0, 0))
        self.assertEqual([r.kind for r in result.rows], ["equal", "added", "equal", "equal", "equal"])

    def test_modified_line_has_character_spans(self):
        result = compare_text(" description old-link\n", " description core-link\n")
        self.assertEqual(result.modifications, 1)
        self.assertEqual(result.rows[0].kind, "modified_old")
        self.assertEqual(result.rows[1].kind, "modified_new")
        self.assertTrue(result.rows[0].changed_spans)
        self.assertTrue(result.rows[1].changed_spans)

    def test_multiple_changes_whitespace_and_chinese(self):
        old = "A\n\n\tkey  value\n设备名称：旧交换机\nZ\n"
        new = "A\n\n\tkey   value\n设备名称：核心交换机\n新行\nZ\n"
        result = compare_text(old, new)
        self.assertFalse(result.identical)
        self.assertIn("新行", result.display_text)
        self.assertGreaterEqual(result.modifications, 1)

    def test_many_insertions_and_deletions(self):
        baseline = [f"interface {i}" for i in range(10000)]
        new = baseline[:5000] + [f"new {i}" for i in range(50)] + baseline[5000:]
        result = compare_text("\n".join(baseline) + "\n", "\n".join(new) + "\n")
        self.assertEqual((result.additions, result.deletions, result.modifications), (50, 0, 0))
        result = compare_text("\n".join(new) + "\n", "\n".join(baseline) + "\n")
        self.assertEqual((result.additions, result.deletions, result.modifications), (0, 50, 0))

    def test_final_newline_difference(self):
        result = compare_text("A", "A\n")
        self.assertEqual(result.modifications, 1)
        self.assertIn("No newline at end of file", result.unified_text)

    def test_file_encodings_and_binary_rejection(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / "config.cfg"
            for payload, expected in (("设备名称：核心交换机".encode("utf-8-sig"), "设备名称：核心交换机"),
                                      ("接口配置".encode("utf-16"), "接口配置"),
                                      ("中文配置".encode("gb18030"), "中文配置")):
                target.write_bytes(payload)
                text, _ = read_text_file(target)
                self.assertEqual(text, expected)
            target.write_bytes(b"\x00\x01\x02")
            with self.assertRaises(ValueError):
                read_text_file(target)


if __name__ == "__main__":
    unittest.main()
