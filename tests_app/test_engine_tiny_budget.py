"""The only engine change: tail() raises BudgetTooSmallError (a ValueError) instead of IndexError."""
import subprocess
import sys

import pytest

from tritobol import Tritobol
from tritobol.tokenizer import BudgetTooSmallError, get_default_tokenizer


@pytest.mark.parametrize("char", ["🎃", "Ń", "😀"])
def test_budget_smaller_than_one_character_raises_clear_error(char):
    tok = get_default_tokenizer()
    assert tok.count(char) == 2  # premise of the scenario
    with pytest.raises(BudgetTooSmallError) as exc:
        Tritobol().optimize(char, max_tokens=1, warn_on_truncation=False)
    assert isinstance(exc.value, ValueError) and "too small" in str(exc.value)


@pytest.mark.parametrize("char", ["🎃", "Ń"])
def test_budget_that_fits_still_works(char):
    assert Tritobol().optimize(char, max_tokens=2, warn_on_truncation=False).text == char


def test_unchanged_behaviour_for_normal_truncation():
    text = " ".join(f"word{i}" for i in range(200))
    r = Tritobol().optimize(text, max_tokens=10, warn_on_truncation=False)
    assert r.stats.truncated and Tritobol().count_tokens(r.text) <= 10 and r.text.endswith("word199")


def test_cli_reports_clean_error_not_traceback():
    p = subprocess.run([sys.executable, "-m", "tritobol", "--max-tokens", "1"], input="🎃", capture_output=True, text=True, encoding="utf-8")
    assert p.returncode != 0 and "too small" in p.stderr and "Traceback" not in p.stderr and "IndexError" not in p.stderr
