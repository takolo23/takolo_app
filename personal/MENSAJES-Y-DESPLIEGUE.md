# Mensajería por usuario y despliegue web

## Lo que funciona en pruebas

Cada cuenta tiene su propia cola, autorizaciones, resultados y conexión. Las simulaciones no contactan a WhatsApp. El trabajador recorre las cuentas activas y procesa una solicitud por espacio en cada ronda. Un error de una cuenta no detiene deliberadamente el resto. La suspensión de una cuenta pausa su cola; una solicitud que ya alcanzó al proveedor no puede retirarse de forma retroactiva.

Las pruebas cubren autorización vinculada al número, teléfono internacional con `+`, deduplicación por lote, reenvío del formulario, estados independientes y bajas. Los resultados de aceptación/entrega y firmas se prueban con fixtures; todavía no se ha verificado ninguna entrega real.

## Conectar un número propio

Cada usuario entra en **Mi conexión** y guarda sus propios datos de WhatsApp Business Platform. No basta con escribir un teléfono personal. Esta versión requiere configuración manual de la API oficial y admite **una conexión por cuenta**, sin incorporación automática por QR ni Meta Embedded Signup.

Campos de cada cuenta:

| Campo | Uso |
| --- | --- |
| ID del número | `META_PHONE_NUMBER_ID` de Meta; no es el teléfono visible. |
| Versión de Graph | `META_GRAPH_VERSION`, la vigente para esa cuenta. No se inventa una versión predeterminada. |
| Plantilla aprobada e idioma | `META_TEMPLATE_NAME` y `META_TEMPLATE_LANGUAGE`. La plantilla debe tener exactamente una variable de cuerpo: el nombre del cliente, sin variables de encabezado/botones. |
| Token de acceso | `META_ACCESS_TOKEN` con permisos para ese número. |
| Secreto de la aplicación | `META_APP_SECRET` para comprobar firmas. |
| Token de verificación | `META_VERIFY_TOKEN`, un valor privado elegido para verificar el webhook. |

Todos estos datos se guardan cifrados en la base del espacio con Fernet. Los campos secretos nunca se devuelven al formulario; dejarlos vacíos conserva los valores existentes. No se reutilizan las variables `META_*` del servidor entre usuarios.

Después de guardar, **Comprobar mi número** realiza una consulta de solo lectura a Meta. Si responde el ID esperado, se vincula ese número a esa cuenta. Otro usuario no puede verificar el mismo ID mientras exista esa vinculación. Guardar cambios retira la verificación anterior. Desconectar retira las claves y cancela los envíos reales pendientes de ese usuario.

La dirección de confirmaciones es específica de cada cuenta:

```
https://TU-DOMINIO/webhooks/whatsapp/ID-DE-CUENTA
```

La pantalla muestra la dirección que corresponde. Configúrala en Meta para el campo `messages`, con el token de verificación propio. Los POST se validan con HMAC SHA-256 usando el secreto de esa cuenta y solo se procesan entradas cuyo ID de número coincida. No se usan la sesión ni las credenciales de otra cuenta para validar esa dirección.

Comprobar el número no acredita que la plantilla, la actividad ni el número personal sean elegibles para el uso previsto. La incorporación del número, los permisos y la aprobación se deben completar con Meta.

## Envíos

El envío real requiere simultáneamente:

1. Que la administración habilite `WHATSAPP_SEND_ENABLED=1` en el servidor.
2. Que el usuario haya guardado y verificado su propia conexión y active su opción de envío real.
3. Que los contactos hayan autorizado ese tipo de mensajes. Tener un teléfono en una cartera no es autorización.
4. Que el usuario seleccione los destinatarios y confirme expresamente un envío real.

El límite de esta versión es de 50 mensajes reales diarios UTC **por cuenta**, con hasta 50 destinatarios por lote y un mensaje por número en cada lote. Es un límite operativo, no un método para evitar bloqueos. Los límites y las políticas de Meta también aplican.

