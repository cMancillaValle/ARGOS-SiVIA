"""
utils/limiter.py  (migrado a slowapi — sin Flask-Limiter)
────────────────────────────────────────────────────────────
Rate limiter para FastAPI usando slowapi.

Uso en routers:
    from utils.limiter import limiter
    @router.post("/login")
    @limiter.limit("5/minute")
    async def login(request: Request, ...):
        ...

El limitador se registra en main.py:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request


def _get_limiter_key(request: Request) -> str:
    """
    Clave de limitación: IP del cliente.
    Si el body JSON contiene 'usuario', 'username' o 'identificador',
    combina IP + campo para prevenir bypass por proxy con distintas IPs.
    """
    ip = get_remote_address(request)
    try:
        body = request._json if hasattr(request, '_json') else None
        if body and isinstance(body, dict):
            user = (
                body.get('usuario')
                or body.get('username')
                or body.get('identificador')
            )
            if user:
                return f"{ip}-{user}"
    except Exception:
        pass
    return ip


limiter = Limiter(key_func=get_remote_address)
