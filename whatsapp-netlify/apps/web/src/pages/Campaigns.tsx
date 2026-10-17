import { useState } from "react";
import {
  campaignLabels,
  messageLabels,
  type VariableMapping,
} from "@takolo/shared";
import { api, date } from "../api/client";
import type { Campaign, Template, Segment, Message, Count } from "../api/types";
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
export function Campaigns() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const q = useSearch(search);
  const load = useLoad<{ campaigns: Campaign[]; total: number }>(
    `/campaigns?page=${page}&pageSize=25&search=${encodeURIComponent(q)}`,
  );
  return (
    <>
      <Header
        title="Conversaciones con propósito"
        description="Elige una lista guardada, prepara tu mensaje y deja programado el siguiente paso."
      >
        <a className="button primary" href="#/campaigns/new">
          + Nueva campaña
        </a>
      </Header>
      <Panel
        title="Tus campañas"
        actions={
          <Field label="Buscar campaña">
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
        ) : !load.data?.campaigns.length ? (
          <Empty
            title="Tu primera campaña te espera"
            description="Necesitas un segmento con contactos autorizados y una plantilla aprobada."
            link="/campaigns/new"
            label="Crear campaña"
          />
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Campaña</th>
                    <th>Lista</th>
                    <th>Estado</th>
                    <th>Programación</th>
                  </tr>
                </thead>
                <tbody>
                  {load.data.campaigns.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <a className="table-link" href={`#/campaigns/${c.id}`}>
                          {c.name}
                        </a>
                        <small>
                          {c.template.name} ·{" "}
                          {c.dryRun ? "Simulación" : "Envío real"}
                        </small>
                      </td>
                      <td>{c.segment.name}</td>
                      <td>
                        <Badge positive={c.status === "COMPLETED"}>
                          {campaignLabels[c.status]}
                        </Badge>
                      </td>
                      <td>{date(c.scheduledAt)}</td>
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
    </>
  );
}
export function NewCampaign() {
  const [name, setName] = useState("");
  const [segmentId, setSegmentId] = useState("");
  const [template, setTemplate] = useState<Template | null>(null);
  const [mapping, setMapping] = useState<VariableMapping>({});
  const [segmentSearch, setSegmentSearch] = useState("");
  const [templateSearch, setTemplateSearch] = useState("");
  const sq = useSearch(segmentSearch);
  const tq = useSearch(templateSearch);
  const segments = useLoad<{ segments: Segment[] }>(
    `/segments?pageSize=100&search=${encodeURIComponent(sq)}`,
  );
  const templates = useLoad<{ templates: Template[] }>(
    `/templates?pageSize=100&search=${encodeURIComponent(tq)}`,
  );
  const [preview, setPreview] = useState<{
    total: number;
    previews: {
      contactId: string;
      name: string;
      phone: string;
      text: string;
    }[];
  } | null>(null);
  const action = useAction();
  const input = {
    segmentId,
    templateId: template?.id ?? "",
    variableMapping: mapping,
  };
  function choose(id: string) {
    const next = templates.data?.templates.find((t) => t.id === id) ?? null;
    setTemplate(next);
    setMapping(
      Object.fromEntries(
        (next?.variables ?? []).map((v, i) => [
          v,
          { source: i === 0 ? "name" : "literal", value: "" },
        ]),
      ),
    );
    setPreview(null);
  }
  return (
    <>
      <a className="back" href="#/campaigns">
        ← Volver a campañas
      </a>
      <Header
        title="Prepara algo que conecte"
        description="Primero revisa los destinatarios y el texto. Después podrás elegir el horario o enviar cuanto antes."
      />
      {action.feedback}
      <form
        className="form-stack"
        onSubmit={(e) => {
          e.preventDefault();
          void action.run(async () => {
            const result = await api<Campaign>("/campaigns", "POST", {
              name,
              ...input,
            });
            window.location.hash = `/campaigns/${result.id}`;
          }, "");
        }}
      >
        <Panel title="01 · Elige tu lista">
          <div className="form-grid">
            <Field label="Nombre de la campaña">
              <input
                required
                maxLength={150}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ej. Seguimiento de octubre"
              />
            </Field>
            <Field label="Buscar lista guardada">
              <input
                type="search"
                value={segmentSearch}
                onChange={(e) => setSegmentSearch(e.target.value)}
              />
            </Field>
          </div>
          {segments.error && <Notice kind="error">{segments.error}</Notice>}
          <Field label="Segmento de destinatarios">
            <select
              required
              value={segmentId}
              onChange={(e) => {
                setSegmentId(e.target.value);
                setPreview(null);
              }}
            >
              <option value="">Selecciona una lista</option>
              {segmentId &&
                !segments.data?.segments.some((s) => s.id === segmentId) && (
                  <option value={segmentId}>Lista seleccionada</option>
                )}
              {segments.data?.segments.map((s) => (
                <option value={s.id} key={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
          <a className="text-link" href="#/segments/new">
            Crear otro segmento →
          </a>
        </Panel>
        <Panel title="02 · Dale forma al mensaje">
          <Field label="Buscar plantilla">
            <input
              type="search"
              value={templateSearch}
              onChange={(e) => setTemplateSearch(e.target.value)}
            />
          </Field>
          {templates.error && <Notice kind="error">{templates.error}</Notice>}
          <Field label="Plantilla aprobada">
            <select
              required
              value={template?.id ?? ""}
              onChange={(e) => choose(e.target.value)}
            >
              <option value="">Selecciona una plantilla</option>
              {template &&
                !templates.data?.templates.some(
                  (t) => t.id === template.id,
                ) && <option value={template.id}>{template.name}</option>}
              {templates.data?.templates.map((t) => (
                <option
                  key={t.id}
                  value={t.id}
                  disabled={
                    t.status !== "APPROVED" ||
                    !t.supported ||
                    (t.category === "MARKETING" && !t.optOutIncluded)
                  }
                >
                  {t.name} · {t.language}
                  {t.status !== "APPROVED"
                    ? " · No aprobada"
                    : !t.supported
                      ? " · Formato no compatible"
                      : t.category === "MARKETING" && !t.optOutIncluded
                        ? " · Falta opción de baja"
                        : ""}
                </option>
              ))}
            </select>
          </Field>
          <a className="text-link" href="#/templates">
            Revisar o sincronizar plantillas →
          </a>
          {template && (
            <>
              <div className="message-bubble">
                <span className="eyebrow">TEXTO APROBADO</span>
                <p>{template.bodyText}</p>
              </div>
              {template.variables.map((variable) => (
                <div className="variable-row" key={variable}>
                  <strong>{`{{${variable}}}`}</strong>
                  <Field label={`Dato para la variable ${variable}`}>
                    <select
                      value={mapping[variable]?.source ?? "literal"}
                      onChange={(e) => {
                        setMapping({
                          ...mapping,
                          [variable]: {
                            source: e.target
                              .value as VariableMapping[string]["source"],
                            value: "",
                          },
                        });
                        setPreview(null);
                      }}
                    >
                      <option value="name">Nombre del contacto</option>
                      <option value="phone">Teléfono del contacto</option>
                      <option value="field">Campo personalizado</option>
                      <option value="literal">Texto fijo</option>
                    </select>
                  </Field>
                  {["field", "literal"].includes(
                    mapping[variable]?.source ?? "",
                  ) && (
                    <Field
                      label={
                        mapping[variable]?.source === "field"
                          ? "Clave del campo"
                          : "Texto para esta variable"
                      }
                    >
                      <input
                        required
                        maxLength={1024}
                        value={mapping[variable]?.value ?? ""}
                        onChange={(e) => {
                          setMapping({
                            ...mapping,
                            [variable]: {
                              source: mapping[variable]!.source,
                              value: e.target.value,
                            },
                          });
                          setPreview(null);
                        }}
                      />
                    </Field>
                  )}
                </div>
              ))}
            </>
          )}
        </Panel>
        <div className="actions">
          <Button
            variant="secondary"
            disabled={action.busy || !segmentId || !template}
            onClick={() =>
              void action.run(
                async () =>
                  setPreview(await api("/campaigns/preview", "POST", input)),
                "",
              )
            }
          >
            Ver destinatarios y mensaje
          </Button>
          <Button
            type="submit"
            disabled={action.busy || !segmentId || !template}
          >
            Guardar borrador →
          </Button>
        </div>
      </form>
      {preview && (
        <Panel
          title={`${preview.total} contactos elegibles`}
          description="Muestra de hasta 20 destinatarios. El consentimiento se vuelve a comprobar antes de enviar."
        >
          {preview.previews.length ? (
            <div className="preview-grid">
              {preview.previews.map((p) => (
                <div className="message-preview" key={p.contactId}>
                  <strong>{p.name}</strong>
                  <small>{p.phone}</small>
                  <p>{p.text}</p>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="Esta lista aún no tiene destinatarios"
              description="Revisa las etiquetas y los permisos antes de lanzar la campaña."
            />
          )}
        </Panel>
      )}
    </>
  );
}
interface CampaignDetailData {
  campaign: Campaign;
  states: Count[];
  messages: Message[];
  total: number;
  metrics: {
    accepted: number;
    delivered: number;
    read: number;
    deliveryRate: number;
    readRate: number;
    errors: { errorCode: string; _count: { _all: number } }[];
  };
}
export function CampaignDetail({ id }: { id: string }) {
  const [page, setPage] = useState(1);
  const load = useLoad<CampaignDetailData>(
    `/campaigns/${id}?page=${page}&pageSize=25`,
  );
  const [scheduledAt, setScheduledAt] = useState("");
  const [confirmLive, setConfirmLive] = useState(false);
  const action = useAction();
  if (load.loading && !load.data) return <Loading />;
  if (load.error || !load.data)
    return <Notice kind="error">{load.error}</Notice>;
  const { campaign: c, messages, total, metrics } = load.data;
  async function transition(actionName: string) {
    await api(`/campaigns/${id}/${actionName}`, "POST", {});
    load.refresh();
  }
  return (
    <>
      <a className="back" href="#/campaigns">
        ← Volver a campañas
      </a>
      <Header
        title={c.name}
        description={`${c.segment.name} · ${c.template.name}`}
      >
        <Badge positive={c.status === "COMPLETED"}>
          {campaignLabels[c.status]}
        </Badge>
        <Button
          variant="secondary"
          disabled={load.loading}
          onClick={load.refresh}
        >
          Actualizar
        </Button>
      </Header>
      {action.feedback}
      {c.status === "DRAFT" ? (
        <Panel
          title="03 · Elige el momento"
          description="Vacío significa procesar cuanto antes. Las horas dependen del dispositivo y de la disponibilidad del servicio."
        >
          <form
            className="form-stack"
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                if (
                  !window.confirm(
                    "¿Confirmas lanzar esta campaña a los contactos autorizados del segmento? Los envíos reales pueden tener costo en Meta.",
                  )
                )
                  return;
                await api(`/campaigns/${id}/launch`, "POST", {
                  ...(scheduledAt
                    ? { scheduledAt: new Date(scheduledAt).toISOString() }
                    : {}),
                  confirmLive,
                });
                load.refresh();
              }, "Campaña preparada. La cola procesará los mensajes cuando corresponda.");
            }}
          >
            <Field
              label="Fecha y hora · opcional"
              hint="Hora local de tu dispositivo. Hasta 90 días en el futuro."
            >
              <input
                type="datetime-local"
                value={scheduledAt}
                onChange={(e) => setScheduledAt(e.target.value)}
              />
            </Field>
            <label className="check">
              <input
                type="checkbox"
                checked={confirmLive}
                onChange={(e) => setConfirmLive(e.target.checked)}
              />{" "}
              Si está habilitado el modo real, confirmo los destinatarios y el
              envío por WhatsApp.
            </label>
            <p className="help">
              El modo de prueba del espacio y del servidor siempre tiene
              prioridad. Lanzar dos veces esta campaña no duplica sus mensajes.
            </p>
            <Button type="submit" disabled={action.busy}>
              {scheduledAt ? "Programar campaña" : "Lanzar campaña"}
            </Button>
          </form>
        </Panel>
      ) : (
        <Panel
          title={c.dryRun ? "Campaña de simulación" : "Campaña de envío real"}
          description={`Programada: ${date(c.scheduledAt)}`}
        >
          <div className="actions">
            {["RUNNING", "SCHEDULED"].includes(c.status) && (
              <Button
                variant="secondary"
                disabled={action.busy}
                onClick={() =>
                  void action.run(() => transition("pause"), "Campaña pausada.")
                }
              >
                Pausar
              </Button>
            )}
            {c.status === "PAUSED" && (
              <Button
                disabled={action.busy}
                onClick={() =>
                  void action.run(
                    () => transition("resume"),
                    "Campaña reanudada.",
                  )
                }
              >
                Reanudar
              </Button>
            )}
            {!["COMPLETED", "CANCELLED"].includes(c.status) && (
              <Button
                variant="danger"
                disabled={action.busy}
                onClick={() => {
                  if (
                    window.confirm(
                      "¿Cancelar los mensajes pendientes de esta campaña?",
                    )
                  )
                    void action.run(
                      () => transition("cancel"),
                      "Campaña cancelada.",
                    );
                }}
              >
                Cancelar pendientes
              </Button>
            )}
          </div>
        </Panel>
      )}
      <div className="stats-grid">
        <div className="stat">
          <small>Destinatarios</small>
          <strong>{total}</strong>
        </div>
        <div className="stat">
          <small>Aceptados por Meta</small>
          <strong>{metrics.accepted}</strong>
        </div>
        <div className="stat">
          <small>Tasa de entrega</small>
          <strong>{Math.round(metrics.deliveryRate * 100)}%</strong>
        </div>
        <div className="stat">
          <small>Tasa de lectura</small>
          <strong>{Math.round(metrics.readRate * 100)}%</strong>
        </div>
      </div>
      <Panel
        title="Resultados por contacto"
        description="Aceptado no significa entregado. Las confirmaciones se actualizan desde WhatsApp."
      >
        {messages.length ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Contacto</th>
                    <th>Estado</th>
                    <th>Intentos</th>
                    <th>Resultado</th>
                  </tr>
                </thead>
                <tbody>
                  {messages.map((m) => (
                    <tr key={m.id}>
                      <td>
                        {m.contact?.name}
                        <small>{m.phoneE164}</small>
                      </td>
                      <td>
                        <Badge
                          positive={["SIMULATED", "DELIVERED", "READ"].includes(
                            m.status,
                          )}
                        >
                          {messageLabels[m.status]}
                        </Badge>
                      </td>
                      <td>{m.attempts}</td>
                      <td className="wrap">
                        {m.lastError ??
                          (m.status === "SIMULATED"
                            ? "Prueba completada sin enviar."
                            : "Consulta el historial para ver sus intentos.")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={page} total={total} pageSize={25} onPage={setPage} />
          </>
        ) : (
          <Empty
            title="Aún no hay mensajes"
            description="Al lanzar la campaña se guardarán sus destinatarios y programaciones."
          />
        )}
      </Panel>
      {metrics.errors.length > 0 && (
        <Panel title="Errores por código">
          <div className="tags">
            {metrics.errors.map((error) => (
              <span className="tag" key={error.errorCode}>
                Código {error.errorCode}: {error._count._all}
              </span>
            ))}
          </div>
        </Panel>
      )}
    </>
  );
}
