import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Segment, Tag } from "../api/types";
import { useLoad, useSearch } from "../hooks/useLoad";
import {
  Header,
  Panel,
  Button,
  Field,
  Notice,
  Empty,
  Loading,
  Pager,
  useAction,
} from "../components/ui";
export function Segments() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const q = useSearch(search);
  const load = useLoad<{ segments: Segment[]; total: number }>(
    `/segments?page=${page}&pageSize=25&search=${encodeURIComponent(q)}`,
  );
  return (
    <>
      <Header
        title="Listas que trabajan contigo"
        description="Guarda un grupo de contactos por etiquetas o campos. Úsalo en todas tus próximas campañas."
      >
        <a className="button primary" href="#/segments/new">
          + Crear segmento
        </a>
      </Header>
      <Panel
        title="Tus segmentos"
        actions={
          <Field label="Buscar segmento">
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
        ) : !load.data?.segments.length ? (
          <Empty
            title="Tu próxima lista empieza aquí"
            description="Elige etiquetas o campos para agrupar a las personas autorizadas."
            link="/segments/new"
            label="Crear mi primer segmento"
          />
        ) : (
          <>
            <div className="card-grid">
              {load.data.segments.map((s) => (
                <a
                  className="segment-card"
                  href={`#/segments/${s.id}`}
                  key={s.id}
                >
                  <span className="card-icon">◉</span>
                  <h3>{s.name}</h3>
                  <p>
                    {s.filters.tagIds.length} etiquetas ·{" "}
                    {s.filters.fields.length} condiciones
                  </p>
                  <span className="text-link">Revisar lista →</span>
                </a>
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
export function SegmentForm({ id }: { id?: string }) {
  const tags = useLoad<Tag[]>("/segments/tags");
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [mode, setMode] = useState<"all" | "any">("any");
  const [fields, setFields] = useState<Segment["filters"]["fields"]>([]);
  const [existing, setExisting] = useState<Segment | null>(null);
  const [loading, setLoading] = useState(Boolean(id));
  const action = useAction();
  useEffect(() => {
    if (id) {
      setLoading(true);
      api<Segment>(`/segments/${id}`)
        .then((s) => {
          setExisting(s);
          setName(s.name);
          setSelected(s.filters.tagIds);
          setMode(s.filters.tagMode);
          setFields(s.filters.fields);
        })
        .catch((e: Error) => {
          void action.run(async () => {
            throw e;
          }, "");
        })
        .finally(() => setLoading(false));
    }
  }, [id]);
  if (loading) return <Loading />;
  return (
    <>
      <a className="back" href="#/segments">
        ← Volver a segmentos
      </a>
      <Header
        title={id ? "Tu lista, a tu manera" : "Crea un segmento"}
        description="Solo se seleccionan contactos con autorización vigente. Una lista guardada no envía mensajes por sí sola."
      />
      {action.feedback}
      <Panel title="Define a quién quieres contactar">
        <form
          className="form-stack"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              const result = await api<Segment>(
                id ? `/segments/${id}` : "/segments",
                id ? "PUT" : "POST",
                { name, filters: { tagIds: selected, tagMode: mode, fields } },
              );
              if (id) {
                setExisting(await api<Segment>(`/segments/${id}`));
              } else window.location.hash = `/segments/${result.id}`;
            });
          }}
        >
          <Field label="Nombre de la lista">
            <input
              required
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ej. Clientes de Guadalajara"
            />
          </Field>
          <div className="subpanel">
            <h3>Etiquetas</h3>
            {tags.error && <Notice kind="error">{tags.error}</Notice>}
            <div className="tag-options">
              {tags.data?.map((tag) => (
                <label className="check tag-check" key={tag.id}>
                  <input
                    type="checkbox"
                    checked={selected.includes(tag.id)}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...selected, tag.id]
                          : selected.filter((t) => t !== tag.id),
                      )
                    }
                  />
                  {tag.name}
                </label>
              ))}
            </div>
            {!tags.data?.length && (
              <p className="help">
                Agrega etiquetas desde los contactos. Sin etiquetas
                seleccionadas, se consideran todos los contactos autorizados.
              </p>
            )}
            <Field label="Coincidencia">
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as "all" | "any")}
              >
                <option value="any">Cualquiera de las etiquetas</option>
                <option value="all">Todas las etiquetas</option>
              </select>
            </Field>
          </div>
          <div className="between">
            <h3>Condiciones adicionales</h3>
            <Button
              variant="secondary"
              disabled={fields.length >= 10}
              onClick={() =>
                setFields([
                  ...fields,
                  { key: "name", operator: "contains", value: "" },
                ])
              }
            >
              + Condición
            </Button>
          </div>
          {fields.map((field, index) => (
            <div className="condition-row" key={index}>
              <Field label="Campo">
                <input
                  required
                  maxLength={50}
                  value={field.key}
                  placeholder="name o ciudad"
                  onChange={(e) =>
                    setFields(
                      fields.map((f, i) =>
                        i === index ? { ...f, key: e.target.value } : f,
                      ),
                    )
                  }
                />
              </Field>
              <Field label="Condición">
                <select
                  value={field.operator}
                  onChange={(e) =>
                    setFields(
                      fields.map((f, i) =>
                        i === index
                          ? {
                              ...f,
                              operator: e.target.value as typeof field.operator,
                            }
                          : f,
                      ),
                    )
                  }
                >
                  <option value="equals">Es igual a</option>
                  <option value="contains">Contiene</option>
                  <option value="exists">Tiene este campo</option>
                </select>
              </Field>
              {field.operator !== "exists" && (
                <Field label="Valor">
                  <input
                    required
                    value={field.value}
                    onChange={(e) =>
                      setFields(
                        fields.map((f, i) =>
                          i === index ? { ...f, value: e.target.value } : f,
                        ),
                      )
                    }
                  />
                </Field>
              )}
              <Button
                variant="secondary"
                onClick={() => setFields(fields.filter((_, i) => i !== index))}
              >
                Quitar
              </Button>
            </div>
          ))}
          <p className="help">
            Usa name para el nombre del contacto, o la clave del campo
            personalizado. Todas las condiciones adicionales deben cumplirse.
          </p>
          <Button type="submit" disabled={action.busy}>
            Guardar segmento
          </Button>
        </form>
      </Panel>
      {existing && (
        <Panel
          title={`${existing.total ?? 0} contactos elegibles`}
          description="Vista previa de hasta 20 personas con consentimiento vigente."
        >
          {existing.contacts?.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Contacto</th>
                    <th>Teléfono</th>
                  </tr>
                </thead>
                <tbody>
                  {existing.contacts.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <a className="table-link" href={`#/contacts/${c.id}`}>
                          {c.name}
                        </a>
                      </td>
                      <td>{c.phoneE164}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title="Todavía no hay coincidencias"
              description="Revisa tus filtros o registra el consentimiento de las personas que deben formar parte de esta lista."
            />
          )}
        </Panel>
      )}
    </>
  );
}
