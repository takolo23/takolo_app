# TAKOLO · plataforma con espacios independientes

Aplicación web con registro e inicio de sesión por usuario. Cada cuenta tiene cartera, pagos, historial, importaciones, mensajes y una conexión oficial de WhatsApp propios. El primer usuario es administrador de la plataforma; las demás cuentas son usuarios. La administración habilita o suspende accesos y no dispone de un visor de las carteras ajenas.

Esta versión reemplaza la limitación de una sola cuenta de TAKOLO Personal. Los nombres históricos `personal/`, `requirements-personal.txt` y `Dockerfile.personal` se conservan para no romper el arranque. `render.yaml` prepara el despliegue de la rama `codex/takolo-multiusuario`.

## Arranque

Desde `/workspace/takolo_app`:

```bash
UV_CACHE_DIR=/workspace/.setup/uv-cache uv venv --allow-existing /workspace/.setup/personal
UV_CACHE_DIR=/workspace/.setup/uv-cache uv pip install --python /workspace/.setup/personal/bin/python -r requirements-personal.txt
source /workspace/.setup/personal/bin/activate
bash personal/serve.sh
```

El script inicia la web y un solo trabajador para las colas. Usa `PORT`, por defecto 8000. Para iniciar solo la web en desarrollo:

```bash
/workspace/.setup/personal/bin/gunicorn --bind 127.0.0.1:5200 'personal.app:create_app()'
```

Inicia aparte `/workspace/.setup/personal/bin/python -m personal.worker` si necesitas el procesamiento automático. No ejecutes varios trabajadores contra el mismo almacenamiento.

## Cuentas y permisos

1. El primer acceso dirige a `/setup` para crear al administrador inicial. Si está configurado `PERSONAL_SETUP_TOKEN`, debes introducir el código privado del alojamiento. No compartas este código con los usuarios.
2. Después, `/register` permite que cada persona cree su propio usuario, nombre y contraseña de al menos 10 caracteres. Los usuarios se normalizan a minúsculas y son únicos. `TAKOLO_REGISTRATION_OPEN=0` permite cerrar nuevas altas sin bloquear accesos existentes.
3. Todos inician sesión con usuario y contraseña. El registro no concede privilegios administrativos aunque alguien los intente enviar en el formulario.
4. El administrador dispone de **Usuarios** para habilitar o suspender cuentas. Suspender invalida sus sesiones y pausa el procesamiento de su cola. Habilitar no restaura las sesiones antiguas: se debe iniciar sesión otra vez.
5. Cada usuario administra **Mi conexión**. Las claves no se muestran después de guardarlas y se cifran en el almacenamiento. No se heredan credenciales globales del servidor ni de otro usuario.

Por ahora no hay equipos con carteras compartidas, acceso por Google/Facebook, recuperación de contraseña por correo ni incorporación automática de números con Meta Embedded Signup. Hay una conexión oficial por usuario. No se ha realizado una auditoría externa ni una prueba de carga para un servicio público de gran escala.

## Cartera

- Importa `.xlsx`, `.xls` o `.csv`, hasta 10 MB, 20,000 filas y 100 columnas. La primera fila debe contener los encabezados. Puedes elegir la hoja de Excel; de lo contrario se usa la primera con datos.
- Relaciona las columnas de nombre y saldo, obligatorias. Referencia, teléfono, gestor y estado son opcionales. Revisa la vista previa y selecciona gestor y cuentas activas antes de confirmar.
- Las referencias existentes se omiten para conservar los pagos. Si no hay referencia, se genera a partir del nombre y teléfono. Usa referencias estables si una persona tiene varios créditos.
- Los importes no válidos detienen el lote antes de guardar clientes y se muestran las filas por corregir.
- Busca por nombre, referencia o teléfono y filtra por gestor o estado. CSV y Excel descargan solamente la selección del usuario actual.
- La ficha de cliente permite editar contacto/notas y registrar pagos en MXN. Los pagos se calculan en centavos, no pueden superar el saldo y no se duplican al reenviar el mismo formulario. No hay anulación de pagos en esta versión: revisa el monto antes de confirmar.
- El historial conserva altas, importaciones, modificaciones y pagos; las horas se muestran en Ciudad de México.

## Mensajes

