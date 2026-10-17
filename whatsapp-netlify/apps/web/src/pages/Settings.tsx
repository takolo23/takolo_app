import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Settings as SettingsData, Bot } from "../api/types";
import { useLoad } from "../hooks/useLoad";
import { useAuth } from "../components/auth";
import {
  Header,
  Panel,
  Button,
  Field,
  Notice,
  Badge,
  Loading,
  useAction,
} from "../components/ui";
export function Settings() {
  const load = useLoad<SettingsData>("/settings");
  const { auth } = useAuth();
  const isAdmin = auth.role === "ADMIN";
  const action = useAction();
  const [name, setName] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [rate, setRate] = useState(1);
  const [bot, setBot] = useState<Bot>({
    enabled: false,
    greetingText: "",
    cooldownSecs: 60,
  });
  useEffect(() => {
    if (load.data) {
      setName(load.data.workspace.name);
      setDryRun(load.data.workspace.dryRun);
      setRate(load.data.workspace.messagesPerMinute);
      setBot({
        enabled: load.data.workspace.botConfig?.enabled ?? false,
        greetingText:
          load.data.workspace.botConfig?.greetingText ??
          "Hola. Un asesor te atenderá pronto. Responde BAJA para salir.",
        cooldownSecs: load.data.workspace.botConfig?.cooldownSecs ?? 60,
      });
    }
  }, [load.data]);
  if (load.loading && !load.data) return <Loading />;
  if (load.error || !load.data)
    return <Notice kind="error">{load.error}</Notice>;
  const settings = load.data;
  const stateLabels: Record<string, string> = {
    ACTIVE: "Activo",
    PAUSED: "Pausado",
    TOKEN_INVALID: "Revisar token",
    ACCOUNT_RESTRICTED: "Cuenta restringida",
    LOW_QUALITY: "Calidad baja",
  };
  const metaChecks = [
    { label: "Token de acceso", ok: settings.meta.tokenConfigured },
    {
      label: "Secreto de la aplicación",
      ok: settings.meta.appSecretConfigured,
    },
    {
      label: "Verificación del webhook",
      ok: settings.meta.verifyTokenConfigured,
    },
    { label: "ID del número", ok: settings.meta.phoneIdConfigured },
    {
      label: "Cuenta de WhatsApp Business",
      ok: settings.meta.businessIdConfigured,
    },
    { label: "Versión de Meta", ok: Boolean(settings.meta.graphVersion) },
  ];
  return (
    <>
      <Header
        title="Un espacio a tu medida"
        description="Configura tu conexión, el ritmo de envío y las respuestas que quieres dar automáticamente."
      >
        <Badge positive={settings.workspace.sendingState === "ACTIVE"}>
          {stateLabels[settings.workspace.sendingState] ??
            settings.workspace.sendingState}
        </Badge>
      </Header>
      {action.feedback}
      <div className="two-columns">
        <Panel
          title="Modo y ritmo de envío"
          description="El modo de prueba permite revisar el flujo sin contactar a nadie."
        >
          <form
            className="form-stack"
            onSubmit={(e) => {
              e.preventDefault();
              void action.run(async () => {
                await api("/settings", "PUT", {
                  name,
                  dryRun,
                  messagesPerMinute: rate,
                });
                load.refresh();
              });
            }}
          >
            <Field label="Nombre del espacio">
              <input
                required
                maxLength={100}
                disabled={!isAdmin}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
            <label className="check">
              <input
                type="checkbox"
                disabled={!isAdmin || settings.globalDryRun}
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
              />{" "}
              Modo de prueba · no enviar a WhatsApp
            </label>
            {settings.globalDryRun && (
              <p className="help">
                El alojamiento mantiene DRY_RUN activado. Para habilitar envíos
                reales, la administración debe cambiarlo en las variables
                privadas.
              </p>
            )}
            <Field
              label="Límite de mensajes por minuto"
              hint={`Máximo del servidor: ${settings.maximumPerMinute}. También se aplican los límites de Meta.`}
            >
              <input
                type="number"
                required
                min={1}
                max={settings.maximumPerMinute}
                disabled={!isAdmin}
                value={rate}
                onChange={(e) => setRate(Number(e.target.value) || 1)}
              />
            </Field>
            {isAdmin && (
              <Button type="submit" disabled={action.busy}>
                Guardar configuración
              </Button>
            )}
          </form>
          <div className="separator" />
          {settings.workspace.pauseReason && (
            <Notice>{settings.workspace.pauseReason}</Notice>
          )}
          {isAdmin && (
            <Button
              variant={
                settings.workspace.sendingState === "ACTIVE"
                  ? "secondary"
                  : "primary"
              }
              disabled={action.busy}
              onClick={() =>
                void action.run(
                  async () => {
                    await api(
                      `/settings/${settings.workspace.sendingState === "ACTIVE" ? "pause" : "resume"}`,
                      "POST",
                      {},
                    );
                    load.refresh();
                  },
                  settings.workspace.sendingState === "ACTIVE"
                    ? "Procesamiento pausado."
                    : "Procesamiento activado.",
                )
              }
            >
              {settings.workspace.sendingState === "ACTIVE"
                ? "Pausar procesamiento"
                : "Activar procesamiento"}
            </Button>
          )}
        </Panel>
        <Panel
          title="Conexión oficial de WhatsApp"
          description="Los datos privados se configuran en el alojamiento y nunca se muestran aquí."
        >
          <div className="connection-checks">
            {metaChecks.map((check) => (
              <div className="between" key={check.label}>
                <span>{check.label}</span>
                <Badge positive={check.ok}>
                  {check.ok ? "Configurado" : "Pendiente"}
                </Badge>
              </div>
            ))}
          </div>
          {isAdmin && (
            <div className="actions">
              <Button
                variant="secondary"
                disabled={action.busy}
                onClick={() =>
                  void action.run(async () => {
                    await api("/settings/verify-meta", "POST", {});
                    load.refresh();
                  }, "Conexión verificada. No se enviaron mensajes.")
                }
              >
                Comprobar conexión
              </Button>
              <a className="button secondary" href="#/templates">
                Ver plantillas
              </a>
            </div>
          )}
          <div className="separator" />
          <Field
            label="Dirección para recibir respuestas"
            hint="Regístrala como URL del webhook de WhatsApp en Meta."
          >
            <input
              readOnly
              value={settings.webhookUrl}
              onFocus={(e) => e.target.select()}
            />
          </Field>
          <Button
            variant="secondary"
            onClick={() =>
              void action.run(
                async () => navigator.clipboard.writeText(settings.webhookUrl),
                "Dirección copiada.",
              )
            }
          >
            Copiar dirección
          </Button>
        </Panel>
      </div>
      <Panel
        title="Tu bot de respuestas"
        description="Responde automáticamente a HOLA o MENU de contactos autorizados. BAJA y STOP retiran el permiso sin enviar otra respuesta."
      >
        <form
          className="form-stack"
          onSubmit={(e) => {
            e.preventDefault();
            void action.run(async () => {
              await api("/settings/bot", "PUT", bot);
              load.refresh();
            }, "Bot actualizado.");
          }}
        >
          <label className="check">
            <input
              type="checkbox"
              disabled={!isAdmin}
              checked={bot.enabled}
              onChange={(e) => setBot({ ...bot, enabled: e.target.checked })}
            />{" "}
            Activar respuestas automáticas
          </label>
          <Field label="Mensaje de bienvenida">
            <textarea
              rows={5}
              required
              maxLength={4096}
              disabled={!isAdmin}
              value={bot.greetingText}
              onChange={(e) => setBot({ ...bot, greetingText: e.target.value })}
            />
          </Field>
          <Field
            label="Tiempo mínimo entre respuestas a la misma persona"
            hint="Segundos. Solo responde dentro de las 24 horas posteriores a un mensaje entrante."
          >
            <input
              type="number"
              required
              min={60}
              max={86400}
              disabled={!isAdmin}
              value={bot.cooldownSecs}
              onChange={(e) =>
                setBot({ ...bot, cooldownSecs: Number(e.target.value) || 60 })
              }
            />
          </Field>
          {isAdmin && (
            <Button type="submit" disabled={action.busy}>
              Guardar bot
            </Button>
          )}
        </form>
      </Panel>
      {isAdmin && <Users />}
    </>
  );
}
function Users() {
  const load =
    useLoad<
      {
        role: string;
        user: { id: string; name: string; email: string; active: boolean };
      }[]
    >("/settings/users");
  const action = useAction();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("OPERATOR");
  return (
    <Panel
      title="Personas que colaboran contigo"
      description="Cada cuenta tiene su acceso. Solo administradores pueden cambiar la conexión y los límites."
    >
      {action.feedback}
      {load.error && <Notice kind="error">{load.error}</Notice>}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Persona</th>
              <th>Correo</th>
              <th>Rol</th>
            </tr>
          </thead>
          <tbody>
            {load.data?.map((member) => (
              <tr key={member.user.id}>
                <td>{member.user.name}</td>
                <td>{member.user.email}</td>
                <td>
                  {member.role === "ADMIN" ? "Administración" : "Operación"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="separator" />
      <form
        className="form-stack"
        onSubmit={(e) => {
          e.preventDefault();
          void action.run(async () => {
            await api("/settings/users", "POST", {
              name,
              email,
              password,
              role,
            });
            setName("");
            setEmail("");
            setPassword("");
            load.refresh();
          }, "Usuario creado.");
        }}
      >
        <h3>Agregar usuario</h3>
        <div className="form-grid">
          <Field label="Nombre de la persona">
            <input
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <Field label="Correo del usuario">
            <input
              type="email"
              required
              maxLength={254}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Field label="Contraseña inicial" hint="Mínimo 14 caracteres.">
            <input
              type="password"
              required
              minLength={14}
              maxLength={200}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Field label="Permisos">
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="OPERATOR">Operación · contactos y campañas</option>
              <option value="ADMIN">
                Administración · configuración completa
              </option>
            </select>
          </Field>
        </div>
        <Button type="submit" disabled={action.busy}>
          Crear usuario
        </Button>
      </form>
    </Panel>
  );
}
