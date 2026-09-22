"""Todos los mensajes que el bot envía, en un solo sitio.

Están aquí para poder ajustar el tono sin tocar lógica. Reglas de estilo:
español de España con su ortografía correcta, tuteo, cero jerga técnica, y
los errores se explican diciendo qué hacer, no qué ha fallado. Nunca rayas
largas como signo de puntuación.

El formato es HTML de Telegram: <b>negrita</b>, <code>monoespaciado</code>.
"""

# ---------------------------------------------------------------------------
# Aviso legal, se reutiliza en varios sitios
# ---------------------------------------------------------------------------

AVISO_DATOS = (
    "🔒 <b>Antes de subir nada, léete esto</b>\n\n"
    "Este bot envía el contenido de tus documentos a la API de Claude para poder "
    "responder. No subas datos personales de clientes, empleados o terceros "
    "(DNI, nóminas, historiales, datos de salud) sin haber verificado antes tu "
    "base legal para ello.\n\n"
    "Sube catálogos, tarifas, procedimientos, manuales y documentación interna."
)


# ---------------------------------------------------------------------------
# Primer arranque y alta del owner
# ---------------------------------------------------------------------------

def bienvenida_owner(codigo: str) -> str:
    return (
        "👋 <b>Ya eres el administrador de este bot</b>\n\n"
        "A partir de ahora esto es tu empleado digital. Tú le das la documentación "
        "de tu empresa y él responde las preguntas de tu equipo sobre ella.\n\n"
        "🔑 <b>Este es el código de acceso para tu gente:</b>\n\n"
        f"<code>{codigo}</code>\n\n"
        "<b>Guárdalo ahora.</b> No te lo voy a volver a enseñar. Si lo pierdes no "
        "pasa nada, generas otro con /codigo, pero el anterior dejará de funcionar "
        "y tendrás que repartir el nuevo.\n\n"
        "Cada empleado que quiera usar el bot tendrá que escribirme y darme ese código."
    )


SIGUIENTE_PASO_DOCUMENTOS = (
    "📄 <b>Vamos con tus documentos</b>\n\n"
    "Mándame los ficheros que quieras que conozca: catálogos, tarifas, manuales, "
    "procedimientos. Acepto PDF, Word, texto, CSV y fotos.\n\n"
    "Puedes mandarlos directamente aquí, uno detrás de otro."
)


def owner_vuelve(documentos: int) -> str:
    if documentos == 0:
        return (
            "👋 Hola de nuevo. Todavía no me has dado ningún documento, así que aún "
            "no puedo responder preguntas.\n\n"
            "Mándame un fichero cuando quieras y empezamos."
        )
    plural = "documento cargado" if documentos == 1 else "documentos cargados"
    return (
        f"👋 Hola de nuevo. Tengo {documentos} {plural} y estoy listo.\n\n"
        "Escribe /ayuda si quieres ver todo lo que puedo hacer."
    )


# ---------------------------------------------------------------------------
# Acceso de empleados
# ---------------------------------------------------------------------------

PEDIR_CODIGO = (
    "👋 <b>Hola</b>\n\n"
    "Soy el asistente de documentación de la empresa. Para poder ayudarte necesito "
    "que me des el código de acceso que te hayan facilitado.\n\n"
    "Escríbelo aquí tal cual, son 6 caracteres."
)


def codigo_correcto(nombre_empresa: str, mensaje_bienvenida: str) -> str:
    if nombre_empresa:
        cabecera = f"✅ <b>Ya tienes acceso a la documentación de {nombre_empresa}</b>\n\n"
    else:
        cabecera = "✅ <b>Ya tienes acceso</b>\n\n"
    cuerpo = mensaje_bienvenida.strip() or (
        "Pregúntame lo que necesites sobre la documentación de la empresa y te "
        "contesto con lo que ponga en ella.\n\n"
        "Escribe /ayuda si quieres ver qué documentación tengo cargada."
    )
    return cabecera + cuerpo


CODIGO_INCORRECTO = (
    "❌ Ese código no es correcto.\n\n"
    "Revísalo y vuelve a intentarlo. No te preocupes por las mayúsculas, las acepto "
    "de las dos formas. Si no tienes código, pídeselo a tu responsable."
)


