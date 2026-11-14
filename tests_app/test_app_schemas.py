import pytest

from tritobol_app.schemas import AppError, MAX_INPUT_BYTES, parse_budget, parse_optimize_request


@pytest.mark.parametrize("value,expected", [(None, None), ("", None), ("  ", None), (5, 5), ("1,024", 1024), (7.0, 7), ("1_000", 1000)])
def test_budget_valid(value, expected):
    assert parse_budget(value) == expected


@pytest.mark.parametrize("value", [0, -1, "0", "-5", 1.5, "abc", "1e3", True, [], {}, 10**12])
def test_budget_invalid(value):
    with pytest.raises(AppError) as exc:
        parse_budget(value)
    assert exc.value.code == "budget_error" and exc.value.field == "max_tokens"


def test_request_defaults():
    req = parse_optimize_request({"text": "hello"})
    assert (req.tokenizer_id, req.max_tokens, req.task_type, req.sensitive_data, req.protect_code_blocks) == (
        "deepseek-v4.1-flash", None, "auto", "skip", True)


@pytest.mark.parametrize("payload,field", [
    ([], None), ({"text": 5}, "text"), ({}, "text"), ({"text": ""}, "text"), ({"text": " \n\t"}, "text"),
    ({"text": "x", "task_type": "bogus"}, "task_type"), ({"text": "x", "sensitive_data": "maybe"}, "sensitive_data"),
    ({"text": "x", "protect_code_blocks": "yes"}, "protect_code_blocks"), ({"text": "x", "tokenizer": ""}, "tokenizer"),
])
def test_request_invalid(payload, field):
    with pytest.raises(AppError) as exc:
        parse_optimize_request(payload)
    assert exc.value.code == "validation_error" and exc.value.field == field


def test_size_limit_is_bytes_not_chars():
    parse_optimize_request({"text": "a" * MAX_INPUT_BYTES})  # exactly at limit passes
    with pytest.raises(AppError) as exc:
        parse_optimize_request({"text": "a" * (MAX_INPUT_BYTES + 1)})
    assert exc.value.code == "input_too_large" and exc.value.status == 413 and "2 MB" in exc.value.message
    with pytest.raises(AppError):  # 3-byte chars: 700k chars > 2 MB
        parse_optimize_request({"text": "€" * 700_000})
