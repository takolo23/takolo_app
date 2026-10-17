import { useState } from "react";
import { messageLabels } from "@takolo/shared";
import { api, date } from "../api/client";
import type { Message, Inbound, Audit } from "../api/types";
import { useLoad, useSearch } from "../hooks/useLoad";
import {
  Header,
  Panel,
  Button,
  Field,
  Notice,
  Badge,
  Empty,
  Pager,
  Loading,
  useAction,
} from "../components/ui";
export function Messages() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState(
    new URLSearchParams(window.location.hash.split("?")[1] ?? "").get(
      "status",
    ) ?? "",
  );
  const q = useSearch(search);
  const load = useLoad<{ messages: Message[]; total: number }>(
    `/messages?page=${page}&pageSize=25&search=${encodeURIComponent(q)}${status ? `&status=${status}` : ""}`,
  );
  const [detail, setDetail] = useState<Message | null>(null);
  const action = useAction();
  return (
    <>
      <Header
        title="Cada mensaje, bajo control"
        description="Revisa pruebas, intentos y confirmaciones de entrega sin perder el historial."
      >
        <Button variant="secondary" onClick={load.refresh}>
          Actualizar
        </Button>
      </Header>
      {action.feedback}
      <Panel
        title="Historial de envíos"
        actions={
          <div className="actions">
            <Field label="Buscar contacto">
              <input
                type="search"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
              />
            </Field>
            <Field label="Estado">
              <select
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">Todos</option>
                {Object.entries(messageLabels).map(([key, label]) => (
                  <option value={key} key={key}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        }
      >
        {load.error ? (
          <Notice kind="error">{load.error}</Notice>
        ) : load.loading ? (
          <Loading />
        ) : !load.data?.messages.length ? (
          <Empty
            title="Aquí aparecerá cada resultado"
            description="Programa una campaña o activa el bot para contactos autorizados."
            link="/campaigns"
            label="Ver campañas"
          />
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Contacto</th>
                    <th>Origen</th>
                    <th>Estado</th>
                    <th>Creado</th>
                    <th>Detalles</th>
                  </tr>
                </thead>
                <tbody>
                  {load.data.messages.map((m) => (
                    <tr key={m.id}>
                      <td>
                        {m.contact?.name}
                        <small>{m.phoneE164}</small>
                      </td>
                      <td>
                        {m.campaign?.name ?? "Respuesta automática"}
                        <small>{m.dryRun ? "Simulación" : "Real"}</small>
                      </td>
                      <td>
                        <Badge
                          positive={["SIMULATED", "READ", "DELIVERED"].includes(
                            m.status,
                          )}
                        >
                          {messageLabels[m.status]}
                        </Badge>
                      </td>
                      <td>{date(m.createdAt)}</td>
                      <td>
                        <Button
                          variant="secondary"
                          onClick={() =>
                            void action.run(
                              async () =>
                                setDetail(
                                  await api<Message>(`/messages/${m.id}`),
                                ),
                              "",
                            )
                          }
                        >
                          Ver intentos
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              page={page}
              total={load.data.total}
              pageSize={25}
              onPage={setPage}
            />
          </>
        )}
      </Panel>
      {detail && (
        <Panel
          title={`Mensaje a ${detail.contact?.name ?? detail.phoneE164}`}
          actions={
            <Button variant="secondary" onClick={() => setDetail(null)}>
              Cerrar detalle
            </Button>
          }
        >
          <div className="detail-summary">
            <Badge>{messageLabels[detail.status]}</Badge>
            <p>
              {detail.lastError ??
                (detail.status === "SIMULATED"
                  ? "Simulación completada sin contactar al destinatario."
                  : "Consulta los intentos y sus confirmaciones.")}
            </p>
            <small>Próximo procesamiento: {date(detail.nextAttemptAt)}</small>
          </div>
          {detail.status === "UNKNOWN" && (
            <Notice>
              No se confirmó el resultado. Revisa el mensaje en Meta antes de
              crear otro envío.
            </Notice>
          )}
          {detail.status === "QUEUED" && (
            <Button
              variant="danger"
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  await api(`/messages/${detail.id}/cancel`, "POST", {});
                  setDetail(await api(`/messages/${detail.id}`));
                  load.refresh();
                }, "Mensaje cancelado.")
              }
            >
              Cancelar mensaje pendiente
            </Button>
          )}
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Intento</th>
                  <th>Resultado</th>
                  <th>Código</th>
                  <th>Fecha</th>
                </tr>
              </thead>
              <tbody>
                {detail.dispatchAttempts?.map((attempt) => (
                  <tr key={attempt.id}>
                    <td>{attempt.number}</td>
                    <td>
                      {(
                        {
                          STARTED: "Iniciado",
                          SIMULATED: "Simulado",
                          ACCEPTED: "Aceptado",
                          RETRYABLE: "Pendiente de reintento",
                          FAILED: "Fallido",
                          UNKNOWN: "Por confirmar",
                        } as Record<string, string>
                      )[attempt.outcome] ?? attempt.outcome}
                    </td>
                    <td>
                      {attempt.errorCode ?? attempt.httpStatus ?? "Sin error"}
                    </td>
                    <td>{date(attempt.startedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </>
  );
}
export function Inbox() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const q = useSearch(search);
  const contact = new URLSearchParams(
    window.location.hash.split("?")[1] ?? "",
  ).get("contact");
  const load = useLoad<{ messages: Inbound[]; total: number }>(
    `/messages/inbox?page=${page}&pageSize=25&search=${encodeURIComponent(q)}${contact ? `&contactId=${encodeURIComponent(contact)}` : ""}`,
  );
  return (
    <>
      <Header
        title="Escucha la conversación"
        description="Las respuestas de tus contactos se guardan aquí. BAJA y STOP retiran el permiso automáticamente."
      >
        <Button variant="secondary" onClick={load.refresh}>
          Actualizar
        </Button>
      </Header>
      <Panel
        title="Bandeja de entrada"
        actions={
          <Field label="Buscar por contacto">
            <input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </Field>
        }
      >
        {load.error ? (
          <Notice kind="error">{load.error}</Notice>
        ) : load.loading ? (
          <Loading />
        ) : !load.data?.messages.length ? (
          <Empty
            title="Tu bandeja está lista"
            description="Conecta el webhook de Meta para recibir y guardar las respuestas."
            link="/settings"
            label="Revisar conexión"
          />
        ) : (
          <>
            <div className="inbox-list">
              {load.data.messages.map((m) => (
                <article className="inbox-item" key={m.id}>
                  <div className="avatar">
                    {m.contact?.name.slice(0, 1).toUpperCase()}
                  </div>
                  <div>
                    <div className="between">
                      <a
                        className="table-link"
                        href={`#/contacts/${m.contact?.id}`}
                      >
                        {m.contact?.name}
                      </a>
                      <small>{date(m.occurredAt)}</small>
                    </div>
                    <small>{m.contact?.phoneE164}</small>
                    <p>{m.text ?? `Mensaje de tipo ${m.type}`}</p>
                  </div>
                </article>
              ))}
            </div>
            <Pager
              page={page}
              total={load.data.total}
              pageSize={25}
              onPage={setPage}
            />
          </>
        )}
      </Panel>
    </>
  );
}
const auditLabels: Record<string, string> = {
  ADMIN_BOOTSTRAPPED: "Administración creada",
  CONTACT_CREATED: "Contacto agregado",
  CONTACT_UPDATED: "Contacto actualizado",
  CONTACTS_IMPORTED: "Lista importada",
  CONSENT_GRANTED: "Permiso registrado",
  CONSENT_WITHDRAWN: "Permiso retirado",
  CONTACT_OPTED_OUT: "Baja por WhatsApp",
  CAMPAIGN_CREATED: "Campaña creada",
  CAMPAIGN_UPDATED: "Campaña actualizada",
  CAMPAIGN_LAUNCHED: "Campaña lanzada",
  CAMPAIGN_PAUSE: "Campaña pausada",
  CAMPAIGN_RESUME: "Campaña reanudada",
  CAMPAIGN_CANCEL: "Campaña cancelada",
  SETTINGS_UPDATED: "Configuración actualizada",
  BOT_UPDATED: "Bot actualizado",
  META_VERIFIED: "Conexión verificada",
  TEMPLATES_SYNCED: "Plantillas sincronizadas",
  USER_CREATED: "Usuario creado",
  WORKSPACE_PAUSE: "Espacio pausado",
  WORKSPACE_RESUME: "Espacio reanudado",
  SENDING_AUTO_PAUSED: "Pausa automática",
  SEGMENT_CREATED: "Segmento creado",
  SEGMENT_UPDATED: "Segmento actualizado",
  MESSAGE_CANCELLED: "Mensaje cancelado",
};
export function AuditPage() {
  const [page, setPage] = useState(1);
  const load = useLoad<{ events: Audit[]; total: number }>(
    `/dashboard/audit?page=${page}&pageSize=25`,
  );
  return (
    <>
      <Header
        title="Un historial que da claridad"
        description="Consulta los cambios y decisiones que se han registrado en tu espacio."
      />
      <Panel title="Actividad del espacio">
        {load.error ? (
          <Notice kind="error">{load.error}</Notice>
        ) : load.loading ? (
          <Loading />
        ) : !load.data?.events.length ? (
          <Empty
            title="Sin actividad todavía"
            description="Aquí se registrarán los cambios en contactos, campañas y configuración."
          />
        ) : (
          <>
            <div className="timeline">
              {load.data.events.map((e) => (
                <article key={e.id}>
                  <span className="timeline-dot" />
                  <div>
                    <strong>{auditLabels[e.action] ?? e.action}</strong>
                    <p>
                      {(
                        {
                          contact: "Contacto",
                          campaign: "Campaña",
                          workspace: "Espacio",
                          user: "Usuario",
                          template: "Plantillas",
                          segment: "Segmento",
                          message: "Mensaje",
                          bot: "Bot",
                        } as Record<string, string>
                      )[e.entityType] ?? e.entityType}
                    </p>
                    <small>{date(e.createdAt)}</small>
                  </div>
                </article>
              ))}
            </div>
            <Pager
              page={page}
              total={load.data.total}
              pageSize={25}
              onPage={setPage}
            />
          </>
        )}
      </Panel>
    </>
  );
}
