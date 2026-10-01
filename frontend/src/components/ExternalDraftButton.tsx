import { useState } from "react";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";
import { post } from "../lib";
import type { Detail } from "../types";
export function ExternalDraftButton({
  caseData: c,
  refresh,
  notify,
}: {
  caseData: Detail;
  refresh: () => void;
  notify: (s: string) => void;
}) {
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false);
  const unresolved = c.template.rules.filter(
    (r) => !["SATISFIED", "NOT_APPLICABLE"].includes(c.statuses[r.id]?.state),
  );
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        disabled={!unresolved.length}
        onClick={() => setOpen(true)}
      >
        Draft external clarification
      </Button>
      <Modal title="Prepare external draft" open={open} onOpenChange={setOpen}>
        <form
          className="form-grid"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            const f = new FormData(e.currentTarget);
            try {
              await post("/cases/" + c.id + "/external-drafts", {
                recipient: f.get("recipient"),
                message: f.get("message"),
                requirements: f.getAll("requirements"),
              });
              setOpen(false);
              refresh();
            } catch (e) {
              notify((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <p className="muted text-sm">
            A reviewer must approve the exact recipient and message. This
            version records the approved draft; it does not deliver email.
          </p>
          <label className="field">
            <span>Recipient email</span>
            <input type="email" name="recipient" required />
          </label>
          <fieldset className="fieldset">
            <legend>Requirements addressed</legend>
            {unresolved.map((r) => (
              <label className="checkbox" key={r.id}>
                <input
                  type="checkbox"
                  name="requirements"
                  value={r.id}
                  defaultChecked
                />
                {r.label}
              </label>
            ))}
          </fieldset>
          <label className="field">
            <span>Draft message</span>
            <textarea name="message" rows={5} maxLength={4000} required />
          </label>
          <Button type="submit" disabled={busy}>
            Create approval request
          </Button>
        </form>
      </Modal>
    </>
  );
}