NO_AUTORIZADO = (
    "🔒 Para usar este bot necesitas un código de acceso.\n\n"
    "Escribe /start y te lo pido."
)


BOT_SIN_PREPARAR = (
    "🔧 Este bot todavía no lo ha terminado de configurar su administrador.\n\n"
    "Vuelve a intentarlo en un rato."
)


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def codigo_regenerado(codigo: str) -> str:
    return (
        "🔑 <b>Código nuevo</b>\n\n"
        f"<code>{codigo}</code>\n\n"
        "El anterior ya no funciona. La gente que ya tenía acceso lo conserva, "
        "esto solo afecta a quien entre a partir de ahora.\n\n"
        "Si quieres quitarle el acceso a alguien que ya estaba dentro, usa /usuarios."
    )


SOLO_OWNER = "🔒 Esto solo lo puede hacer el administrador del bot."


def _listado(nombres: list[str]) -> str:
    listado = "\n".join(f"  • {nombre}" for nombre in nombres[:15])
    if len(nombres) > 15:
        listado += f"\n  • y {len(nombres) - 15} más"
    return listado


def ayuda_owner(documentos: int, nombres: list[str]) -> str:
    if documentos == 0:
        estado = (
            "📭 <b>Todavía no tengo documentación cargada.</b>\n"
            "Mándame ficheros y empiezo a poder responder.\n\n"
        )
    else:
        plural = "documento" if documentos == 1 else "documentos"
        estado = f"📚 <b>Tengo {documentos} {plural}:</b>\n{_listado(nombres)}\n\n"

    return (
        "<b>Esto es lo que puedo hacer</b>\n\n"
        + estado
        + "<b>Tus documentos</b>\n"
        "/doc  subir documentación\n"
        "/docs  ver lo que tengo cargado\n"
        "/borrar  quitar un documento\n\n"
        "<b>Tu gente</b>\n"
        "/codigo  generar un código de acceso nuevo\n"
        "/usuarios  ver quién tiene acceso y quitárselo\n"
        "/logs  últimos accesos\n\n"
        "<b>Tu dinero</b>\n"
        "/costes  cuánto llevas gastado este mes\n"
        "/limite  cambiar el tope mensual\n\n"
        "<b>Por si acaso</b>\n"
        "/backup  descargar una copia de todo"
    )


def ayuda_usuario(documentos: int, nombres: list[str]) -> str:
    if documentos == 0:
        return (
            "📭 Todavía no tengo documentación cargada, así que aún no puedo "
            "responderte.\n\nAvisa a tu responsable para que suba los documentos."
        )
    return (
        "<b>Pregúntame lo que quieras sobre esto</b>\n\n"
        f"{_listado(nombres)}\n\n"
        "Escríbeme en lenguaje normal, como si le preguntaras a un compañero. "
        "Si la respuesta no está en la documentación te lo diré claramente, en "
        "vez de inventármela."
    )


COMANDO_DESCONOCIDO = (
    "🤔 Ese comando no lo conozco.\n\n"
    "Escribe /ayuda y te enseño lo que sí sé hacer."
)


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------

ERROR_GENERICO = (
    "😕 Algo no ha ido bien por mi parte.\n\n"
    "Prueba otra vez en unos segundos. Si sigue igual, avisa al administrador."
)


# ---------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------

PIDE_DOCUMENTOS = (
    "📄 <b>Mándame lo que quieras que aprenda</b>\n\n"
    "Acepto PDF, Word, texto, CSV y fotos. Puedes mandarlos uno detrás de otro, "
    "no hace falta que avises entre uno y otro.\n\n"
    "Si el PDF está escaneado también lo leo, solo que tardo un poco más."
)


LEYENDO = "📖 Estoy leyendo el documento, dame un momento."
LEYENDO_ESCANEADO = (
    "📖 Ese PDF está escaneado, así que lo tengo que leer a ojo. "
    "Tardo un poco más de lo normal."
)
ESCUCHANDO = "🎧 Estoy escuchando la nota de voz."


