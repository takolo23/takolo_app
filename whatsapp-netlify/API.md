# Contrato del backend

Todas las respuestas son JSON salvo el challenge GET del webhook. Los errores
incluyen `error`, `code` y, cuando corresponde, `details`. Las mutaciones de la
interfaz requieren Origin igual a APP_URL, cookie de sesión y X-CSRF-Token.
Login también verifica Origin. Las cookies son HttpOnly/SameSite=Strict y Secure
en producción. X-Workspace-ID selecciona una membresía autorizada.

## Acceso

- POST `/api/auth/login`: email y password; devuelve csrfToken y usuario.
- GET `/api/auth/me`: usuario, membresías, espacio, rol y csrfToken.
- POST `/api/auth/logout`: cierra la sesión.
- GET `/api/health`: estado mínimo de conexión a la base.

## Contactos y listas

- GET `/api/contacts`: page, pageSize, search, tagId opcional.
- POST `/api/contacts`: name, phone, consent, consentAt, consentSource,
  tags y customFields. Se puede crear sin consentimiento; no será contactable.
- POST `/api/contacts/import`: cuerpo text/csv; devuelve created, skipped, total.
- GET `/api/contacts/:id`: datos, permisos y los últimos 50 movimientos.
- PATCH `/api/contacts/:id`: name, tags, customFields.
- POST `/api/contacts/:id/consent`: granted, source y occurredAt.
- GET/POST `/api/segments/tags`: consultar o crear una etiqueta.
- GET/POST `/api/segments`: listar o crear filtros reutilizables.
- GET/PUT `/api/segments/:id`: consultar muestra elegible o editar.

Los filtros admiten tagIds, tagMode=any/all y fields con key,
operator=equals/contains/exists y value. name filtra por nombre; las demás claves
buscan customFields. La elegibilidad siempre exige consentimiento y ausencia de baja.

## Plantillas y campañas

- GET `/api/templates`: plantillas sincronizadas, variables y compatibilidad.
- POST `/api/templates/sync`: sincroniza desde Meta; ADMIN.
- GET/POST `/api/campaigns`: listado o borrador.
- PUT `/api/campaigns/:id`: editar solo un borrador.
- POST `/api/campaigns/preview`: segmentId, templateId, variableMapping.
- POST `/api/campaigns/:id/launch`: scheduledAt opcional y confirmLive.
- POST `/api/campaigns/:id/pause`, `/resume`, `/cancel`: transiciones.
- GET `/api/campaigns/:id`: campaña, estados, tasas, errores y mensajes paginados.

Cada asignación de variable usa un índice numérico y source=name/phone/field/literal;
value indica el campo o texto cuando se necesita. No se envía texto libre fuera
de la plantilla aprobada. Un doble lanzamiento devuelve 409 y no duplica mensajes.

## Bot, historial y administración

- GET/PUT `/api/settings`: configuración, modo y límites; PUT requiere ADMIN.
- PUT `/api/settings/bot`: enabled, greetingText, cooldownSecs; ADMIN.
- POST `/api/settings/verify-meta`: comprueba el número y calidad; ADMIN.
- POST `/api/settings/pause`, `/resume`: pausa o reactiva el espacio; ADMIN.
- GET/POST `/api/settings/users`: lista miembros o crea un usuario; ADMIN.
- GET `/api/messages`: historial paginado con campaignId/status/search opcionales.
- GET `/api/messages/inbox`: respuestas entrantes; contactId/search opcionales.
- GET `/api/messages/:id`: intentos y resultados del mensaje.
- POST `/api/messages/:id/cancel`: solo mensajes aún en cola.
- GET `/api/dashboard`: métricas globales y errores por código.
- GET `/api/dashboard/audit`: auditoría paginada.

## Webhook

GET/POST `/api/webhooks/whatsapp` usan el token de verificación y firma HMAC de
Meta, respectivamente. POST verifica X-Hub-Signature-256 sobre bytes originales,
incluso al invocarse mediante el adaptador de Netlify. Los eventos se guardan
antes del 200. Las bajas se aplican en el callback; el resto se procesa en cola.
HOLA/MENU solo genera una respuesta para un contacto autorizado y dentro de
24 horas, con enfriamiento configurable. BAJA/STOP no genera una respuesta.
