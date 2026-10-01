import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import {
  Download,
  Play,
  CheckCircle2,
  AlertTriangle,
  Clock3,
  FileText,
  Activity,
  ChevronRight,
  Upload,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Modal } from "../components/ui/dialog";
import { AgentGraph } from "../components/AgentGraph";
import { ExternalDraftButton } from "../components/ExternalDraftButton";
import { ActionCard } from "../components/ActionCard";
import { Timeline } from "../components/Timeline";
import { useResource } from "../hooks";
import { api, post, date } from "../lib";
import type { Detail, Fact, User } from "../types";
import {
  ErrorBox,
  PageTitle,
  Field,
  StateBadge,
  Empty,
  can,
  type Notify,
} from "../components/common";
export default function CaseWorkspace({
  user,
  notify,
}: {
  user: User;
  notify: Notify;
}) {
  const { id } = useParams(),
    { data: c, error, refresh } = useResource<Detail>("/cases/" + id),
    [tab, setTab] = useState("Requirements"),
    [busy, setBusy] = useState(false),
    [selectedFact, setSelectedFact] = useState<Fact | null>(null),
    [contextOpen, setContextOpen] = useState(false),
    [liveStatus, setLiveStatus] = useState("Connecting to live updates");
  useEffect(() => {
    if (!id) return;
    const stream = new EventSource("/api/cases/" + id + "/events", {
      withCredentials: true,
    });
    let timer: ReturnType<typeof setTimeout> | undefined;
    stream.onmessage = () => {
      if (!timer)
        timer = setTimeout(() => {
          timer = undefined;
          refresh();
        }, 150);
    };
    stream.onopen = () => {
      setLiveStatus("Live updates connected");
      refresh();
    };
    stream.onerror = () => {
      setLiveStatus("Live updates reconnecting; periodic refresh is active");
      refresh();
    };
    const fallback = setInterval(refresh, 5000);
    return () => {
      stream.close();
      clearInterval(fallback);
      clearTimeout(timer);
    };
  }, [id, refresh]);
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      refresh();
      return true;
    } catch (e) {
      notify((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };
  if (!c)
    return error ? (
      <ErrorBox error={error} />
    ) : (
      <div className="loading" role="status">
        Loading case…
      </div>
    );
  return (
    <>
      <Link className="back-link" to="/cases">
        ← Handoff queue
      </Link>
      <PageTitle
        eyebrow={`${c.business_key} / ${c.source.toUpperCase()} → ${c.destination.toUpperCase()}`}
        title={c.title}
        description={`Goal: ${c.goal}`}
      >
        <Button asChild variant="outline">
          <a href={"/api/cases/" + id + "/export"}>
            <Download size={15} />
            Export package
          </a>
        </Button>
        {can(user, "operate") && (
          <Button
            disabled={
              busy ||
              c.jobs.some((j) => ["RUNNING", "QUEUED"].includes(j.status))
            }
            onClick={() => act(() => post("/cases/" + id + "/run"))}
          >
            <Play size={15} />
            {c.state === "READY" ? "Reverify handoff" : "Run investigation"}
          </Button>
        )}
      </PageTitle>
      <ErrorBox error={error || c.error || ""} />
      <div className="case-summary">
        <div>
          <StateBadge state={c.state} />
          {c.sample && <span className="sample-label">DEVELOPMENT SAMPLE</span>}
          <p>
            Workflow v{c.template.version} · Evidence revision {c.revision}
          </p>
        </div>
        <div className="case-readiness">
          <strong>{c.readiness}%</strong>
          <span>Requirements satisfied</span>
          <div className="progress-track">
            <i style={{ width: c.readiness + "%" }} />
          </div>
        </div>
        <div>
          <strong>
            {
              Object.values(c.statuses).filter(
                (s) => !["SATISFIED", "NOT_APPLICABLE"].includes(s.state),
              ).length
            }
          </strong>
          <p>Open requirement states</p>
        </div>
      </div>
      <div className="tabs" role="tablist" aria-label="Case sections">
        {[
          "Requirements",
          "Evidence",
          "Repair plan",
          "Agent activity",
          "History",
        ].map((t) => (
          <button
            role="tab"
            aria-selected={tab === t}
            key={t}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "Requirements" && (
        <div className="case-grid">
          <section className="panel">
            <div className="panel-title">
              <h2>Destination checklist</h2>
              <span>{c.template.rules.length} requirements</span>
            </div>
            {c.conflicts.length > 0 && (
              <div className="p-5" aria-label="Unresolved conflicts">
                <h3>Unresolved conflicts</h3>
                {c.conflicts.map((conflict) => (
                  <div key={conflict.id} className="mt-3">
                    <strong>
                      {
                        c.template.rules.find(
                          (r) => r.id === conflict.requirement_id,
                        )?.label
                      }
                    </strong>
                    <p className="muted text-sm">{conflict.explanation}</p>
                    {conflict.expected_value != null && (
                      <p>Policy expected: {conflict.expected_value}</p>
                    )}
                    <div className="fact-links">
                      {c.facts
                        .filter((f) => conflict.facts.includes(f.id))
                        .map((f) => (
                          <button key={f.id} onClick={() => setSelectedFact(f)}>
                            {f.value} ·{" "}
                            {c.documents.find((d) => d.id === f.document_id)
                              ?.name ?? f.location}
                          </button>
                        ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {c.template.rules.map((r) => {
              const s = c.statuses[r.id];
              return (
                <div className="requirement" key={r.id}>
                  <div className="requirement-icon">
                    {s?.state === "SATISFIED" ? (
                      <CheckCircle2 size={19} />
                    ) : s?.state === "CONFLICTING" ? (
                      <AlertTriangle size={19} />
                    ) : (
                      <Clock3 size={19} />
                    )}
                  </div>
                  <div className="requirement-body">
                    <div className="requirement-heading">
                      <h3>{r.label}</h3>
                      <StateBadge state={s?.state ?? "UNEVALUATED"} />
                    </div>
                    <p>
                      {s?.reason ?? "Run investigation to search for evidence."}
                    </p>
                    <small>
                      {r.mandatory ? "Mandatory" : "Optional"}
                      {r.review ? " · Human acceptance required" : ""}
                      {r.depends_on.length
                        ? " · Depends on " + r.depends_on.join(", ")
                        : ""}
                    </small>
                    <div className="fact-links">
                      {c.facts
                        .filter((f) => s?.facts.includes(f.id))
                        .map((f) => (
                          <button key={f.id} onClick={() => setSelectedFact(f)}>
                            <FileText size={13} />
                            {f.value}
                            <span>{f.accepted ? "Accepted" : "Candidate"}</span>
                          </button>
                        ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </section>
          <section className="panel">
            <div className="panel-title">
              <h2>What happens next</h2>
            </div>
            <div className="next-step">
              <Activity size={24} />
              <h3>
                {c.state === "READY"
                  ? "Ready for the receiver"
                  : c.state === "WAITING"
                    ? "Waiting on human input"
                    : "Investigation and repair"}
              </h3>
              <p>
                {c.state === "READY"
                  ? "All mandatory checks pass against the current evidence and policy version."
                  : c.actions.some(
                        (a) => a.approval_required && a.status === "PROPOSED",
                      )
                    ? "Review the proposed evidence acceptance in the Action center."
                    : c.actions.some((a) => a.status === "WAITING")
                      ? "Record the requested clarification, then review the new evidence."
                      : "Run the case to search its authorized evidence and identify the next permitted action."}
              </p>
              <Button variant="outline" onClick={() => setTab("Repair plan")}>
                Inspect repair plan
                <ChevronRight size={15} />
              </Button>
            </div>
            <div className="panel-foot">
              Changes to supporting evidence reopen verification and invalidate
              affected conclusions.
            </div>
            {can(user, "review") && (
              <div className="p-4 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setContextOpen(true)}
                >
                  Edit case conditions
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={
                    busy || c.state === "READY" || c.state === "ESCALATED"
                  }
                  onClick={() => {
                    const reason = window.prompt("Reason for escalation");
                    if (reason)
                      act(() =>
                        post("/cases/" + id + "/transition", {
                          state: "ESCALATED",
                          reason,
                        }),
                      );
                  }}
                >
                  Escalate case
                </Button>
              </div>
            )}
          </section>
        </div>
      )}
      {tab === "Evidence" && (
        <section className="panel">
          <div className="panel-title">
            <h2>Source documents</h2>
            {can(user, "operate") && (
              <label className="upload-button">
                <Upload size={16} />
                Upload evidence
                <input
                  type="file"
                  accept=".pdf,.txt,.csv,.json"
                  disabled={busy}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) {
                      const body = new FormData();
                      body.append("file", f);
                      act(() =>
                        api("/cases/" + id + "/documents", {
                          method: "POST",
                          body,
                        }),
                      );
                    }
                    e.target.value = "";
                  }}
                />
              </label>
            )}
          </div>
          {c.documents.length ? (
            c.documents.map((d) => (
              <details className="document" key={d.id}>
                <summary>
                  <FileText size={19} />
                  <div>
                    <strong>{d.name}</strong>
                    <small>
                      v{d.version} ·{" "}
                      {d.active ? "Current" : "Inactive / retained"} ·{" "}
                      {date(d.created_at)}
                    </small>
                  </div>
                  <a
                    href={"/api/documents/" + d.id + "/download"}
                    onClick={(e) => e.stopPropagation()}
                    aria-label={"Download " + d.name}
                  >
                    <Download size={16} />
                  </a>
                </summary>
                <p className="hash">SHA-256 {d.sha256}</p>
                {d.parse_error ? (
                  <ErrorBox error={d.parse_error} />
                ) : (
                  <pre>{d.text}</pre>
                )}
                {d.active && can(user, "review") && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const reason = window.prompt(
                        "Reason for excluding this source from active evidence",
                      );
                      if (reason)
                        act(() =>
                          post("/documents/" + d.id + "/exclude", { reason }),
                        );
                    }}
                  >
                    Exclude from active evidence
                  </Button>
                )}
                {d.active && can(user, "operate") && (
                  <label className="upload-button">
                    Replace with a new version
                    <input
                      type="file"
                      accept=".pdf,.txt,.csv,.json"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) {
                          const body = new FormData();
                          body.append("file", f);
                          body.append("replaces_id", d.id);
                          act(() =>
                            api("/cases/" + id + "/documents", {
                              method: "POST",
                              body,
                            }),
                          );
                        }
                        e.target.value = "";
                      }}
                    />
                  </label>
                )}
              </details>
            ))
          ) : (
            <Empty>Upload source evidence to begin investigation.</Empty>
          )}
        </section>
      )}
      {tab === "Repair plan" && (
        <section className="panel">
          <div className="panel-title">
            <h2>Minimum repair proposals</h2>
            <div className="flex items-center gap-3">
              <span className="muted text-xs">
                Effort scores are heuristics
              </span>
              {can(user, "operate") && (
                <ExternalDraftButton
                  caseData={c}
                  refresh={refresh}
                  notify={notify}
                />
              )}
            </div>
          </div>
          {c.actions.length ? (
            c.actions.map((a) => (
              <ActionCard
                key={a.id}
                action={a}
                user={user}
                notify={notify}
                refresh={refresh}
              />
            ))
          ) : (
            <Empty>No repair actions have been proposed.</Empty>
          )}
        </section>
      )}
      {tab === "Agent activity" && (
        <section className="panel">
          <div className="panel-title">
            <h2>Observed agent dispatches</h2>
            <span>Edges represent recorded backend routing</span>
          </div>
          <p className="panel-foot" role="status">
            {liveStatus}
          </p>
          <AgentGraph
            events={c.events}
            caseState={c.state}
            running={c.jobs.some((j) =>
              ["RUNNING", "QUEUED"].includes(j.status),
            )}
          />
          <Timeline
            events={c.events
              .filter((e) => e.agent)
              .slice()
              .reverse()}
          />
        </section>
      )}
      {tab === "History" && (
        <section className="panel">
          <div className="panel-title">
            <h2>Immutable case timeline</h2>
          </div>
          <Timeline events={c.events.slice().reverse()} />
        </section>
      )}
      <Modal
        title="Source-linked evidence"
        open={!!selectedFact}
        onOpenChange={(x) => {
          if (!x) setSelectedFact(null);
        }}
      >
        {selectedFact && (
          <>
            <dl className="fact-details">
              <dt>Value</dt>
              <dd>{selectedFact.value}</dd>
              <dt>Provenance</dt>
              <dd>
                {selectedFact.document_id
                  ? c.documents.find((d) => d.id === selectedFact.document_id)
                      ?.name
                  : selectedFact.location}
              </dd>
              <dt>Extraction</dt>
              <dd>
                {selectedFact.method} · {selectedFact.location}
              </dd>
              <dt>Source version</dt>
              <dd>{selectedFact.source_version}</dd>
              <dt>SHA-256</dt>
              <dd className="hash">{selectedFact.source_hash}</dd>
              <dt>Source quote</dt>
              <dd className="source-quote">{selectedFact.quote}</dd>
            </dl>
            {can(user, "review") && (
              <form
                className="form-grid"
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  const fact = selectedFact;
                  act(() =>
                    post("/facts/" + fact.id + "/review", {
                      accepted: f.get("decision") === "accept",
                      comment: f.get("comment"),
                      supersedes: f.getAll("supersedes"),
                    }),
                  ).then((ok) => {
                    if (ok) setSelectedFact(null);
                  });
                }}
              >
                <Field label="Evidence decision">
                  <select name="decision">
                    <option value="accept">Accept evidence</option>
                    <option value="reject">Reject evidence</option>
                  </select>
                </Field>
                <fieldset className="fieldset">
                  <legend>
                    Supersede conflicting evidence (explicit authority required)
                  </legend>
                  {c.facts
                    .filter(
                      (f) =>
                        f.requirement_id === selectedFact.requirement_id &&
                        f.id !== selectedFact.id,
                    )
                    .map((f) => (
                      <label className="checkbox" key={f.id}>
                        <input type="checkbox" name="supersedes" value={f.id} />
                        {f.value} · {f.location}
                      </label>
                    ))}
                </fieldset>
                <Field label="Decision reason">
                  <textarea name="comment" required />
                </Field>
                <Button type="submit" disabled={busy}>
                  Record human decision
                </Button>
              </form>
            )}
          </>
        )}
      </Modal>
      <Modal
        title="Case conditions"
        open={contextOpen}
        onOpenChange={setContextOpen}
      >
        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            let body;
            try {
              body = JSON.parse(String(f.get("context")));
            } catch {
              notify("Invalid JSON");
              return;
            }
            act(() =>
              api("/cases/" + id + "/context", {
                method: "PUT",
                body: JSON.stringify(body),
              }),
            ).then((ok) => {
              if (ok) setContextOpen(false);
            });
          }}
        >
          <p>
            Changing a condition invalidates prior decisions. Unknown condition
            fields block readiness.
          </p>
          <Field label="Conditions (JSON)">
            <textarea
              name="context"
              defaultValue={JSON.stringify(c.context, null, 2)}
              rows={6}
            />
          </Field>
          <Button type="submit">Save conditions</Button>
        </form>
      </Modal>
    </>
  );
}
