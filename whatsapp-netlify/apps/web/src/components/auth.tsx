import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
  type FormEvent,
} from "react";
import { api, setCredentials } from "../api/client";
import type { Auth } from "../api/types";
import { Button, Field, Notice, Loading, useAction } from "./ui";
const AuthContext = createContext<{
  auth: Auth;
  reload: () => Promise<void>;
  logout: () => Promise<void>;
} | null>(null);
export const useAuth = () => {
  const value = useContext(AuthContext);
  if (!value) throw Error("No hay una sesión activa.");
  return value;
};
export function AuthGate({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<Auth | null>(null);
  const [loading, setLoading] = useState(true);
  async function reload() {
    const current = await api<Auth>("/auth/me");
    setCredentials(current.csrfToken, current.workspaceId);
    setAuth(current);
  }
  useEffect(() => {
    void reload()
      .catch(() => setAuth(null))
      .finally(() => setLoading(false));
    const expired = () => {
      setAuth(null);
      setCredentials("");
    };
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, []);
  async function logout() {
    await api("/auth/logout", "POST", {});
    setCredentials("");
    setAuth(null);
  }
  if (loading) return <Loading />;
  if (!auth) return <Login onSuccess={reload} />;
  return (
    <AuthContext.Provider value={{ auth, reload, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
function Login({ onSuccess }: { onSuccess: () => Promise<void> }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const action = useAction();
  function submit(event: FormEvent) {
    event.preventDefault();
    void action.run(async () => {
      setCredentials("");
      const result = await api<{ csrfToken: string }>("/auth/login", "POST", {
        email,
        password,
      });
      setCredentials(result.csrfToken);
      await onSuccess();
    }, "");
  }
  return (
    <div className="login-shell">
      <div className="login-intro">
        <a className="brand" href="#/">
          <span className="brand-icon">
            t<span>•</span>
          </span>
          <span>
            takolo<small>CONVERSACIONES QUE CONECTAN</small>
          </span>
        </a>
        <h1>
          Tu siguiente
          <br />
          conversación
          <br />
          <span>empieza aquí.</span>
        </h1>
        <p>
          Contactos organizados, campañas programadas y respuestas en un mismo
          espacio.
        </p>
        <div className="login-decoration">
          <span>01 · Organiza</span>
          <span>02 · Programa</span>
          <span>03 · Conecta</span>
        </div>
      </div>
      <div className="login-form panel">
        <p className="eyebrow">QUÉ BUENO VERTE</p>
        <h2>Entra a tu espacio.</h2>
        <p className="muted">Usa el acceso que te dio la administración.</p>
        {action.feedback}
        <form onSubmit={submit} className="form-stack">
          <Field label="Correo electrónico">
            <input
              type="email"
              autoComplete="username"
              required
              maxLength={254}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Field label="Contraseña">
            <input
              type="password"
              autoComplete="current-password"
              required
              maxLength={200}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Button type="submit" disabled={action.busy}>
            {action.busy ? "Entrando…" : "Entrar a mi espacio →"}
          </Button>
        </form>
        <Notice>
          La primera cuenta administradora se configura en el alojamiento. Las
          contraseñas nunca se comparten aquí.
        </Notice>
      </div>
    </div>
  );
}
