"""Contabilidad del gasto.

Acumula en uso.json lo que se va gastando, aplica el tope mensual y avisa
al owner cuando lleva el 80% consumido. Se contabiliza todo, tambien las
lecturas de PDF escaneados y de fotos, que no son baratas.
"""

import logging
from datetime import datetime, timezone

import ajustes
import almacen

log = logging.getLogger("empleado.costes")

# La API factura en dólares y al owner hay que hablarle en euros. El tipo se
# queda fijo a propósito: consultarlo en vivo añadiría una dependencia
# externa por una cifra que solo sirve para orientar. Las cantidades se
# presentan siempre como aproximadas.
TIPO_CAMBIO_EUR = 0.92

# Salida típica de una respuesta del bot, para estimar lo que cuesta una
# pregunta antes de hacerla.
TOKENS_SALIDA_TIPICOS = 500


def periodo_actual() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def euros(dolares: float) -> float:
    return dolares * TIPO_CAMBIO_EUR


def en_euros(dolares: float) -> str:
    """Formatea en lenguaje de empresario, no de contable."""
    cantidad = euros(dolares)
    if cantidad < 0.01:
        return "menos de 1 céntimo"
    if cantidad < 1:
        centimos = round(cantidad * 100)
        return "1 céntimo" if centimos == 1 else f"{centimos:.0f} céntimos"
    return f"{cantidad:.2f} euros".replace(".", ",")


def con_miles(numero: int) -> str:
    """30000 se lee mucho mejor como 30.000."""
    return f"{numero:,}".replace(",", ".")


def coste_llamada(
    entrada: int = 0,
    salida: int = 0,
    cache_lectura: int = 0,
    cache_escritura: int = 0,
    ttl: str | None = None,
) -> float:
    """Coste en dólares de una llamada, a partir de los tokens reales."""
    precio_escritura = ajustes.PRECIOS[
        "cache_escritura_1h" if (ttl or ajustes.CACHE_TTL) == "1h" else "cache_escritura_5m"
    ]
    return (
        entrada * ajustes.PRECIOS["entrada"]
        + salida * ajustes.PRECIOS["salida"]
        + cache_lectura * ajustes.PRECIOS["cache_lectura"]
        + cache_escritura * precio_escritura
    ) / 1_000_000


def coste_de_uso(uso: object) -> float:
    """Igual que el anterior pero leyendo el objeto usage de la respuesta."""
    return coste_llamada(
        entrada=getattr(uso, "input_tokens", 0) or 0,
        salida=getattr(uso, "output_tokens", 0) or 0,
        cache_lectura=getattr(uso, "cache_read_input_tokens", 0) or 0,
        cache_escritura=getattr(uso, "cache_creation_input_tokens", 0) or 0,
    )


def estimar_pregunta(tokens_documentos: int) -> tuple[float, float]:
    """Devuelve (coste en caliente, coste en frío) en dólares.

    En caliente es cuando la caché está viva, que es el caso normal si hay
    actividad. En frío es la primera pregunta después de un rato largo, que
    paga la escritura de la caché.
    """
    salida = TOKENS_SALIDA_TIPICOS * ajustes.PRECIOS["salida"] / 1_000_000
    caliente = tokens_documentos * ajustes.PRECIOS["cache_lectura"] / 1_000_000 + salida
    precio_escritura = ajustes.PRECIOS[
        "cache_escritura_1h" if ajustes.CACHE_TTL == "1h" else "cache_escritura_5m"
    ]
    frio = tokens_documentos * precio_escritura / 1_000_000 + salida
    return caliente, frio


async def registrar_uso(uso: object, etiqueta: str = "consulta") -> dict:
    """Suma esta llamada al acumulado del mes. Reinicia si cambió el mes."""
    datos = almacen.leer_json(almacen.FICHERO_USO, almacen.USO_POR_DEFECTO)
    periodo = periodo_actual()

    if datos.get("periodo") != periodo:
        datos = dict(almacen.USO_POR_DEFECTO)
        datos["periodo"] = periodo

    datos["coste_usd"] = round(float(datos.get("coste_usd", 0.0)) + coste_de_uso(uso), 6)
    datos["peticiones"] = int(datos.get("peticiones", 0)) + 1
    datos["tokens_entrada"] += getattr(uso, "input_tokens", 0) or 0
    datos["tokens_salida"] += getattr(uso, "output_tokens", 0) or 0
    datos["cache_lectura"] += getattr(uso, "cache_read_input_tokens", 0) or 0
    datos["cache_escritura"] += getattr(uso, "cache_creation_input_tokens", 0) or 0

    await almacen.guardar_json(almacen.FICHERO_USO, datos)
    log.info("Uso registrado (%s): %.6f USD acumulados", etiqueta, datos["coste_usd"])
    return datos


def gasto_del_mes() -> float:
    datos = almacen.leer_json(almacen.FICHERO_USO, almacen.USO_POR_DEFECTO)
    if datos.get("periodo") != periodo_actual():
        return 0.0
    return float(datos.get("coste_usd", 0.0))


def datos_del_mes() -> dict:
    datos = almacen.leer_json(almacen.FICHERO_USO, almacen.USO_POR_DEFECTO)
    if datos.get("periodo") != periodo_actual():
        datos = dict(almacen.USO_POR_DEFECTO)
        datos["periodo"] = periodo_actual()
    return datos


# ---------------------------------------------------------------------------
# El tope mensual
# ---------------------------------------------------------------------------
#
# Esto no es opcional. El bot va a estar en manos de gente que no sabe lo que
# es un token, y una factura sorpresa convierte un regalo en un disgusto.

UMBRAL_AVISO = 0.80


def limite_mensual() -> float:
    """El que haya puesto el owner con /limite manda sobre la variable."""
    guardado = almacen.leer_config().get("limite_mensual_usd", "")
    try:
        if guardado:
            return float(guardado)
    except ValueError:
        pass
    return ajustes.LIMITE_MENSUAL_USD


async def cambiar_limite(nuevo: float) -> None:
    await almacen.actualizar_config(limite_mensual_usd=f"{nuevo:.2f}")


def porcentaje_gastado() -> float:
    tope = limite_mensual()
    if tope <= 0:
        return 0.0
    return gasto_del_mes() / tope


def limite_alcanzado() -> bool:
    return porcentaje_gastado() >= 1.0


def hay_que_avisar_del_80() -> bool:
    """True una sola vez por periodo, cuando se cruza el umbral."""
    datos = datos_del_mes()
    if datos.get("avisado_80"):
        return False
    return UMBRAL_AVISO <= porcentaje_gastado() < 1.0


def hay_que_avisar_del_100() -> bool:
    datos = datos_del_mes()
    return limite_alcanzado() and not datos.get("avisado_100")


async def marcar_avisado(clave: str) -> None:
    datos = datos_del_mes()
    datos[clave] = True
    await almacen.guardar_json(almacen.FICHERO_USO, datos)


def proyeccion_fin_de_mes() -> float:
    """A este ritmo, cuánto habrá gastado el día 30.

    Con muy pocos días transcurridos la cifra baila mucho, así que quien la
    enseña tiene que decir que es una estimación.
    """
    import calendar

    hoy = datetime.now(timezone.utc)
    dias_del_mes = calendar.monthrange(hoy.year, hoy.month)[1]
    transcurridos = max(1, hoy.day)
    return gasto_del_mes() / transcurridos * dias_del_mes
