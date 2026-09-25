"""Leer páginas web que el owner pega en el chat.

Solo las páginas que él elige, una por dirección. No se sigue ningún enlace:
una tienda o una web corporativa tiene cientos de páginas repetidas en
varios idiomas, y rastrearlas llenaría la documentación de basura y
dispararía lo que cuesta cada pregunta.

Cuando una web no se deja leer (es privada, bloquea a los robots o monta el
contenido con JavaScript), no se intenta esquivar. Se explica qué ha pasado
y se ofrece el camino que funciona siempre: guardar la página como PDF.
"""

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin, urlsplit

import httpx

import extraccion

# Tope de direcciones por mensaje. Cada una cuesta un resumen, y diez ya es
# mucho leer de una sentada.
MAX_DIRECCIONES = 10

# Una página normal pesa bastante menos. Esto corta las descargas absurdas
# sin dejar fuera ninguna página de verdad.
MAX_BYTES_PAGINA = 8 * 1024 * 1024
MAX_REDIRECCIONES = 5
TIEMPO_MAXIMO = 20.0

# Por debajo de esto, lo que ha bajado no es la página: es el esqueleto que
# luego rellena el navegador con JavaScript, o un aviso de algún tipo.
MINIMO_CARACTERES = 200

# Se identifica con nombre propio. No se hace pasar por un navegador.
CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; EmpleadoDigital/1.0; "
        "+https://github.com/FunnelCracks/empleado-digital-telegram)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.5",
}

# Señales de las páginas de "comprobando que eres humano". Algunas llegan con
# un 200, así que no basta con mirar el código de respuesta.
SENALES_DE_BLOQUEO = (
    "just a moment",
    "cf-browser-verification",
    "cf-challenge",
    "challenge-platform",
    "attention required",
    "verify you are human",
    "are you a robot",
    "captcha",
    "comprobando que eres humano",
    "access denied",
)

_DIRECCION = re.compile(
    r"^(?:https?://)?"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}"
    r"(?::\d{1,5})?"
    r"(?:[/?#]\S*)?$",
    re.IGNORECASE,
)


