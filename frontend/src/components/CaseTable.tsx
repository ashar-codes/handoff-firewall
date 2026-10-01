import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import type { Handoff } from "../types";
import { StateBadge, Empty } from "./common";
export function CaseTable({ cases }: { cases: Handoff[] }) {
  return cases.length ? (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Handoff</th>
            <th>Teams</th>
            <th>State</th>
            <th>Readiness</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.id}>
              <td>
                <Link className="case-link" to={"/cases/" + c.id}>
                  {c.business_key}
                  <strong>{c.title}</strong>
                </Link>
                {c.sample && <small className="sample-label">SAMPLE</small>}
              </td>
              <td>
                <span className="teams">
                  {c.source}
                  <ArrowRight size={13} />
                  {c.destination}
                </span>
              </td>
              <td>
                <StateBadge state={c.state} />
              </td>
              <td>
                <div className="readiness">
                  <span>{c.readiness}%</span>
                  <div className="progress-track">
                    <i style={{ width: c.readiness + "%" }} />
                  </div>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <Empty>No handoffs yet. Create a workflow and then a case.</Empty>
  );
}
