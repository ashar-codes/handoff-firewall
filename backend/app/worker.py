import logging
import time

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from .agents import run_case
from .config import settings
from .db import SessionLocal
from .domain import audit, scoped, transition
from .leases import LeaseLost, guard_claim
from .models import Case, Job, now

log = logging.getLogger(__name__)


def tick():
    with SessionLocal() as db:
        job = db.scalar(
            select(Job)
            .where(
                or_(Job.status == "QUEUED", (Job.status == "RUNNING") & (Job.lease_until < now()))
            )
            .order_by(Job.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return False
        exhausted = job.attempts >= 3
        job.status = "RUNNING"
        job.attempts += 1
        job.lease_until = now() + settings().max_run_seconds + settings().model_timeout * 4 + 60
        job_id, case_id, tenant_id, actor_id = job.id, job.case_id, job.tenant_id, job.actor_id
        claim = (job_id, job.attempts)
        db.commit()
    try:
        result = "FAILED" if exhausted else run_case(case_id, tenant_id, actor_id, claim=claim)
        if result == "LEASE_LOST":
            return True
        status = "FAILED" if result == "FAILED" else "DONE"
    except Exception:
        log.error("Job failed: %s", job_id)
        status = "FAILED"
    with SessionLocal() as db:
        # Checkpoint/finalization lock case then job. Claiming never waits for a
        # case while holding a job lock, preventing reversed lock ordering.
        case = scoped(db, Case, case_id, tenant_id, lock=True)
        try:
            guard_claim(db, case, claim)
        except LeaseLost:
            return True
        job = db.get(Job, job_id)
        if exhausted:
            if case.state not in {"READY", "ESCALATED"}:
                transition(db, case, "ESCALATED", "Worker recovery retry budget exhausted")
        elif status == "FAILED":
            case.error = "Worker failed; persisted evidence retained for authorized retry"
            audit(db, tenant_id, case_id, "worker_failed", case.error, data={"job_id": job_id})
            if case.state in {"CHECKING", "VERIFYING"}:
                transition(db, case, "BLOCKED", case.error)
        job.status = status
        job.active_key = None
        db.commit()
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    delay = 0.5
    while True:
        try:
            worked = tick()
            delay = 0.5
            if not worked:
                time.sleep(delay)
        except SQLAlchemyError:
            log.error("Database unavailable; worker will retry without discarding durable jobs")
            time.sleep(delay)
            delay = min(delay * 2, 10)


if __name__ == "__main__":
    main()