def documento_guardado(
    nombre: str,
    tokens: int,
    total_documentos: int,
    total_tokens: int,
    coste_caliente: str,
    sobrescrito: bool,
    avisos: list[str],
) -> str:
    cabecera = (
        f"♻️ <b>He actualizado {nombre}</b>\n"
        if sobrescrito
        else f"✅ <b>Guardado: {nombre}</b>\n"
    )
    plural = "documento" if total_documentos == 1 else "documentos"
    cuerpo = (
        f"\nYa tengo <b>{total_documentos} {plural}</b> cargados.\n"
        f"Cada pregunta te costará <b>{coste_caliente}</b> más o menos."
    )
    if sobrescrito:
        cuerpo += "\n\nHabía otro con el mismo nombre y lo he reemplazado, "
        cuerpo += "así que no tienes nada duplicado."
    if avisos:
        cuerpo += "\n\n⚠️ " + ". ".join(aviso.capitalize() for aviso in avisos) + "."
    return cabecera + cuerpo


def aviso_documentacion_grande(total_tokens: int, coste_caliente: str) -> str:
    return (
        "💡 <b>Un aviso, que no es un error</b>\n\n"
        "Ya tienes bastante documentación cargada. No pasa nada, funciona igual, "
        f"pero cada pregunta te va a costar unos <b>{coste_caliente}</b>.\n\n"
        "Si ves que se te va de las manos, con /docs puedes ver qué ocupa más y "
        "con /borrar quitar lo que ya no uses."
    )


def lista_documentos(
    fichas: list[tuple[str, int]], total_tokens: int, coste_caliente: str
) -> str:
    if not fichas:
        return (
            "📭 <b>Todavía no tengo ningún documento</b>\n\n"
            "Mándame un fichero y empezamos. Acepto PDF, Word, texto, CSV y fotos."
        )
    lineas = "\n".join(
        f"  • <b>{nombre}</b>  ({tokens:,} tokens)".replace(",", ".")
        for nombre, tokens in fichas
    )
    plural = "documento" if len(fichas) == 1 else "documentos"
    return (
        f"📚 <b>Tengo {len(fichas)} {plural}</b>\n\n"
        f"{lineas}\n\n"
        f"En total ocupan {total_tokens:,} tokens, ".replace(",", ".")
        + f"y cada pregunta te cuesta alrededor de <b>{coste_caliente}</b>.\n\n"
        "Para quitar alguno, /borrar."
    )


ELIGE_DOCUMENTO_A_BORRAR = "🗑️ <b>¿Cuál quieres quitar?</b>"
BORRADO_CANCELADO = "Vale, no toco nada."


def documento_borrado(nombre: str, quedan: int) -> str:
    if quedan == 0:
        return (
            f"🗑️ Quitado <b>{nombre}</b>.\n\n"
            "Ya no me queda ningún documento, así que no puedo responder preguntas "
            "hasta que me mandes alguno."
        )
    plural = "documento" if quedan == 1 else "documentos"
    return f"🗑️ Quitado <b>{nombre}</b>.\n\nMe quedan {quedan} {plural}."


# ---------------------------------------------------------------------------
# Problemas al subir
# ---------------------------------------------------------------------------

def no_he_podido_leer(motivo: str) -> str:
    return (
        f"😕 No he podido con ese fichero: {motivo}.\n\n"
        "Prueba con otro, o pásalo a PDF o a Word y me lo mandas otra vez."
    )


FICHERO_DEMASIADO_GRANDE = (
    "📦 Ese fichero pesa demasiado.\n\n"
    "Telegram no me deja recibir más de 20 MB. Si es un PDF muy gordo, pártelo "
    "en dos y mándamelo en dos veces."
)


FORMATO_NO_SOPORTADO = (
    "🤷 Ese tipo de fichero no lo sé leer.\n\n"
    "Mándame PDF, Word (.docx), texto, CSV o una foto."
)


SOLO_OWNER_SUBE = (
    "🔒 Solo el administrador puede subir documentación.\n\n"
    "Tú puedes preguntarme lo que quieras sobre la que ya hay cargada."
)


VOZ_SIN_CONFIGURAR = (
    "🎤 De momento no sé escuchar notas de voz, solo texto e imágenes.\n\n"
    "Escríbeme la pregunta y te contesto igual."
)


VOZ_HA_FALLADO = (
    "🎤 No he conseguido entender esa nota de voz.\n\n"
    "Prueba a escribírmelo, o repítela en un sitio con menos ruido."
)


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------

SIN_DOCUMENTACION_OWNER = (
    "📭 Todavía no me has dado ningún documento, así que no tengo nada que "
    "consultar.\n\nMándame un PDF, un Word o una foto y ya podré responderte."
)

