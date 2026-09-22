"""Quien es el owner, quien esta autorizado y el codigo de acceso.

El codigo nunca se guarda en claro. Se guarda un salt aleatorio y el
SHA-256 de salt mas codigo, los dos en config.txt. Si alguien consigue leer
el fichero no puede deducir el codigo, y si el owner lo pierde se genera
uno nuevo con /codigo y el anterior deja de valer.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timezone

import almacen
from ajustes import ALFABETO_CODIGO, LONGITUD_CODIGO, OWNER_CHAT_ID


# ---------------------------------------------------------------------------
# Codigo de acceso
# ---------------------------------------------------------------------------


def generar_codigo() -> str:
    """Genera un codigo legible por telefono, sin caracteres ambiguos."""
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(LONGITUD_CODIGO))


def normalizar_codigo(texto: str) -> str:
    """Lo que teclea el usuario: quitamos espacios y guiones y subimos a mayusculas."""
    return "".join(caracter for caracter in texto.strip().upper() if caracter.isalnum())


def hashear_codigo(salt: str, codigo: str) -> str:
    return hashlib.sha256((salt + codigo).encode("utf-8")).hexdigest()


async def establecer_codigo_nuevo() -> str:
    """Genera un codigo, guarda su hash e invalida el anterior.

    Devuelve el codigo en claro. Es la unica vez que existe en memoria, asi
    que quien llame a esto tiene que ensenarlo al owner en ese momento.
    """
    codigo = generar_codigo()
    salt = secrets.token_hex(16)
    await almacen.actualizar_config(
        codigo_salt=salt,
        codigo_hash=hashear_codigo(salt, codigo),
        codigo_creado=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return codigo


def codigo_correcto(codigo: str) -> bool:
    """Compara en tiempo constante para no filtrar informacion por el reloj."""
    config = almacen.leer_config()
    salt = config.get("codigo_salt", "")
    esperado = config.get("codigo_hash", "")
    if not salt or not esperado:
        return False
    return hmac.compare_digest(hashear_codigo(salt, normalizar_codigo(codigo)), esperado)


# ---------------------------------------------------------------------------
# Owner
# ---------------------------------------------------------------------------


def owner_id() -> int | None:
    """El owner fijado por variable de entorno manda sobre el de config.txt."""
    if OWNER_CHAT_ID:
        try:
            return int(OWNER_CHAT_ID)
        except ValueError:
            return None
    guardado = almacen.leer_config().get("owner_chat_id", "")
    try:
        return int(guardado) if guardado else None
    except ValueError:
        return None


def hay_owner() -> bool:
    return owner_id() is not None


def es_owner(chat_id: int) -> bool:
    return owner_id() == chat_id


def registro_automatico_activo() -> bool:
    """Si OWNER_CHAT_ID viene relleno, nadie puede autoproclamarse owner."""
    return not OWNER_CHAT_ID


async def registrar_owner(chat_id: int, nombre: str = "") -> bool:
    """Registra al primer usuario como owner. Devuelve False si ya habia uno."""
    if hay_owner():
        return False
    await almacen.actualizar_config(
        owner_chat_id=str(chat_id),
        owner_nombre=nombre,
        owner_desde=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    await almacen.registrar_evento("alta_owner", chat_id, nombre)
    return True


# ---------------------------------------------------------------------------
# Autorizados
# ---------------------------------------------------------------------------
#
# Formato de autorizados.txt: chat_id|nombre|fecha, una linea por persona.


def autorizados() -> dict[int, dict[str, str]]:
    gente: dict[int, dict[str, str]] = {}
    for linea in almacen.leer_texto(almacen.FICHERO_AUTORIZADOS).splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        partes = linea.split("|")
        try:
            chat_id = int(partes[0])
        except (ValueError, IndexError):
            continue
        gente[chat_id] = {
            "nombre": partes[1] if len(partes) > 1 else "",
            "desde": partes[2] if len(partes) > 2 else "",
        }
    return gente


def esta_autorizado(chat_id: int) -> bool:
    return es_owner(chat_id) or chat_id in autorizados()


def _serializar_autorizados(gente: dict[int, dict[str, str]]) -> str:
    return "".join(
        f"{chat_id}|{datos.get('nombre', '')}|{datos.get('desde', '')}\n"
        for chat_id, datos in sorted(gente.items())
    )


async def autorizar(chat_id: int, nombre: str = "") -> None:
    gente = autorizados()
    gente[chat_id] = {
        "nombre": nombre,
        "desde": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    await almacen.guardar_texto(almacen.FICHERO_AUTORIZADOS, _serializar_autorizados(gente))
    await almacen.registrar_evento("acceso_concedido", chat_id, nombre)


async def revocar(chat_id: int) -> bool:
    gente = autorizados()
    if chat_id not in gente:
        return False
    nombre = gente.pop(chat_id).get("nombre", "")
    await almacen.guardar_texto(almacen.FICHERO_AUTORIZADOS, _serializar_autorizados(gente))
    await almacen.registrar_evento("acceso_revocado", chat_id, nombre)
    return True
