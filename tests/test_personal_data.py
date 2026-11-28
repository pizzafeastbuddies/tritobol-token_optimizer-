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

    def test_email_domains_from_many_providers_and_institutions(self) -> None:
        domains = (
            "gmail.com outlook.com hotmail.com yahoo.com icloud.com qq.com "
            "163.com 126.com foxmail.com proton.me tuta.com gmx.com odu.edu "
            "mit.edu stanford.edu harvard.edu ox.ac.uk cam.ac.uk utoronto.ca "
            "nus.edu.sg tsinghua.edu.cn pku.edu.cn amd.com nvidia.com "
            "intel.com microsoft.com google.com amazon.com meta.com ibm.com "
            "oracle.com cisco.com qualcomm.com arm.com dell.com hpe.com "
            "openai.com anthropic.com huggingface.co github.com gitlab.com "
            "cloudflare.com databricks.com snowflake.com digitalocean.com "
            "canonical.com nasa.gov cern.ch esa.int nsf.gov ornl.gov lbl.gov "
            "anl.gov"
        ).split()
        for domain in domains:
            for local in ("jane.doe", "j_doe+test", "student123"):
                address = f"{local}@{domain}"
                with self.subTest(address=address):
                    self.assertEqual(
                        _spans(f"Mail {address}, thanks"), [("EMAIL", address)]
                    )

    def test_email_surrounded_by_punctuation_and_case(self) -> None:
        self.assertEqual(
            _spans("Mail <jane.doe@ox.ac.uk>."), [("EMAIL", "jane.doe@ox.ac.uk")]
        )
        self.assertEqual(
            _spans("mailto:jane@mit.edu?subject=x"), [("EMAIL", "jane@mit.edu")]
        )
        self.assertEqual(
            _spans("JANE.DOE@GMAIL.COM"), [("EMAIL", "JANE.DOE@GMAIL.COM")]
        )
        self.assertEqual(
            _spans("jane@163.com,bob@126.com"),
            [("EMAIL", "jane@163.com"), ("EMAIL", "bob@126.com")],
        )

    def test_incomplete_addresses_and_ssh_remotes_are_ignored(self) -> None:
        for text in (
            "a@b",
            "@gmail.com",
            "user@@gmail.com",
            "x@127.0.0.1",
            "git clone git@github.com:org/repo.git",
        ):
            with self.subTest(text=text):
                self.assertEqual(_spans(text), [])

    def test_known_first_and_last_name_pair_is_detected(self) -> None:
        self.assertEqual(
            _spans("Ask John Smith about it."),
            [("PERSONAL_NAME", "John Smith")],
        )

    def test_name_lists_load_from_bundled_data_files(self) -> None:
        from tritobol import personal_data

        self.assertIn("John", personal_data.FIRST_NAMES)
        self.assertIn("Smith", personal_data.LAST_NAMES)
        self.assertIn("M\u00fcller", personal_data.LAST_NAMES)
        self.assertNotIn("", personal_data.FIRST_NAMES)
        self.assertNotIn("", personal_data.LAST_NAMES)

    def test_sample_names_by_country(self) -> None:
        samples = {
            "CN": ["Shizhe Liang", "Wei Zhang", "Yuchen Wang"],
            "US": ["William Smith", "James Johnson", "Emily Brown"],
            "UK": ["Oliver Wilson", "Harry Taylor", "Charlotte Davis"],
            "KR": ["Jiho Kim", "Minjun Park", "Seoyeon Lee"],
            "JP": ["Haruto Sato", "Yuki Tanaka", "Aoi Suzuki"],
            "IN": ["Arjun Sharma", "Priya Patel", "Rahul Kumar"],
            "FR": ["Louis Martin", "Emma Bernard", "Hugo Dubois"],
            "DE": ["Lukas M\u00fcller", "Anna Schmidt", "Felix Weber"],
            "ES": ["Alejandro Garc\u00eda", "Lucia Martinez", "Pablo Rodriguez"],
            "IT": ["Luca Rossi", "Sofia Romano", "Marco Ferrari"],
            "BR": ["Jo\u00e3o Silva", "Maria Santos", "Gabriel Oliveira"],
            "RU": ["Alexander Ivanov", "Anna Smirnova", "Dmitry Petrov"],
            "CA": ["Liam Anderson", "Olivia Clark", "Noah Thompson"],
            "AU": ["Jack Williams", "Grace Thomas", "Ethan Walker"],
            "MX": ["Diego Hern\u00e1ndez", "Sof\u00eda L\u00f3pez", "Mateo Gonz\u00e1lez"],
            "NG": ["Chinedu Okafor", "Adaeze Nwosu", "Tunde Adeyemi"],
            "ZA": ["Thabo Nkosi", "Naledi Mokoena", "Sipho Dlamini"],
            "SG": ["Wei Ming Tan", "Jia Hui Lim", "Daniel Lee"],
            "VN": ["Minh Nguyen", "Anh Tran", "Duc Pham"],
            "TR": ["Mehmet Y\u0131lmaz", "Elif Kaya", "Emir Demir"],
        }
        for country, names in samples.items():
            for name in names:
                with self.subTest(country=country, name=name):
                    self.assertEqual(
                        _spans(f"Ask {name} about it."),
                        [("PERSONAL_NAME", name)],
                    )

    def test_names_with_punctuation_and_several_people(self) -> None:
        self.assertEqual(
            _spans("Hello, Jo\u00e3o Silva!"), [("PERSONAL_NAME", "Jo\u00e3o Silva")]
        )
        self.assertEqual(
            _spans("Priya Patel and Wei Ming Tan met."),
            [("PERSONAL_NAME", "Priya Patel"), ("PERSONAL_NAME", "Wei Ming Tan")],
        )

    def test_common_words_and_places_are_not_names(self) -> None:
        for text in (
            "Mark my words.",
            "The Green Park is open",
            "Anna wrote to Smith",
            "Priya  Patel",
            "priya patel",
        ):
            with self.subTest(text=text):
                self.assertEqual(_spans(text), [])

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

    def test_number_lists_sizes_and_isbn_are_not_phones(self) -> None:
        for text in (
            "Values 10 20 30 40 50 60 70",
            "Values 10-20-30-40-50-60-70",
            "Sizes 1024 768 and 640",
            "Scores: 1234 5678 9012",
            "ISBN 978-3-16-148410-0",
            "Prices 12.50 13.75 14.20 15.00",
        ):
            with self.subTest(text=text):
                self.assertEqual(_spans(text), [])

    def test_two_phones_in_one_sentence(self) -> None:
        self.assertEqual(
            _spans("Call 415-555-0132 or 415-555-0133"),
            [("PHONE", "415-555-0132"), ("PHONE", "415-555-0133")],
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