SIN_DOCUMENTACION_EMPLEADO = (
    "📭 Todavía no tengo documentación cargada, así que no puedo responderte.\n\n"
    "Avisa a tu responsable para que suba los documentos de la empresa."
)

RESPUESTA_VACIA = (
    "😕 Me he quedado en blanco con esa pregunta.\n\n"
    "Prueba a formularla de otra manera, o a ser un poco más concreto."
)


# Cada problema se cuenta diciendo qué hacer, no qué ha fallado. El usuario
# no sabe lo que es un 429 ni tiene por qué saberlo.
_PROBLEMAS = {
    "demanda": (
        "⏳ Ahora mismo hay mucha demanda y no me han dejado contestar.\n\n"
        "Prueba otra vez en unos segundos, suele arreglarse solo."
    ),
    "conexion": (
        "📡 No he conseguido conectarme para responderte.\n\n"
        "Prueba otra vez en un momento."
    ),
    "credito": (
        "💳 Se ha quedado sin saldo la cuenta que me da la inteligencia.\n\n"
        "Avisa al administrador para que recargue crédito en su cuenta de "
        "Anthropic. Hasta entonces no voy a poder responder."
    ),
    "clave": (
        "🔑 La clave de acceso a la inteligencia no es válida.\n\n"
        "Esto lo tiene que revisar el administrador en la configuración del bot."
    ),
    "desconocido": (
        "😕 Algo no ha ido bien y no he podido responderte.\n\n"
        "Prueba otra vez en un momento. Si sigue igual, avisa al administrador."
    ),
}


def problema_al_responder(motivo: str) -> str:
    return _PROBLEMAS.get(motivo, _PROBLEMAS["desconocido"])


# Los mismos fallos, pero contados a quien está subiendo un documento. Cambia
# el tono porque cambia el interlocutor: subir documentos solo puede hacerlo el
# owner, así que aquí no vale decirle "avisa al administrador". Se le dice qué
# tiene que ir a tocar él.
_PROBLEMAS_AL_SUBIR = {
    "demanda": (
        "⏳ Ahora mismo hay mucha demanda y no me han dejado leerlo.\n\n"
        "Vuelve a mandármelo en unos segundos, suele arreglarse solo."
    ),
    "conexion": (
        "📡 No he conseguido conectarme para leer ese documento.\n\n"
        "Vuelve a mandármelo en un momento."
    ),
    "credito": (
        "💳 Tu cuenta de Claude se ha quedado sin saldo, así que no he podido "
        "leer el documento.\n\n"
        "Entra en console.anthropic.com y recárgala. En cuanto lo hagas, vuelve "
        "a mandármelo y lo guardo."
    ),
    "clave": (
        "🔑 La clave de Claude que tengo configurada no es válida, así que no "
        "he podido leer el documento.\n\n"
        "Revísala donde tengas alojado el bot. Tiene que empezar por sk-ant- y "
        "estar entera, sin espacios ni comillas alrededor. Al copiarla se corta "
        "con muchísima facilidad, y es lo que falla casi siempre."
    ),
    "desconocido": (
        "😕 Algo no ha ido bien y no he podido leer ese documento.\n\n"
        "Vuelve a mandármelo en un momento."
    ),
}


def problema_al_subir(motivo: str) -> str:
    return _PROBLEMAS_AL_SUBIR.get(motivo, _PROBLEMAS_AL_SUBIR["desconocido"])


def voz_entendida(texto: str) -> str:
    return f"🎤 Te he entendido: «{texto}»"


# ---------------------------------------------------------------------------
# Costes y límites
# ---------------------------------------------------------------------------

