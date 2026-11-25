"""Password hashing and policy (pure; no DB)."""

import unicodedata

import pytest

from core.security.passwords import (
    _dummy_hash,
    dummy_verify,
    hash_password,
    needs_rehash,
    validate_password,
    verify_password,
)

PASSWORD = "correct horse battery"
EMAIL = "user@example.com"


@pytest.fixture(scope="module")
def hashed() -> str:
    # argon2 is deliberately slow; hash once per module.
    return hash_password(PASSWORD)


def test_hash_is_not_the_password_and_is_argon2id(hashed):
    assert hashed != PASSWORD
    assert hashed.startswith("$argon2id$")


def test_hash_is_salted(hashed):
    assert hash_password(PASSWORD) != hashed


def test_verify_right_and_wrong(hashed):
    assert verify_password(hashed, PASSWORD) is True
    assert verify_password(hashed, PASSWORD + "x") is False


@pytest.mark.parametrize("bad", ["", "not-a-hash", "$argon2id$garbage", "$argon2id$v=19$m=65536,t=3,p=4$AAAA$BBBB"])
def test_verify_corrupt_hash_is_false(bad):
    assert verify_password(bad, PASSWORD) is False


def test_vietnamese_unicode_password():
    pw = "Mật khẩu rất dài 2026"
    h = hash_password(pw)
    assert verify_password(h, pw) is True
    # Diacritics matter: the unaccented form is a different password.
    assert verify_password(h, "Mat khau rat dai 2026") is False


def test_needs_rehash_false_for_current_params(hashed):
    assert needs_rehash(hashed) is False


def test_needs_rehash_true_for_weaker_params():
    from argon2 import PasswordHasher

    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    assert needs_rehash(weak) is True


def test_dummy_verify_returns_none_and_never_raises():
    assert dummy_verify("anything at all") is None
    assert dummy_verify("") is None


@pytest.mark.parametrize(
    "length,ok",
    [(11, False), (12, True), (128, True), (129, False)],
)
def test_policy_length_boundaries(length, ok):
    errors = validate_password("a" * length, email=EMAIL)
    assert (errors == []) is ok


def test_policy_counts_characters_not_bytes():
    # 12 characters, 24+ bytes in UTF-8.
    assert validate_password("ệ" * 12, email=EMAIL) == []
    assert validate_password("ệ" * 11, email=EMAIL) != []


def test_policy_rejects_email_case_insensitive():
    email = "Nguyen.Van.A@Example.com"
    assert validate_password("nguyen.van.a@example.com", email=email) != []
    assert validate_password("NGUYEN.VAN.A@EXAMPLE.COM", email=email) != []


def test_policy_no_composition_rules():
    assert validate_password("alllowercaseletters", email=EMAIL) == []


def test_policy_reports_all_violations():
    # Too short AND equal to the email.
    assert len(validate_password("a@b.c", email="a@b.c")) == 2


def test_verify_still_raises_on_programming_errors():
    with pytest.raises((TypeError, AttributeError)):
        verify_password(None, "pw")


def test_dummy_hash_uses_current_params():
    dummy = _dummy_hash()
    assert dummy.startswith("$argon2id$")
    assert not needs_rehash(dummy)


def test_nfd_password_verifies_against_nfc_hash_and_vice_versa():
    nfc = unicodedata.normalize("NFC", "Mật khẩu rất dài 2026")
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    assert verify_password(hash_password(nfc), nfd) is True
    assert verify_password(hash_password(nfd), nfc) is True


def test_policy_counts_length_after_nfc():
    # 6 characters typed, but 12 code points in NFD (e + combining acute).
    nfd = unicodedata.normalize("NFD", "é" * 6)
    assert len(nfd) == 12
    assert validate_password(nfd, email=EMAIL) != []


def test_policy_email_comparison_after_nfc():
    email = unicodedata.normalize("NFC", "việt.nam.user@example.com")
    assert validate_password(unicodedata.normalize("NFD", email), email=email) != []
    # And the other way round: NFC password, NFD email.
    assert validate_password(email, email=unicodedata.normalize("NFD", email)) != []
