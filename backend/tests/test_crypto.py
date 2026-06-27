from stocktrack.crypto import encrypt, decrypt

KEY = "k" * 32

def test_roundtrip():
    assert decrypt(encrypt("hello", KEY), KEY) == "hello"

def test_empty_string():
    assert decrypt(encrypt("", KEY), KEY) == ""

def test_different_keys_fail():
    import pytest
    from cryptography.fernet import InvalidToken
    token = encrypt("secret", KEY)
    with pytest.raises(InvalidToken):
        decrypt(token, "z" * 32)

def test_deterministic_key():
    # Same key always produces same Fernet instance (same raw bytes)
    t1 = encrypt("data", KEY)
    t2 = encrypt("data", KEY)
    # Fernet adds random IV so tokens differ, but both decrypt
    assert decrypt(t1, KEY) == decrypt(t2, KEY) == "data"
