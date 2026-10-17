import { useEffect, useState, type FormEvent } from "react";
import { api, date, localInput } from "../api/client";
import type { Contact } from "../api/types";
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
  CustomFields,
  useAction,
} from "../components/ui";
export function Contacts() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const q = useSearch(search);
  const list = useLoad<{ contacts: Contact[]; total: number }>(
    `/contacts?page=${page}&pageSize=25&search=${encodeURIComponent(q)}`,
  );
  const [importing, setImporting] = useState(false);
  return (
    <>
      <Header
        title="Tus contactos"
        description="Tu lista se queda guardada. Agrega personas y organiza tus próximas conversaciones."
      >
        <Button variant="secondary" onClick={() => setImporting((v) => !v)}>
          Importar CSV
        </Button>
        <a className="button primary" href="#/contacts/new">
          + Agregar contacto
        </a>
      </Header>
      {importing && <ImportContacts onImported={list.refresh} />}
      <Panel
        title="Tu lista de contactos"
        actions={
          <Field label="Buscar contacto">
            <input
              type="search"
              value={search}
              placeholder="Nombre o teléfono"
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </Field>
        }
      >
        {list.error ? (
          <Notice kind="error">{list.error}</Notice>
        ) : list.loading ? (
          <Loading />
        ) : !list.data?.contacts.length ? (
          <Empty
            title="Todo empieza con un contacto"
            description="Puedes agregarlo aquí, sin preparar un Excel."
            link="/contacts/new"
            label="Agregar mi primer contacto"
          />
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Contacto</th>
                    <th>Permiso</th>
                    <th>Etiquetas</th>
                    <th>Última respuesta</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.contacts.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <a className="table-link" href={`#/contacts/${c.id}`}>
                          {c.name}
                        </a>
                        <small>{c.phoneE164}</small>
                      </td>
                      <td>
                        <Badge positive={c.consentGranted && !c.optedOutAt}>
                          {c.optedOutAt
                            ? "Solicitó baja"
                            : c.consentGranted
                              ? "Autorizado"
                              : "Sin autorización"}
                        </Badge>
                      </td>
                      <td>
                        <div className="tags">
                          {c.tags.map((t) => (
                            <span className="tag" key={t.tag.id}>
                              {t.tag.name}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td>{date(c.lastInboundAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              page={page}
              total={list.data.total}
              pageSize={25}
              onPage={setPage}
            />
          </>
        )}
      </Panel>
    </>
  );
}
function ImportContacts({ onImported }: { onImported: () => void }) {
  const [content, setContent] = useState("");
  const [summary, setSummary] = useState<{
    created: number;
    skipped: number;
  } | null>(null);
  const action = useAction();
  return (
    <Panel
      title="Importar una lista"
      description="Opcional: elige un CSV o pega su contenido. Desde Excel, guarda el archivo como CSV UTF-8."
    >
      {action.feedback}
      {summary && (
        <Notice kind="success">
          {summary.created} contactos nuevos · {summary.skipped} duplicados
          omitidos. Los permisos existentes se conservaron.
        </Notice>
      )}
      <form
        className="form-stack"
        onSubmit={(e) => {
          e.preventDefault();
          void action.run(async () => {
            const result = await api<{ created: number; skipped: number }>(
              "/contacts/import",
              "POST",
              content,
              true,
            );
            setSummary(result);
            onImported();
          }, "");
        }}
      >
        <Field
          label="Archivo CSV"
          hint="Hasta 2 MB. No se requiere volver a cargarlo para usar la lista."
        >
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file)
                void action.run(async () => {
                  if (file.size > 2097152)
                    throw Error("El archivo supera 2 MB.");
                  setContent(await file.text());
                }, "");
            }}
          />
        </Field>
        <Field
          label="Contenido de la lista"
          hint="Columnas: nombre, telefono, consentimiento, fecha y fuente. Opcionales: etiquetas separadas por | y campos con prefijo campo_."
        >
          <textarea
            rows={7}
            required
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Pega aquí el CSV con sus encabezados"
          />
        </Field>
        <p className="help">
          Usa sí/no para consentimiento y fecha con zona horaria. La columna
          fuente explica cómo se obtuvo el permiso. Importar no envía mensajes.
        </p>
        <Button type="submit" disabled={action.busy || !content.trim()}>
          Guardar contactos de la lista
        </Button>
      </form>
    </Panel>
  );
}
export function NewContact() {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [tags, setTags] = useState("");
  const [consent, setConsent] = useState(false);
  const [consentAt, setConsentAt] = useState(localInput());
  const [source, setSource] = useState("");
  const [fields, setFields] = useState<{ key: string; value: string }[]>([]);
  const action = useAction();
  function submit(e: FormEvent) {
    e.preventDefault();
    void action.run(async () => {
      const contact = await api<Contact>("/contacts", "POST", {
        name,
        phone,
        consent,
        ...(consent
          ? {
              consentAt: new Date(consentAt).toISOString(),
              consentSource: source,
            }
          : {}),
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        customFields: Object.fromEntries(fields.map((f) => [f.key, f.value])),
      });
      window.location.hash = `/contacts/${contact.id}`;
    }, "");
  }
  return (
    <>
      <a className="back" href="#/contacts">
        ← Volver a contactos
      </a>
      <Header
        title="Agrega una persona"
        description="Guarda sus datos una vez. Después podrás usar etiquetas y segmentos para tus campañas."
      />
      <Panel title="Datos del contacto">
        {action.feedback}
        <form className="form-stack" onSubmit={submit}>
          <div className="form-grid">
            <Field label="Nombre">
              <input
                required
                maxLength={200}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
            <Field
              label="Teléfono"
              hint="Incluye el código de país, por ejemplo +52 para México."
            >
              <input
                type="tel"
                required
                maxLength={30}
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+52 y diez dígitos"
              />
            </Field>
          </div>
          <Field
            label="Etiquetas"
            hint="Separa con comas. Puedes crear una lista como Clientes, Seguimiento o Evento."
          >
            <input
              maxLength={1000}
              value={tags}
              onChange={(e) => setTags(e.target.value)}
            />
          </Field>
          <CustomFields value={fields} onChange={setFields} />
          <div className="subpanel">
            <label className="check">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />{" "}
              La persona autorizó recibir estos mensajes por WhatsApp
            </label>
            {consent ? (
              <div className="form-grid">
                <Field
                  label="Fecha de autorización"
                  hint="Hora local de tu dispositivo."
                >
                  <input
                    type="datetime-local"
                    required
                    value={consentAt}
                    onChange={(e) => setConsentAt(e.target.value)}
                  />
                </Field>
                <Field label="Cómo obtuviste el permiso">
                  <input
                    required
                    minLength={3}
                    maxLength={500}
                    value={source}
                    onChange={(e) => setSource(e.target.value)}
                    placeholder="Formulario, solicitud firmada u otro registro"
                  />
                </Field>
              </div>
            ) : (
              <p className="help">
                Se guardará en tu lista, pero no recibirá campañas hasta
                registrar su autorización.
              </p>
            )}
          </div>
          <div className="actions">
            <Button type="submit" disabled={action.busy}>
              Guardar contacto
            </Button>
            <a className="button secondary" href="#/contacts">
              Cancelar
            </a>
          </div>
        </form>
      </Panel>
    </>
  );
}
export function ContactDetail({ id }: { id: string }) {
  const load = useLoad<Contact>(`/contacts/${id}`);
  const [name, setName] = useState("");
  const [tags, setTags] = useState("");
  const [fields, setFields] = useState<{ key: string; value: string }[]>([]);
  const [granted, setGranted] = useState(false);
  const [source, setSource] = useState("");
  const [occurredAt, setOccurredAt] = useState(localInput());
  const action = useAction();
  useEffect(() => {
    if (load.data) {
      setName(load.data.name);
      setTags(load.data.tags.map((t) => t.tag.name).join(", "));
      setFields(
        Object.entries(load.data.customFields).map(([key, value]) => ({
          key,
          value,
        })),
      );
      setGranted(load.data.consentGranted && !load.data.optedOutAt);
    }
  }, [load.data]);
  if (load.loading) return <Loading />;
  if (load.error || !load.data)
    return (
      <Notice kind="error">
        {load.error || "No se encontró el contacto."}
      </Notice>
    );
  const contact = load.data;
  return (
    <>
      <a className="back" href="#/contacts">
        ← Volver a contactos
      </a>
      <Header title={contact.name} description={contact.phoneE164}>
        <Badge positive={contact.consentGranted && !contact.optedOutAt}>
          {contact.optedOutAt
            ? "Solicitó baja"
            : contact.consentGranted
              ? "Autorizado"
              : "Sin autorización"}
        </Badge>
      </Header>
      {action.feedback}
      <div className="two-columns">
        <Panel title="Datos y etiquetas">
          <form
            className="form-stack"
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                await api(`/contacts/${id}`, "PATCH", {
                  name,
                  tags: tags
                    .split(",")
                    .map((t) => t.trim())
                    .filter(Boolean),
                  customFields: Object.fromEntries(
                    fields.map((f) => [f.key, f.value]),
                  ),
                });
                load.refresh();
              });
            }}
          >
            <Field label="Nombre">
              <input
                required
                maxLength={200}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
            <Field label="Etiquetas">
              <input value={tags} onChange={(e) => setTags(e.target.value)} />
            </Field>
            <CustomFields value={fields} onChange={setFields} />
            <Button type="submit" disabled={action.busy}>
              Guardar datos
            </Button>
          </form>
        </Panel>
        <Panel
          title="Autorización de contacto"
          description="Registra un permiso real o retíralo para detener los mensajes pendientes."
        >
          <form
            className="form-stack"
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                await api(`/contacts/${id}/consent`, "POST", {
                  granted,
                  source,
                  occurredAt: new Date(occurredAt).toISOString(),
                });
                setSource("");
                load.refresh();
              });
            }}
          >
            <Field label="Estado de autorización">
              <select
                value={String(granted)}
                onChange={(e) => setGranted(e.target.value === "true")}
              >
                <option value="false">
                  Sin permiso / retirar autorización
                </option>
                <option value="true">Tiene una autorización vigente</option>
              </select>
            </Field>
            <Field label="Fecha del registro">
              <input
                type="datetime-local"
                required
                value={occurredAt}
                onChange={(e) => setOccurredAt(e.target.value)}
              />
            </Field>
            <Field label="Motivo o evidencia">
              <textarea
                required
                minLength={10}
                maxLength={500}
                value={source}
                onChange={(e) => setSource(e.target.value)}
              />
            </Field>
            <Button type="submit" disabled={action.busy}>
              Actualizar autorización
            </Button>
          </form>
        </Panel>
      </div>
      <Panel title="Registro de autorizaciones">
        {contact.consentEvents?.length ? (
          <div className="timeline">
            {contact.consentEvents.map((event) => (
              <article key={event.id}>
                <span className="timeline-dot" />
                <div>
                  <strong>
                    {event.action === "GRANTED"
                      ? "Autorización registrada"
                      : "Autorización retirada"}
                  </strong>
                  <p>{event.source}</p>
                  <small>{date(event.occurredAt)}</small>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="muted">No hay registros de autorización.</p>
        )}
      </Panel>
      <Panel
        title="Conversación e historial"
        actions={
          <a className="button secondary" href={`#/inbox?contact=${id}`}>
            Ver respuestas
          </a>
        }
      >
        <p className="muted">
          {contact.messages?.length ?? 0} mensajes recientes · Última respuesta:{" "}
          {date(contact.lastInboundAt)}
        </p>
        <a className="text-link" href="#/messages">
          Consultar historial de envíos →
        </a>
      </Panel>
    </>
  );
}
