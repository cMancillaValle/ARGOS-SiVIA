"""
backend/services/two_factor.py
──────────────────────────────
Lógica TOTP (2FA) para ARGOS - SiViA.

Dependencias: pyotp, qrcode[pil], cryptography
    pip install pyotp qrcode[pil] cryptography

Secret TOTP: cifrado con Fernet (AES-128 CBC + HMAC-SHA256).
La clave Fernet DEBE venir de la variable de entorno ARGOS_FERNET_KEY.

Generar una clave nueva (solo hacerlo una vez y guardar):
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations
import os
import json
import secrets
import string
import hmac
import hashlib
from typing import Optional

# ── Dependencias opcionales ────────────────────────────────────────────────
try:
    import pyotp
    PYOTP_OK = True
except ImportError:
    PYOTP_OK = False

try:
    from cryptography.fernet import Fernet, InvalidToken
    FERNET_OK = True
except ImportError:
    FERNET_OK = False

try:
    import qrcode
    import qrcode.image.svg
    import io
    import base64
    QRCODE_OK = True
except ImportError:
    QRCODE_OK = False


# ── Clave Fernet desde ENV ─────────────────────────────────────────────────
_FERNET_KEY_RAW = os.environ.get('ARGOS_FERNET_KEY', '')
_fernet: Optional['Fernet'] = None  # type: ignore[type-arg]

def _get_fernet() -> 'Fernet':
    """Instancia Fernet perezosamente (singleton)."""
    global _fernet
    if _fernet is not None:
        return _fernet
    if not FERNET_OK:
        raise RuntimeError('Instalar: pip install cryptography')
    if not _FERNET_KEY_RAW:
        raise RuntimeError(
            'Variable de entorno ARGOS_FERNET_KEY no definida. '
            'Genera una con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    _fernet = Fernet(_FERNET_KEY_RAW.encode())
    return _fernet


# ── Cifrado / Descifrado ───────────────────────────────────────────────────
def encrypt_secret(plain_secret: str) -> str:
    """Cifra el TOTP secret con Fernet. Devuelve b64url string."""
    return _get_fernet().encrypt(plain_secret.encode()).decode()


def decrypt_secret(encrypted: str) -> str:
    """Descifra. Lanza ValueError si el token es inválido."""
    try:
        return _get_fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        raise ValueError('Token TOTP inválido o clave incorrecta.')


# ── Generar secret TOTP ────────────────────────────────────────────────────
def generate_totp_secret() -> str:
    """Genera un nuevo secret TOTP en Base32 (32 chars = 160 bits)."""
    if not PYOTP_OK:
        raise RuntimeError('Instalar: pip install pyotp')
    return pyotp.random_base32()


# ── Generar URI para QR ────────────────────────────────────────────────────
def totp_uri(secret: str, username: str, issuer: str = 'ARGOS SiViA') -> str:
    """Devuelve el otpauth:// URI para generar el QR."""
    if not PYOTP_OK:
        raise RuntimeError('Instalar: pip install pyotp')
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


# ── QR como data-URI PNG base64 ────────────────────────────────────────────
def totp_qr_base64(secret: str, username: str) -> str:
    """Genera un QR PNG y lo devuelve como data:image/png;base64,..."""
    if not QRCODE_OK:
        raise RuntimeError('Instalar: pip install qrcode[pil]')
    uri = totp_uri(secret, username)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f'data:image/png;base64,{b64}'


# ── Verificar código TOTP ──────────────────────────────────────────────────
def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
    """
    Verifica un código TOTP de 6 dígitos.
    valid_window=1 acepta ±30s de desfase de reloj.
    """
    if not PYOTP_OK:
        raise RuntimeError('Instalar: pip install pyotp')
    totp = pyotp.TOTP(secret)
    return totp.verify(str(code).strip(), valid_window=valid_window)


# ── Backup Codes ───────────────────────────────────────────────────────────
_BC_ALPHABET = string.ascii_uppercase + string.digits
_BC_GROUP    = 4
_BC_GROUPS   = 2
_BC_COUNT    = 8


def generate_backup_codes() -> tuple[list[str], list[str]]:
    """
    Genera 8 backup codes de un solo uso.
    Devuelve (plain_codes, hashed_codes).
    plain_codes  → mostrar al usuario UNA SOLA VEZ.
    hashed_codes → guardar en la BD (SHA-256 hexdigest).
    Formato: XXXX-XXXX
    """
    plain, hashed = [], []
    for _ in range(_BC_COUNT):
        groups = [
            ''.join(secrets.choice(_BC_ALPHABET) for _ in range(_BC_GROUP))
            for _ in range(_BC_GROUPS)
        ]
        code = '-'.join(groups)
        plain.append(code)
        hashed.append(hashlib.sha256(code.encode()).hexdigest())
    return plain, hashed


def verify_backup_code(code: str, stored_hashed: list[str]) -> tuple[bool, list[str]]:
    """
    Intenta consumir un backup code.
    Devuelve (ok, remaining_hashed_codes).
    Si ok=True, el código se elimina de la lista (de un solo uso).
    """
    code_norm  = code.strip().upper().replace(' ', '')
    code_hash  = hashlib.sha256(code_norm.encode()).hexdigest()
    remaining  = list(stored_hashed)
    for i, h in enumerate(remaining):
        if hmac.compare_digest(h, code_hash):   # timing-safe
            remaining.pop(i)
            return True, remaining
    return False, remaining


def serialize_backup_codes(hashed: list[str]) -> str:
    """Convierte la lista de hashes a JSON para guardar en la BD."""
    return json.dumps(hashed)


def deserialize_backup_codes(raw: str) -> list[str]:
    """Parsea el JSON de la BD."""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


# ── Disponibilidad ─────────────────────────────────────────────────────────
def check_availability() -> dict:
    return {
        'pyotp':        PYOTP_OK,
        'fernet':       FERNET_OK,
        'qrcode':       QRCODE_OK,
        'fernet_key':   bool(_FERNET_KEY_RAW),
        'listo':        PYOTP_OK and FERNET_OK and bool(_FERNET_KEY_RAW),
    }
