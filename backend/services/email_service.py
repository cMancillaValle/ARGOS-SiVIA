"""
backend/services/email_service.py
──────────────────────────────────
Envío de emails transaccionales para ARGOS - SiViA.

Configuración via variables de entorno:
    SMTP_HOST      → smtp.gmail.com  (default)
    SMTP_PORT      → 587             (default, TLS STARTTLS)
    SMTP_USER      → @gmail.com
    SMTP_PASS      → contraseña de aplicación (App Password)
    SMTP_FROM      → @gmail.com   (default = SMTP_USER)
    ARGOS_DEV_MODE → 1              (si=1, no envía email, devuelve código en respuesta)
"""

from __future__ import annotations
import os
import secrets
import string
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from threading import Lock
from typing import Optional

#import sib_api_v3_sdk
#from sib_api_v3_sdk.rest import ApiException

# ── Configuración SMTP desde ENV ───────────────────────────────────────────
SMTP_HOST    = os.environ.get('SMTP_HOST',  'smtp.gmail.com')
SMTP_PORT    = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER    = os.environ.get('SMTP_USER',  '')
SMTP_PASS    = os.environ.get('SMTP_PASS',  '')
SMTP_FROM    = os.environ.get('SMTP_FROM',  SMTP_USER)
DEV_MODE     = os.environ.get('ARGOS_DEV_MODE', '0') == '1'

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
USE_BREVO = bool(BREVO_API_KEY)

SMTP_CONFIGURED = bool(SMTP_USER and SMTP_PASS)

# ── Almacenamiento en memoria de códigos pendientes ────────────────────────
# Estructura: { "namespace:identifier": {"code": str, "expires": datetime, "data": dict} }
_codes: dict[str, dict] = {}
_codes_lock = Lock()

CODE_TTL_MINUTES = 10
CODE_LENGTH      = 6


# ── Generador de código ────────────────────────────────────────────────────
def _gen_code(length: int = CODE_LENGTH) -> str:
    """Genera un código numérico de `length` dígitos."""
    return ''.join(secrets.choice(string.digits) for _ in range(length))


# ── Almacenamiento y validación de códigos ─────────────────────────────────
def store_code(namespace: str, identifier: str, extra_data: Optional[dict] = None) -> str:
    """
    Genera y almacena un código temporal.
    Devuelve el código en texto plano (para enviarlo por email).
    """
    code    = _gen_code()
    key     = f'{namespace}:{identifier}'
    expires = datetime.utcnow() + timedelta(minutes=CODE_TTL_MINUTES)
    with _codes_lock:
        _codes[key] = {'code': code, 'expires': expires, 'data': extra_data or {}}
    return code


def validate_code(namespace: str, identifier: str, code: str) -> tuple[bool, dict]:
    """
    Valida el código. Si es correcto lo elimina (de un solo uso).
    Devuelve (ok, extra_data).
    """
    key = f'{namespace}:{identifier}'
    with _codes_lock:
        entry = _codes.get(key)
        if not entry:
            return False, {}
        if datetime.utcnow() > entry['expires']:
            _codes.pop(key, None)
            return False, {}
        if entry['code'] != str(code).strip():
            return False, {}
        data = entry.get('data', {})
        _codes.pop(key, None)
        return True, data


def peek_code(namespace: str, identifier: str) -> Optional[str]:
    """Solo para modo desarrollo: devuelve el código activo sin consumirlo."""
    key = f'{namespace}:{identifier}'
    with _codes_lock:
        entry = _codes.get(key)
        if entry and datetime.utcnow() <= entry['expires']:
            return entry['code']
    return None


