import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from apcontrol import cuit  # noqa: E402


def test_check_digit_round_trip():
    body = "3071234567"
    dv = cuit.check_digit(body)
    assert dv is not None
    assert cuit.is_valid(body + str(dv))
    assert not cuit.is_valid(body + str((dv + 1) % 10))


def test_separators_are_ignored():
    body = "2012345678"
    full = body + str(cuit.check_digit(body))
    assert cuit.is_valid(cuit.format_cuit(full))
    assert cuit.format_cuit(full).count("-") == 2


def test_rejects_wrong_length_and_prefix():
    assert not cuit.is_valid("123")
    assert not cuit.is_valid("")
    body = "9912345678"  # 99 is not a valid type prefix
    assert not cuit.is_valid(body + "0")