def informe_de_costes(
    gastado: str,
    limite_dolares: float,
    porcentaje: int,
    preguntas: int,
    coste_pregunta: str,
    proyeccion: str,
    documentos: int,
    tokens: str,
) -> str:
    if porcentaje >= 100:
        semaforo = "🔴 Has llegado al tope, he dejado de responder"
    elif porcentaje >= 80:
        semaforo = "🟠 Te estás acercando al tope"
    elif porcentaje >= 40:
        semaforo = "🟡 Vas por la mitad"
    else:
        semaforo = "🟢 Vas muy holgado"

    plural_preguntas = "pregunta" if preguntas == 1 else "preguntas"
    plural_documentos = "documento" if documentos == 1 else "documentos"
    tope = f"{limite_dolares:.0f}".replace(".", ",")

    if preguntas == 0:
        actividad = "Este mes todavía no te ha preguntado nadie.\n"
    else:
        actividad = (
            f"Has recibido {preguntas} {plural_preguntas}, "
            f"a unos {coste_pregunta} cada una.\n"
            f"A este ritmo acabarás el mes en torno a {proyeccion}.\n"
        )

    return (
        "💰 <b>Tus costes de este mes</b>\n\n"
        f"Llevas gastado <b>{gastado}</b>.\n"
        f"{semaforo}: has usado el <b>{porcentaje}%</b> de tu tope.\n\n"
        + actividad
        + f"\nTienes {documentos} {plural_documentos} cargados, "
        f"{tokens} tokens en total.\n\n"
        f"Tu tope está en {tope} dólares al mes, que es lo que se descuenta de "
        "tu saldo de Anthropic. Para cambiarlo: <code>/limite 30</code>"
    )


def limite_cambiado(nuevo_dolares: float, gastado: str) -> str:
    tope = f"{nuevo_dolares:.0f}".replace(".", ",")
    return (
        f"✅ Tope nuevo: <b>{tope} dólares al mes</b>.\n\n"
        f"Ahora mismo llevas gastado {gastado}."
    )


LIMITE_MAL_ESCRITO = (
    "🤔 No he entendido la cantidad.\n\n"
    "Escríbelo así: <code>/limite 30</code>, para poner el tope en 30 dólares al mes."
)


LIMITE_DEMASIADO_BAJO = (
    "🤔 Ese tope es tan bajo que el bot no podría ni responder una pregunta.\n\n"
    "Pon al menos 1."
)


def tope_alcanzado_usuario(nombre_empresa: str) -> str:
    de_quien = f"de {nombre_empresa}" if nombre_empresa else "de la empresa"
    return (
        "🛑 Este mes ya se ha agotado el presupuesto del asistente.\n\n"
        f"Avisa al responsable {de_quien}. El día 1 se reinicia solo."
    )


def tope_alcanzado_owner(gastado: str, limite_dolares: float) -> str:
    tope = f"{limite_dolares:.0f}"
    return (
        "🛑 <b>Has llegado a tu tope de gasto</b>\n\n"
        f"Llevas {gastado} gastados y tu tope está en {tope} dólares al mes, así "
        "que he dejado de responder preguntas para no seguir gastando.\n\n"
        "Tienes dos opciones:\n"
        "  • Subir el tope con /limite 40\n"
        "  • Esperar al día 1, que el contador se reinicia solo\n\n"
        "Si quieres que cada pregunta cueste menos, quita documentación que ya "
        "no uses con /borrar."
    )


def aviso_80_por_ciento(gastado: str, limite_dolares: float, proyeccion: str) -> str:
    tope = f"{limite_dolares:.0f}"
    return (
        "🟠 <b>Aviso de gasto</b>\n\n"
        f"Llevas {gastado} gastados, el 80% de tu tope de {tope} dólares al mes.\n\n"
        f"A este ritmo acabarás el mes en torno a {proyeccion}. Cuando llegues al "
        "tope dejaré de responder, así que si lo ves justo súbelo con /limite.\n\n"
        "No tienes que hacer nada ahora mismo, es solo para que no te pille por sorpresa."
    )


def demasiadas_preguntas(minutos: int) -> str:
    espera = "un minuto" if minutos <= 1 else f"{minutos} minutos"
    return (
        "⏳ Has hecho muchas preguntas seguidas.\n\n"
        f"Espera {espera} y seguimos. Es para que el presupuesto del mes llegue "
        "a fin de mes."
    )


MENU_AQUI = "👇 Aquí tienes los botones. Están siempre disponibles."


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

def lista_de_usuarios(gente: list[tuple[str, str]]) -> str:
    if not gente:
        return (
            "👥 <b>Todavía no ha entrado nadie</b>\n\n"
            "Reparte el código de acceso entre tu equipo. Si no lo recuerdas, "
            "genera uno nuevo con /codigo."
        )
    lineas = "\n".join(f"  • <b>{nombre}</b>, desde el {desde}" for nombre, desde in gente)
    plural = "persona" if len(gente) == 1 else "personas"
    return (
        f"👥 <b>{len(gente)} {plural} con acceso</b>\n\n"
        f"{lineas}\n\n"
        "Pulsa en alguien para quitarle el acceso."
    )


