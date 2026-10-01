import { Link } from "react-router-dom";
import {
  ArrowRightLeft,
  AlertTriangle,
  Clock3,
  CheckCircle2,
  ArrowRight,
  ChevronRight,
  ShieldCheck,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { CaseTable } from "../components/CaseTable";
import { useResource } from "../hooks";
import type { Handoff } from "../types";
import { ErrorBox, PageTitle, Empty, StateBadge } from "../components/common";
export default function Dashboard() {
  const { data, error } = useResource<Handoff[]>("/cases");
  if (!data)
    return error ? (
      <ErrorBox error={error} />
    ) : (
      <div className="loading" role="status">
        Loading workspace…
      </div>
    );
  const metrics = [
    {
      label: "Active handoffs",
      value: data.filter((c) => !["READY", "ESCALATED"].includes(c.state))
        .length,
      icon: ArrowRightLeft,
    },
    {
      label: "Blocked or escalated",
      value: data.filter((c) => ["BLOCKED", "ESCALATED"].includes(c.state))
        .length,
      icon: AlertTriangle,
    },
    {
      label: "Waiting for input",
      value: data.filter((c) => c.state === "WAITING").length,
      icon: Clock3,
    },
    {
      label: "Verified ready",
      value: data.filter((c) => c.state === "READY").length,
      icon: CheckCircle2,
    },
  ];
  const exceptions: Record<string, number> = {};
  data.forEach((c) =>
    Object.values(c.statuses).forEach((s) => {
      if (!["SATISFIED", "NOT_APPLICABLE"].includes(s.state))
        exceptions[s.state] = (exceptions[s.state] ?? 0) + 1;
    }),
  );
  return (
    <>
      <PageTitle
        eyebrow="OPERATIONS / OVERVIEW"
        title="Every handoff, accounted for."
        description="A live view of readiness, outstanding evidence and work waiting on people."
      >
        <Button asChild>
          <Link to="/cases">
            Open handoff queue
            <ArrowRight size={16} />
          </Link>
        </Button>
      </PageTitle>
      {data.some((c) => c.sample) && (
        <div className="sample-banner">
          Development sample records are labeled throughout this workspace.
        </div>
      )}
      <div className="metrics">
        {metrics.map((m) => (
          <div className="metric" key={m.label}>
            <span className="metric-icon">
              <m.icon size={20} />
            </span>
            <p>{m.label}</p>
            <strong>{m.value.toString().padStart(2, "0")}</strong>
          </div>
        ))}
      </div>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-title">
            <h2>Recent handoffs</h2>
            <Link to="/cases">
              View all <ChevronRight size={14} />
            </Link>
          </div>
          <CaseTable cases={data.slice(0, 6)} />
        </section>
        <section className="panel">
          <div className="panel-title">
            <h2>Open requirement states</h2>
            <AlertTriangle size={17} />
          </div>
          {Object.keys(exceptions).length ? (
            Object.entries(exceptions).map(([s, n]) => (
              <div className="exception-row" key={s}>
                <StateBadge state={s} />
                <strong>{n}</strong>
              </div>
            ))
          ) : (
            <Empty>No evaluated requirement gaps.</Empty>
          )}
          <div className="panel-foot">
            Counts come from persisted cases. Unevaluated cases are excluded
            from requirement-state counts.
          </div>
        </section>
      </div>
      <section className="principle-strip">
        <ShieldCheck size={26} />
        <div>
          <h3>Readiness is a decision backed by evidence.</h3>
          <p>
            A model suggestion cannot bypass approval, change a rule, or clear
            an incomplete handoff.
          </p>
        </div>
      </section>
    </>
  );
}
