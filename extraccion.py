"""Sacar texto de lo que sube el owner: PDF, Word, texto plano, fotos y voz.

Los ficheros originales no se guardan nunca. Se extrae el texto y se tira el
binario. Es una decision de seguridad: lo que no se guarda no se filtra.

Todo lo que bloquea (pypdf, python-docx) se ejecuta fuera del hilo del bot
con `asyncio.to_thread`, porque si no el bot se congela para todos los
usuarios mientras se procesa un PDF grande.
"""

import asyncio
import csv
import io
import logging
import re
import unicodedata
from dataclasses import dataclass, field

import claude_api

log = logging.getLogger("empleado.extraccion")

EXTENSIONES_TEXTO = {".txt", ".md", ".csv", ".log", ".json"}
EXTENSION_PDF = ".pdf"
EXTENSION_DOCX = ".docx"
EXTENSIONES_ACEPTADAS = EXTENSIONES_TEXTO | {EXTENSION_PDF, EXTENSION_DOCX}

# Si un PDF da menos de esto por página, damos por hecho que es un escaneo y
# que el texto que trae, si trae alguno, es basura de la capa OCR.
MINIMO_CARACTERES_POR_PAGINA = 100

# A partir de aquí, mandar el PDF entero a Claude para que lo lea empieza a
# costar dinero de verdad, así que avisamos antes.
PAGINAS_AVISO_ESCANEADO = 100


class ErrorExtraccion(Exception):
    """Algo que el usuario puede entender y corregir."""


@dataclass
class Documento:
    texto: str
    origen: str  # pypdf, claude-pdf, docx, plano, claude-imagen, whisper
    paginas: int = 0
    uso: object | None = None  # objeto usage de Anthropic, si hubo llamada
    avisos: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Nombres de fichero
# ---------------------------------------------------------------------------


def sanear_nombre(nombre: str) -> str:
    """Convierte el nombre en algo seguro para el sistema de ficheros.

    Sin acentos, sin espacios, sin barras y sin puntos de ruta. Esto además
    cierra la puerta a que alguien suba un fichero llamado ../../config.txt.
    """
    base = nombre.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." in base:
        base = base.rsplit(".", 1)[0]
    # Quitar tildes dejando la letra base. La ñ se convierte en n.
    sin_tildes = unicodedata.normalize("NFKD", base)
    sin_tildes = "".join(letra for letra in sin_tildes if not unicodedata.combining(letra))
    limpio = re.sub(r"[^A-Za-z0-9]+", "_", sin_tildes).strip("_").lower()
    limpio = re.sub(r"_+", "_", limpio)
    return (limpio or "documento")[:40]


def extension_de(nombre: str) -> str:
    return ("." + nombre.rsplit(".", 1)[1].lower()) if "." in nombre else ""


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def _leer_pdf_sincrono(datos: bytes) -> tuple[str, int]:
    """Extrae texto con pypdf. Bloqueante, se llama desde un hilo aparte."""
    from pypdf import PdfReader

    try:
        lector = PdfReader(io.BytesIO(datos))
    except Exception as error:  # PDF corrupto o protegido
        raise ErrorExtraccion("no he podido abrir el PDF") from error

    if getattr(lector, "is_encrypted", False):
        try:
            lector.decrypt("")
        except Exception:
            raise ErrorExtraccion("el PDF está protegido con contraseña")

    partes = []
    for pagina in lector.pages:
        try:
            partes.append(pagina.extract_text() or "")
        except Exception:
            partes.append("")
    return "\n\n".join(partes).strip(), len(lector.pages)