def acceso_revocado(nombre: str) -> str:
    return (
        f"🚫 <b>{nombre}</b> ya no tiene acceso.\n\n"
        "Si lo vuelve a intentar le pediré el código. Ojo: si todavía se sabe "
        "el código actual, puede volver a entrar. Para cerrarle la puerta del "
        "todo, genera un código nuevo con /codigo."
    )


REVOCAR_CANCELADO = "Vale, no toco nada."
NADIE_A_QUIEN_QUITAR = "Esa persona ya no tenía acceso."


# ---------------------------------------------------------------------------
# Registro de accesos
# ---------------------------------------------------------------------------

EVENTOS = {
    "alta_owner": "🧑‍💼 se hizo administrador",
    "acceso_concedido": "✅ entró con el código",
    "acceso_revocado": "🚫 perdió el acceso",
    "codigo_fallido": "❌ falló el código",
    "bloqueo_intentos": "🔒 bloqueado por fallar cinco veces",
    "codigo_regenerado": "🔑 generó un código nuevo",
    "documento_guardado": "📄 subió documentación",
    "documento_borrado": "🗑️ borró documentación",
    "limite_cambiado": "💰 cambió el tope de gasto",
    "copia_enviada": "💾 copia de seguridad enviada",
}


def registro_de_accesos(lineas: list[str]) -> str:
    if not lineas:
        return "📋 Todavía no hay nada registrado."
    return (
        "📋 <b>Últimos movimientos</b>\n\n"
        + "\n".join(lineas)
        + "\n\nLas horas son de España."
    )


# ---------------------------------------------------------------------------
# Copia de seguridad
# ---------------------------------------------------------------------------

COPIA_PREPARANDO = "💾 Preparando tu copia de seguridad."

COPIA_MANUAL = (
    "💾 <b>Aquí tienes tu copia</b>\n\n"
    "Dentro está el texto de todos tus documentos, tu configuración y la lista "
    "de quién tiene acceso. Guárdala donde quieras, aunque dejándola en este "
    "chat ya te vale: Telegram no la borra.\n\n"
    "Dentro hay un LEEME.txt que explica cómo recuperarte si algún día lo "
    "necesitas."
)

COPIA_AUTOMATICA = (
    "💾 <b>Copia de seguridad al día</b>\n\n"
    "Has cambiado tu documentación, así que te mando una copia actualizada. "
    "No tienes que hacer nada, solo dejarla en este chat.\n\n"
    "Si algún día se pierde todo, aquí lo tienes."
)

COPIA_SIN_NADA = (
    "💾 Todavía no tienes documentación que copiar.\n\n"
    "Súbeme algún documento y entonces la copia tendrá sentido."
)


# ---------------------------------------------------------------------------
# Bloqueo por intentos
# ---------------------------------------------------------------------------

def codigo_incorrecto_con_avisos(restantes: int) -> str:
    if restantes == 1:
        aviso = "\n\n⚠️ Te queda <b>un intento</b>. Al siguiente fallo tendrás que esperar una hora."
    elif restantes <= 2:
        aviso = f"\n\n⚠️ Te quedan <b>{restantes} intentos</b>."
    else:
        aviso = ""
    return CODIGO_INCORRECTO + aviso


def estas_bloqueado(minutos: int) -> str:
    espera = "un minuto" if minutos <= 1 else f"{minutos} minutos"
    return (
        "🔒 Has fallado el código cinco veces, así que te he cerrado la puerta "
        f"un rato.\n\nVuelve a intentarlo dentro de {espera}. Aprovecha para "
        "pedirle el código correcto a tu responsable."
    )


def aviso_intentos_al_owner(quien: str) -> str:
    return (
        "🔒 <b>Alguien ha estado probando códigos</b>\n\n"
        f"{quien} ha fallado cinco veces seguidas y le he bloqueado una hora.\n\n"
        "Si es alguien de tu equipo que no se aclara, pásale el código otra vez. "
        "Si no sabes quién es, genera un código nuevo con /codigo."
    )
