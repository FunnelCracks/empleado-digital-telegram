"""Configuracion global: variables de entorno, precios y constantes.

Todo lo configurable del proyecto pasa por aqui. Ningun otro modulo lee
os.environ directamente, para que se vea de un vistazo que se puede tocar.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# En local las claves viven en .env.local, que esta en .gitignore.
# En Railway no existe el fichero y las variables vienen del entorno.
load_dotenv(".env.local")


def _entero(nombre: str, por_defecto: int) -> int:
    """Lee una variable numerica tolerando que venga vacia o con basura."""
    try:
        return int(os.getenv(nombre, "").strip() or por_defecto)
    except ValueError:
        return por_defecto


def _decimal(nombre: str, por_defecto: float) -> float:
    try:
        return float(os.getenv(nombre, "").strip().replace(",", ".") or por_defecto)
    except ValueError:
        return por_defecto


# Obligatorias. Son las dos unicas que el usuario rellena en Railway.
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# Opcionales.
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID", "").strip()
LIMITE_MENSUAL_USD = _decimal("LIMITE_MENSUAL_USD", 20.0)
LIMITE_PREGUNTAS_HORA = _entero("LIMITE_PREGUNTAS_HORA", 20)
CACHE_TTL = os.getenv("CACHE_TTL", "1h").strip() or "1h"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# En Railway el volume se monta en /app/data. En local se apunta a ./data
# desde .env.local para no necesitar permisos de raiz.
RUTA_DATOS = Path(os.getenv("RUTA_DATOS", "").strip() or "/app/data")

# Modelo. Fijo a proposito: Haiku no es intercambiable aqui, tiene otro
# minimo cacheable, otro contexto y otro parametro de razonamiento.
MODELO = "claude-sonnet-5"

# Precios en dolares por millon de tokens, verificados contra la referencia
# de la API. Si Anthropic los cambia, se tocan aqui.
PRECIOS = {
    "entrada": 2.00,
    "salida": 10.00,
    "cache_lectura": 0.20,
    "cache_escritura_5m": 2.50,
    "cache_escritura_1h": 4.00,
}

# Minimo de tokens que Sonnet 5 necesita para que un prefijo se cachee.
# Por debajo de esto el cache_control no hace nada y no avisa.
MINIMO_CACHEABLE = 1024

# Umbral a partir del cual avisamos al owner de que su documentacion
# empieza a costar dinero de verdad.
AVISO_TOKENS_DOCUMENTOS = 50_000

# Limites duros que nos vienen impuestos desde fuera.
MAX_CARACTERES_TELEGRAM = 4096  # Telegram rechaza mensajes mas largos
MAX_BYTES_DESCARGA = 20 * 1024 * 1024  # la Bot API no deja descargar mas
MAX_PAGINAS_PDF_API = 600  # limite de Anthropic para PDF en Sonnet 5

# Parametros de la consulta.
MAX_TOKENS_RESPUESTA = 1500
TURNOS_HISTORIAL = 4

# Alfabeto del codigo de acceso, sin caracteres que se confundan al
# dictarlos por telefono: fuera I, L minuscula, 1, O y 0.
ALFABETO_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LONGITUD_CODIGO = 6


def faltan_variables_obligatorias() -> list[str]:
    """Devuelve la lista de variables obligatorias que estan sin rellenar."""
    faltan = []
    if not TELEGRAM_TOKEN:
        faltan.append("TELEGRAM_TOKEN")
    if not ANTHROPIC_API_KEY:
        faltan.append("ANTHROPIC_API_KEY")
    return faltan
