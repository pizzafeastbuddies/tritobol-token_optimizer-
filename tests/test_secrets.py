"""Tests for local credential pattern detection."""

from __future__ import annotations

import unittest

from tritobol import SecretScanner


class SecretScannerTests(unittest.TestCase):
    def test_known_provider_prefixes_and_longest_prefix_match(self) -> None:
        body = "A1b2C3d4E5f6G7h8"
        text = f"sk-{body} sk-ant-{body} AIza{body} hf_{body}"

        findings = SecretScanner().scan(text)

        self.assertEqual(
            [finding.provider for finding in findings],
            ["openai", "anthropic", "google", "huggingface"],
        )
        self.assertEqual(
            [text[finding.start:finding.end] for finding in findings],
            [f"sk-{body}", f"sk-ant-{body}", f"AIza{body}", f"hf_{body}"],
        )
        self.assertNotIn(body, repr(findings))

    def test_short_values_and_prefixes_inside_words_are_ignored(self) -> None:
        scanner = SecretScanner()

        self.assertEqual(
            scanner.scan("sk-short and task-sk-" + "A" * 20),
            [],
        )

    def test_custom_provider_prefix_is_supported(self) -> None:
        scanner = SecretScanner({"internal-service": ("internal_",)})

        finding = scanner.scan("token=internal_" + "Z" * 12)[0]

        self.assertEqual(finding.provider, "internal-service")

    def test_invalid_custom_prefix_configuration_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SecretScanner({"invalid": "prefix"})


if __name__ == "__main__":
    unittest.main()
