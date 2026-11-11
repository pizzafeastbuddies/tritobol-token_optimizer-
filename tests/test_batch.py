"""Tests for local project processing."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tritobol import process_path


class BatchProcessingTests(unittest.TestCase):
    def test_project_processing_respects_gitignore_and_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            destination = base / "optimized"
            source.mkdir()
            (source / ".gitignore").write_text(
                "ignored/\n*.tmp\n!keep.tmp\n",
                encoding="utf-8",
            )
            (source / "notes.md").write_text(
                "This repeated sentence is more than twenty four chars long.\n\n"
                "This repeated sentence is more than twenty four chars long.\n\n"
                "api_key = sk-abcdefghijklmnopqrstuvwxyz123456\n",
                encoding="utf-8",
            )
            (source / "settings.json").write_text(
                '{\n  "enabled": true,\n  "retries": 3\n}\n',
                encoding="utf-8",
            )
            (source / "app.py").write_text(
                "# removable comment\n"
                "# removable comment\n"
                "def greet(name):\n\n"
                "    # another note\n"
                "    return f'hello {name}'\n"
                "print(greet('world'))\n",
                encoding="utf-8",
            )
            (source / "ignored").mkdir()
            (source / "ignored" / "secret.txt").write_text("do not process", encoding="utf-8")
            (source / "skip.tmp").write_text("ignored by gitignore", encoding="utf-8")
            (source / "keep.tmp").write_text("kept by negation", encoding="utf-8")
            (source / "asset.bin").write_bytes(b"\x00\x01\xff")
            nested = source / "nested"
            nested.mkdir()
            (nested / ".gitignore").write_text("*.md\n!keep.md\n", encoding="utf-8")
            (nested / "drop.md").write_text("ignored by nested rule", encoding="utf-8")
            (nested / "keep.md").write_text("re-included by nested rule", encoding="utf-8")

            report = process_path(source, destination)
            report_path = base / "report.json"
            report.write_json(report_path)
            report_text = report_path.read_text(encoding="utf-8")
            serialized = json.loads(report_text)
            self.assertNotIn(str(base), report_text)

            self.assertTrue((destination / "notes.md").exists())
            self.assertEqual(
                (destination / "settings.json").read_text(encoding="utf-8"),
                '{"enabled":true,"retries":3}\n',
            )
            optimized_python = (destination / "app.py").read_text(encoding="utf-8")
            compile(optimized_python, "<test-app>", "exec")
            self.assertEqual(optimized_python.count("removable comment"), 1)
            self.assertIn("another note", optimized_python)
            self.assertIn(
                "sk-abcdefghijklmnopqrstuvwxyz123456",
                (destination / "notes.md").read_text(encoding="utf-8"),
            )
            self.assertFalse((destination / "ignored" / "secret.txt").exists())
            self.assertFalse((destination / "nested" / "drop.md").exists())
            self.assertTrue((destination / "nested" / "keep.md").exists())
            self.assertFalse((destination / "skip.tmp").exists())
            self.assertTrue((destination / "keep.tmp").exists())
            self.assertEqual((destination / "asset.bin").read_bytes(), b"\x00\x01\xff")
            self.assertEqual(report.failed_files, 0)
            self.assertGreaterEqual(report.processed_files, 3)
            self.assertEqual(serialized["processed_files"], report.processed_files)
            self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", report_text)
            self.assertTrue(
                any(
                    log["status"] == "compressed"
                    for item in serialized["items"]
                    for log in item["logs"]
                )
            )

    def test_in_place_project_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                process_path(root, root)

    def test_code_file_is_restored_when_budget_would_truncate_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source.py"
            destination = base / "optimized.py"
            original = (
                "def greet(name):\n"
                "    return f'hello {name}'\n"
                "print(greet('world'))\n"
                "print('keep full source')\n"
                "print('one more line')\n"
            )
            source.write_text(original, encoding="utf-8")

            report = process_path(
                source,
                destination,
                max_tokens=2,
                warn_on_truncation=False,
            )

            self.assertEqual(destination.read_text(encoding="utf-8"), original)
            self.assertTrue(
                any(
                    log.status == "rollback" and "Token budget" in log.detail
                    for log in report.items[0].logs
                )
            )


if __name__ == "__main__":
    unittest.main()
