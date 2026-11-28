"""Tests for local personal-data detection."""

from __future__ import annotations

import unittest

from tritobol import PersonalDataFinding, find_personal_data


def _spans(text: str) -> list[tuple[str, str]]:
    return [(f.kind, text[f.start:f.end]) for f in find_personal_data(text)]


class PersonalDataTests(unittest.TestCase):
    def test_email_addresses_are_detected(self) -> None:
        self.assertEqual(
            _spans("Contact john.doe+work@example.co.uk today"),
            [("EMAIL", "john.doe+work@example.co.uk")],
        )

    def test_known_first_and_last_name_pair_is_detected(self) -> None:
        self.assertEqual(
            _spans("Ask John Smith about it."),
            [("PERSONAL_NAME", "John Smith")],
        )

    def test_single_names_and_unknown_pairs_are_ignored(self) -> None:
        self.assertEqual(_spans("John went home."), [])
        self.assertEqual(_spans("Smith went home."), [])
        self.assertEqual(_spans("Zorblax Quux wrote it."), [])

    def test_common_phone_formats_are_detected(self) -> None:
        text = "A +1 (415) 555-0132, B 415.555.0132, C 0812-3456-7890"

        self.assertEqual(
            [kind for kind, _ in _spans(text)],
            ["PHONE", "PHONE", "PHONE"],
        )

    def test_dates_versions_ips_and_short_numbers_are_not_phones(self) -> None:
        text = "On 2026-11-28, use v1.2.3 at 192.168.1.100 with 12 34 items."

        self.assertEqual(_spans(text), [])

    def test_email_digits_are_not_reported_as_phone(self) -> None:
        self.assertEqual(
            _spans("Write to user2024555123@mail.com"),
            [("EMAIL", "user2024555123@mail.com")],
        )

    def test_mixed_text_is_sorted_and_non_overlapping(self) -> None:
        text = "Mary Jones (mary@x.org) called +44 20 7946 0958."

        self.assertEqual(
            _spans(text),
            [
                ("PERSONAL_NAME", "Mary Jones"),
                ("EMAIL", "mary@x.org"),
                ("PHONE", "+44 20 7946 0958"),
            ],
        )

    def test_findings_do_not_expose_matched_text(self) -> None:
        findings = find_personal_data("Email john@email.com")

        self.assertEqual(
            findings,
            [PersonalDataFinding("EMAIL", 6, 20)],
        )
        self.assertNotIn("john@email.com", repr(findings))

    def test_non_string_input_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            find_personal_data(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
