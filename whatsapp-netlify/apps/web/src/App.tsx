import { Component, useEffect, type ReactNode } from "react";
import { AuthGate, useAuth } from "./components/auth";
import { useHash, useLoad } from "./hooks/useLoad";
import { Notice, Button, Empty, useAction } from "./components/ui";
import type { Settings as SettingsData } from "./api/types";
import { Dashboard } from "./pages/Dashboard";
import { Contacts, NewContact, ContactDetail } from "./pages/Contacts";
import { Segments, SegmentForm } from "./pages/Segments";
import { Campaigns, NewCampaign, CampaignDetail } from "./pages/Campaigns";
import { Templates } from "./pages/Templates";
import { Messages, Inbox, AuditPage } from "./pages/History";
import { Settings } from "./pages/Settings";
const navigation = [
  { path: "/", label: "Resumen", icon: "dashboard" },
  { path: "/contacts", label: "Contactos", icon: "contacts" },
  { path: "/segments", label: "Mis listas", icon: "lists" },
  { path: "/campaigns", label: "Campañas", icon: "campaigns" },
  { path: "/templates", label: "Plantillas", icon: "templates" },
  { path: "/messages", label: "Envíos", icon: "messages" },
  { path: "/inbox", label: "Respuestas", icon: "inbox" },
  { path: "/settings", label: "Configuración", icon: "settings" },
  { path: "/audit", label: "Actividad", icon: "audit" },
];
function Icon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    dashboard: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="2" />
        <rect x="14" y="3" width="7" height="7" rx="2" />
        <rect x="3" y="14" width="7" height="7" rx="2" />
        <rect x="14" y="14" width="7" height="7" rx="2" />
      </>
    ),
    contacts: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 21v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 4v2" />
      </>
    ),
    lists: (
      <>
        <path d="M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1" />
      </>
    ),
    campaigns: (
      <>
        <path d="m3 10 18-7-7 18-3-8-8-3Zm8 3 5-5" />
      </>
    ),
    templates: (
      <>
        <rect x="4" y="3" width="16" height="18" rx="2" />
        <path d="M8 8h8M8 12h8M8 16h5" />
      </>
    ),
    messages: (
      <>
        <path d="M21 11a8 8 0 0 1-8 8H6l-4 3 1-7a8 8 0 1 1 18-4Z" />
        <path d="M7 10h10M7 14h6" />
      </>
    ),
    inbox: (
      <>
        <path d="M4 4h16l2 13v3H2v-3L4 4Zm-2 13h6l2 3h4l2-3h6M12 7v7m-3-3 3 3 3-3" />
      </>
    ),
    settings: (
      <>
        <path d="M4 7h16M4 17h16" />
        <circle cx="9" cy="7" r="3" />
        <circle cx="16" cy="17" r="3" />
      </>
    ),
    audit: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
  };
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
function Page({ path }: { path: string }) {
  const route = path.split("?")[0] ?? "/";
  const parts = route.split("/").filter(Boolean);
  switch (parts[0]) {
    case undefined:
      return <Dashboard />;
    case "contacts":
      return parts[1] === "new" ? (
        <NewContact />
      ) : parts[1] ? (
        <ContactDetail id={parts[1]} />
      ) : (
        <Contacts />
      );
    case "segments":
      return parts[1] === "new" ? (
        <SegmentForm />
      ) : parts[1] ? (
        <SegmentForm id={parts[1]} />
      ) : (
        <Segments />
      );
    case "campaigns":
      return parts[1] === "new" ? (
        <NewCampaign />
      ) : parts[1] ? (
        <CampaignDetail id={parts[1]} />
      ) : (
        <Campaigns />
      );
    case "templates":
      return <Templates />;
    case "messages":
      return <Messages />;
    case "inbox":
      return <Inbox />;
    case "settings":
      return <Settings />;
    case "audit":
      return <AuditPage />;
    default:
      return (
        <Empty
          title="No encontramos esta página"
          description="Vuelve al resumen para continuar."
          link="/"
          label="Ir al resumen"
        />
      );
  }
}
function Layout() {
  const path = useHash();
  const { auth, logout } = useAuth();
  const settings = useLoad<SettingsData>("/settings");
  const action = useAction();
  useEffect(() => {
    const changed = () => settings.refresh();
    window.addEventListener("workspace-updated", changed);
    return () => window.removeEventListener("workspace-updated", changed);
  }, [settings.refresh]);
  const current = navigation.find((n) =>
    n.path === "/" ? path === "/" : path.startsWith(n.path),
  );
  const isDry =
    settings.data &&
    (settings.data.globalDryRun || settings.data.workspace.dryRun);
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main-content")?.focus();
          document.getElementById("main-content")?.scrollIntoView();
        }}
      >
        Saltar al contenido
      </a>
      <aside className="sidebar">
        <a className="brand" href="#/">
          <span className="brand-icon">
            t<span>•</span>
          </span>
          <span>
            takolo<small>ESPACIOS QUE CONECTAN</small>
          </span>
        </a>
        <p className="nav-label">TU ESPACIO</p>
        <nav aria-label="Navegación principal">
          {navigation.map((n) => (
            <a
              key={n.path}
              href={`#${n.path}`}
              className={current?.path === n.path ? "active" : ""}
              aria-current={current?.path === n.path ? "page" : undefined}
            >
              <Icon name={n.icon} />
              <span>{n.label}</span>
              {current?.path === n.path && <span className="nav-dot" />}
            </a>
          ))}
        </nav>
        <div className="sidebar-note">
          <span>✦</span>
          <strong>
            Menos tareas.
            <br />
            Más conversaciones.
          </strong>
          <p>Tus listas y horarios se quedan guardados.</p>
        </div>
      </aside>
      <div className="workspace">
        <div className="topbar">
          <div>
            <span className="connection-dot" />
            {settings.data?.workspace.name ?? "Tu espacio"}
            <span className="top-divider">/</span>
            <span className="muted">{current?.label ?? "Resumen"}</span>
          </div>
          <div className="user-menu">
            <span className="avatar">
              {auth.user.name.slice(0, 1).toUpperCase()}
            </span>
            <span>
              {auth.user.name}
              <small>
                {auth.role === "ADMIN" ? "Administración" : "Operación"}
              </small>
            </span>
            <button
              className="logout"
              title="Cerrar sesión"
              aria-label="Cerrar sesión"
              onClick={() => void action.run(logout, "")}
            >
              ↪
            </button>
          </div>
        </div>
        <main id="main-content" tabIndex={-1}>
          <div className="mode-strip">
            <span className={`mode-dot ${isDry ? "" : "real"}`} />
            {settings.data
              ? isDry
                ? "Modo de prueba · no se envían mensajes reales"
                : "Modo real · envíos por WhatsApp oficial"
              : "Consultando configuración del espacio"}
            <a href="#/settings">Revisar configuración →</a>
          </div>
          {settings.error && (
            <Notice kind="error">
              No se pudo consultar el modo de envío: {settings.error}
            </Notice>
          )}
          {settings.data &&
            settings.data.workspace.sendingState !== "ACTIVE" && (
              <Notice>
                El procesamiento está pausado.{" "}
                {settings.data.workspace.pauseReason ??
                  "Actívalo desde Configuración cuando estés listo."}
              </Notice>
            )}
          {action.feedback}
          <Page path={path} key={path} />
          <footer>
            TAKOLO <span>Hecho para conectar con claridad.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className="fatal">
        <h1>No se pudo mostrar esta pantalla.</h1>
        <p>Tus datos guardados se conservan. Recarga para continuar.</p>
        <Button onClick={() => window.location.reload()}>
          Recargar aplicación
        </Button>
      </div>
    ) : (
      this.props.children
    );
  }
}
export function App() {
  return (
    <ErrorBoundary>
      <AuthGate>
        <Layout />
      </AuthGate>
    </ErrorBoundary>
  );
}
