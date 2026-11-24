"""Login de un solo usuario. El usuario y la clave salen de las variables de Railway: el repo es público."""
import base64
import hashlib
import hmac
import os
import secrets
import time
from fastapi import HTTPException, Request

COOKIE = 'sesion'
DURACION = 12 * 3600

# Sin SECRET_KEY la sesión se firma con una clave al azar: anda, pero cada reinicio desloguea.
CLAVE_DE_FIRMA = (os.environ.get('SECRET_KEY') or secrets.token_hex(32)).encode()


def credenciales_configuradas():
    return bool(os.environ.get('APP_USUARIO') and os.environ.get('APP_CLAVE'))


def credenciales_validas(usuario, clave):
    if not credenciales_configuradas():
        return False
    ok_usuario = hmac.compare_digest(usuario.encode(), os.environ['APP_USUARIO'].encode())
    ok_clave = hmac.compare_digest(clave.encode(), os.environ['APP_CLAVE'].encode())
    return ok_usuario and ok_clave


def firmar(texto):
    return hmac.new(CLAVE_DE_FIRMA, texto.encode(), hashlib.sha256).hexdigest()


def crear_token(usuario):
    cuerpo = base64.urlsafe_b64encode(f'{usuario}|{int(time.time()) + DURACION}'.encode()).decode()
    return f'{cuerpo}.{firmar(cuerpo)}'


def usuario_del_token(token):
    try:
        cuerpo, firma = token.rsplit('.', 1)
        if not hmac.compare_digest(firma, firmar(cuerpo)):
            return None
        usuario, vence = base64.urlsafe_b64decode(cuerpo).decode().rsplit('|', 1)
        return usuario if int(vence) > time.time() else None
    except (ValueError, UnicodeDecodeError):
        return None


def usuario_actual(request: Request):
    if not (usuario := usuario_del_token(request.cookies.get(COOKIE, ''))):
        raise HTTPException(401, 'Iniciá sesión.')
    return usuario
