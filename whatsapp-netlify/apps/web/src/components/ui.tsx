import {
  useState,
  useId,
  isValidElement,
  cloneElement,
  type ReactNode,
} from "react";
import { ApiError } from "../api/client";
export function Button({
  children,
  onClick,
  type = "button",
  disabled = false,
  variant = "primary",
}: {
  children: ReactNode;
  onClick?: () => void;
  type?: "button" | "submit";
  disabled?: boolean;
  variant?: "primary" | "secondary" | "danger";
}) {
  return (
    <button
      className={`button ${variant}`}
      type={type}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
export function Notice({
  children,
  kind = "info",
}: {
  children: ReactNode;
  kind?: "info" | "error" | "success";
}) {
  return (
    <div
      className={`notice ${kind}`}
      role={kind === "error" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {isValidElement<{ id?: string; "aria-describedby"?: string }>(children)
        ? cloneElement(children, {
            id,
            ...(hint ? { "aria-describedby": `${id}-hint` } : {}),
          })
        : children}
      {hint && <small id={`${id}-hint`}>{hint}</small>}
    </div>
  );
}
export function Header({
  eyebrow = "TU ESPACIO, ORGANIZADO",
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>
          {title}
          <span>.</span>
        </h1>
        <p className="muted">{description}</p>
      </div>
      <div className="actions">{children}</div>
    </header>
  );
}
export function Panel({
  title,
  description,
  children,
  actions,
}: {
  title?: string;
  description?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="panel">
      {title && (
        <div className="panel-head">
          <div>
            <h2>{title}</h2>
            {description && <p className="muted">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className="panel-body">{children}</div>
    </section>
  );
}
export function Empty({
  title,
  description,
  link,
  label,
}: {
  title: string;
  description: string;
  link?: string;
  label?: string;
}) {
  return (
    <div className="empty">
      <div className="empty-orbit">✦</div>
      <h3>{title}</h3>
      <p>{description}</p>
      {link && (
        <a className="button primary" href={`#${link}`}>
          {label ?? "Empezar"}
        </a>
      )}
    </div>
  );
}
export function Badge({
  children,
  positive = false,
}: {
  children: ReactNode;
  positive?: boolean;
}) {
  return (
    <span className={`badge ${positive ? "positive" : ""}`}>{children}</span>
  );
}
export function Pager({
  page,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  total: number;
  pageSize: number;
  onPage: (n: number) => void;
}) {
  const last = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pager">
      <span>
        {total} registros · Página {page} de {last}
      </span>
      <div className="actions">
        <Button
          variant="secondary"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          Anterior
        </Button>
        <Button
          variant="secondary"
          disabled={page >= last}
          onClick={() => onPage(page + 1)}
        >
          Siguiente
        </Button>
      </div>
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <span className="spinner" /> Cargando tu espacio…
    </div>
  );
}
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  async function run(fn: () => Promise<void>, message = "Cambios guardados.") {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await fn();
      setSuccess(message);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? `${e.message}${
              e.details.length
                ? " " +
                  e.details
                    .slice(0, 5)
                    .map((d) => `${d.row ? `Fila ${d.row}: ` : ""}${d.message}`)
                    .join(" ")
                : ""
            }`
          : e instanceof Error
            ? e.message
            : "No se pudo completar la operación.",
      );
    } finally {
      setBusy(false);
    }
  }
  return {
    busy,
    error,
    success,
    run,
    feedback: (
      <>
        {error && <Notice kind="error">{error}</Notice>}
        {success && <Notice kind="success">{success}</Notice>}
      </>
    ),
  };
}
export function CustomFields({
  value,
  onChange,
}: {
  value: { key: string; value: string }[];
  onChange: (v: { key: string; value: string }[]) => void;
}) {
  return (
    <div className="form-stack">
      <div className="between">
        <h3>Campos personalizados</h3>
        <Button
          variant="secondary"
          disabled={value.length >= 30}
          onClick={() => onChange([...value, { key: "", value: "" }])}
        >
          + Campo
        </Button>
      </div>
      {value.map((field, index) => (
        <div className="field-row" key={index}>
          <Field label="Nombre del campo">
            <input
              value={field.key}
              maxLength={50}
              pattern="[a-zA-Z][a-zA-Z0-9_]*"
              placeholder="Ej. ciudad"
              onChange={(e) =>
                onChange(
                  value.map((f, i) =>
                    i === index ? { ...f, key: e.target.value } : f,
                  ),
                )
              }
            />
          </Field>
          <Field label="Valor">
            <input
              value={field.value}
              maxLength={1000}
              placeholder="Ej. Guadalajara"
              onChange={(e) =>
                onChange(
                  value.map((f, i) =>
                    i === index ? { ...f, value: e.target.value } : f,
                  ),
                )
              }
            />
          </Field>
          <Button
            variant="secondary"
            onClick={() => onChange(value.filter((_, i) => i !== index))}
          >
            Quitar
          </Button>
        </div>
      ))}
    </div>
  );
}
