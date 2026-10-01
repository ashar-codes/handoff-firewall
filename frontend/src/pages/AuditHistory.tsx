import { Timeline } from "../components/Timeline";
import { useResource } from "../hooks";
import type { AuditEvent } from "../types";
import { ErrorBox, PageTitle } from "../components/common";
export default function AuditHistory() {
  const { data, error } = useResource<AuditEvent[]>("/audit");
  return (
    <>
      <PageTitle
        eyebrow="GOVERNANCE / AUDIT"
        title="Audit history"
        description="A persisted, append-only record of case decisions and workspace changes."
      />
      <ErrorBox error={error} />
      <section className="panel">
        <Timeline events={data ?? []} />
      </section>
    </>
  );
}
