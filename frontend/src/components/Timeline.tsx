import { date } from "../lib";
import type { AuditEvent } from "../types";
import { Empty } from "./common";
export function Timeline({ events }: { events: AuditEvent[] }) {
  return events.length ? (
    <ol className="timeline">
      {events.map((e) => (
        <li key={e.id}>
          <span className="timeline-dot" />
          <div>
            <div>
              <strong>{e.agent ?? e.kind.replaceAll("_", " ")}</strong>
              <time>{date(e.created_at)}</time>
            </div>
            <p>{e.summary}</p>
            {e.data.target && <small>Dispatch → {String(e.data.target)}</small>}
          </div>
        </li>
      ))}
    </ol>
  ) : (
    <Empty>No recorded activity yet.</Empty>
  );
}
