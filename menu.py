"""El teclado de botones que sale bajo el chat.

Un empresario no se acuerda de los comandos con barra. Los botones están
siempre a la vista y hacen lo mismo.

Es un teclado sin estado: cada botón manda un texto fijo que se traduce al
comando correspondiente. No guarda en qué paso va nadie, así que no se puede
desincronizar ni quedarse colgado, que es justo el problema que arrastran
los menús que sí guardan en qué paso va cada uno.
"""

from telegram import KeyboardButton, ReplyKeyboardMarkup

# Etiqueta del botón y comando al que equivale.
SUBIR = "📄 Subir documento"
DOCUMENTOS = "📚 Mis documentos"
BORRAR = "🗑️ Borrar documento"
COSTES = "💰 Mis costes"
CODIGO = "🔑 Código nuevo"
USUARIOS = "👥 Quién tiene acceso"
ACCESOS = "📋 Últimos movimientos"
RESPALDO = "💾 Copia de seguridad"
AYUDA = "❓ Ayuda"

QUE_PREGUNTAR = "📚 Qué puedo preguntar"

# El texto del botón lleva al nombre del comando. comandos.py se encarga de
# despacharlo. Aquí solo vive la correspondencia.
EQUIVALENCIAS = {
    SUBIR: "doc",
    DOCUMENTOS: "docs",
    BORRAR: "borrar",
    COSTES: "costes",
    CODIGO: "codigo",
    USUARIOS: "usuarios",
    ACCESOS: "logs",
    RESPALDO: "backup",
    AYUDA: "ayuda",
    QUE_PREGUNTAR: "docs",
}


def es_boton(texto: str) -> bool:
    return texto.strip() in EQUIVALENCIAS


def comando_de(texto: str) -> str | None:
    return EQUIVALENCIAS.get(texto.strip())


def teclado_owner() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(SUBIR), KeyboardButton(DOCUMENTOS)],
            [KeyboardButton(COSTES), KeyboardButton(BORRAR)],
            [KeyboardButton(USUARIOS), KeyboardButton(ACCESOS)],
            [KeyboardButton(CODIGO), KeyboardButton(RESPALDO)],
            [KeyboardButton(AYUDA)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Escribe tu pregunta o usa un botón",
    )


def teclado_empleado() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(QUE_PREGUNTAR), KeyboardButton(AYUDA)]],
        resize_keyboard=True,
        input_field_placeholder="Escribe tu pregunta",
    )


def teclado_para(es_owner: bool) -> ReplyKeyboardMarkup:
    return teclado_owner() if es_owner else teclado_empleado()


# Los mismos comandos en el menú de la barra de Telegram, para quien prefiera
# escribirlos. Se registran al arrancar.
COMANDOS_OWNER = [
    ("ayuda", "Ver todo lo que puedo hacer"),
    ("doc", "Subir documentación"),
    ("docs", "Ver los documentos cargados"),
    ("borrar", "Quitar un documento"),
    ("costes", "Cuánto llevas gastado este mes"),
    ("limite", "Cambiar el tope de gasto mensual"),
    ("codigo", "Generar un código de acceso nuevo"),
    ("usuarios", "Ver quién tiene acceso y quitárselo"),
    ("logs", "Los últimos movimientos"),
    ("backup", "Descargar una copia de seguridad"),
    ("menu", "Volver a sacar los botones"),
]

COMANDOS_EMPLEADO = [
    ("ayuda", "Ver qué puedo responderte"),
    ("docs", "Ver la documentación disponible"),
]
