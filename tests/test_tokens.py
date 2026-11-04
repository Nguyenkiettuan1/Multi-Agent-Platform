"""Session token generation and HMAC signing (pure; stdlib only)."""

import pytest

from core.security.tokens import new_token, sign, token_hash, unsign

SECRET = "test-secret-key"


def test_new_tokens_differ_and_are_urlsafe():
    a, b = new_token(), new_token()
    assert a != b
    assert "." not in a and "." not in b
    assert len(a) >= 43  # 32 random bytes, base64url


def test_token_hash_is_sha256_hex():
    h = token_hash("abc")
    assert h == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert len(h) == 64


def test_token_hash_differs_per_token():
    assert token_hash("a") != token_hash("b")


def test_sign_unsign_roundtrip():
    token = new_token()
    signed = sign(token, SECRET)
    assert signed.startswith(token + ".")
    assert "=" not in signed
    assert unsign(signed, SECRET) == token


def test_unsign_rejects_changed_signature_char():
    signed = sign(new_token(), SECRET)
    head, sig = signed.rsplit(".", 1)
    flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
    assert unsign(f"{head}.{flipped}", SECRET) is None


def test_unsign_rejects_changed_token():
    token = new_token()
    sig = sign(token, SECRET).rsplit(".", 1)[1]
    other = "A" + token[1:] if token[0] != "A" else "B" + token[1:]
    assert unsign(f"{other}.{sig}", SECRET) is None


def test_unsign_rejects_different_secret():
    assert unsign(sign(new_token(), SECRET), "another-secret") is None


def test_unsign_splits_on_last_dot():
    # token_urlsafe never emits dots, but the rule is the last dot, so a
    # token that contains one still round-trips.
    assert unsign(sign("a.b", SECRET), SECRET) == "a.b"


@pytest.mark.parametrize(
    "value",
    [
        "", "nodot", ".", "abc.", ".abc", "abc.!!!notbase64!!!", "abc.a",
        None, 123, b"abc.def",
        # Non-ASCII can never be a value we signed; must not raise.
        "\ud800.abc", "abc.\udcff", "abc.\xff", "tôi.abc",
    ],
)
def test_unsign_malformed_returns_none(value):
    assert unsign(value, SECRET) is None


def test_unsign_rejects_padded_signature():
    # Signatures are issued without padding; a padded variant is not ours.
    token = new_token()
    assert unsign(sign(token, SECRET) + "=", SECRET) is None


@pytest.mark.parametrize("secret", ["", None])
def test_empty_secret_is_a_programming_error(secret):
    with pytest.raises(ValueError):
        sign("tok", secret)
    with pytest.raises(ValueError):
        unsign("tok.sig", secret)
