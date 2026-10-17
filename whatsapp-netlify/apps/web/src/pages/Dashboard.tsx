import { messageLabels } from "@takolo/shared";
import type { Metrics } from "../api/types";
import { useLoad } from "../hooks/useLoad";
import { useAuth } from "../components/auth";
import {
  Header,
  Panel,
  Notice,
  Button,
  Loading,
  Empty,
} from "../components/ui";
export function Dashboard() {
  const load = useLoad<Metrics>("/dashboard");
  const { auth } = useAuth();
  if (load.loading && !load.data) return <Loading />;
  return (
    <>
      <Header
        eyebrow="UN BUEN DÍA PARA CONECTAR"
        title={`Hola, ${auth.user.name.split(" ")[0]}`}
        description="Tu lista, tus campañas y cada respuesta en un solo lugar."
      >
        <Button variant="secondary" onClick={load.refresh}>
          Actualizar
        </Button>
        <a className="button primary" href="#/campaigns/new">
          + Nueva campaña
        </a>
      </Header>
      {load.error && <Notice kind="error">{load.error}</Notice>}
      {load.data && (
        <>
          <div className="stats-grid">
            <div className="stat">
              <span className="stat-icon">◉</span>
              <small>Contactos guardados</small>
              <strong>{load.data.contacts.toLocaleString("es-MX")}</strong>
              <a href="#/contacts">Ver mi lista →</a>
            </div>
            <div className="stat">
              <span className="stat-icon">✓</span>
              <small>Con permiso vigente</small>
              <strong>{load.data.eligible.toLocaleString("es-MX")}</strong>
              <a href="#/segments">Revisar segmentos →</a>
            </div>
            <div className="stat">
              <span className="stat-icon">↗</span>
              <small>Tasa de entrega</small>
              <strong>{Math.round(load.data.deliveryRate * 100)}%</strong>
              <span>
                {load.data.delivered} confirmados de {load.data.accepted}{" "}
                aceptados
              </span>
            </div>
            <div className="stat">
              <span className="stat-icon">✦</span>
              <small>Tasa de lectura</small>
              <strong>{Math.round(load.data.readRate * 100)}%</strong>
              <span>{load.data.read} lecturas confirmadas</span>
            </div>
          </div>
          <div className="two-columns">
            <Panel
              title="Cada mensaje tiene un estado"
              description="Las simulaciones se muestran por separado de los envíos de WhatsApp."
            >
              {load.data.states.length ? (
                <div className="status-bars">
                  {load.data.states.map((s) => {
                    const total = load.data!.states.reduce(
                      (n, x) => n + x._count._all,
                      0,
                    );
                    return (
                      <a
                        className="status-row"
                        key={s.status}
                        href={`#/messages?status=${s.status}`}
                      >
                        <div className="between">
                          <span>
                            {messageLabels[
                              s.status as keyof typeof messageLabels
                            ] ?? s.status}
                          </span>
                          <strong>{s._count._all}</strong>
                        </div>
                        <div className="bar">
                          <span
                            style={{
                              width: `${Math.max(1, (s._count._all / Math.max(1, total)) * 100)}%`,
                            }}
                          />
                        </div>
                      </a>
                    );
                  })}
                </div>
              ) : (
                <Empty
                  title="Todo preparado para empezar"
                  description="Agrega contactos y crea tu primera campaña."
                  link="/contacts/new"
                  label="Agregar contacto"
                />
              )}
            </Panel>
            <Panel
              title="De tu lista a una conversación"
              description="Prepara tu espacio una vez y reutilízalo en cada campaña."
            >
              <div className="setup-steps">
                <a href="#/contacts">
                  <span>01</span>
                  <div>
                    <strong>Organiza tus contactos</strong>
                    <p>Agrega personas y etiquetas sin usar Excel.</p>
                  </div>
                  <b>→</b>
                </a>
                <a href="#/segments">
                  <span>02</span>
                  <div>
                    <strong>Guarda tus listas</strong>
                    <p>Elige grupos por etiquetas o campos.</p>
                  </div>
                  <b>→</b>
                </a>
                <a href="#/campaigns/new">
                  <span>03</span>
                  <div>
                    <strong>Programa tu mensaje</strong>
                    <p>Revisa el texto, la lista y el horario.</p>
                  </div>
                  <b>→</b>
                </a>
              </div>
            </Panel>
          </div>
          {load.data.errors.length > 0 && (
            <Panel title="Errores que necesitan atención">
              <div className="tags">
                {load.data.errors.map((error) => (
                  <a
                    href="#/messages?status=FAILED"
                    className="tag"
                    key={error.errorCode}
                  >
                    Código {error.errorCode}: {error._count._all} intentos
                  </a>
                ))}
              </div>
            </Panel>
          )}
        </>
      )}
    </>
  );
}
