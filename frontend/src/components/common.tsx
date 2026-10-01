import type { ReactNode } from "react";
import { FileText, AlertTriangle } from "lucide-react";
import type { User } from "../types";
export type Notify = (message: string) => void;
export const can = (user: User, p: string) =>
  user.role === "Administrator" ||
  (p === "operate" && ["Operator", "Reviewer"].includes(user.role)) ||
  (p === "review" && user.role === "Reviewer") ||
  (p === "policy" && user.role === "Policy Manager");
export function StateBadge({ state }: { state: string }) {
  return (
    <span className={"state state-" + state.toLowerCase()}>
      {state.replaceAll("_", " ")}
    </span>
  );
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty">
      <FileText size={26} />
      <p>{children}</p>
    </div>
  );
}
export function ErrorBox({ error }: { error: string }) {
  return error ? (
    <div role="alert" className="error-box">
      <AlertTriangle size={18} />
      {error}
    </div>
  ) : null;
}
export function PageTitle({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-title">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="muted">{description}</p>
      </div>
      <div className="page-actions">{children}</div>
    </header>
  );
}
