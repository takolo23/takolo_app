# Fase 1: estructura y persistencia

Este proyecto se despliega desde el repositorio `takolo_app` con directorio base
`whatsapp-netlify` y archivo `whatsapp-netlify/netlify.toml`. No modifica la
aplicación Flask/Render. Usa Node 20.19 o superior dentro de la rama 20.

## Directorios

| Ruta | Responsabilidad | Fase |
| --- | --- | --- |
| `prisma/schema.prisma` | Modelo relacional y cliente Prisma | 1 |
| `prisma/migrations` | Migraciones versionadas de PostgreSQL | 1 |
| `netlify.toml` | Build, SPA, API y cron cada minuto | 1 |
| `apps/api/src/config` | Validación de variables privadas y Prisma | 2 |
| `apps/api/src/http` | Express y respuestas de error en español | 2 |
| `apps/api/src/middleware` | Sesiones, CSRF, autorización y límites | 2 |
| `apps/api/src/routes` | API de contactos, campañas, bot y webhook | 2 |
| `apps/api/src/services` | Meta, consentimiento, plantillas y auditoría | 2 |
| `apps/api/src/workers` | Reclamos atómicos, límites y reintentos | 2 |
| `netlify/functions` | Entradas `api.ts` y `queue.ts` | 2 |
| `packages/shared/src` | Contratos y esquemas zod compartidos | 2 |
| `apps/web/src/api` | Cliente HTTP de la API | 3 |
| `apps/web/src/components` | Componentes React en español | 3 |
| `apps/web/src/pages` | Contactos, segmentos, plantillas, campañas y panel | 3 |
| `apps/web/src/hooks` | Estado y carga de datos | 3 |
| `tests/unit` | Teléfonos, plantillas, reintentos y webhook | 4 |
| `tests/integration` | Consentimiento, concurrencia y aislamiento | 4 |
| `scripts` | Comprobaciones operativas | 4 |

Las fases pendientes no contienen implementaciones simuladas ni funciones vacías.
`npm run build` y las pruebas funcionales estarán disponibles cuando existan sus
fuentes. En esta fase se validan el esquema, el cliente generado y las migraciones.

## Contratos de ejecución

- El frontend consume `/api`. Netlify lo dirige a la función `api`; en desarrollo
  Vite lo enviará al servidor Express local. El webhook público será
  `/api/webhooks/whatsapp`, con GET de verificación y POST de eventos firmados.
- `queue.ts` es la única entrada programada. No expone una ruta de envío público;
  su ejecución HTTP manual deberá rechazarse. Trabaja con presupuesto de 20
  segundos y lease renovable; nunca usa un proceso permanente ni un temporizador.
- Cada usuario pertenece a uno o más espacios con rol ADMIN u OPERATOR. Las
  referencias entre contactos, segmentos, plantillas y campañas incluyen el
  espacio para impedir mezclar carteras. La primera instalación usa un admin de
  bootstrap configurado privadamente; no hay contraseñas predeterminadas.
- Esta instalación administra una integración oficial de Meta mediante variables
  de entorno. Las credenciales no van a la base ni al navegador. Los IDs de Meta
  identifican el espacio autorizado; tener una cuenta no permite conectar un
  número personal automáticamente.
- `DRY_RUN=true` es la barrera global; cada espacio y mensaje también conserva su
  modo de prueba. Un mensaje nacido como simulación nunca se convierte a real
  cuando se cambie una variable. El bot y el envío comienzan pausados.
- El consentimiento mantiene fecha, fuente y eventos. Una importación repetida
  no revoca una baja ni renueva permiso automáticamente. Una entrada al webhook
  tampoco equivale a consentimiento para campañas. BAJA/STOP invalida permiso y
  cancela pendientes en la misma transacción.
- Los segmentos guardan filtros validados con zod. Al lanzar una campaña se
  congela la selección y su plantilla; los mensajes guardan destinatario y
  parámetros. Se vuelve a verificar consentimiento, baja, teléfono, estado de la
  plantilla y pausa antes de cada intento.
- `@@unique([campaignId, contactId])` e idempotencia por espacio impiden duplicar
  mensajes de una campaña. El reclamo usa transacciones Prisma y actualización
  condicional, sin consultas SQL escritas a mano. Un resultado incierto de Meta
  pasa a UNKNOWN: no se reintenta ciegamente. No existe una transacción distribuida
  entre Postgres y Meta que permita prometer entrega exactamente una vez.
- Cada intento tiene su propio registro. Los fallos explícitamente transitorios
  usan backoff exponencial acotado y jitter. Token inválido, restricciones y
  calidad baja pausan el espacio. Los eventos de estado se deduplican y conservan
  aunque lleguen antes de la respuesta de envío o fuera de orden.
- Las respuestas HOLA/MENU usan texto solo dentro de las 24 horas siguientes al
  mensaje del contacto. Fuera de esa ventana se requiere plantilla aprobada. Las
  plantillas de marketing deben contener instrucciones reales de BAJA; no se
  añade texto libre a una plantilla ya aprobada. Componentes no soportados se
  muestran como tales y no se envían.
- El límite por minuto se comparte en PostgreSQL, no en memoria de una función.
  Cada cron puede procesar varios lotes pequeños y conserva cursores de campaña;
  no carga toda la cartera ni espera entre mensajes dentro de la función.
