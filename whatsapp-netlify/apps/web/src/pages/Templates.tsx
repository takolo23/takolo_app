import { useState } from "react";
import type { Template } from "../api/types";
import { api } from "../api/client";
import { useLoad, useSearch } from "../hooks/useLoad";
import { useAuth } from "../components/auth";
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
const statuses: Record<string, string> = {
  APPROVED: "Aprobada",
  PENDING: "En revisión",
  REJECTED: "Rechazada",
  PAUSED: "Pausada",
  DISABLED: "Desactivada",
  UNKNOWN: "Sin confirmar",
};
export function Templates() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const q = useSearch(search);
  const load = useLoad<{ templates: Template[]; total: number }>(
    `/templates?page=${page}&pageSize=25&search=${encodeURIComponent(q)}`,
  );
  const action = useAction();
  const { auth } = useAuth();
  return (
    <>
      <Header
        title="Mensajes listos para conectar"
        description="Consulta tus plantillas de Meta, sus variables y el texto que recibirán tus contactos."
      >
        {auth.role === "ADMIN" && (
          <Button
            disabled={action.busy}
            onClick={() =>
              void action.run(async () => {
                await api("/templates/sync", "POST", {});
                load.refresh();
              }, "Plantillas sincronizadas.")
            }
          >
            {action.busy ? "Sincronizando…" : "Sincronizar con Meta"}
          </Button>
        )}
      </Header>
      {action.feedback}
      <Panel
        title="Biblioteca de plantillas"
        actions={
          <Field label="Buscar plantilla">
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
        ) : !load.data?.templates.length ? (
          <Empty
            title="Conecta tus plantillas"
            description="Configura tu conexión oficial y sincroniza las plantillas aprobadas. Aquí no se crean aprobaciones de prueba."
            link="/settings"
            label="Revisar conexión"
          />
        ) : (
          <>
            <div className="template-grid">
              {load.data.templates.map((t) => (
                <article className="template-card" key={t.id}>
                  <div className="between">
                    <h3>{t.name}</h3>
                    <Badge positive={t.status === "APPROVED"}>
                      {statuses[t.status] ?? t.status}
                    </Badge>
                  </div>
                  <small>
                    {t.language} ·{" "}
                    {t.category === "MARKETING"
                      ? "Marketing"
                      : t.category === "UTILITY"
                        ? "Utilidad"
                        : "Autenticación"}
                  </small>
                  <div className="message-bubble">
                    <p>{t.bodyText}</p>
                  </div>
                  <div className="tags">
                    {t.variables.map((v) => (
                      <span className="tag" key={v}>{`{{${v}}}`}</span>
                    ))}
                    {!t.variables.length && (
                      <span className="tag">Sin variables</span>
                    )}
                  </div>
                  {!t.supported && (
                    <p className="help">
                      Este formato no está habilitado para enviar desde esta
                      aplicación.
                    </p>
                  )}
                  {t.category === "MARKETING" && !t.optOutIncluded && (
                    <p className="help">
                      Necesita instrucciones de BAJA o STOP en el texto
                      aprobado.
                    </p>
                  )}
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
