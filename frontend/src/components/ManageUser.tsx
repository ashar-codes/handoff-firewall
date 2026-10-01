import { useState } from "react";
import { api } from "../lib";
import type { User } from "../types";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";
export function ManageUser({
  user,
  actor,
  refresh,
  notify,
}: {
  user: User;
  actor: User;
  refresh: () => void;
  notify: (s: string) => void;
}) {
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false);
  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        Manage
      </Button>
      <Modal title={"Manage " + user.name} open={open} onOpenChange={setOpen}>
        <form
          className="form-grid"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            const f = new FormData(e.currentTarget);
            try {
              await api("/users/" + user.id, {
                method: "PATCH",
                body: JSON.stringify({
                  role: f.get("role"),
                  active: f.get("active") === "yes",
                  password: String(f.get("password") || "") || null,
                }),
              });
              setOpen(false);
              refresh();
              if (user.id === actor.id) location.reload();
            } catch (e) {
              notify((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="field">
            <span>Role</span>
            <select name="role" defaultValue={user.role}>
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
          </label>
          <label className="field">
            <span>Access</span>
            <select name="active" defaultValue={user.active ? "yes" : "no"}>
              <option value="yes">Active</option>
              <option value="no">Disabled</option>
            </select>
          </label>
          <label className="field">
            <span>Reset password (optional, 12+ characters)</span>
            <input
              type="password"
              name="password"
              minLength={12}
              autoComplete="new-password"
            />
          </label>
          <p className="muted text-sm">
            Saving revokes this user’s existing sessions. You cannot disable or
            demote your own administrator account.
          </p>
          <Button type="submit" disabled={busy}>
            Save access changes
          </Button>
        </form>
      </Modal>
    </>
  );
}
