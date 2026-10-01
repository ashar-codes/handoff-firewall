import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { Button } from "../components/ui/button";
import { Modal } from "../components/ui/dialog";
import { CaseTable } from "../components/CaseTable";
import { useResource } from "../hooks";
import { post } from "../lib";
import type { Handoff, Template, User } from "../types";
import {
  ErrorBox,
  PageTitle,
  Field,
  can,
  type Notify,
} from "../components/common";
export default function Queue({
  user,
  notify,
}: {
  user: User;
  notify: Notify;
}) {
  const { data, error, refresh } = useResource<Handoff[]>("/cases"),
    templates = useResource<Template[]>("/templates"),
    users = useResource<User[]>("/users");
  const [query, setQuery] = useState(""),
    [state, setState] = useState(""),
    [source, setSource] = useState(""),
    [owner, setOwner] = useState(""),
    [sort, setSort] = useState("newest"),
    [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const filtered = (data ?? [])
    .filter(
      (c) =>
        (!state || c.state === state) &&
        (!source || c.source === source) &&
        (!owner || c.owner_id === owner) &&
        `${c.title} ${c.business_key} ${c.destination}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    )
    .sort((a, b) =>
      sort === "readiness"
        ? a.readiness - b.readiness
        : sort === "oldest"
          ? a.created_at - b.created_at
          : b.updated_at - a.updated_at,
    );
  return (
    <>
      <PageTitle
        eyebrow="OPERATIONS / CASES"
        title="Handoff queue"
        description="Find the next case to investigate, repair or review."
      >
        {can(user, "operate") && (
          <Button
            disabled={!templates.data?.length}
            onClick={() => setOpen(true)}
          >
            <Plus size={16} />
            New handoff
          </Button>
        )}
      </PageTitle>
      <ErrorBox error={error} />
      <section className="panel">
        <div className="filters">
          <label className="search-input">
            <Search size={16} />
            <input
              aria-label="Search cases"
              placeholder="Search title, ID or receiving team"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <select
            aria-label="Case state"
            value={state}
            onChange={(e) => setState(e.target.value)}
          >
            <option value="">All states</option>
            {[
              "NEW",
              "CHECKING",
              "BLOCKED",
              "WAITING",
              "VERIFYING",
              "READY",
              "ESCALATED",
            ].map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
          <select
            aria-label="Source team"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            <option value="">All source teams</option>
            {[...new Set(data?.map((c) => c.source))].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <select
            aria-label="Case owner"
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
          >
            <option value="">All owners</option>
            {users.data?.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
          <select
            aria-label="Sort cases"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            <option value="newest">Recently updated</option>
            <option value="oldest">Oldest first</option>
            <option value="readiness">Lowest readiness</option>
          </select>
        </div>
        <CaseTable cases={filtered} />
      </section>
      <Modal title="Create handoff" open={open} onOpenChange={setOpen}>
        <form
          className="form-grid"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            const f = new FormData(e.currentTarget);
            try {
              const c = await post<Handoff>("/cases", {
                title: f.get("title"),
                business_key: f.get("business_key"),
                template_id: f.get("template_id"),
                goal: f.get("goal"),
                context: can(user, "review")
                  ? JSON.parse(String(f.get("context") ?? "{}"))
                  : {},
              });
              setOpen(false);
              refresh();
              navigate("/cases/" + c.id);
            } catch (e) {
              notify((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Field label="Business ID">
            <input name="business_key" required maxLength={120} />
          </Field>
          <Field label="Title">
            <input name="title" required maxLength={180} />
          </Field>
          <Field label="Workflow version">
            <select name="template_id">
              {templates.data?.map((t) => (
                <option value={t.id} key={t.id}>
                  {t.name} · v{t.version}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Destination goal">
            <textarea
              name="goal"
              required
              defaultValue="Ready for receiving-team review"
            />
          </Field>
          {can(user, "review") && (
            <Field label="Case conditions (JSON object)">
              <textarea name="context" defaultValue="{}" />
            </Field>
          )}
          <p className="muted">
            Conditional rules stay unresolved until a reviewer supplies their
            applicability inputs.
          </p>
          <Button disabled={busy} type="submit">
            Create case
          </Button>
        </form>
      </Modal>
    </>
  );
}
