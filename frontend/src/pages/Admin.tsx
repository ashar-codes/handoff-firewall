import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "../components/ui/button";
import { Modal } from "../components/ui/dialog";
import { ManageUser } from "../components/ManageUser";
import { useResource } from "../hooks";
import { post } from "../lib";
import type { User } from "../types";
import {
  ErrorBox,
  PageTitle,
  Field,
  can,
  type Notify,
} from "../components/common";
export default function Admin({
  user,
  notify,
}: {
  user: User;
  notify: Notify;
}) {
  const { data, error, refresh } = useResource<User[]>("/users"),
    system = useResource<{
      workspace: string;
      environment: string;
      provider: string;
      model: string;
      external_delivery: string;
      max_steps: number;
    }>("/system"),
    [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false);
  if (!can(user, "admin"))
    return <ErrorBox error="Administrator permission required" />;
  return (
    <>
      <PageTitle
        eyebrow="CONFIGURATION / ADMIN"
        title="Workspace administration"
        description="Manage local accounts and inspect runtime configuration."
      >
        <Button onClick={() => setOpen(true)}>
          <Plus size={16} />
          Create account
        </Button>
      </PageTitle>
      <ErrorBox error={error || system.error} />
      <section className="panel">
        <div className="panel-title">
          <h2>Users and access</h2>
          <span>Backend-enforced roles</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Email</th>
                <th>Role</th>
                <th>Access</th>
                <th>Manage</th>
              </tr>
            </thead>
            <tbody>
              {data?.map((u) => (
                <tr key={u.id}>
                  <td>{u.name}</td>
                  <td>{u.email}</td>
                  <td>{u.role}</td>
                  <td>{u.active ? "Active" : "Disabled"}</td>
                  <td>
                    <ManageUser
                      user={u}
                      actor={user}
                      refresh={refresh}
                      notify={notify}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {system.data && (
        <section className="panel mt-5">
          <div className="panel-title">
            <h2>Runtime and integrations</h2>
          </div>
          <dl className="runtime-grid">
            {Object.entries(system.data).map(([k, v]) => (
              <div key={k}>
                <dt>{k.replaceAll("_", " ")}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
          <p className="panel-foot">
            Model configuration is set through environment variables. External
            communication and ERP connectors are deferred; the application
            records approved drafts and internal requests only.
          </p>
        </section>
      )}
      <Modal title="Create local account" open={open} onOpenChange={setOpen}>
        <form
          className="form-grid"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            const f = new FormData(e.currentTarget);
            try {
              await post("/users", Object.fromEntries(f));
              setOpen(false);
              refresh();
            } catch (e) {
              notify((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Field label="Name">
            <input name="name" required />
          </Field>
          <Field label="Email">
            <input name="email" type="email" required />
          </Field>
          <Field label="Role">
            <select name="role">
              {[
                "Operator",
                "Reviewer",
                "Viewer",
                "Policy Manager",
                "Administrator",
              ].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </Field>
          <Field label="Initial password (12+ characters)">
            <input
              name="password"
              type="password"
              minLength={12}
              autoComplete="new-password"
              required
            />
          </Field>
          <Button type="submit" disabled={busy}>
            Create account
          </Button>
        </form>
      </Modal>
    </>
  );
}
