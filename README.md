# Tu Empleado Digital

> Desarrollado por **IA para Empresarios**, el curso de IA más completo del mercado,
> avalado por grandes empresarios como José Elías, Eric Ponce, Magí Pons, Eric G y
> Héctor Matías.

Un bot de Telegram que responde preguntas sobre la documentación de tu empresa.

Le subes tus catálogos, tus tarifas, tus manuales y tus procedimientos, y a partir de ahí
tu equipo le pregunta por Telegram como le preguntaría a un compañero. Responde solo con
lo que hay en esos documentos, y cuando algo no lo sabe, lo dice.

Está pensado para que lo monte y lo use alguien que no ha programado nunca.

---

## Qué sabe hacer

- **Lee tus documentos.** PDF, Word, texto plano, CSV y Markdown. Si el PDF es un escaneo
  sin texto seleccionable, también lo lee. Y si le mandas la foto de un papel, la lee
  igual.
- **Lee páginas web.** Le pegas la dirección de una página, o de varias, y se guarda lo
  que pone. Te cuenta en unas frases lo que ha entendido para que compruebes que está
  bien.
- **Responde por Telegram**, en lenguaje normal, citando lo que pone en tu documentación.
- **Entiende notas de voz**, si activas esa opción.
- **Controla el gasto.** Trae un tope mensual puesto de fábrica. Al 80% te avisa y al 100%
  deja de responder, para que nadie se lleve un susto en la factura.
- **Da acceso a tu equipo con un código**, y tú decides a quién se lo quitas y cuándo.
- **Se hace copias de seguridad solo** y te las manda por Telegram cuando cambia la
  documentación.

## Los comandos

| Comando | Qué hace |
|---|---|
| `/start` | Empieza. El primero que lo escribe se queda como administrador |
| `/docs` | Lista los documentos que tiene cargados |
| `/borrar` | Borra un documento |
| `/codigo` | Genera un código nuevo para dar acceso a alguien del equipo |
| `/usuarios` | Quién tiene acceso, y un botón para quitárselo |
| `/costes` | Lo que llevas gastado este mes y la previsión a fin de mes |
| `/limite` | Cambia el tope de gasto mensual |
| `/logs` | Los últimos movimientos: quién ha entrado y quién lo ha intentado |
| `/backup` | Te manda una copia de seguridad al momento |
| `/menu` | Saca los botones, por si no te apetece escribir comandos |
| `/ayuda` | Recuerda todo esto |

Para preguntar no hace falta ningún comando: se escribe la pregunta y ya está.

---

> ### ⚠️ Antes de subir nada, léete esto
>
> Este bot envía el contenido de tus documentos a la API de Claude para poder responder.
> No subas datos personales de clientes, empleados o terceros (DNI, nóminas, historiales,
> datos de salud) sin haber verificado antes tu base legal para ello. Sube catálogos,
> tarifas, procedimientos, manuales y documentación interna.

---

## Qué necesitas para montarlo

Tres cosas, y ninguna lleva más de un par de minutos:

