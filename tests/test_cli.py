"""Tests for the command-line interface."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tritobol import Tritobol
from tritobol.__main__ import main


class CliGuidedWorkflowTests(unittest.TestCase):
    def test_no_arguments_starts_guided_flow_in_a_terminal(self) -> None:
        class TtyInput(io.StringIO):
            def isatty(self) -> bool:
                return True

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdin", TtyInput()), \
            patch("builtins.input", side_effect=EOFError), \
            redirect_stdout(stdout), redirect_stderr(stderr):
            status = main([])

        self.assertEqual(status, 0)
        self.assertIn("guided mode", stdout.getvalue())
        self.assertIn("Cancelled.", stdout.getvalue())

    def test_no_arguments_keeps_piped_stdin_behavior(self) -> None:
        stdin = io.StringIO("Piped text stays on the normal CLI path.\n")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
            status = main([])

        self.assertEqual(status, 0)
        self.assertNotIn("guided mode", stdout.getvalue())
        self.assertIn("Piped text stays on the normal CLI path.", stdout.getvalue())

    def test_guided_flow_shows_preview_and_saves_separate_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            input_path = Path(temporary) / "prompt.txt"
            original = (
                "This is a repeated paragraph that is definitely long enough.\n\n"
                "This is a repeated paragraph that is definitely long enough.\n"
            )
            input_path.write_text(original, encoding="utf-8")
            output_path = Path(temporary) / "prompt.optimized.txt"
            answers = iter([str(input_path), "", "", "yes"])
            prompts = []
            stdout = io.StringIO()
            stderr = io.StringIO()

            def answer(prompt: str) -> str:
                prompts.append(prompt)
                return next(answers)

            with patch(
                "builtins.input",
                side_effect=answer,
            ), \
                redirect_stdout(stdout), redirect_stderr(stderr):
                status = main(["--interactive"])

            self.assertEqual(status, 0)
            self.assertIn("Tokens:", stdout.getvalue())
            self.assertIn("Preview (unified diff", stdout.getvalue())
            self.assertIn("Optional maximum token budget", prompts[1])
            self.assertTrue(output_path.is_file())
            self.assertNotEqual(output_path.read_text(encoding="utf-8"), original)
            self.assertEqual(input_path.read_text(encoding="utf-8"), original)

    def test_guided_flow_defaults_to_no_token_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            input_path = Path(temporary) / "prompt.md"
            text = "A short text file.\n"
            input_path.write_text(text, encoding="utf-8")
            answers = iter([str(input_path), "", "", "n"])
            stdout = io.StringIO()
            stderr = io.StringIO()
            optimizer = Mock(return_value=Tritobol().optimize(text))

            with patch("builtins.input", side_effect=lambda _prompt: next(answers)), \
                patch(
                    "tritobol.__main__.Tritobol",
                    return_value=SimpleNamespace(optimize=optimizer),
                ) as tritobol, \
                redirect_stdout(stdout), redirect_stderr(stderr):
                status = main(["--interactive"])

            self.assertEqual(status, 0)
            tritobol.assert_called_once_with()
            optimizer.assert_called_once_with(text, max_tokens=None)
            self.assertIn("Cancelled; no output file was written.", stdout.getvalue())
            self.assertEqual(list(Path(temporary).iterdir()), [input_path])

    def test_guided_flow_refuses_source_or_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            input_path = Path(temporary) / "prompt.txt"
            original = "Source remains untouched.\n"
            input_path.write_text(original, encoding="utf-8")

            for output_path, expected_message in (
                (input_path, "must not overwrite the source"),
                (Path(temporary) / "existing.txt", "output already exists"),
            ):
                if output_path != input_path:
                    output_path.write_text("Keep this file.", encoding="utf-8")
                answers = iter([str(input_path), "", str(output_path)])
                stdout = io.StringIO()
                stderr = io.StringIO()

                with patch("builtins.input", side_effect=lambda _prompt: next(answers)), \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                    status = main(["--interactive"])

                self.assertEqual(status, 1)
                self.assertIn(expected_message, stderr.getvalue())
                self.assertEqual(input_path.read_text(encoding="utf-8"), original)
                if output_path != input_path:
                    self.assertEqual(output_path.read_text(encoding="utf-8"), "Keep this file.")


class CliPreviewTests(unittest.TestCase):
    def test_diff_shows_changes_without_writing_or_mutating_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            input_path = Path(temporary) / "prompt.txt"
            original = (
                "This is a repeated paragraph that is definitely long enough.\n\n"
                "This is a repeated paragraph that is definitely long enough.\n"
            )
            input_path.write_text(original, encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = main([str(input_path), "--diff"])

            self.assertEqual(status, 0)
            self.assertIn("--- " + str(input_path), stdout.getvalue())
            self.assertIn("+++ " + str(input_path) + " (optimized)", stdout.getvalue())
            self.assertIn("-This is a repeated paragraph", stdout.getvalue())
            self.assertIn("tokens", stderr.getvalue())
            self.assertEqual(input_path.read_text(encoding="utf-8"), original)
            self.assertEqual(list(Path(temporary).iterdir()), [input_path])

    def test_diff_rejects_output_file(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(["--diff", "--output", "optimized.txt"])
        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("--diff cannot be combined with --output", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
