"""Acceso al volume de datos.

Dos cosas importantes que resuelve este modulo:

1. El volume de Railway se monta al arrancar el contenedor, no durante el
   build, asi que puede estar completamente vacio. `inicializar()` crea todo
   lo que falte y se puede llamar mil veces sin romper nada.

2. Varios handlers escriben los mismos ficheros a la vez. Sin un lock se
   pierden actualizaciones, y si Railway reinicia el contenedor a mitad de
   una escritura queda un JSON truncado que impide volver a arrancar. Por eso
   toda escritura pasa por un lock y va a un fichero temporal que despues se
   mueve encima del bueno, que es una operacion atomica del sistema.
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ajustes import RUTA_DATOS

DIR_CONOCIMIENTO = RUTA_DATOS / "knowledge"
FICHERO_CONFIG = RUTA_DATOS / "config.txt"
FICHERO_AUTORIZADOS = RUTA_DATOS / "autorizados.txt"
FICHERO_BLOQUEOS = RUTA_DATOS / "bloqueos.json"
FICHERO_USO = RUTA_DATOS / "uso.json"
FICHERO_LOG = RUTA_DATOS / "access.log"
# Metadatos de cada documento: tokens, fecha y de donde salio el texto.
# Se guardan aparte para no
# tener que gastar una llamada a count_tokens por documento cada vez que
# alguien escribe /docs.
FICHERO_DOCUMENTOS = RUTA_DATOS / "documentos.json"

# Un lock por fichero. Se crean sobre la marcha porque el event loop no
# existe todavia cuando se importa el modulo.
_locks: dict[str, asyncio.Lock] = {}


def _lock(ruta: Path) -> asyncio.Lock:
    clave = str(ruta)
    if clave not in _locks:
        _locks[clave] = asyncio.Lock()
    return _locks[clave]


# ---------------------------------------------------------------------------
# Escritura y lectura de bajo nivel
# ---------------------------------------------------------------------------


def escribir_atomico(ruta: Path, contenido: str) -> None:
    """Escribe el contenido entero de forma que no pueda quedar a medias.

    Escribe primero en un temporal del mismo directorio (tiene que ser el
    mismo para que el movimiento sea atomico) y luego lo mueve encima. Si el
    proceso muere antes del movimiento, el fichero original sigue intacto.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(dir=str(ruta.parent), suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as fichero:
            fichero.write(contenido)
            fichero.flush()
            os.fsync(fichero.fileno())
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


def leer_texto(ruta: Path, por_defecto: str = "") -> str:
    """Lee un fichero de texto. Si no existe devuelve el valor por defecto."""
    try:
        return ruta.read_text(encoding="utf-8")
    except FileNotFoundError:
        return por_defecto


def leer_json(ruta: Path, por_defecto: dict[str, Any] | None = None) -> dict[str, Any]:
    """Lee un JSON tolerando que no exista o que este corrupto.

    Un JSON truncado por un reinicio a destiempo no puede impedir que el bot
    arranque, asi que en ese caso empezamos de cero en vez de reventar.
    """
    base = dict(por_defecto or {})
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return base
    if not isinstance(datos, dict):
        return base
    base.update(datos)
    return base


async def guardar_json(ruta: Path, datos: dict[str, Any]) -> None:
    """Guarda un JSON de forma atomica y con el lock del fichero cogido."""
    async with _lock(ruta):
        escribir_atomico(ruta, json.dumps(datos, ensure_ascii=False, indent=2))


async def guardar_texto(ruta: Path, contenido: str) -> None:
    async with _lock(ruta):
        escribir_atomico(ruta, contenido)


# ---------------------------------------------------------------------------
# config.txt
# ---------------------------------------------------------------------------
#
# Formato clave=valor, una por linea. Texto plano a proposito: el owner tiene
# que poder abrirlo y entenderlo despues de un /backup.


def leer_config() -> dict[str, str]:
    config: dict[str, str] = {}
    for linea in leer_texto(FICHERO_CONFIG).splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        # Los saltos de linea se guardan escapados para no romper el formato.
        config[clave.strip()] = valor.strip().replace("\\n", "\n")
    return config


def _serializar_config(config: dict[str, str]) -> str:
    cabecera = (
        "# Configuracion de Tu Empleado Digital.\n"
        "# Puedes editar los valores, pero no cambies los nombres de la izquierda.\n"
        "# Los saltos de linea se escriben como \\n.\n\n"
    )
    cuerpo = "".join(
        f"{clave}={str(valor).replace(chr(10), chr(92) + 'n')}\n"
        for clave, valor in sorted(config.items())
    )
    return cabecera + cuerpo


async def guardar_config(config: dict[str, str]) -> None:
    async with _lock(FICHERO_CONFIG):
        escribir_atomico(FICHERO_CONFIG, _serializar_config(config))


async def actualizar_config(**cambios: str) -> dict[str, str]:
    """Lee, aplica los cambios y guarda, todo con el lock cogido.

    Hacerlo en un solo paso evita que dos handlers lean la misma version y
    uno pise los cambios del otro.
    """
    async with _lock(FICHERO_CONFIG):
        config = leer_config()
        config.update({clave: str(valor) for clave, valor in cambios.items()})
        escribir_atomico(FICHERO_CONFIG, _serializar_config(config))
        return config


# ---------------------------------------------------------------------------
# access.log
# ---------------------------------------------------------------------------


async def registrar_evento(evento: str, chat_id: int | str = "", detalle: str = "") -> None:
    """Anade una linea al log de accesos. Nunca falla hacia fuera.

    Que el log no se pueda escribir no es motivo para dejar de responder al
    usuario, asi que los errores se tragan a proposito.
    """
    marca = datetime.now(timezone.utc).isoformat(timespec="seconds")
    linea = f"{marca}\t{evento}\t{chat_id}\t{detalle}".rstrip() + "\n"
    try:
        async with _lock(FICHERO_LOG):
            FICHERO_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(FICHERO_LOG, "a", encoding="utf-8", newline="\n") as fichero:
                fichero.write(linea)
    except OSError:
        pass


def ultimos_eventos(cuantos: int = 20) -> list[str]:
    lineas = leer_texto(FICHERO_LOG).splitlines()
    return lineas[-cuantos:]


# ---------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------
#
# El texto extraido vive en knowledge/<nombre>.txt y los metadatos en
# documentos.json. Los ficheros originales no se guardan nunca.


def ruta_documento(nombre: str) -> Path:
    return DIR_CONOCIMIENTO / f"{nombre}.txt"


def listar_documentos() -> list[str]:
    """Nombres ordenados. El orden es lo que fija el prefijo cacheado."""
    if not DIR_CONOCIMIENTO.exists():
        return []
    return sorted(ruta.stem for ruta in DIR_CONOCIMIENTO.glob("*.txt"))


def metadatos() -> dict[str, Any]:
    return leer_json(FICHERO_DOCUMENTOS, {})


def metadatos_de(nombre: str) -> dict[str, Any]:
    return metadatos().get(nombre, {})


def existe_documento(nombre: str) -> bool:
    return ruta_documento(nombre).is_file()


def leer_documento(nombre: str) -> str:
    return leer_texto(ruta_documento(nombre))


def total_tokens() -> int:
    return sum(int(datos.get("tokens", 0)) for datos in metadatos().values())


async def guardar_documento(nombre: str, texto: str, tokens: int, origen: str) -> bool:
    """Guarda el texto y sus metadatos. Devuelve True si ha sobrescrito.

    Nunca se duplica un documento: si ya existe uno con ese nombre, se
    reemplaza y se avisa a quien lo sube.
    """
    sobrescrito = existe_documento(nombre)
    async with _lock(ruta_documento(nombre)):
        escribir_atomico(ruta_documento(nombre), texto)
    async with _lock(FICHERO_DOCUMENTOS):
        fichas = leer_json(FICHERO_DOCUMENTOS, {})
        fichas[nombre] = {
            "tokens": tokens,
            "caracteres": len(texto),
            "origen": origen,
            "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        escribir_atomico(
            FICHERO_DOCUMENTOS, json.dumps(fichas, ensure_ascii=False, indent=2)
        )
    return sobrescrito


async def borrar_documento(nombre: str) -> bool:
    if not existe_documento(nombre):
        return False
    async with _lock(ruta_documento(nombre)):
        ruta_documento(nombre).unlink(missing_ok=True)
    async with _lock(FICHERO_DOCUMENTOS):
        fichas = leer_json(FICHERO_DOCUMENTOS, {})
        fichas.pop(nombre, None)
        escribir_atomico(
            FICHERO_DOCUMENTOS, json.dumps(fichas, ensure_ascii=False, indent=2)
        )
    return True


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

USO_POR_DEFECTO: dict[str, Any] = {
    "periodo": "",
    "coste_usd": 0.0,
    "peticiones": 0,
    "tokens_entrada": 0,
    "tokens_salida": 0,
    "cache_lectura": 0,
    "cache_escritura": 0,
    "avisado_80": False,
    "avisado_100": False,
}


def inicializar() -> None:
    """Crea la estructura del volume. Idempotente y tolera un volume vacio.

    Sincrono a proposito: se llama una sola vez antes de arrancar el bot, y
    asi puede fallar ruidosamente si el volume no se puede escribir, que es
    justo lo que queremos saber antes de empezar a aceptar mensajes.
    """
    RUTA_DATOS.mkdir(parents=True, exist_ok=True)
    DIR_CONOCIMIENTO.mkdir(parents=True, exist_ok=True)

    if not FICHERO_CONFIG.exists():
        escribir_atomico(FICHERO_CONFIG, _serializar_config({
            "owner_chat_id": "",
            "nombre_empresa": "",
            "mensaje_bienvenida": "",
            "codigo_salt": "",
            "codigo_hash": "",
            "creado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }))

    if not FICHERO_AUTORIZADOS.exists():
        escribir_atomico(FICHERO_AUTORIZADOS, "")

    if not FICHERO_BLOQUEOS.exists():
        escribir_atomico(FICHERO_BLOQUEOS, json.dumps({}, indent=2))

    if not FICHERO_USO.exists():
        escribir_atomico(FICHERO_USO, json.dumps(USO_POR_DEFECTO, indent=2))

    if not FICHERO_DOCUMENTOS.exists():
        escribir_atomico(FICHERO_DOCUMENTOS, json.dumps({}, indent=2))

    if not FICHERO_LOG.exists():
        escribir_atomico(FICHERO_LOG, "")


def resumen_arranque() -> str:
    """Una linea para el log de Railway que dice si el volume traia datos."""
    documentos = len(list(DIR_CONOCIMIENTO.glob("*.txt"))) if DIR_CONOCIMIENTO.exists() else 0
    config = leer_config()
    owner = config.get("owner_chat_id") or "sin asignar"
    return f"Volume en {RUTA_DATOS} | documentos: {documentos} | owner: {owner}"
