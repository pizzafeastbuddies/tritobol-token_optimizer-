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

    def test_phone_samples_by_country(self) -> None:
        samples = {
            "US": ["+1 (415) 555-0132", "415-555-0132", "415.555.0132",
                   "(415) 555-0132", "+14155550132"],
            "UK": ["+44 7700 900123", "07700 900123", "+44 20 7946 0958",
                   "020 7946 0958"],
            "CN": ["+86 138 0013 8000", "13800138000", "+86 13800138000",
                   "138-0013-8000"],
            "KR": ["+82 10-1234-5678", "010-1234-5678", "+82 2-312-3456",
                   "01012345678"],
            "JP": ["+81 90-1234-5678", "090-1234-5678", "+81 3-1234-5678",
                   "03-1234-5678"],
            "DE": ["+49 151 12345678", "0151 12345678", "+49 30 23125 123",
                   "030 23125123"],
            "FR": ["+33 6 12 34 56 78", "06 12 34 56 78", "+33 1 99 00 12 34",
                   "0612345678"],
            "AU": ["+61 491 570 156", "0491 570 156", "+61 2 5550 1234",
                   "(02) 5550 1234"],
            "IN": ["+91 98765 43210", "098765 43210", "+91-98765-43210",
                   "9876543210"],
            "SG": ["+65 6123 4567", "+65 9123 4567", "6123 4567"],
        }
        for country, numbers in samples.items():
            for number in numbers:
                with self.subTest(country=country, number=number):
                    self.assertEqual(
                        _spans(f"Call {number} now"), [("PHONE", number)]
                    )

    def test_bare_ids_and_counters_are_not_phones(self) -> None:
        for text in (
            "Order 12345678 shipped",
            "Ticket #1234567 closed",
            "Total 91234567 bytes",
            "Build 2026112 passed",
        ):
            with self.subTest(text=text):
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
