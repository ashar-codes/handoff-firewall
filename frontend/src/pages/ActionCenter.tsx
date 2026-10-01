import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "../components/ui/button";
import { ActionCard } from "../components/ActionCard";
import { useResource } from "../hooks";
import type { Action, User } from "../types";
import { ErrorBox, PageTitle, Empty, type Notify } from "../components/common";
export default function ActionCenter({
  user,
  notify,
}: {
  user: User;
  notify: Notify;
}) {
  const { data, error, refresh } = useResource<Action[]>("/actions"),
    [filter, setFilter] = useState("pending");
  return (
    <>
      <PageTitle
        eyebrow="GOVERNANCE / ACTIONS"
        title="Action center"
        description="Review proposed actions, record clarification and inspect exact approval context."
      >
        <Button variant="outline" onClick={refresh}>
          <RefreshCw size={16} />
          Refresh
        </Button>
      </PageTitle>
      <ErrorBox error={error} />
      <div className="filters">
        <select
          aria-label="Action filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="pending">Active actions</option>
          <option value="approval">Approval inbox</option>
          <option value="all">All actions</option>
        </select>
      </div>
      <div className="panel">
        {data
          ?.filter(
            (a) =>
              filter === "all" ||
              (filter === "approval"
                ? a.approval_required && a.status === "PROPOSED"
                : ["PROPOSED", "APPROVED", "WAITING"].includes(a.status)),
          )
          .map((a) => (
            <ActionCard
              key={a.id}
              action={a}
              user={user}
              notify={notify}
              refresh={refresh}
            />
          ))}
        {!data?.length && <Empty>No actions have been proposed yet.</Empty>}
      </div>
    </>
  );
}
