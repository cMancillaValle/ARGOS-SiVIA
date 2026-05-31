import re
import urllib.parse
from flask import jsonify

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

def validate_email(email: str) -> bool:
    """Verifica que el correo tenga un formato estándar usando RegExp."""
    if not email:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))

def validate_password(password: str) -> tuple[bool, str]:
    """Mínimo 8 caracteres, al menos 1 mayúscula, 1 número y 1 símbolo."""
    if not password or len(password) < 8:
        return False, "mínimo 8 caracteres"
    if not any(c.isupper() for c in password):
        return False, "al menos una mayúscula"
    if not any(c.isdigit() for c in password):
        return False, "al menos un número"
    if not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?\\" for c in password):
        return False, "al menos un símbolo"
    return True, ""

def validate_avatar(avatar: str) -> bool:
    """Asegura que de haber un avatar, sea URL (http) o URI Base64 válida y no exceda límites burdos."""
    if not avatar:
        return True # Es opcional

    if len(avatar) > 200000: # ~200kb previniendo payloads
        return False
        
    # Verificar prefix de URl / base64
    if avatar.startswith(('http://', 'https://')):
        return True
    
    if avatar.startswith('data:image/'):
        return True
        
    return False

def format_error(msg="Datos no válidos"):
    return jsonify({'error': msg}), 400