Consulta [Mensajes y despliegue web](MENSAJES-Y-DESPLIEGUE.md). El modo inicial es simulación: no envía mensajes. Cada número debe ser compatible con el registro oficial de WhatsApp; abrir una cuenta o escribir un teléfono personal no lo conecta automáticamente. Ningún sistema garantiza evitar bloqueos.

## Almacenamiento y respaldo

La aplicación admite dos modos:

**Desarrollo local sin `DATABASE_URL`:** usa SQLite dentro de `PERSONAL_DATA_DIR`, con identidades en `accounts.sqlite3`, la primera cartera en `personal.sqlite3` y otras carteras en `workspace-<id>.sqlite3`. Las claves están en `session.key` y `connections.key`. Respalda el conjunto completo de forma privada con web y trabajador detenidos. La migración de la versión personal conserva su usuario `principal` y su contraseña anterior.

**Alojamiento gratuito con `DATABASE_URL`:** usa PostgreSQL externo. Cada espacio ocupa un esquema generado por el servidor y las identidades otro esquema independiente. El disco de Render es temporal; no se usa para conservar los datos. `TAKOLO_SESSION_SECRET` y `TAKOLO_ENCRYPTION_SECRET` son secretos estables del alojamiento y deben conservarse junto con los respaldos PostgreSQL. No los regeneres si ya existen conexiones cifradas. Los archivos temporales locales pueden desaparecer sin perder las cuentas, los pagos o las conexiones.

`TAKOLO_REQUIRE_REMOTE_DB=1` impide arrancar si falta la base externa; no hay una caída silenciosa a SQLite temporal. Si existen datos previos en SQLite, configurarle otra base no los migra automáticamente: hay que preparar una migración y respaldo antes de cambiar el almacenamiento. La instancia de alojamiento aún no tenía cuentas creadas.

Las conexiones remotas PostgreSQL verifican el certificado y el nombre del servidor por TLS. Solo las instancias de prueba aisladas en loopback permiten comunicación local sin TLS. No subas bases, claves ni `DATABASE_URL` a GitHub ni al chat.

## Verificación

```bash
cd /workspace/takolo_app
/workspace/.setup/personal/bin/python -m unittest discover -s personal/tests -v
```

Las pruebas de SQLite verifican cartera, autenticación, pagos, importaciones, exportación, simulaciones, firmas y estados de WhatsApp, aislamiento entre cuentas, credenciales cifradas, roles, suspensión y migración. Sin TAKOLO_PG_TEST_URL se omiten las 9 pruebas de integración PostgreSQL. En esta tarea pasaron 51 pruebas, todas ejecutadas, contra SQLite y PostgreSQL local aislado. Los resultados de Meta son fixtures simulados: no se verificó un envío real.

## Publicación gratuita

`render.yaml` usa **Render Free sin disco de pago**, con una base PostgreSQL externa (por ejemplo, un proyecto **Neon Free**). Antes de confirmar, revisa que ambos proveedores muestren su plan gratuito; las cuotas y condiciones pueden cambiar. Esta aplicación no contrata servicios ni evita las verificaciones que cada proveedor pueda exigir.

1. Crea un proyecto PostgreSQL gratuito en [Neon](https://console.neon.tech/), preferiblemente dedicado a esta aplicación.
2. Copia su cadena de conexión en el campo **DATABASE_URL de Render**, nunca en el chat.
3. En el Blueprint selecciona el repositorio `takolo23/takolo_app`, rama `codex/takolo-multiusuario`, archivo `render.yaml`. Pulsa **Retry** si aún muestra la configuración anterior de pago.
4. Confirma que el servicio muestre **Free** y que no aparezca un disco persistente de pago. Conserva las claves generadas automáticamente.
5. Cuando la web esté disponible, crea al administrador con el código generado en `PERSONAL_SETUP_TOKEN` dentro de las variables de Render.

La web gratuita puede dormirse por inactividad y tardar en despertar. El trabajador solo funciona mientras el servicio está activo: **no ofrece envíos de mensajes continuos las 24 horas**. Los datos pendientes quedan en PostgreSQL. Las cuotas gratuitas pueden suspender el servicio al agotarse; no se ha validado una capacidad de producción a gran escala. Las tarifas de WhatsApp son independientes; el envío real sigue apagado.

La configuración está publicada en la rama de despliegue. No se ha creado ni conectado todavía una base Neon real ni se ha comprobado una URL pública del alojamiento. Publicar el entorno de desarrollo no publica la web.
