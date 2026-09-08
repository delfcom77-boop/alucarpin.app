import base64
import hashlib
import hmac
import secrets
import time
import unicodedata
from typing import Optional

ITERACIONES = 210000
ADMIN_SALT = "237b07afc6b78e4459b4350601717f70"
ADMIN_HASH = "536a79b9c2cf97ae7e78fd8bebaac1012eaaf597cce0d3f773342a432fe191e5"


def usuario_normalizado(nombre):
    texto = unicodedata.normalize("NFKD", nombre or "")
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return "".join(caracter.lower() for caracter in texto if caracter.isalnum()) or "usuario"


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERACIONES).hex()
    return salt, digest


def password_valida(password, salt, digest):
    _, calculado = hash_password(password, salt)
    return hmac.compare_digest(calculado, digest)


def inicializar_usuarios(db):
    es_postgres = hasattr(db, "db")
    if not es_postgres:
        db.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL UNIQUE,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL,
                ayudante_id INTEGER UNIQUE,
                activo INTEGER NOT NULL DEFAULT 1,
                creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
    consulta_admin = (
        "INSERT INTO usuarios (usuario, password_salt, password_hash, rol) "
        "VALUES (?, ?, ?, 'administrador') ON CONFLICT (usuario) DO NOTHING"
        if es_postgres
        else "INSERT OR IGNORE INTO usuarios (usuario, password_salt, password_hash, rol) VALUES (?, ?, ?, 'administrador')"
    )
    db.execute(consulta_admin, ("administrador", ADMIN_SALT, ADMIN_HASH))
    ayudantes = db.execute("SELECT id, nombre FROM ayudantes ORDER BY id").fetchall()
    for ayudante in ayudantes:
        if isinstance(ayudante, dict):
            ayudante_id, nombre = ayudante["id"], ayudante["nombre"]
        else:
            ayudante_id, nombre = ayudante
        usuario = usuario_normalizado(nombre)
        salt, digest = hash_password("Cambiar123!")
        consulta_ayudante = (
            "INSERT INTO usuarios (usuario, password_salt, password_hash, rol, ayudante_id) "
            "VALUES (?, ?, ?, 'ayudante', ?) "
            "ON CONFLICT (ayudante_id) DO NOTHING"
            if es_postgres
            else "INSERT OR IGNORE INTO usuarios (usuario, password_salt, password_hash, rol, ayudante_id) VALUES (?, ?, ?, 'ayudante', ?)"
        )
        db.execute(consulta_ayudante, (usuario, salt, digest, ayudante_id))
    db.commit()


def crear_token(usuario_id, secreto):
    caduca = int(time.time()) + 8 * 60 * 60
    contenido = f"{usuario_id}:{caduca}".encode()
    firma = hmac.new(secreto.encode(), contenido, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(contenido + b":" + firma.encode()).decode()


def usuario_desde_token(token, secreto):
    try:
        contenido, firma = base64.urlsafe_b64decode(token.encode()).rsplit(b":", 1)
        esperado = hmac.new(secreto.encode(), contenido, hashlib.sha256).hexdigest().encode()
        if not hmac.compare_digest(firma, esperado):
            return None
        usuario_id, caduca = contenido.decode().split(":")
        if int(caduca) < int(time.time()):
            return None
        return int(usuario_id)
    except (ValueError, TypeError, base64.binascii.Error):
        return None
