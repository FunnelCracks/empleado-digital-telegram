"""Cuántas preguntas puede hacer cada uno por hora.

El tope de gasto mensual protege la cartera a lo grande. Esto la protege de
lo pequeño: un empleado que se pone a jugar con el bot y hace doscientas
preguntas en una tarde se come el presupuesto del mes de todos.

Se persiste en disco, nunca en memoria, porque Railway reinicia contenedores
y un límite que se olvida al reiniciar no es un límite.
"""

import logging
import time

import ajustes
import almacen

log = logging.getLogger("empleado.limites")

UNA_HORA = 3600

# bloqueos.json guarda dos cosas distintas bajo dos claves. La de codigos
# es la del bloqueo por intentos fallidos.
CLAVE_PREGUNTAS = "preguntas"
CLAVE_CODIGOS = "codigos"


def _estado() -> dict:
    datos = almacen.leer_json(almacen.FICHERO_BLOQUEOS, {})
    datos.setdefault(CLAVE_PREGUNTAS, {})
    datos.setdefault(CLAVE_CODIGOS, {})
    return datos


def _recientes(marcas: list, ahora: float) -> list[float]:
    """Se queda solo con las de la última hora. De paso limpia el fichero."""
    return [float(marca) for marca in marcas if ahora - float(marca) < UNA_HORA]


def preguntas_en_la_ultima_hora(chat_id: int) -> int:
    ahora = time.time()
    marcas = _estado()[CLAVE_PREGUNTAS].get(str(chat_id), [])
    return len(_recientes(marcas, ahora))


def quedan(chat_id: int) -> int:
    return max(0, ajustes.LIMITE_PREGUNTAS_HORA - preguntas_en_la_ultima_hora(chat_id))


def minutos_hasta_poder_preguntar(chat_id: int) -> int:
    """Cuánto falta para que caduque la pregunta más antigua de la ventana."""
    ahora = time.time()
    marcas = sorted(_recientes(_estado()[CLAVE_PREGUNTAS].get(str(chat_id), []), ahora))
    if not marcas:
        return 0
    faltan = UNA_HORA - (ahora - marcas[0])
    return max(1, int(faltan / 60) + 1)


async def registrar_pregunta(chat_id: int) -> None:
    """Apunta una pregunta y de paso poda las que ya no cuentan."""
    ahora = time.time()
    datos = _estado()
    marcas = _recientes(datos[CLAVE_PREGUNTAS].get(str(chat_id), []), ahora)
    marcas.append(ahora)
    datos[CLAVE_PREGUNTAS][str(chat_id)] = marcas

    # Aprovechamos para tirar a la basura a quien ya no tiene marcas vivas,
    # o el fichero crecería indefinidamente con gente que paso por aqui una vez.
    datos[CLAVE_PREGUNTAS] = {
        identificador: _recientes(lista, ahora)
        for identificador, lista in datos[CLAVE_PREGUNTAS].items()
        if _recientes(lista, ahora)
    }
    await almacen.guardar_json(almacen.FICHERO_BLOQUEOS, datos)


def ha_pasado_del_limite(chat_id: int) -> bool:
    return preguntas_en_la_ultima_hora(chat_id) >= ajustes.LIMITE_PREGUNTAS_HORA


# ---------------------------------------------------------------------------
# Bloqueo por códigos fallidos
# ---------------------------------------------------------------------------
#
# Cinco intentos y a la calle una hora. Sin esto, el código de 6 caracteres
# se puede sacar a base de probar. Con esto, alguien que lo intente a ciegas
# tardaría siglos.

MAX_INTENTOS = 5
BLOQUEO_SEGUNDOS = UNA_HORA


def esta_bloqueado(chat_id: int) -> bool:
    ficha = _estado()[CLAVE_CODIGOS].get(str(chat_id), {})
    return float(ficha.get("bloqueado_hasta", 0)) > time.time()


def minutos_de_bloqueo(chat_id: int) -> int:
    ficha = _estado()[CLAVE_CODIGOS].get(str(chat_id), {})
    faltan = float(ficha.get("bloqueado_hasta", 0)) - time.time()
    return max(1, int(faltan / 60) + 1) if faltan > 0 else 0


def intentos_restantes(chat_id: int) -> int:
    ficha = _estado()[CLAVE_CODIGOS].get(str(chat_id), {})
    return max(0, MAX_INTENTOS - int(ficha.get("intentos", 0)))


async def registrar_fallo(chat_id: int) -> int:
    """Suma un intento fallido. Devuelve los que le quedan, 0 si se bloquea."""
    datos = _estado()
    ficha = datos[CLAVE_CODIGOS].get(str(chat_id), {"intentos": 0, "bloqueado_hasta": 0})
    ficha["intentos"] = int(ficha.get("intentos", 0)) + 1

    if ficha["intentos"] >= MAX_INTENTOS:
        ficha["bloqueado_hasta"] = time.time() + BLOQUEO_SEGUNDOS
        ficha["intentos"] = 0  # al salir del bloqueo empieza de cero
        log.warning("Chat %s bloqueado por intentos fallidos", chat_id)
        restantes = 0
    else:
        restantes = MAX_INTENTOS - ficha["intentos"]

    datos[CLAVE_CODIGOS][str(chat_id)] = ficha
    await almacen.guardar_json(almacen.FICHERO_BLOQUEOS, datos)
    return restantes


async def perdonar(chat_id: int) -> None:
    """Se llama al acertar el código: el contador vuelve a cero."""
    datos = _estado()
    if datos[CLAVE_CODIGOS].pop(str(chat_id), None) is not None:
        await almacen.guardar_json(almacen.FICHERO_BLOQUEOS, datos)
