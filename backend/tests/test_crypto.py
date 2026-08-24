import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import settings
from app.storage.crypto import decrypt_bytes, decrypt_str, encrypt_bytes, encrypt_str

KEY_A = Fernet.generate_key().decode()
KEY_B = Fernet.generate_key().decode()


def test_str_round_trip(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", KEY_A)
    token = encrypt_str("namaste, main theek hoon")
    assert decrypt_str(token) == "namaste, main theek hoon"
    assert token != "namaste, main theek hoon"


def test_bytes_round_trip(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", KEY_A)
    token = encrypt_bytes(b"\x00\x01 secret")
    assert decrypt_bytes(token) == b"\x00\x01 secret"


def test_ciphertext_is_opaque(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", KEY_A)
    plain = "primary_thread_should_not_leak"
    assert plain not in encrypt_str(plain)


def test_different_key_cannot_decrypt(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", KEY_A)
    token = encrypt_str("secret")
    monkeypatch.setattr(settings, "secret_key", KEY_B)
    with pytest.raises(InvalidToken):
        decrypt_str(token)


def test_tampered_token_raises(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", KEY_A)
    token = encrypt_str("secret")
    with pytest.raises(InvalidToken):
        decrypt_str(token[:-2] + "xx")
