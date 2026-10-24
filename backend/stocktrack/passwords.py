"""Password hashing (argon2id) for the single login user.

Parameters are the fleet template's: time_cost=2, memory_cost=64 MiB,
parallelism=2. Secrets at rest (the Gotify token) use ``crypto.py`` instead.
"""
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_HASHER = PasswordHasher(time_cost=2, memory_cost=64 * 1024, parallelism=2)


def hash_password(plain: str) -> str:
    return _HASHER.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return _HASHER.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