class WebNoLeida(Exception):
    """La página no se ha podido leer. `motivo` elige el mensaje."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo  # privada, bloqueada, no_existe, no_responde,
        # sin_texto, formato, demasiado_grande, interna


@dataclass
class PaginaLeida:
    direccion: str  # la final, después de las redirecciones
    titulo: str
    documento: extraccion.Documento


# ---------------------------------------------------------------------------
# Reconocer un mensaje que solo trae direcciones
# ---------------------------------------------------------------------------


def direcciones_del_mensaje(texto: str) -> list[str]:
    """Devuelve las direcciones si el mensaje no trae nada más.

    Si hay una sola palabra que no sea una dirección, el mensaje es una
    pregunta ("¿qué pone en miweb.es sobre envíos?") y se deja pasar. Así no
    hace falta ningún comando: pegar direcciones es pedir que se lean.
    """
    trozos = texto.split()
    if not trozos or not all(_DIRECCION.match(trozo) for trozo in trozos):
        return []
    # Sin repetir y en el orden en que llegaron.
    vistas: list[str] = []
    for trozo in trozos:
        direccion = normalizar(trozo)
        if direccion not in vistas:
            vistas.append(direccion)
    return vistas


def normalizar(direccion: str) -> str:
    direccion = direccion.strip().rstrip(".,;")
    if not re.match(r"^https?://", direccion, re.IGNORECASE):
        direccion = "https://" + direccion
    return direccion


def nombre_para(direccion: str) -> str:
    """Nombre del documento: web_ + dominio sin www ni extensión + ruta.

    Si se vuelve a pegar la misma dirección, sale el mismo nombre y el
    documento se actualiza en vez de duplicarse.
    """
    partes = urlsplit(direccion)
    dominio = (partes.hostname or "").lower().removeprefix("www.")
    dominio = dominio.rsplit(".", 1)[0] if "." in dominio else dominio
    ruta = partes.path.strip("/")
    base = f"web {dominio} {ruta}".replace(".", " ").replace("/", " ")
    return extraccion.sanear_nombre(base)


# ---------------------------------------------------------------------------
# Que el bot no mire dentro de la red del servidor
# ---------------------------------------------------------------------------
#
# El bot vive en Railway. Sin esta comprobación, una dirección como
# http://10.0.0.5 o http://localhost le haría mirar dentro de la red privada
# del servidor. Se comprueba el destino de cada salto, no solo el primero,
# porque una web pública podría redirigir a una dirección interna.


def es_direccion_interna(ip: str) -> bool:
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return not direccion.is_global


async def comprobar_destino(direccion: str) -> None:
    partes = urlsplit(direccion)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise WebNoLeida("no_existe")
    try:
        resueltas = await asyncio.get_running_loop().getaddrinfo(
            partes.hostname, partes.port or (443 if partes.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        raise WebNoLeida("no_existe")
    if not resueltas or any(es_direccion_interna(r[4][0]) for r in resueltas):
        raise WebNoLeida("interna")


# ---------------------------------------------------------------------------
# Descargar
# ---------------------------------------------------------------------------


def motivo_por_codigo(codigo: int) -> str | None:
    if codigo < 400:
        return None
    if codigo == 401:
        return "privada"
    if codigo in (403, 429, 503):
        # 403 lo usan casi todas las protecciones contra robots. Si fuera
        # una página privada de verdad, pedir el PDF sirve igual.
        return "bloqueada"
    if codigo in (404, 410):
        return "no_existe"
    return "no_responde"


async def descargar(
    direccion: str, transporte: httpx.AsyncBaseTransport | None = None
) -> tuple[bytes, str, str]:
    """Devuelve (contenido, tipo, dirección final).

    Las redirecciones se siguen a mano para comprobar el destino de cada una.
    `transporte` solo lo usan las pruebas, para no salir a internet.
    """
    async with httpx.AsyncClient(
        headers=CABECERAS,
        timeout=TIEMPO_MAXIMO,
        follow_redirects=False,
        transport=transporte,
    ) as sesion:
        for _salto in range(MAX_REDIRECCIONES + 1):
            if transporte is None:
                await comprobar_destino(direccion)
            try:
                async with sesion.stream("GET", direccion) as respuesta:
                    if respuesta.is_redirect and "location" in respuesta.headers:
                        direccion = urljoin(direccion, respuesta.headers["location"])
                        continue

                    motivo = motivo_por_codigo(respuesta.status_code)
                    if motivo:
                        raise WebNoLeida(motivo)

                    contenido = bytearray()
                    async for trozo in respuesta.aiter_bytes():
                        contenido.extend(trozo)
                        if len(contenido) > MAX_BYTES_PAGINA:
                            raise WebNoLeida("demasiado_grande")
                    tipo = respuesta.headers.get("content-type", "").lower()
                    return bytes(contenido), tipo, direccion
            except httpx.TimeoutException:
                raise WebNoLeida("no_responde")
            except httpx.HTTPError:
                raise WebNoLeida("no_responde")
    # Demasiadas redirecciones seguidas: la web está mal configurada.
    raise WebNoLeida("no_responde")


# ---------------------------------------------------------------------------
# Sacar el texto
# ---------------------------------------------------------------------------


def titulo_de(html: str) -> str:
    encontrado = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not encontrado:
        return ""
    return re.sub(r"\s+", " ", unescape(encontrado.group(1))).strip()[:120]


def parece_bloqueo(html: str) -> bool:
    muestra = html[:20000].lower()
    return any(senal in muestra for senal in SENALES_DE_BLOQUEO)


def _extraer_html_sincrono(html: str, direccion: str) -> str:
    """Quita menús, pies, cookies y banners y deja el contenido.

    Bloqueante, se llama desde un hilo aparte.
    """
    import trafilatura

    texto = trafilatura.extract(
        html,
        url=direccion,
        include_tables=True,
        include_comments=False,
        favor_recall=True,
    )
    return (texto or "").strip()


def _decodificar(contenido: bytes, tipo: str) -> str:
    codificacion = "utf-8"
    encontrada = re.search(r"charset=([\w-]+)", tipo)
    if encontrada:
        codificacion = encontrada.group(1)
    try:
        return contenido.decode(codificacion, errors="replace")
    except LookupError:
        return contenido.decode("utf-8", errors="replace")


async def leer_pagina(
    direccion: str, transporte: httpx.AsyncBaseTransport | None = None
) -> PaginaLeida:
    contenido, tipo, final = await descargar(direccion, transporte)

    if "application/pdf" in tipo:
        try:
            documento = await extraccion.extraer_pdf(contenido)
        except extraccion.ErrorExtraccion:
            raise WebNoLeida("formato")
        return PaginaLeida(final, "", documento)

    if "text/plain" in tipo:
        texto = _decodificar(contenido, tipo).strip()
        titulo = ""
    elif "html" in tipo or not tipo:
        html = _decodificar(contenido, tipo)
        texto = await asyncio.to_thread(_extraer_html_sincrono, html, final)
        titulo = titulo_de(html)
        if len(texto) < MINIMO_CARACTERES:
            raise WebNoLeida("bloqueada" if parece_bloqueo(html) else "sin_texto")
    else:
        raise WebNoLeida("formato")

    if len(texto) < MINIMO_CARACTERES:
        raise WebNoLeida("sin_texto")

    # La dirección va dentro del texto para que el bot pueda decir de dónde
    # ha sacado algo, igual que con el nombre de un fichero.
    cabecera = f"Página web: {final}"
    if titulo:
        cabecera += f"\nTítulo: {titulo}"
    return PaginaLeida(final, titulo, extraccion.Documento(
        texto=f"{cabecera}\n\n{texto}", origen="web"
    ))
