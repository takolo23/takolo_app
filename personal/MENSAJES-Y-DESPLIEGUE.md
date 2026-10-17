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

## Alojamiento

El despliegue propuesto en `render.yaml` usa una instancia web con trabajador en segundo plano y un disco de 1 GB en `/data`. Ambos procesos se supervisan juntos mediante `personal/serve.sh`. La web expone `/healthz`. Se conserva el almacenamiento tras reiniciar el contenedor.

Variables globales:

- `PERSONAL_DATA_DIR=/data`: carpeta persistente completa.
- `TAKOLO_TRUST_PROXY=1`: confiar en un único proxy que normalice las cabeceras de dirección y protocolo; usar solo detrás del proxy del alojamiento.
- `PERSONAL_HTTPS=1`: cookies que solo se envían por HTTPS.
- `PERSONAL_SETUP_TOKEN`: código privado de activación del primer administrador; el blueprint lo genera.
- `TAKOLO_REGISTRATION_OPEN=1`: registro público después de crear la administración. Usar `0` para cerrar nuevas altas.
- `WHATSAPP_SEND_ENABLED=0`: simulaciones por defecto. Solo habilitar después de completar las verificaciones necesarias.

Las credenciales de cada usuario se introducen en **Mi conexión**, no en variables globales de Meta ni en el chat. El volumen debe conservar `accounts.sqlite3`, todas las bases de los espacios, `session.key` y `connections.key`. Sigue el respaldo completo explicado en README.

La plataforma sigue sin alojamiento público ni acceso a una cuenta del proveedor. El manifiesto puede requerir un plan de pago con disco persistente; no se ha contratado. Usa la rama `codex/takolo-multiusuario` y el archivo raíz `render.yaml` al crear el Blueprint. Una publicación real requiere cuenta de alojamiento, fuente accesible al proveedor y validación de HTTPS, permisos, registro, aislamiento, reinicios y respaldos allí. La incorporación automática de clientes de WhatsApp mediante Meta Embedded Signup requiere trabajo y aprobación adicionales; esta versión usa configuración manual.

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