- Los cron de Netlify requieren sitio publicado y están sujetos a cuotas y
  disponibilidad del proveedor. No se promete ejecución puntual ni costo cero
  para tráfico real de Meta. Las pruebas unitarias y DRY_RUN no acreditan entrega.

## Variables y migraciones

`.env.example` contiene nombres y valores no secretos. Los campos privados están
vacíos deliberadamente: no son credenciales utilizables. `DATABASE_URL` usa el
pool de Neon/Supabase y `DIRECT_URL` la conexión de migración. Ambas necesitan TLS.
La guía completa de Meta y Netlify se entrega en la fase 4.

Los scripts `db:validate`, `db:generate` y `db:deploy` se ejecutan desde esta
carpeta con Node 20. La migración inicial es SQL generado por Prisma; la aplicación
no ejecutará `$queryRaw`, `$executeRaw` ni consultas SQL manuales. Las migraciones
de producción son un paso explícito; un preview de Netlify no migra producción
como efecto secundario del build.

## Verificación de esta fase

Se instalaron las dependencias con Node 20.20.2 y npm 10.9.9, con versiones
fijadas y lockfile. La auditoría de dependencias no detectó vulnerabilidades.
`npm ci` se repitió correctamente. npm avisa que el auxiliar de desarrollo local
`@prisma/streams-local` requiere Node 22; no se usa `prisma dev` ni ese servidor
auxiliar en esta arquitectura. El runtime solicitado sigue siendo Node 20.
El esquema se validó con `npm run db:validate:wasm`, que usa el motor oficial
de Prisma mediante `@prisma/get-dmmf`: 20 modelos y 9 enumeraciones válidos.
Se revisaron workspaces, JSON, rutas de TypeScript, función programada y
redirecciones de Netlify.

El CLI de Prisma intentó descargar su motor desde `binaries.prisma.sh` y el proxy
de este entorno respondió 403. No se desactivaron checksums ni TLS. Se guardó ese
dominio en el borrador de configuración del entorno; aún requiere aplicar/publicar
la configuración. Esta fase no acredita generación del cliente, migración de una
base ni un build completo. El validador WASM no accede a la base ni sustituye esas
operaciones. Las entradas de Functions y los archivos de React se entregan en sus
fases respectivas.

## Fase 2: backend implementado y comprobado

El bloqueo anterior de descarga dejó de reproducirse: el CLI validó el esquema,
generó el cliente y aplicó la migración inicial a un PostgreSQL 17 aislado local.
La compilación estricta de API, contratos y entradas Netlify pasó con Node 20.
Se comprobó el flujo HTTP real contra esa base: login/CSRF, roles, contactos,
etiquetas, segmentos, previsualización, lanzamiento idempotente, dos trabajadores
concurrentes, DRY_RUN sin acceso a Graph, respuestas HOLA, firma del webhook, BAJA
antes de confirmar el callback, importación que conserva bajas, estados fuera de
orden y métricas. No se enviaron mensajes reales ni se verificó un despliegue en
Netlify. Las pruebas Vitest de entrega siguen previstas para la fase 4.

Los comandos disponibles son `npm run build:backend` y `npm run queue:once`.
El segundo ejecuta un lote local, respetando las mismas barreras del cron; no se
expone una ruta HTTP para disparar el trabajador. La autenticación de desarrollo
carga el `.env` de la raíz del proyecto incluso desde el workspace de la API.
En producción los valores se leen directamente de las variables de Netlify.
El administrador inicial se crea una sola vez desde las variables BOOTSTRAP;
no hay registro público ni credenciales predeterminadas.

Las listas se conservan como contactos y etiquetas; los segmentos son filtros
reutilizables. No es necesario cargar un CSV para agregar contactos o lanzar
otra campaña. Cada campaña congela hasta 10,000 destinatarios al lanzarla;
se vuelve a comprobar permiso antes de cada intento. No repite la campaña
indefinidamente ni incorpora contactos futuros a una campaña ya lanzada.
Los operadores pueden gestionar carteras y campañas; la conexión, bot, límites
y creación de usuarios requieren rol ADMIN. Los números no se cambian sobre un
contacto existente para evitar reutilizar un consentimiento concedido a otro
número. Se crea otro contacto con su autorización correspondiente.

La normalización usa libphonenumber, sin insertar un 1 mexicano por defecto.
La importación solo acepta CSV y necesita nombre, telefono, consentimiento,
fecha; las autorizaciones afirmativas también necesitan fuente. Opcionales:
etiquetas separadas por `|` y campos con prefijo `campo_`. Fechas ISO con zona.
Una fila inválida rechaza el archivo completo. Referencias existentes por número
se omiten sin alterar permisos. Las claves de campos personalizados son acotadas;
los filtros se convierten a expresiones de Prisma, nunca SQL manual.

Se admiten plantillas con variables numéricas consecutivas en el cuerpo y
componentes estáticos compatibles. Los formatos no compatibles se muestran como
tales y no se envían. No se crean plantillas ficticias como aprobadas en la
aplicación: la sincronización consulta Meta. El trabajador refresca plantillas
usadas que superen diez minutos de antigüedad antes de un envío real y verifica
el número/calidad. Un resultado UNKNOWN no tiene botón de reintento automático.
El límite efectivo por minuto es el menor entre espacio y variable del servidor.
Los cron y callbacks son idempotentes y conservan estado durable; ninguna API
puede retirar un mensaje que ya esté en vuelo hacia Meta.