async def extraer_pdf(datos: bytes) -> Documento:
    """pypdf primero. Si no sale texto, es un escaneo y lo lee Claude."""
    texto, paginas = await asyncio.to_thread(_leer_pdf_sincrono, datos)

    suficiente = len(texto) >= MINIMO_CARACTERES_POR_PAGINA * max(paginas, 1)
    if suficiente:
        return Documento(texto=texto, origen="pypdf", paginas=paginas)

    # Es un escaneado. Lo lee Claude, que cuesta dinero, así que avisamos.
    avisos = []
    if paginas > PAGINAS_AVISO_ESCANEADO:
        avisos.append(
            f"son {paginas} páginas escaneadas y leerlas cuesta bastante"
        )
    log.info("PDF escaneado de %s paginas, lo lee Claude", paginas)
    texto_claude, uso = await claude_api.leer_pdf_escaneado(datos)
    if not texto_claude:
        raise ErrorExtraccion("no he conseguido leer nada dentro de ese PDF")
    return Documento(
        texto=texto_claude, origen="claude-pdf", paginas=paginas, uso=uso, avisos=avisos
    )


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------


def _leer_docx_sincrono(datos: bytes) -> str:
    """Párrafos y tablas. Las tablas se aplanan a texto separado por tabulador."""
    from docx import Document as DocumentoWord

    try:
        documento = DocumentoWord(io.BytesIO(datos))
    except Exception as error:
        raise ErrorExtraccion("no he podido abrir ese Word") from error

    partes = [parrafo.text for parrafo in documento.paragraphs if parrafo.text.strip()]
    for tabla in documento.tables:
        for fila in tabla.rows:
            celdas = [celda.text.strip() for celda in fila.cells]
            if any(celdas):
                partes.append("\t".join(celdas))
    return "\n".join(partes).strip()


async def extraer_docx(datos: bytes) -> Documento:
    texto = await asyncio.to_thread(_leer_docx_sincrono, datos)
    if not texto:
        raise ErrorExtraccion("ese Word no tiene texto dentro")
    return Documento(texto=texto, origen="docx")


# ---------------------------------------------------------------------------
# Texto plano y CSV
# ---------------------------------------------------------------------------


def decodificar(datos: bytes) -> str:
    """UTF-8 primero. Si falla, cp1252, que es lo que suelta Excel en España."""
    for codificacion in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return datos.decode("utf-8", errors="replace")


def extraer_plano(datos: bytes, nombre: str = "") -> Documento:
    texto = decodificar(datos).strip()
    if not texto:
        raise ErrorExtraccion("ese fichero está vacío")
    if extension_de(nombre) == ".csv":
        texto = _csv_legible(texto)
    return Documento(texto=texto, origen="plano")


def _csv_legible(texto: str) -> str:
    """Normaliza el separador a tabulador para que Claude lea mejor la tabla."""
    muestra = texto[:4096]
    try:
        dialecto = csv.Sniffer().sniff(muestra, delimiters=",;\t|")
    except csv.Error:
        return texto
    filas = csv.reader(io.StringIO(texto), dialecto)
    return "\n".join("\t".join(campo.strip() for campo in fila) for fila in filas)


# ---------------------------------------------------------------------------
# Fotos y voz
# ---------------------------------------------------------------------------


async def extraer_imagen(datos: bytes, tipo_mime: str = "image/jpeg") -> Documento:
    texto, uso = await claude_api.leer_imagen(datos, tipo_mime)
    if not texto:
        raise ErrorExtraccion("no he visto texto legible en esa foto")
    return Documento(texto=texto, origen="claude-imagen", uso=uso)


async def transcribir(datos: bytes, nombre: str = "nota.ogg") -> Documento:
    texto = await claude_api.transcribir_voz(datos, nombre)
    if not texto:
        raise ErrorExtraccion("no he entendido nada en esa nota de voz")
    return Documento(texto=texto, origen="whisper")


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


async def extraer_fichero(nombre: str, datos: bytes) -> Documento:
    """Elige el método según la extensión. Lanza ErrorExtraccion si no puede."""
    extension = extension_de(nombre)
    if extension == EXTENSION_PDF:
        return await extraer_pdf(datos)
    if extension == EXTENSION_DOCX:
        return await extraer_docx(datos)
    if extension in EXTENSIONES_TEXTO:
        return extraer_plano(datos, nombre)
    if extension == ".doc":
        raise ErrorExtraccion(
            "ese Word es del formato antiguo. Ábrelo y guárdalo como .docx"
        )
    raise ErrorExtraccion("no sé leer ese tipo de fichero")