Los mensajes pendientes se vuelven a comprobar antes de enviar. Si cambia el teléfono o se retira la autorización, se cancelan. Las palabras `BAJA`, `STOP`, `CANCELAR`, `NO MAS` y `NO MÁS` recibidas mediante el webhook firmado retiran el permiso y cancelan pendientes para ese teléfono en el espacio correspondiente.

«Aceptado» no significa «entregado». La entrega y la lectura se confirman por eventos del proveedor, sin degradar un estado leído a enviado por un evento atrasado. Ante un HTTP 429 explícito hay hasta tres intentos separados por cinco minutos. Ante un timeout, error de red/servidor o interrupción con resultado incierto no se reenvía automáticamente; se debe revisar el resultado en Meta para evitar duplicados.

No se implementan rotación de números, automatización no oficial de sesiones ni escritura simulada para eludir restricciones. Escribir letra por letra no hace que una cuenta sea “inbaneable”. La aplicación maneja carteras: revisa las restricciones vigentes de WhatsApp sobre cobranza y servicios financieros antes de activar ese uso. El acceso a las páginas oficiales devolvió HTTP 403 desde este entorno; no se pudo revisar su contenido actual.

Fuentes oficiales: [Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started) y [políticas de WhatsApp](https://business.whatsapp.com/policy).

## Alojamiento gratuito

La propuesta actual en `render.yaml` es **Render Free**, sin disco de pago. Usa `DATABASE_URL` para PostgreSQL externo, como un proyecto Neon Free. La rama es `codex/takolo-multiusuario`. Las cuentas y sus datos ocupan esquemas independientes de PostgreSQL; el almacenamiento local de Render se puede borrar.

Variables globales del Blueprint:

- `DATABASE_URL`: cadena de conexión que se copia directamente de Neon a Render, sin pasar por el chat. El campo es obligatorio y secreto.
- `TAKOLO_REQUIRE_REMOTE_DB=1`: impide usar SQLite temporal si falta esa conexión.
- `TAKOLO_SESSION_SECRET` y `TAKOLO_ENCRYPTION_SECRET`: secretos generados automáticamente que deben mantenerse estables entre reinicios. Conserva también estas claves al respaldar o trasladar la base.
- `PERSONAL_DATA_DIR=/tmp/takolo`: únicamente espacio de trabajo temporal en este modo.
- `PERSONAL_HTTPS=1` y `TAKOLO_TRUST_PROXY=1`: cookies HTTPS y confianza en un único proxy normalizado del proveedor.
- `PERSONAL_SETUP_TOKEN`: código privado generado para el primer administrador.
- `TAKOLO_REGISTRATION_OPEN=1`: permite registros después de crear la administración.
- `WHATSAPP_SEND_ENABLED=0`: mantiene los envíos reales apagados.
- `TAKOLO_FREE_HOSTING=1`: muestra el aviso de disponibilidad limitada.

El plan Free puede dormirse por inactividad. El trabajador se pausa con el servicio, por lo que no se garantiza procesamiento o envío automático continuo 24/7. Al volver a arrancar, los pendientes siguen guardados en PostgreSQL; las solicitudes interrumpidas con resultado incierto no se reenvían a ciegas. No se implementan pings para evitar artificialmente el reposo del proveedor.

Para continuar, crea una base en [Neon](https://console.neon.tech/) eligiendo su plan Free. En Render, revisa o vuelve a cargar el Blueprint, comprueba que diga **Free** y que no incluya disco de pago, y pega la cadena de conexión de Neon en `DATABASE_URL`. El primer acceso requiere el código privado `PERSONAL_SETUP_TOKEN` generado en Render. Si un proveedor exige una verificación adicional o muestra un coste, compruébalo antes de aceptar: no se garantiza ausencia de verificación de tarjeta ni gratuidad fuera de las cuotas vigentes.

No se han creado cuentas externas ni servicios de pago. Los límites y condiciones vigentes de esos proveedores no se pudieron consultar desde la red restringida de este entorno. El despliegue público y una base Neon real siguen pendientes de las cuentas del usuario. Las tarifas de mensajes de Meta son independientes del alojamiento; no se ha enviado ningún mensaje real.

Los datos locales SQLite previos no se copian automáticamente al activar PostgreSQL. Para una instalación existente, prepara primero una migración con respaldo. Esta instalación de alojamiento aún no tenía usuarios creados.

## Contenedor y pruebas

```bash
cd /workspace/takolo_app
docker build -f Dockerfile.personal -t takolo .
docker run --rm -p 127.0.0.1:5204:8000 -v takolo-data:/data -e WHATSAPP_SEND_ENABLED=0 takolo
```

Si el entorno de construcción usa un proxy con CA propia, conserva la verificación TLS pasando su certificado público de confianza como secreto temporal:

```bash
docker build --secret id=build_ca,src="$SSL_CERT_FILE" -f Dockerfile.personal -t takolo .
```

La CA de construcción no queda incorporada en la imagen. El almacenamiento de prueba debe ser independiente del volumen real; no crees cuentas ni números ficticios dentro de espacios de usuarios reales.

## Validación de la versión multiusuario

Pasaron 39 pruebas automatizadas. En navegador, dos cuentas independientes verificaron registro, permisos de administración, carteras y conexiones separadas, secretos guardados que no se devolvieron al HTML, simulación automática, persistencia después de reiniciar, suspensión que invalida sesiones y vista móvil. La imagen final arrancó reutilizando el volumen de prueba y conservó usuarios, conexión cifrada y mensajes simulados. Los fixtures usaron un volumen independiente y no se añadieron a la plataforma real. No se verificaron un alojamiento público ni envíos reales.

## Verificación de PostgreSQL para el plan gratuito

Se añadieron pruebas con un PostgreSQL real aislado: registro/login, roles, importación y duplicados, pagos e historial, exportaciones, cantidades grandes, aislamiento de cuentas, claves estables al perder archivos locales, simulaciones en segundo plano y pagos concurrentes. También se comprueba el rechazo de una configuración sin base/secretos y la verificación TLS de servidores remotos.

Para ejecutarlas usa solo una base de prueba dedicada llamada `takolo_test` en loopback. La suite borra sus esquemas de prueba; rechaza una conexión remota o con otro nombre. No uses `DATABASE_URL` de producción al ejecutar las pruebas.

```bash
cd /workspace/takolo_app
TAKOLO_PG_TEST_URL=postgresql://postgres@127.0.0.1:55432/takolo_test /workspace/.setup/personal/bin/python -m unittest discover -s personal/tests -p test_postgres.py -v
```

Las pruebas locales no sustituyen la comprobación de TLS, permisos, cuotas y persistencia en una base externa real después de conectarla.

La conexión remota usa `verify-full` y el archivo de certificados resuelto por `ssl.get_default_verify_paths().cafile`. No usa `sslrootcert=system`: OpenSSL incluido en `psycopg-binary` puede buscar ese almacén en una ruta de la máquina donde se compiló. Si falta el archivo de confianza, la aplicación rechaza el arranque. Una prueba TLS con PostgreSQL aislado verificó conexión con CA válida y rechazo de certificados sin confianza o con otro nombre de servidor.

Resultado de esta adaptación: 51 pruebas ejecutadas y aprobadas, incluida la base PostgreSQL real local. La imagen final arrancó con dos cuentas y se comprobó en navegador que borrar la carpeta local y reiniciar conserva usuarios, clientes, mensajes y conexiones cifradas. La prueba incluyó aislamiento, permisos, suspensión de sesiones y vista móvil. No se observó ningún error del servidor ni de JavaScript. Esto no acredita una conexión Neon real ni un despliegue público; ambos siguen pendientes de la cuenta externa del usuario.