# ── Envío de email ─────────────────────────────────────────────────────────
_EMAIL_CSS = """
body { font-family: 'Segoe UI', Arial, sans-serif; background: #060A0F; margin: 0; padding: 0; }
.wrap { max-width: 520px; margin: 40px auto; background: #0D1520; border: 1px solid rgba(232,0,29,0.2);
        border-radius: 16px; overflow: hidden; }
.header { background: linear-gradient(135deg, #9C0012, #E8001D); padding: 28px 32px; }
.logo  { font-size: 22px; font-weight: 800; letter-spacing: 4px; color: #fff; }
.sub   { font-size: 11px; color: rgba(255,255,255,0.7); letter-spacing: 2px; margin-top: 4px; }
.body  { padding: 32px; color: #E2EAF4; }
.code-box { background: #111E2E; border: 1px solid rgba(232,0,29,0.3); border-radius: 12px;
            text-align: center; padding: 20px; margin: 24px 0; }
.code  { font-size: 36px; font-weight: 900; letter-spacing: 12px; color: #E8001D; font-family: monospace; }
.note  { font-size: 12px; color: #7A93B2; margin-top: 8px; }
.footer { padding: 16px 32px; border-top: 1px solid rgba(255,255,255,0.05);
          font-size: 10px; color: #3A5070; text-align: center; letter-spacing: 1px; }
"""


def _build_email_html(subject: str, message: str, code: Optional[str] = None) -> str:
    code_block = ''
    if code:
        code_block = f"""
        <div class="code-box">
            <div class="code">{code}</div>
            <div class="note">Válido por {CODE_TTL_MINUTES} minutos · No compartas este código</div>
        </div>"""
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>{_EMAIL_CSS}</style></head>
<body><div class="wrap">
  <div class="header"><div class="logo">ARGOS</div><div class="sub">SiViA · Sistema de Visión Artificial · TransMilenio</div></div>
  <div class="body">
    <p style="font-size:15px;font-weight:600;margin:0 0 12px">{subject}</p>
    <p style="font-size:13px;color:#7A93B2;line-height:1.6;margin:0">{message}</p>
    {code_block}
    <p style="font-size:12px;color:#3A5070;margin-top:16px">Si no solicitaste esto, ignora este correo.</p>
  </div>
  <div class="footer">ARGOS SiViA - TransMilenio S.A. · {datetime.now().year}</div>
</div></body></html>"""


def send_email(to_email: str, subject: str, message: str, code: Optional[str] = None) -> dict:
    """
    Envía un email HTML. Si SMTP no está configurado o DEV_MODE=1,
    devuelve {'dev': True, 'code': code} para mostrar en la UI.
    """
    if not SMTP_CONFIGURED or DEV_MODE:
        return {
            'enviado': False,
            'dev': True,
            'mensaje': 'SMTP no configurado. Código disponible en respuesta (modo desarrollo).',
            'code': code,
        }

    html = _build_email_html(subject, message, code)
    msg  = MIMEMultipart('alternative')
    msg['Subject'] = f'[ARGOS SiViA] {subject}'
    msg['From']    = SMTP_FROM
    msg['To']      = to_email
    msg.attach(MIMEText(message, 'plain', 'utf-8'))
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        return {'enviado': True, 'dev': False}
    except Exception as e:
        return {'enviado': False, 'dev': False, 'error': str(e)}

# ── Funciones de alto nivel para cada caso de uso ─────────────────────────────
def enviar_codigo_cambio_email(user_id: int, email_destino: str,
                               nuevo_email: Optional[str] = None) -> dict:
    """Genera y envía código para verificar cambio de email."""
    ns   = 'email_cambio' if nuevo_email is None else 'email_nuevo'
    code = store_code(ns, str(user_id), {'nuevo_email': nuevo_email})
    subj = 'Verificación de cambio de email'
    msg  = ('Recibimos una solicitud para cambiar el email de tu cuenta ARGOS SiViA. '
            'Ingresa el siguiente código para confirmar:')
    return send_email(email_destino, subj, msg, code)


def enviar_codigo_reset_password(email: str, username: str) -> dict:
    """Genera y envía código para restablecer contraseña."""
    code = store_code('reset_pass', username)
    subj = 'Restablecer contraseña'
    msg  = (f'Hola {username}, recibimos una solicitud para restablecer la contraseña '
            'de tu cuenta ARGOS SiViA. Usa el siguiente código:')
    return send_email(email, subj, msg, code)


def enviar_notificacion_2fa_activado(email: str, username: str) -> dict:
    """Aviso de que se activó el 2FA."""
    subj = 'Autenticación 2FA activada'
    msg  = (f'Hola {username}, la autenticación de dos factores ha sido activada '
            'en tu cuenta ARGOS SiViA. Si no fuiste tú, contacta al administrador inmediatamente.')
    return send_email(email, subj, msg)
