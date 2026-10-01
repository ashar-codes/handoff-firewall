import { useState } from "react";
import { Plus, ArrowRight, CheckCheck } from "lucide-react";
import { Button } from "../components/ui/button";
import { Modal } from "../components/ui/dialog";
import { useResource } from "../hooks";
import { post } from "../lib";
import type { Template, User, Rule } from "../types";
import {
  ErrorBox,
  PageTitle,
  Field,
  can,
  type Notify,
} from "../components/common";
export default function Workflows({
  user,
  notify,
}: {
  user: User;
  notify: Notify;
}) {
  const { data, error, refresh } = useResource<Template[]>("/templates"),
    users = useResource<User[]>("/users"),
    [editing, setEditing] = useState<Template | null>(null),
    [open, setOpen] = useState(false),
    [rules, setRules] = useState<Partial<Rule>[]>([]),
    [busy, setBusy] = useState(false);
  const start = (t: Template | null) => {
    setEditing(t);
    setRules(
      t
        ? t.rules.map((r) => ({ ...r }))
        : [
            {
              id: "purchase_order",
              label: "Customer purchase order",
              fields: ["po_number"],
              mandatory: true,
              review: false,
              depends_on: [],
              precedence: "none",
            },
          ],
    );
    setOpen(true);
  };
  const update = (i: number, patch: Partial<Rule>) =>
    setRules((old) => old.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <>
      <PageTitle
        eyebrow="CONFIGURATION / POLICIES"
        title="Workflow studio"
        description="Define what the receiving team needs. Every edit creates an immutable version."
      >
        {can(user, "policy") && (
          <Button onClick={() => start(null)}>
            <Plus size={16} />
            New workflow
          </Button>
        )}
      </PageTitle>
      <ErrorBox error={error} />
      <div className="workflow-list">
        {data?.map((t) => (
          <section key={t.id} className="panel workflow-card">
            <div className="panel-title">
              <div>
                <span className="eyebrow">VERSION {t.version}</span>
                <h2>{t.name}</h2>
              </div>
              {can(user, "policy") && (
                <Button variant="outline" size="sm" onClick={() => start(t)}>
                  Create new version
                </Button>
              )}
            </div>
            <div className="team-route">
              {t.source}
              <ArrowRight size={20} />
              {t.destination}
            </div>
            <div className="workflow-rules">
              {t.rules.map((r) => (
                <div key={r.id}>
                  <CheckCheck size={16} />
                  <span>{r.label}</span>
                  <small>
                    {r.mandatory ? "Required" : "Optional"}
                    {r.review ? " · Review" : ""}
                    {r.condition ? " · Conditional" : ""}
                  </small>
                </div>
              ))}
            </div>
            <p className="hash">Approved rule hash {t.rule_hash}</p>
          </section>
        ))}
      </div>
      <Modal
        title={editing ? "Create workflow version" : "Create workflow"}
        open={open}
        onOpenChange={setOpen}
      >
        <form
          className="form-grid"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            const f = new FormData(e.currentTarget);
            try {
              await post(
                editing
                  ? "/templates/" + editing.id + "/versions"
                  : "/templates",
                {
                  name: f.get("name"),
                  source: f.get("source"),
                  destination: f.get("destination"),
                  rules,
                },
              );
              setOpen(false);
              refresh();
            } catch (e) {
              notify((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Field label="Workflow name">
            <input name="name" required defaultValue={editing?.name} />
          </Field>
          <div className="two-columns">
            <Field label="Source team">
              <input name="source" required defaultValue={editing?.source} />
            </Field>
            <Field label="Receiving team">
              <input
                name="destination"
                required
                defaultValue={editing?.destination}
              />
            </Field>
          </div>
          {rules.map((r, i) => (
            <fieldset className="rule-editor" key={i}>
              <legend>Requirement {i + 1}</legend>
              <div className="two-columns">
                <Field label="Stable ID">
                  <input
                    value={r.id ?? ""}
                    required
                    onChange={(e) => update(i, { id: e.target.value })}
                  />
                </Field>
                <Field label="Label">
                  <input
                    value={r.label ?? ""}
                    required
                    onChange={(e) => update(i, { label: e.target.value })}
                  />
                </Field>
              </div>
              <Field label="Accepted field aliases (comma separated)">
                <input
                  value={r.fields?.join(",") ?? ""}
                  required
                  onChange={(e) =>
                    update(i, {
                      fields: e.target.value.split(",").map((x) => x.trim()),
                    })
                  }
                />
              </Field>
              <div className="two-columns">
                <Field label="Expected value (optional)">
                  <input
                    value={r.expected ?? ""}
                    onChange={(e) =>
                      update(i, { expected: e.target.value || null })
                    }
                  />
                </Field>
                <Field label="Owner">
                  <select
                    value={r.owner_id ?? ""}
                    onChange={(e) =>
                      update(i, { owner_id: e.target.value || null })
                    }
                  >
                    <option value="">Case owner</option>
                    {users.data?.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.name}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={r.mandatory ?? true}
                  onChange={(e) => update(i, { mandatory: e.target.checked })}
                />
                Mandatory
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={r.review ?? false}
                  onChange={(e) => update(i, { review: e.target.checked })}
                />
                Human evidence acceptance required
              </label>
              <Field label="Prerequisite IDs (comma separated)">
                <input
                  value={r.depends_on?.join(",") ?? ""}
                  onChange={(e) =>
                    update(i, {
                      depends_on: e.target.value
                        .split(",")
                        .map((x) => x.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </Field>
              <div className="two-columns">
                <Field label="Condition field (optional)">
                  <input
                    value={r.condition?.field ?? ""}
                    onChange={(e) =>
                      update(i, {
                        condition: e.target.value
                          ? {
                              field: e.target.value,
                              equals: r.condition?.equals ?? "yes",
                            }
                          : null,
                      })
                    }
                  />
                </Field>
                <Field label="Condition equals">
                  <input
                    value={r.condition?.equals ?? ""}
                    disabled={!r.condition}
                    onChange={(e) =>
                      update(i, {
                        condition: {
                          field: r.condition!.field,
                          equals: e.target.value,
                        },
                      })
                    }
                  />
                </Field>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setRules((old) => old.filter((_, j) => j !== i))}
              >
                Remove requirement
              </Button>
            </fieldset>
          ))}
          <Button
            type="button"
            variant="outline"
            onClick={() =>
              setRules((r) => [
                ...r,
                {
                  id: "requirement_" + (r.length + 1),
                  label: "",
                  fields: [""],
                  mandatory: true,
                  depends_on: [],
                  review: false,
                  precedence: "none",
                },
              ])
            }
          >
            <Plus size={14} />
            Add requirement
          </Button>
          <Button type="submit" disabled={busy || !rules.length}>
            Publish approved version
          </Button>
        </form>
      </Modal>
    </>
  );
}
