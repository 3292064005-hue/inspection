from inspection_utils.param_parsing import coerce_bool


def test_coerce_bool_handles_string_tokens() -> None:
    assert coerce_bool('true') is True
    assert coerce_bool('TRUE') is True
    assert coerce_bool('1') is True
    assert coerce_bool('false', default=True) is False
    assert coerce_bool('0', default=True) is False
    assert coerce_bool('off', default=True) is False


def test_coerce_bool_does_not_treat_false_string_as_truthy() -> None:
    assert bool('false') is True
    assert coerce_bool('false') is False