1. **Un bot de Telegram.** Se crea hablando con [@BotFather](https://t.me/BotFather) desde
   tu propio Telegram. Te da un código largo que se llama *token*.
2. **Una clave de Claude.** Se saca en [console.anthropic.com](https://console.anthropic.com).
   Hay que cargar saldo, porque se paga por uso. Es de prepago: gastas lo que cargas y ni
   un céntimo más.
3. **Una cuenta en [Railway](https://railway.com)**, que es donde va a vivir el bot para
   que esté encendido siempre. Se puede empezar con su prueba gratuita de 30 días, que no
   pide tarjeta.

La guía paso a paso con capturas de cada pantalla está en
**[GUIA-DESPLIEGUE.md](GUIA-DESPLIEGUE.md)**.

## Lo que cuesta

Dos facturas independientes y las dos las controlas tú:

- **El servidor (Railway).** Alrededor de 1 $ al mes de consumo real. Su prueba gratuita
  da 5 $ y 30 días sin pedir tarjeta. Para mantenerlo después, su plan de pago son 5 $ al
  mes.
- **Las respuestas (Claude).** Depende de cuánto preguntéis y de cuánta documentación
  tengas cargada. El bot viene con un tope de 20 $ al mes que puedes subir o bajar con
  `/limite`, y con `/costes` ves en todo momento lo que llevas.

---

## La parte técnica

A partir de aquí es para quien quiera mirar cómo está hecho o cambiarlo. Si solo quieres
usarlo, con lo de arriba te sobra.

### Stack

| Componente | Tecnología |
|---|---|
| Runtime | Python 3.11+ (se despliega con 3.13) |
| Bot | `python-telegram-bot` v22, async, long polling |
| LLM | API de Claude con el SDK oficial `anthropic`, cliente `AsyncAnthropic` |
| Modelo | `claude-sonnet-5`, fijo |
| Voz | Whisper de OpenAI, opcional, llamado con `httpx` |
| Extracción de PDF | `pypdf`, y Claude como respaldo para los escaneados |
| Extracción de DOCX | `python-docx` |
| Hosting | Railway |
| Persistencia | Ficheros de texto plano en un volume. Sin base de datos |

### Cómo está montado

**Todo asíncrono.** Una llamada síncrona congelaría el bot para todos los usuarios durante
los diez o veinte segundos que tarda una respuesta. Lo que bloquea de verdad, que es la
extracción con `pypdf` y `python-docx`, se saca del hilo del bot con `asyncio.to_thread`.

**Prompt caching con TTL de una hora.** El system se construye en tres bloques, en este
orden, porque la caché funciona por prefijo:

1. Instrucciones fijas del asistente.
2. Configuración de la empresa.
3. El contenido de todos los documentos, cada uno precedido por `=== NOMBRE ===`.

El punto de corte va al final del bloque 3 y cachea todo el prefijo. Por eso los bloques 1
y 2 no pueden contener nada dinámico: ni una fecha, ni un contador, ni el nombre del
usuario, o la caché se invalidaría en cada pregunta. Por el mismo motivo los documentos se
concatenan siempre en orden alfabético: un solo byte distinto en el prefijo tira la caché
entera, sin dar ningún error.

**Sin base de datos.** Todo vive en ficheros de texto plano dentro de un único volume
montado en `/app/data`:

```
/app/data/
├── knowledge/          el texto extraído de cada documento, en .txt
├── config.txt          configuración de la empresa y el código de acceso
├── autorizados.txt     quién tiene acceso
├── bloqueos.json       límites por hora y bloqueos por códigos fallidos
├── uso.json            gasto acumulado del mes
├── documentos.json     tokens, fecha y origen de cada documento
└── access.log          registro de accesos e intentos
```

El volume se monta al arrancar el contenedor, no durante la construcción. Por eso el
arranque comprueba que existe todo y lo crea con valores por defecto si no: es idempotente
y tolera un volume completamente vacío.

**Escrituras atómicas.** Varios handlers pueden escribir a la vez en `uso.json` y
`bloqueos.json`. Van con `asyncio.Lock` y escritura atómica, porque un reinicio a mitad de
escritura dejaría un JSON truncado que impediría arrancar.

**Seguridad.** Código de acceso de 6 caracteres alfanuméricos sin ambigüedades (fuera la I,
la l, el 1, la O y el 0), guardado como hash SHA-256 con salt. El rate limiting se persiste
en disco y nunca en memoria, porque los contenedores se reinician. Los ficheros originales
se descartan en cuanto se extrae el texto. Y el contenido de los documentos se trata
siempre como datos y nunca como instrucciones: el system lleva una línea explícita que
descarta cualquier instrucción que aparezca dentro de un documento.

### Estructura de ficheros

| Fichero | Qué hace |
|---|---|
| `bot.py` | Arranque, registro de handlers y `main` |
| `ajustes.py` | Variables de entorno, precios y constantes |
| `almacen.py` | El volume, el arranque idempotente y la escritura atómica |
| `acceso.py` | Códigos, hash, autorizados, bloqueos y el registro de accesos |
| `claude_api.py` | Cliente compartido, conteo de tokens, PDF escaneados, fotos y voz |
| `extraccion.py` | PDF, DOCX, TXT, CSV, MD y saneado de nombres |
| `consulta.py` | El system en tres bloques, la caché y el historial |
| `costes.py` | Contabilidad del gasto, tope mensual y aviso al 80% |
| `limites.py` | Preguntas por hora y bloqueo por códigos fallidos |
| `copia.py` | El ZIP de seguridad y cuándo mandarlo solo |
| `menu.py` | El teclado de botones y el menú de comandos |
| `comandos.py` | Los comandos y la recepción de ficheros |
| `comun.py` | Responder, listar documentos y la señal de "escribiendo" |
| `textos.py` | Todos los mensajes del bot, en un solo sitio |
| `pruebas/` | Tests de la lógica, sin red ni credenciales |

Los mensajes del bot viven todos en `textos.py` a propósito, para poder cambiar cómo habla
sin tocar la lógica.

### Variables de entorno

Obligatorias:

| Variable | Descripción |
|---|---|
| `TELEGRAM_TOKEN` | El token que da @BotFather |
| `ANTHROPIC_API_KEY` | La clave de console.anthropic.com |

Opcionales:

| Variable | Defecto | Descripción |
|---|---|---|
| `OWNER_CHAT_ID` | vacío | Si se rellena, fija el administrador y desactiva el alta automática |
| `LIMITE_MENSUAL_USD` | `20` | Tope de gasto mensual |
| `LIMITE_PREGUNTAS_HORA` | `20` | Tope de preguntas por usuario y hora. El administrador queda exento |
| `CACHE_TTL` | `1h` | Duración de la caché de documentos |
| `RUTA_DATOS` | `/app/data` | En local se apunta a `./data` |
| `OPENAI_API_KEY` | vacío | Si está, se transcriben las notas de voz |

### Levantarlo en local

```bash
git clone https://github.com/FunnelCracks/empleado-digital-telegram.git
cd empleado-digital-telegram
python -m venv .venv
.venv/Scripts/activate        # en Linux y Mac: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.local    # y rellenas las dos claves
python bot.py
```

Las pruebas:

```bash
python -m unittest discover -s pruebas -v
```

No tocan la red ni gastan créditos.

Un aviso que ahorra un rato de desconcierto: Telegram no permite que dos procesos pidan
mensajes a la vez con el mismo token. Si tienes el bot desplegado y lo arrancas también en
local con el mismo token, los dos empiezan a fallar. Para trastear en local, crea un
segundo bot en @BotFather.
