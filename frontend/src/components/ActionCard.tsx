import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";
import { post } from "../lib";
import type { Action, User } from "../types";
import { StateBadge, Field, can, type Notify } from "./common";
export function ActionCard({
  action: a,
  user,
  notify,
  refresh,
}: {
  action: Action;
  user: User;
  notify: Notify;
  refresh: () => void;
}) {
  const outstanding = a.payload.requirements.filter(
    (k) => !a.result?.answered_requirements?.includes(k),
  );
  const [mode, setMode] = useState(""),
    [busy, setBusy] = useState(false);
  const submit = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      setMode("");
      refresh();
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <article
      className={
        "action-card " +
        (["INVALIDATED", "COMPLETED", "REJECTED"].includes(a.status)
          ? "historical"
          : "")
      }
    >
      <div className="action-card-title">
        <div>
          <span className="eyebrow">{a.kind.replaceAll("_", " ")}</span>
          <h3>{a.payload.requirements.join(" · ")}</h3>
        </div>
        <StateBadge state={a.status} />
      </div>
      <p>{a.payload.message}</p>
      <small>{a.reason}</small>
      <div className="action-meta">
        <span>Effort {a.effort}</span>
        <span>
          {a.approval_required
            ? "Human approval required"
            : "Permitted internal action"}
        </span>
        <Link to={"/cases/" + a.case_id}>
          Open case
          <ChevronRight size={13} />
        </Link>
      </div>
      <details>
        <summary>Exact action and approval context</summary>
        <p className="hash">Fingerprint {a.fingerprint}</p>
        <pre>
          {JSON.stringify(
            {
              payload: a.payload,
              snapshot: a.snapshot,
              prerequisites: a.prerequisites,
            },
            null,
            2,
          )}
        </pre>
      </details>
      <div className="action-buttons">
        {a.approval_required &&
          ["PROPOSED", "APPROVED"].includes(a.status) &&
          can(user, "review") && (
            <>
              <Button
                size="sm"
                disabled={busy}
                onClick={() => setMode("approve")}
              >
                Approve action
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => setMode("reject")}
              >
                Reject
              </Button>
            </>
          )}
        {a.status === "WAITING" &&
          a.kind === "internal_clarification" &&
          can(user, "operate") &&
          (user.id === a.owner_id || can(user, "review")) && (
            <Button size="sm" onClick={() => setMode("reply")}>
              Record clarification
            </Button>
          )}
        {a.status === "PROPOSED" &&
          !a.approval_required &&
          can(user, "operate") && (
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                submit(() => post("/actions/" + a.id + "/execute"))
              }
            >
              Create internal request
            </Button>
          )}
      </div>
      <Modal
        title={
          mode === "reply" ? "Record clarification" : "Review exact action"
        }
        open={!!mode}
        onOpenChange={(x) => {
          if (!x) setMode("");
        }}
      >
        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            if (mode === "reply") {
              const values: Record<string, string> = {};
              outstanding.forEach((k) => {
                const v = String(f.get(k) ?? "").trim();
                if (v) values[k] = v;
              });
              submit(() =>
                post("/actions/" + a.id + "/reply", {
                  values,
                  comment: f.get("comment"),
                }),
              );
            } else
              submit(() =>
                post("/actions/" + a.id + "/decision", {
                  fingerprint: a.fingerprint,
                  decision: mode === "approve" ? "APPROVED" : "REJECTED",
                  comment: f.get("comment"),
                }),
              );
          }}
        >
          <p>{a.payload.message}</p>
          {mode !== "reply" &&
            a.payload.evidence?.map((f) => (
              <div key={f.id} className="source-quote">
                <strong>{f.value}</strong>
                <p>{f.quote}</p>
                <small>
                  {f.location} · Source v{f.source_version}
                </small>
                <p className="hash">SHA-256 {f.source_hash}</p>
              </div>
            ))}
          {mode === "reply" &&
            outstanding.map((k) => (
              <Field key={k} label={k + " (leave blank if unresolved)"}>
                <input name={k} maxLength={2000} />
              </Field>
            ))}
          <Field label="Reason / source of clarification">
            <textarea name="comment" required />
          </Field>
          <p className="muted text-sm">
            {mode === "reply"
              ? "Replies are candidate evidence until a reviewer accepts them."
              : "Approval binds to the displayed payload, recipient and evidence/rule versions."}
          </p>
          <Button type="submit" disabled={busy}>
            {mode === "reply"
              ? "Submit clarification"
              : mode === "approve"
                ? "Confirm approval"
                : "Confirm rejection"}
          </Button>
        </form>
      </Modal>
    </article>
  );
}
