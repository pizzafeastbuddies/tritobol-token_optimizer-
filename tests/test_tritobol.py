"""Tests for tritobol.

Run from the project root:

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from tritobol import HuggingFaceTokenizer, Tritobol

BOILERPLATE = (
    "This is a repeated boilerplate paragraph that should appear only once "
    "in the optimized prompt because it adds no new information."
)


def report(label: str, result) -> None:
    """Print the token counts required by the project brief."""
    stats = result.stats
    print(
        f"\n[{label}] original={stats.original_tokens} "
        f"optimized={stats.optimized_tokens} "
        f"saved={stats.saved_percent:.1f}%"
    )
    print(f"         {stats.summary()}")


class TokenizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = Tritobol()

    def test_deepseek_v41_flash_tokenizer_is_bundled(self) -> None:
        self.assertEqual(self.tool.tokenizer.model_name, "deepseek-v4.1-flash")
        self.assertEqual(self.tool.tokenizer.vocab_size, 129_280)
        # Counts from the official tokenizer, not an approximation.
        self.assertEqual(self.tool.count_tokens("Hello world"), 2)
        self.assertEqual(self.tool.count_tokens("你好，世界！"), 4)

    def test_empty_text(self) -> None:
        result = self.tool.optimize("")
        self.assertEqual(result.text, "")
        self.assertEqual(result.stats.original_tokens, 0)
        self.assertEqual(result.stats.optimized_tokens, 0)
        self.assertEqual(result.stats.saved_percent, 0.0)

    def test_custom_hugging_face_tokenizer_is_used(self) -> None:
        tokenizer_path = (
            Path(__file__).parents[1]
            / "tritobol"
            / "data"
            / "deepseek_v41_tokenizer.json"
        )
        tokenizer = HuggingFaceTokenizer(
            tokenizer_path,
            model_name="custom-compatible-model",
        )
        tool = Tritobol(tokenizer=tokenizer)

        self.assertEqual(tokenizer.model_name, "custom-compatible-model")
        self.assertEqual(tool.count_tokens("Hello world"), 2)
        result = tool.optimize("Hello world", max_tokens=2)
        self.assertEqual(result.stats.original_tokens, 2)
        self.assertEqual(result.text, "Hello world")
        windowed = tool.optimize(
            "Hello world " * 8,
            max_tokens=2,
            warn_on_truncation=False,
        )
        self.assertTrue(windowed.stats.truncated)
        self.assertLessEqual(windowed.stats.optimized_tokens, 2)


class TrimmingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = Tritobol()

    def test_low_noise_whitespace_reduction(self) -> None:
        # Mostly unique prose surrounded by redundant indentation and blank
        # lines.  This is the low end of the expected 10-80% saving range.
        text = """
            Alpha is the first item in the sequence and it must remain.




            Beta is the second item in the sequence and it must remain.


            Gamma is the third item in the sequence and it must remain.
        """
        result = self.tool.optimize(text)
        report("low noise / whitespace", result)
        self.assertGreaterEqual(result.stats.saved_percent, 10.0)
        self.assertLessEqual(result.stats.saved_percent, 20.0)
        self.assertIn("Alpha", result.text)
        self.assertIn("Beta", result.text)
        self.assertIn("Gamma", result.text)
        self.assertNotIn("\n\n\n", result.text)

    def test_repeated_paragraphs_and_unique_content(self) -> None:
        text = f"""
        Introduction: This document explains the deployment process in detail.

        The deployment process starts with a backup of the production database
        and a review of the release notes.

        The deployment process starts with a backup of the production database
        and a review of the release notes.

        After the backup completes, run the migration and verify the health
        checks before routing traffic.

        After the backup completes, run the migration and verify the health
        checks before routing traffic.

        Conclusion: Keep the latest context when the input is too long.
        """
        result = self.tool.optimize(text)
        report("duplicate paragraphs", result)
        self.assertGreaterEqual(result.stats.saved_percent, 30.0)
        self.assertGreaterEqual(result.stats.removed_paragraphs, 1)
        self.assertEqual(result.text.count("The deployment process starts"), 1)
        self.assertEqual(result.text.count("After the backup completes"), 1)
        self.assertIn("Introduction", result.text)
        self.assertIn("Conclusion", result.text)

    def test_high_noise_reaches_upper_range(self) -> None:
        # Seven copies of a long boilerplate block plus unique opening/closing
        # content.  Only the first copy remains.
        text = (
            "Intro: unique opening sentence that must stay.\n\n"
            + "\n\n".join([BOILERPLATE] * 7)
            + "\n\nOutro: unique closing sentence that must stay."
        )
        result = self.tool.optimize(text)
        report("high noise / repeated blocks", result)
        self.assertGreaterEqual(result.stats.saved_percent, 70.0)
        self.assertLessEqual(result.stats.saved_percent, 80.0)
        self.assertEqual(result.text.count(BOILERPLATE), 1)
        self.assertIn("Intro:", result.text)
        self.assertIn("Outro:", result.text)

    def test_repeated_sentences_are_removed(self) -> None:
        sentence = "This exact sentence is repeated and should be kept once."
        text = f"{sentence} A unique middle sentence stays here. {sentence}"
        result = self.tool.optimize(text)
        report("duplicate sentences", result)
        self.assertEqual(result.text.count(sentence), 1)
        self.assertIn("A unique middle sentence stays here.", result.text)
        self.assertGreater(result.stats.removed_sentences, 0)

    def test_fenced_code_is_preserved_verbatim(self) -> None:
        code = "```python\n  values  = [1,  2]\n\nprint(  values )\n```\n"
        text = f"Introductory prose before the code example.\n\n{code}\nMore prose after it."

        result = self.tool.optimize(text)

        self.assertIn(code, result.text)
        self.assertIn("Introductory prose before the code example.", result.text)
        self.assertIn("More prose after it.", result.text)

    def test_code_block_line_endings_are_preserved(self) -> None:
        code = "```python\r\n  value  =  1\r\n```\r\n"
        result = self.tool.optimize(f"Example:\r\n\r\n{code}\r\nDone.")

        self.assertIn(code, result.text)

    def test_duplicate_fenced_code_blocks_are_not_removed(self) -> None:
        code = (
            "~~~python\n"
            "a_repeatedly_named_variable = {'first':  1, 'second':  2}\n"
            "~~~"
        )
        result = self.tool.optimize(f"{code}\n\n{code}")

        self.assertEqual(result.text.count(code), 2)

    def test_code_block_protection_can_be_disabled(self) -> None:
        code = "```text\n" + ("duplicate line with spacing   \n" * 2) + "```"
        tool = Tritobol(protect_code_blocks=False)

        result = tool.optimize(code)

        self.assertNotEqual(result.text, code)

    def test_long_python_block_compresses_comments_and_blank_lines(self) -> None:
        code = (
            "```python\n"
            "# explanatory comment\n"
            "# explanatory comment\n"
            "def calculate(value):\n"
            "\n"
            "    # another comment\n"
            "    return value + 1\n"
            "\n"
            "print(calculate(2))\n"
            "```\n"
        )

        result = self.tool.optimize(code)

        self.assertIn("def calculate(value):", result.text)
        self.assertIn("    return value + 1", result.text)
        self.assertIn("print(calculate(2))", result.text)
        self.assertEqual(result.text.count("explanatory comment"), 1)
        self.assertIn("another comment", result.text)
        self.assertTrue(any(log.status == "compressed" for log in result.segments))
        self.assertIn("```python", result.text)

    def test_short_python_snippet_and_tool_directives_are_preserved(self) -> None:
        short = "```python\nx = 1\nprint(x)\n```\n"
        short_result = self.tool.optimize(short)
        self.assertIn(short, short_result.text)
        self.assertTrue(any(log.status == "protected" for log in short_result.segments))

        code = (
            "```python\n#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n"
            "# noqa\n# type: ignore\n# nosec\n"
            "def main():\n    return 1\n\nprint(main())\n```\n"
        )
        result = self.tool.optimize(code)
        for directive in ("#!/usr/bin/env python", "# -*- coding: utf-8 -*-", "# noqa", "# type: ignore", "# nosec"):
            self.assertIn(directive, result.text)

    def test_blank_lines_inside_python_multiline_string_are_preserved(self) -> None:
        body = (
            'def message():\n'
            '    return """first line\n'
            '\n'
            'third line"""\n'
            'print(message())\n'
            'print("extra line")\n'
        )
        code = f"```python\n{body}```\n"

        result = self.tool.optimize(code)

        self.assertIn('"""first line\n\nthird line"""', result.text)
        compile(
            result.text.removeprefix("```python\n").removesuffix("```\n"),
            "<test-multiline-string>",
            "exec",
        )

    def test_python_syntax_failure_rolls_back_segment(self) -> None:
        code = (
            "```python\n# comment\n\ndef broken():\n"
            "    return 1\nreturn 2\nprint('done')\nprint('still broken')\n```\n"
        )

        result = self.tool.optimize(code)

        self.assertIn(code, result.text)
        self.assertTrue(any(log.status == "rollback" for log in result.segments))
        self.assertTrue(any("Validation failed" in log.detail for log in result.segments))

    def test_json_config_is_compacted_and_validated(self) -> None:
        code = '```json\n{\n  "service": {\n    "enabled": true,\n    "retries": 3\n  }\n}\n```\n'

        result = self.tool.optimize(code)

        self.assertIn('{"service":{"enabled":true,"retries":3}}', result.text)
        self.assertTrue(any(log.status == "compressed" for log in result.segments))

    def test_malformed_json_config_is_rolled_back(self) -> None:
        code = '```json\n{\n  "enabled": true,\n  "enabled":\n}\n```\n'

        result = self.tool.optimize(code)

        self.assertIn(code, result.text)
        self.assertTrue(any(log.status == "rollback" for log in result.segments))

    def test_duplicate_json_keys_are_not_silently_discarded(self) -> None:
        code = '```json\n{\n  "enabled": true,\n  "enabled": false\n}\n```\n'

        result = self.tool.optimize(code)

        self.assertIn(code, result.text)
        self.assertTrue(any(log.status == "rollback" for log in result.segments))

    def test_task_type_changes_prose_aggressiveness(self) -> None:
        text = "Keep this phrase.\n\nKeep this phrase."

        coding = self.tool.optimize(text, task_type="coding")
        document = self.tool.optimize(text, task_type="document")

        self.assertEqual(coding.text.count("Keep this phrase."), 2)
        self.assertEqual(document.text.count("Keep this phrase."), 1)

    def test_sensitive_data_can_be_protected_or_masked(self) -> None:
        secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
        anthropic_secret = "sk-ant-" + "A1b2C3d4E5f6G7h8"
        confidential = "CONFIDENTIAL: internal implementation details must remain."
        text = (
            f"api_key = {secret}\n\napi_key = {anthropic_secret}\n\n{confidential}"
            "\n\nAn explanatory sentence remains."
        )

        protected = self.tool.optimize(text)
        masked = Tritobol(sensitive_data="mask").optimize(text)

        self.assertIn(secret, protected.text)
        self.assertIn(anthropic_secret, protected.text)
        self.assertIn(confidential, protected.text)
        self.assertNotIn(secret, masked.text)
        self.assertNotIn(anthropic_secret, masked.text)
        self.assertIn("[REDACTED]", masked.text)
        self.assertNotIn(confidential, masked.text)
        self.assertTrue(any(log.kind == "sensitive" for log in protected.segments))
        anthropic_logs = [
            log for log in protected.segments if log.provider == "anthropic"
        ]
        self.assertTrue(anthropic_logs)
        self.assertTrue(
            all(secret not in log.detail for log in (*protected.segments, *masked.segments))
        )


class SlidingWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = Tritobol()
        cls.long_text = "\n\n".join(
            f"Section {index}: " + "detail " * 30 for index in range(20)
        )

    def test_keeps_latest_context_and_warns_once(self) -> None:
        stderr = io.StringIO()
        result = self.tool.optimize(
            self.long_text,
            max_tokens=80,
            warning_stream=stderr,
        )
        report("long text / sliding window", result)

        self.assertTrue(result.stats.truncated)
        self.assertLessEqual(result.stats.optimized_tokens, 80)
        self.assertIn("Section 19", result.text)
        self.assertNotIn("Section 0", result.text)
        self.assertEqual(stderr.getvalue().count("WARNING:"), 1)
        self.assertIn("discarded the earliest", stderr.getvalue())
        self.assertIn("max_tokens=80", stderr.getvalue())
        self.assertIsNotNone(result.warning)

    def test_no_warning_when_under_budget(self) -> None:
        text = "A short unique prompt that already fits the budget."
        stderr = io.StringIO()
        result = self.tool.optimize(text, max_tokens=100, warning_stream=stderr)
        report("under budget", result)
        self.assertFalse(result.stats.truncated)
        self.assertEqual(result.stats.discarded_tokens, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIsNone(result.warning)
        self.assertEqual(result.text, text)

    def test_warning_can_be_suppressed(self) -> None:
        stderr = io.StringIO()
        result = self.tool.optimize(
            self.long_text,
            max_tokens=50,
            warn_on_truncation=False,
            warning_stream=stderr,
        )
        self.assertTrue(result.stats.truncated)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIsNotNone(result.warning)

    def test_invalid_budget_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.tool.optimize("some text", max_tokens=0)


class SummaryTests(unittest.TestCase):
    def test_summary_contains_counts_and_percentage(self) -> None:
        tool = Tritobol()
        result = tool.optimize("Clean prose. " * 10)
        summary = result.stats.summary()
        self.assertIn("tokens", summary)
        self.assertIn("%", summary)
        self.assertIn("saved", summary)


if __name__ == "__main__":
    unittest.main(verbosity=2)
