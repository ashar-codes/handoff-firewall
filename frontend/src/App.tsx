import { useCallback, useEffect, useState, lazy, Suspense } from "react";
import { NavLink, Route, Routes, Link } from "react-router-dom";
import {
  ShieldCheck,
  LayoutDashboard,
  ArrowRightLeft,
  CheckCheck,
  Workflow,
  History,
  Settings,
  LogOut,
  ArrowRight,
  type LucideIcon,
} from "lucide-react";
import { Button } from "./components/ui/button";
import { Field, ErrorBox, Empty, can } from "./components/common";
import { api, post } from "./lib";
import type { User } from "./types";
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Queue = lazy(() => import("./pages/Queue"));
const CaseWorkspace = lazy(() => import("./pages/CaseWorkspace"));
const ActionCenter = lazy(() => import("./pages/ActionCenter"));
const Workflows = lazy(() => import("./pages/Workflows"));
const AuditHistory = lazy(() => import("./pages/AuditHistory"));
const Admin = lazy(() => import("./pages/Admin"));
export default function App() {
  const [user, setUser] = useState<User | null>(null),
    [loading, setLoading] = useState(true),
    [toast, setToast] = useState("");
  useEffect(() => {
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);
  const notify = useCallback((s: string) => setToast(s), []);
  if (loading) return <div className="loading">Opening workspace…</div>;
  if (!user) return <Login onLogin={setUser} />;
  const links: [string, string, LucideIcon][] = [
    ["/", "Overview", LayoutDashboard],
    ["/cases", "Handoff queue", ArrowRightLeft],
    ["/actions", "Action center", CheckCheck],
    ["/workflows", "Workflow studio", Workflow],
    ["/audit", "Audit history", History],
  ];
  if (can(user, "admin")) links.push(["/admin", "Administration", Settings]);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link to="/" className="brand">
          <span className="brand-icon">
            <ShieldCheck size={24} />
          </span>
          <div>
            Handoff<span>FIREWALL</span>
          </div>
        </Link>
        <p className="nav-label">WORKSPACE</p>
        <nav>
          {links.map(([to, label, Icon]) => (
            <NavLink key={to} to={to} end={to === "/"}>
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={18} />
          <strong>Evidence before clearance</strong>
          <p>Every handoff stays accountable to its approved rules.</p>
        </div>
        <div className="user-block">
          <span className="avatar">{user.name.slice(0, 1)}</span>
          <div>
            <strong>{user.name}</strong>
            <small>{user.role}</small>
          </div>
          <button
            aria-label="Sign out"
            onClick={() =>
              post("/auth/logout")
                .then(() => setUser(null))
                .catch((e) => notify(e.message))
            }
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <div className="topbar">
          <span>
            <span className="live-dot" />
            Governed handoff operations
          </span>
          <span className="topbar-right">{user.email}</span>
        </div>
        <main>
          <Suspense fallback={<div className="loading">Opening page…</div>}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route
                path="/cases"
                element={<Queue user={user} notify={notify} />}
              />
              <Route
                path="/cases/:id"
                element={<CaseWorkspace user={user} notify={notify} />}
              />
              <Route
                path="/actions"
                element={<ActionCenter user={user} notify={notify} />}
              />
              <Route
                path="/workflows"
                element={<Workflows user={user} notify={notify} />}
              />
              <Route path="/audit" element={<AuditHistory />} />
              <Route
                path="/admin"
                element={<Admin user={user} notify={notify} />}
              />
              <Route
                path="*"
                element={
                  <Empty>
                    Page not found. <Link to="/">Return to overview</Link>
                  </Empty>
                }
              />
            </Routes>
          </Suspense>
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <span>{toast}</span>
          <button
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}
function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="login-layout">
      <div className="login-story">
        <ShieldCheck size={40} />
        <p className="eyebrow">HANDOFF FIREWALL</p>
        <h1>
          Move work forward.
          <br />
          Keep the evidence.
        </h1>
        <p>
          Investigate gaps. Resolve contradictions. Clear handoffs only when the
          receiving team has what it needs.
        </p>
        <div className="login-steps">
          <span>01 Investigate</span>
          <span>02 Repair</span>
          <span>03 Verify</span>
        </div>
      </div>
      <div className="login-form">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              onLogin(await post<User>("/auth/login", { email, password }));
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <ShieldCheck size={28} />
          <h2>Sign in to your workspace</h2>
          <p className="muted">Use the account created during local setup.</p>
          <Field label="Email">
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </Field>
          <Field label="Password">
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </Field>
          <ErrorBox error={error} />
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Signing in…" : "Sign in"}
            <ArrowRight size={16} />
          </Button>
          <p className="login-help">
            Sample accounts are created only by the development seed command. No
            default production password is supplied.
          </p>
        </form>
      </div>
    </div>
  );
}
