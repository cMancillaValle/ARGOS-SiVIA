from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

def get_limiter_key():
    """
    By default uses the remote address. 
    If a JSON body with 'usuario' or 'username' exists, 
    combines remote address with the username to prevent targeted proxy bypasses.
    """
    ip = get_remote_address()
    if request.is_json:
        data = request.get_json(silent=True) or {}
        user = data.get('usuario') or data.get('username') or data.get('identificador')
        if user:
            return f"{ip}-{user}"
    return ip

limiter = Limiter(
    key_func=get_limiter_key,
    default_limits=[],
    storage_uri="memory://"
)
