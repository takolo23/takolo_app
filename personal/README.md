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

La carpeta definida por `PERSONAL_DATA_DIR`, por defecto `/workspace/.personal-app`, contiene:

- `accounts.sqlite3`: identidades, contraseñas con hash, roles, estados y asociación exclusiva de los números.
- `personal.sqlite3`: cartera del primer administrador o espacio personal anterior conservado.
- `workspace-<id>.sqlite3`: base independiente de cada usuario posterior, con clientes, pagos, archivos temporales, autorizaciones, mensajes y conexión cifrada.
- `session.key`: firma de las sesiones.
- `connections.key`: clave maestra del cifrado de conexiones. Perderla impide recuperar las credenciales cifradas.

Conserva **toda la carpeta** en un volumen persistente y realiza respaldos privados. Para un respaldo completo coherente entre cuentas, detén web y trabajador y copia la carpeta completa incluyendo ambas claves. No copies solo una base de cartera. Para restaurar, detén los procesos y restaura el conjunto completo. No subas bases ni claves a GitHub ni las envíes por chat.

La migración conserva el espacio personal anterior, si existía, bajo el usuario `principal` y la contraseña anterior. No elimina clientes, pagos ni historial. Si la plataforma ya tenía identidades, no crea otra cuenta por la presencia de la tabla histórica. Las conexiones nuevas se configuran por cuenta; no se reparten credenciales del servidor.

## Verificación

```bash
cd /workspace/takolo_app
/workspace/.setup/personal/bin/python -m unittest discover -s personal/tests -v
```

39 pruebas verifican cartera, autenticación, pagos, importaciones, exportación, simulaciones, firmas y estados de WhatsApp, aislamiento entre cuentas, credenciales cifradas, roles, suspensión y migración. Los resultados de Meta son fixtures simulados: no se verificó un envío real.

## Publicación

`render.yaml` propone una sola instancia con volumen persistente de 1 GB y HTTPS. El plan con disco puede tener coste. No hay una web pública creada ni una cuenta de alojamiento conectada. La rama de despliegue es `codex/takolo-multiusuario`; selecciónala al conectar el repositorio en el alojamiento. Antes de un lanzamiento público se deben verificar el alojamiento real, respaldos, cuotas/capacidad y los requisitos de la conexión oficial para cada usuario. Publicar el entorno de desarrollo no publica la aplicación en Internet.
