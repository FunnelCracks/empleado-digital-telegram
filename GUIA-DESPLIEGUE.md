# Cómo montar tu Empleado Digital, paso a paso

En unos 10 minutos vas a tener un bot de Telegram que responde a tu equipo con lo que pone
en la documentación de tu empresa. No hace falta saber programar ni instalar nada en tu
ordenador. Todo se hace desde el navegador y desde el Telegram de tu móvil.

Son cuatro pasos:

1. Crear el bot en Telegram (2 minutos)
2. Sacar tu clave de Claude, que es la inteligencia que responde (3 minutos)
3. Encender el bot en Railway, que es donde va a vivir (3 minutos)
4. Hablar con él por primera vez y darle tus documentos (2 minutos)

Si en algún momento algo no sale como aquí se cuenta, salta a
[Si algo no sale como esperabas](#si-algo-no-sale-como-esperabas). Ahí están los atascos
más habituales y cómo salir de cada uno.

---

## Antes de empezar

Ten a mano:

- **Un ordenador** con el navegador abierto. Se puede hacer desde el móvil, pero copiar y
  pegar claves largas en una pantalla pequeña es donde más se equivoca la gente.
- **Tu móvil con Telegram.**
- **Una tarjeta** para cargar saldo en Claude. Es prepago: gastas lo que cargas y ni un
  céntimo más.
- **Una nota en blanco** (el Bloc de notas, una nota del móvil, lo que uses). Vas a sacar
  dos claves largas y conviene pegarlas ahí según las consigues, para no perderlas. Cuando termines, bórralas de la nota.

---

## Paso 1. Crea tu bot en Telegram

Los bots de Telegram se crean hablando con otro bot, uno oficial que se llama
**BotFather**.

1. Abre Telegram y busca **@BotFather**. Tiene una marca azul de verificado al lado del
   nombre. Si no la tiene, no es el bueno.

   > 📸 **[CAPTURA 01]** Buscador de Telegram con @BotFather y la marca azul de verificado.

2. Entra y pulsa **Iniciar** (o escribe `/start`).
3. Escribe `/newbot`.
4. Te pregunta el **nombre** del bot. Es el que verá tu equipo, así que pon algo
   reconocible, por ejemplo `Asistente de Talleres García`.
5. Te pregunta el **nombre de usuario**. Este tiene que ser único en todo Telegram,
   sin espacios, y **terminar en `bot`**. Por ejemplo `talleresgarcia_bot`.

   > 📸 **[CAPTURA 02]** Conversación con BotFather: /newbot, el nombre y el nombre de usuario.

6. Si el nombre está libre, BotFather te felicita y te da un **token**. Es una línea
   larga con esta pinta:

   ```
   7412345678:AAHd8kLm...
   ```

   Números, dos puntos y un montón de letras. **Cópialo entero y pégalo en tu nota.**

   > 📸 **[CAPTURA 03]** Mensaje de BotFather con el token, señalando qué parte hay que copiar.

> 🔐 **Ese token es la llave de tu bot.** Quien lo tenga puede hacerse pasar por él. No lo
> mandes por WhatsApp ni lo pegues en ningún sitio que no sea el que te dice esta guía.

---

## Paso 2. Saca tu clave de Claude

Claude es la inteligencia artificial que lee tus documentos y responde. Se paga por uso,
y para usarlo necesitas una clave.

1. Entra en **[console.anthropic.com](https://console.anthropic.com)** y crea una cuenta.
   Te pedirá tu correo y te mandará un enlace para entrar.

   > 📸 **[CAPTURA 04]** Pantalla de registro de console.anthropic.com.

2. **Carga saldo.** En el menú busca **Billing** (facturación) y añade crédito. Con 10
   dólares tienes para empezar con holgura.

   > 📸 **[CAPTURA 05]** Pantalla de Billing con el botón para añadir crédito.

   Un consejo: si te ofrece **recarga automática** (*auto-reload*), déjala desactivada.
   Así nunca se gasta más de lo que tú has cargado a mano. El bot, además, trae su propio
   tope de gasto mensual.

3. Ve a **API Keys** y pulsa **Create Key**. Ponle un nombre que te diga para qué es, por
   ejemplo `empleado digital`.

   > 📸 **[CAPTURA 06]** Pantalla de API Keys con el botón Create Key.

4. Te enseña la clave. Empieza por **`sk-ant-`** y es muy larga. **Cópiala entera y
   pégala en tu nota ahora mismo**: esta pantalla solo te la enseña una vez. Si la
   cierras sin copiarla, no pasa nada, borras esa y creas otra.

   > 📸 **[CAPTURA 07]** La clave recién creada, con el botón de copiar señalado.

Ahora en tu nota tienes dos cosas:

| | Cómo se reconoce |
|---|---|
| El token de Telegram | Empieza por **números y dos puntos** |
| La clave de Claude | Empieza por **`sk-ant-`** |

---

## Paso 3. Enciende el bot en Railway

Railway es un servicio que mantiene tu bot encendido las 24 horas, sin que tengas que
dejar ningún ordenador encendido.

1. Pulsa este botón:

   [![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/MyZtQB?referralCode=ia_para_empresarios&utm_medium=integration&utm_source=template&utm_campaign=generic)

   Si el botón no se ve, entra en este enlace:
   **[Montar mi Empleado Digital en Railway](https://railway.com/deploy/MyZtQB?referralCode=ia_para_empresarios&utm_medium=integration&utm_source=template&utm_campaign=generic)**

2. Railway te pide entrar. Puedes crear la cuenta con tu correo o con una cuenta de
   GitHub si ya tienes una.

   > 📸 **[CAPTURA 08]** Pantalla de registro de Railway.

   Las cuentas nuevas empiezan con una **prueba gratuita de 30 días y 5 dólares de
   crédito, sin pedir tarjeta**. Te sobra para ese mes. Más abajo te cuento qué hacer
   cuando se acabe.

3. Llegas a un formulario que te pide **dos cosas**. Pega cada una de tu nota:

   | Casilla | Qué pegas |
   |---|---|
   | `TELEGRAM_TOKEN` | El token de Telegram (el de los números y dos puntos) |
   | `ANTHROPIC_API_KEY` | La clave de Claude (la de `sk-ant-`) |

   > 📸 **[CAPTURA 09]** Formulario de la plantilla con las dos casillas.

   Al pegar, fíjate en dos cosas, que son las que fallan casi siempre:
   - Que no se haya quedado un **espacio** delante o detrás.
   - Que esté **entera**. Al copiar claves tan largas es facilísimo dejarse el final.

4. Pulsa **Deploy**.

5. Railway empieza a montar el bot. Tarda **dos o tres minutos**. Verás un recuadro con
   el nombre del servicio. Espera a que se ponga en verde y diga **Active** (o
   **Online**).

   > 📸 **[CAPTURA 10]** El servicio en verde y en marcha.

   Si en vez de verde se pone en rojo, ve a
   [El servicio sale en rojo](#el-servicio-sale-en-rojo-en-railway).

---

## Paso 4. Habla con tu bot por primera vez

> ⚠️ **Haz este paso tú, y antes que nadie.** La primera persona que le escribe al bot se
> queda como su administrador: la que sube documentos, reparte el acceso y controla el
> gasto. No compartas el bot con nadie hasta haber terminado este paso.

1. En Telegram, busca tu bot por el nombre de usuario que le pusiste en el paso 1 (el que
   termina en `bot`). BotFather también te dejó un enlace directo, `t.me/...`, en el
   mensaje del token.
2. Pulsa **Iniciar**.
3. El bot te responde que ya eres el administrador, te enseña un aviso sobre protección
   de datos y te da el **código de acceso** para tu equipo: seis letras y números.

   > 📸 **[CAPTURA 11]** El mensaje de bienvenida del administrador con el código de acceso.

   **Guarda ese código.** Es lo que vas a repartir a tu gente. Si lo pierdes no pasa
   nada, con `/codigo` sacas uno nuevo.

4. **Mándale un documento.** Un catálogo, una tarifa, un manual. Se lo mandas como
   mandarías cualquier fichero por Telegram, con el clip. Acepta PDF, Word, texto, CSV y
   fotos de documentos.

   > 📸 **[CAPTURA 12]** El bot confirmando que ha guardado el documento.

5. **Pregúntale algo** que esté en ese documento, escrito normal, como se lo preguntarías
   a un compañero.

   > 📸 **[CAPTURA 13]** Una pregunta y la respuesta del bot.

**Ya está. Tu Empleado Digital está funcionando.**

---

## Dos trucos para que sepa más

**¿Tienes tienda online? Mándale tu catálogo en CSV.** Shopify, WooCommerce, PrestaShop
y casi todas las plataformas de tienda tienen una opción para **exportar los productos**
a un fichero CSV. Descárgalo y mándaselo al bot como cualquier otro documento. Así sabrá
tus productos con sus precios y referencias, mucho mejor que si leyera la tienda página a
página.

**¿Quieres que sepa lo que pone en tu web? Pégale la dirección.** Copia la dirección de
la página desde el navegador y pégasela al bot en el chat, sin escribir nada más. Si son
varias, una por línea. El bot la lee, te cuenta en unas frases lo que ha entendido para
que compruebes que está bien, y la guarda como un documento más. Elige las páginas que
tengan información útil para tu equipo: servicios, precios, preguntas frecuentes,
envíos, garantías...

Algunas webs no se dejan leer: las privadas, las que se protegen contra robots y
algunas muy modernas. Si te pasa, el bot te lo dirá. Entonces abre la página en el
navegador del ordenador, pulsa **Imprimir** (Control + P, o Cmd + P en Mac) y, donde se
elige la impresora, escoge **Guardar como PDF**. Ese PDF se lo mandas al bot y listo.

---

## Dale acceso a tu equipo

A cada persona que quieras que lo use, mándale dos cosas:

1. El enlace del bot (`t.me/el_nombre_de_tu_bot`).
2. El código de acceso.

Cuando abran el bot, les pedirá el código. Lo escriben una vez y ya pueden preguntar
todo lo que quieran.

> 📸 **[CAPTURA 14]** Lo que ve un empleado: el bot pidiendo el código y dándole acceso.

Si algún día quieres quitarle el acceso a alguien, escribe `/usuarios` y pulsa en su
nombre. Y si quieres cerrar la puerta a cualquiera que se sepa el código actual, saca
uno nuevo con `/codigo`: quien ya estaba dentro sigue dentro, y los nuevos necesitarán
el código nuevo.

---

## Lo que cuesta y cómo lo controlas

Tienes dos facturas, las dos independientes y las dos en tus manos.

**Railway, el sitio donde vive el bot.** El consumo real ronda 1 dólar al mes. Los
primeros 30 días entran en la prueba gratuita. Cuando se acaben, para que el bot siga
encendido tienes que pasarte a su plan **Hobby**, que son **5 dólares al mes**. Railway
te avisa por correo antes de que termine la prueba.

> 📸 **[CAPTURA 15]** Dónde se cambia al plan Hobby en Railway.

**Claude, las respuestas.** Depende de cuánto pregunte tu equipo y de cuánta
documentación tengas cargada. Cuando subes un documento, el bot ya te dice más o menos
lo que te va a costar cada pregunta.

Para no llevarte sustos:

- El bot viene con un **tope de 20 dólares al mes**. Al llegar al 80% te avisa, y al 100%
  deja de responder hasta el día 1, que el contador se pone a cero solo.
- Con `/costes` ves en cualquier momento lo que llevas gastado y lo que vas a gastar a
  final de mes al ritmo que vas.
- Con `/limite` cambias el tope. Por ejemplo, `/limite 30` lo pone en 30 dólares.
- Cuanta más documentación cargada, más cuesta cada pregunta. Si hay algo que ya no usas,
  quítalo con `/borrar`.

---

## Tus documentos están a salvo

Cada vez que cambias la documentación, el bot te manda por Telegram una **copia de
seguridad** en un fichero ZIP, como mucho una vez al día. No tienes que hacer nada: con
dejarla en el chat es suficiente, Telegram no la borra. Si algún día la quieres al
momento, escribe `/backup`.

> ### ⚠️ Sobre los datos que subes
>
> Este bot envía el contenido de tus documentos a la API de Claude para poder responder.
> No subas datos personales de clientes, empleados o terceros (DNI, nóminas, historiales,
> datos de salud) sin haber verificado antes tu base legal para ello. Sube catálogos,
> tarifas, procedimientos, manuales y documentación interna.

---

## Si algo no sale como esperabas

Busca aquí lo que te está pasando. Casi todo se arregla en un minuto.

### En Telegram, al crear el bot

**BotFather dice que el nombre de usuario ya está cogido** (*Sorry, this username is
already taken*). Prueba con otro. Añadir el nombre de tu ciudad o un número suele bastar:
`talleresgarcia_madrid_bot`.

**BotFather dice que el nombre de usuario no es válido.** Tiene que terminar en `bot`, no
puede llevar espacios ni tildes, y solo admite letras, números y guion bajo.

**He perdido el token.** Escribe a BotFather `/mybots`, elige tu bot y pulsa **API
Token**. Te lo vuelve a enseñar.

**Se me ha escapado el token** (lo he mandado a alguien, lo he pegado donde no era). En
BotFather: `/mybots`, tu bot, **API Token** y **Revoke current token**. Te da uno nuevo y
el viejo deja de valer. Luego cambia el token en Railway, como se explica
[más abajo](#cómo-cambiar-una-clave-en-railway).

### En Claude, al sacar la clave

**No encuentro dónde se crea la clave.** Está en el menú de la izquierda, en **API Keys**.
Si no ves ese menú, puede que te falte terminar de crear la cuenta o de cargar saldo.

**He cerrado la pantalla sin copiar la clave.** No se puede volver a ver, pero no pasa
nada: bórrala y crea otra.

### En Railway, al encenderlo

#### El servicio sale en rojo en Railway

Casi siempre es que alguna de las dos claves está mal pegada. Para verlo:

1. Pulsa en el servicio y entra en la pestaña **Deployments**.
2. Abre el último y mira los mensajes (*logs*).

> 📸 **[CAPTURA 16]** Dónde se ven los logs de un despliegue en Railway.

- Si pone **"No puedo arrancar porque faltan estas variables"**, te has dejado alguna
  casilla vacía. Rellénala como se explica
  [más abajo](#cómo-cambiar-una-clave-en-railway).
- Si pone algo de **token** o **Unauthorized**, el token de Telegram está mal copiado.
  Vuelve a copiarlo de BotFather y pégalo otra vez.

#### Cómo cambiar una clave en Railway

1. Pulsa en el servicio y ve a la pestaña **Variables**.
2. Busca la que quieres cambiar, pulsa en los tres puntos y **Edit**.
3. Pega el valor bueno y guarda.
4. Railway te pedirá aplicar los cambios (**Deploy**). Pulsa y espera a que se ponga en
   verde otra vez.

> 📸 **[CAPTURA 17]** La pestaña Variables con el menú para editar una variable.

### Hablando con el bot

**El bot no contesta nada.** Mira en Railway que el servicio esté en verde. Si está en
rojo, mira [aquí](#el-servicio-sale-en-rojo-en-railway). Si está en verde y acabas de
cambiar algo, dale un par de minutos.

**Le escribo pero me pide un código de acceso.** Alguien le escribió antes que tú y se ha
quedado como administrador. Si has sido tú desde otra cuenta, entra con esa. Si no sabes
quién ha sido, ve a [Empezar de cero](#empezar-de-cero).

**Me dice que la clave de Claude no es válida.** La clave está mal pegada en Railway. Tiene
que empezar por `sk-ant-` y estar entera, sin espacios. Cámbiala
[así](#cómo-cambiar-una-clave-en-railway).

**Me dice que se ha quedado sin saldo.** Entra en console.anthropic.com, en **Billing**, y
carga crédito. En cuanto lo hagas vuelve a funcionar, no hay que tocar nada más.

**Me dice que he llegado a mi tope de gasto.** Es el tope del propio bot, para protegerte.
Súbelo con `/limite 40` (o la cifra que quieras) o espera al día 1.

**Me dice que el fichero pesa demasiado.** Telegram no deja pasar ficheros de más de
20 MB. Parte el PDF en dos y mándalo en dos veces.

**Me dice que no sabe leer ese tipo de fichero.** Pásalo a PDF o a Word y vuelve a
mandarlo.

**Le pregunto algo y me dice que no está en la documentación.** Es a propósito: prefiere
decirte que no lo sabe antes que inventárselo. Revisa con `/docs` que el documento que lo
explica esté cargado.

**Me he olvidado del código de acceso.** Escribe `/codigo` y te da uno nuevo. La gente que
ya tenía acceso lo conserva.

**A un empleado le dice que ha fallado el código cinco veces.** Se le bloquea una hora
por seguridad. Pásale el código correcto y que lo intente pasado ese rato.

### Empezar de cero

Si quieres borrarlo todo y que el bot vuelva a estar como el primer día (sin documentos,
sin usuarios y sin administrador), hay que vaciar su disco en Railway:

1. En tu proyecto de Railway, pulsa en el **volume**, el recuadro pequeño pegado al
   servicio.
2. Ve a **Settings** y pulsa **Wipe Volume**.
3. Confirma.

> 📸 **[CAPTURA 18]** El botón Wipe Volume en los ajustes del volume.

El bot se reinicia vacío. Escríbele `/start` y volverás a ser el administrador.

> Ojo, que esto no tiene vuelta atrás. Si tienes una copia de seguridad en el chat, los
> documentos los puedes recuperar después: el ZIP lleva dentro un `LEEME.txt` que explica
> cómo.

### Extra: que entienda notas de voz

Es opcional. Si quieres que tu equipo le pueda preguntar con notas de voz, necesitas una
clave de OpenAI (se saca en [platform.openai.com](https://platform.openai.com), igual que
la de Claude, y también es de prepago).

Cuando la tengas, en Railway ve a la pestaña **Variables** del servicio, pulsa **New
Variable**, pon como nombre `OPENAI_API_KEY` y como valor tu clave. Guarda y aplica los
cambios. Sin esta clave el bot funciona igual, solo que a las notas de voz responde
pidiendo que se lo escriban.

---

## ¿Sigues atascado?

Escríbenos en [CANAL-DE-DUDAS] contándonos en qué paso estás y qué ves en la pantalla.
Si puedes, manda una captura: ayuda muchísimo. **Nunca mandes tus claves ni tu token**,
ni siquiera a nosotros. Para ayudarte no nos hacen falta.
