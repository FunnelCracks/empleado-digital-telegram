"""La copia de seguridad.

Railway puede perder un volume, y aquí no hay base de datos ni nada fuera de
ese volume. Los ficheros originales se descartan tras extraer el texto, así
que si se pierde hay que volver a subirlo todo.

Un `/backup` manual solo salva a quien se acordó de ejecutarlo antes del
desastre, y un empresario no técnico no se acuerda. Por eso la copia se
manda sola cuando cambia la documentación, como mucho una vez al día.
El ZIP se queda en el chat de Telegram del owner, que es el
único sitio donde va a seguir estando dentro de seis meses.
"""

import asyncio
import io
import logging
import zipfile
from datetime import date

import almacen

log = logging.getLogger("empleado.copia")

# Lo que entra en el ZIP. bloqueos.json se queda fuera a proposito: es
# temporal y restaurarlo solo serviria para revivir bloqueos caducados.
FICHEROS = ("config.txt", "autorizados.txt", "documentos.json", "uso.json", "access.log")


def _construir_sincrono() -> bytes:
    """Comprimir bloquea, así que esto se llama desde un hilo aparte."""
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as zip_:
        for nombre in FICHEROS:
            ruta = almacen.RUTA_DATOS / nombre
            if ruta.is_file():
                zip_.write(ruta, nombre)
        for documento in sorted(almacen.DIR_CONOCIMIENTO.glob("*.txt")):
            zip_.write(documento, f"knowledge/{documento.name}")
        zip_.writestr("LEEME.txt", INSTRUCCIONES_RESTAURACION)
    return memoria.getvalue()


async def construir() -> tuple[str, bytes]:
    """Devuelve (nombre del fichero, contenido)."""
    datos = await asyncio.to_thread(_construir_sincrono)
    nombre = f"copia_empleado_digital_{date.today().isoformat()}.zip"
    return nombre, datos


INSTRUCCIONES_RESTAURACION = """COPIA DE SEGURIDAD DE TU EMPLEADO DIGITAL

Que hay aqui dentro:

  knowledge/         El texto de todos tus documentos, ya extraido.
  config.txt         La configuracion y el codigo de acceso, cifrado.
  autorizados.txt    Quien tiene acceso al bot.
  documentos.json    Cuanto ocupa cada documento.
  uso.json           Lo que llevas gastado este mes.
  access.log         El registro de accesos.

Como recuperarte si pierdes tus documentos:

  La forma sencilla es volver a subir tus ficheros originales al bot, uno a
  uno, como hiciste la primera vez. Los tienes en tu ordenador y el bot los
  vuelve a leer sin problema.

  Si no los tienes, dentro de la carpeta knowledge estan los textos que el
  bot habia extraido. Cada .txt se puede volver a subir tal cual al bot.

  Si has perdido el codigo de acceso, no hace falta este fichero: genera uno
  nuevo con el comando /codigo y repartelo.

Este ZIP no contiene tus ficheros originales, solo el texto que el bot saco
de ellos, porque los originales se borran despues de leerlos.
"""


# ---------------------------------------------------------------------------
# Cuándo toca mandarla sola
# ---------------------------------------------------------------------------


def toca_copia_automatica() -> bool:
    """Como mucho una al día, y solo si hay algo que copiar."""
    if not almacen.listar_documentos():
        return False
    return almacen.leer_config().get("ultima_copia", "") != date.today().isoformat()


async def marcar_copia_hecha() -> None:
    await almacen.actualizar_config(ultima_copia=date.today().isoformat())
