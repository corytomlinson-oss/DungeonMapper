import secrets
import string


def generate_code(length: int = 6) -> str:
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def generate_token() -> str:
    return secrets.token_hex(16)
