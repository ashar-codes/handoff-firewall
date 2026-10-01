"""Fence every durable worker checkpoint with its current claim generation."""

from sqlalchemy import select

from .models import Job, now


class LeaseLost(Exception):
    pass


def guard_claim(db, case, claim):
    if claim is None:  # direct, synchronous invocation used by focused tests
        return
    job_id, generation = claim
    job = db.scalar(
        select(Job)
        .where(Job.id == job_id, Job.tenant_id == case.tenant_id, Job.case_id == case.id)
        .with_for_update()
    )
    if (
        not job
        or job.status != "RUNNING"
        or job.active_key != case.id
        or job.attempts != generation
        or job.lease_until <= now()
    ):
        raise LeaseLost("Worker claim is no longer current")
