"""Two live workers against a disposable native PostgreSQL database named handoff_test.

Run from backend:
  TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/handoff_test \
    uv run python ../scripts/verify-pg-concurrency.py

Recreates the public schema of handoff_test only. Phase 1: two workers drain many queued cases.
Phase 2: a stale worker resumes after its lease was reclaimed and must be fenced.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import httpx
from sqlalchemy import create_engine, make_url, text

url = os.environ.get("TEST_DATABASE_URL", "")
if not url.startswith("postgresql") or make_url(url).database != "handoff_test":
    raise SystemExit("Set TEST_DATABASE_URL to a disposable PostgreSQL database named handoff_test")
backend = Path(__file__).resolve().parents[1] / "backend"
root = Path(tempfile.mkdtemp(prefix="handoff-pg-concurrency-"))
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
env = {
    **os.environ,
    "APP_ENV": "test",
    "MODEL_PROVIDER": "test",
    "DATABASE_URL": url,
    "STORAGE_PATH": str(root / "files"),
    "SEED_PASSWORD": "Concurrency-fixture-password-42",
    "FRONTEND_ORIGIN": "http://localhost:5173",
}
log = (root / "process.log").open("wb")
processes = []
CASES = 24

# Each worker records the claims it actually ran; tick() and its SKIP LOCKED claim are unchanged.
WORKER = """import os, sys, time
from pathlib import Path
from app import agents, worker
from app.providers import TestProvider
claims = Path(sys.argv[1]); release = Path(sys.argv[2]) if len(sys.argv) > 2 else None
class Slow(TestProvider):
    def structured(self, *args):
        if release:
            (claims.parent / (claims.name + ".entered")).write_text("1")
            while not release.exists():
                time.sleep(0.05)
        else:
            time.sleep(0.2)
        return super().structured(*args)
agents.provider = lambda: Slow()
original = worker.run_case
def recorded(case_id, tenant_id, actor_id, model=None, claim=None):
    with claims.open("a") as f:
        f.write(f"{os.getpid()} {claim[0]} {claim[1]}\\n")
    return original(case_id, tenant_id, actor_id, model=model, claim=claim)
worker.run_case = recorded
if release:
    worker.tick()
else:
    worker.main()
"""


def spawn(*args):
    p = subprocess.Popen([sys.executable, *args], cwd=backend, env=env, stdout=log, stderr=log)
    processes.append(p)
    return p


def run(*args):
    subprocess.run(
        [sys.executable, *args], cwd=backend, env=env, check=True, stdout=log, stderr=log
    )


def wait_for(predicate, seconds, message):
    end = time.time() + seconds
    while time.time() < end:
        if predicate():
            return
        time.sleep(0.2)
    raise AssertionError(message + "; see " + str(root / "process.log"))


try:
    engine = create_engine(url)
    with engine.begin() as connection:
        assert connection.execute(text("select current_database()")).scalar() == "handoff_test"
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    run("-m", "alembic", "upgrade", "head")
    run("-c", 'from app.seed import seed; import os; seed(os.environ["SEED_PASSWORD"])')
    spawn("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port))
    client = httpx.Client(
        base_url=f"http://127.0.0.1:{port}/api",
        headers={"Origin": env["FRONTEND_ORIGIN"]},
        timeout=20,
        trust_env=False,
    )

    def healthy():
        try:
            return client.get("/health").is_success
        except httpx.HTTPError:
            return False

    wait_for(healthy, 20, "API failed to start")
    client.post(
        "/auth/login", json={"email": "admin@example.test", "password": env["SEED_PASSWORD"]}
    ).raise_for_status()
    client.headers["X-CSRF-Token"] = client.cookies["hf_csrf"]
    template = client.post(
        "/templates",
        json={
            "name": "Concurrency",
            "source": "A",
            "destination": "B",
            "rules": [{"id": "po", "label": "PO", "fields": ["po"]}],
        },
    ).json()

    def new_case(key, complete):
        case = client.post(
            "/cases",
            json={
                "title": key,
                "business_key": key,
                "template_id": template["id"],
                "goal": "Ready",
            },
        ).json()
        if complete:
            client.post(
                f"/cases/{case['id']}/documents",
                files={"file": (key + ".txt", f"po: {key}".encode(), "text/plain")},
            ).raise_for_status()
        return case["id"]

    # Phase 1: queue every case before any worker exists, then start two workers together.
    cases = {new_case(f"C-{i:02d}", i % 2 == 0): i % 2 == 0 for i in range(CASES)}
    for case_id in cases:
        client.post(f"/cases/{case_id}/run", json={}).raise_for_status()
    claim_files = [root / "worker-a.claims", root / "worker-b.claims"]
    workers = [spawn("-c", WORKER, str(path)) for path in claim_files]

    def jobs():
        with engine.connect() as connection:
            return connection.execute(text("select id, case_id, status, attempts from jobs")).all()

    wait_for(lambda: all(j.status in {"DONE", "FAILED"} for j in jobs()), 180, "Jobs did not drain")
    for w in workers:
        w.terminate()
        w.wait(timeout=10)
    claims = [line.split() for path in claim_files for line in path.read_text().splitlines()]
    per_worker = Counter(pid for pid, _, _ in claims)
    per_job = Counter(job for _, job, _ in claims)
    all_jobs = jobs()
    assert len(all_jobs) == CASES and all(j.status == "DONE" for j in all_jobs), all_jobs
    assert all(j.attempts == 1 for j in all_jobs), "A job was claimed more than once"
    assert sorted(per_job) == sorted(j.id for j in all_jobs) and set(per_job.values()) == {1}
    assert len(per_worker) == 2, f"Both workers must claim work: {per_worker}"
    for case_id, complete in cases.items():
        detail = client.get(f"/cases/{case_id}").json()
        steps = Counter(e["data"]["step"] for e in detail["events"] if e["kind"] == "routing")
        executed = [e for e in detail["events"] if e["kind"] == "action_executed"]
        assert set(steps.values()) == {1}, f"Duplicate agent step in {case_id}: {steps}"
        if complete:
            assert detail["state"] == "READY" and not detail["actions"], detail["state"]
        else:
            assert detail["state"] == "WAITING", detail["state"]
            assert [a["status"] for a in detail["actions"]] == ["WAITING"]
            assert len(executed) == 1

    # Phase 2: worker A gets the shortest configurable lease and stalls inside its model call
    # past expiry. Its open checkpoint transaction keeps the job row locked, so worker B must
    # skip it. When A resumes, its next checkpoint must be fenced and roll back; B then
    # reclaims the expired job and completes it exactly once. No database row is edited.
    stale_case = new_case("STALE", False)
    # Prose makes the Evidence Agent call the model, which is where worker A stalls.
    client.post(
        f"/cases/{stale_case}/documents",
        files={"file": ("note.txt", b"The buyer will send the order shortly.", "text/plain")},
    ).raise_for_status()
    client.post(f"/cases/{stale_case}/run", json={}).raise_for_status()
    stale_claims, release = root / "stale.claims", root / "release"
    short = {"MAX_RUN_SECONDS": "15", "MODEL_TIMEOUT": "1"}
    stale = subprocess.Popen(
        [sys.executable, "-c", WORKER, str(stale_claims), str(release)],
        cwd=backend,
        env={**env, **short},
        stdout=log,
        stderr=log,
    )
    processes.append(stale)
    entered = root / "stale.claims.entered"
    wait_for(entered.exists, 30, "Stale worker did not reach its model call")
    fresh_claims = root / "fresh.claims"
    fresh_claims.touch()
    fresh = spawn("-c", WORKER, str(fresh_claims))
    lease = next(j for j in jobs() if j.case_id == stale_case)
    with engine.connect() as connection:
        lease_until = connection.execute(
            text("select lease_until from jobs where case_id = :c"), {"c": stale_case}
        ).scalar()
    wait_for(lambda: time.time() > lease_until + 3, 120, "Lease did not expire")
    assert not fresh_claims.read_text(), "Second worker claimed a job still locked by its owner"
    release.write_text("go")
    stale.wait(timeout=30)
    wait_for(
        lambda: client.get(f"/cases/{stale_case}").json()["state"] == "WAITING",
        60,
        "Reclaimed job did not finish",
    )
    fresh.terminate()
    fresh.wait(timeout=10)
    detail = client.get(f"/cases/{stale_case}").json()
    job = next(j for j in jobs() if j.case_id == stale_case)
    executed = [e for e in detail["events"] if e["kind"] == "action_executed"]
    completed = Counter(e["agent"] for e in detail["events"] if e["kind"] == "agent_completed")
    stale_gen = [line.split()[2] for line in stale_claims.read_text().splitlines()]
    fresh_gen = [line.split()[2] for line in fresh_claims.read_text().splitlines()]
    assert lease.attempts == 1 and stale_gen == ["1"] and fresh_gen == ["2"], (stale_gen, fresh_gen)
    assert stale.returncode == 0, "Stale worker crashed instead of yielding"
    assert job.status == "DONE" and job.attempts == 2, job
    assert detail["state"] == "WAITING" and len(detail["actions"]) == 1 and len(executed) == 1
    # The stalled extraction step must not have been committed twice.
    assert completed["Repair Planner"] == 1 and completed["Action Agent"] == 1, completed
    extracted = [e for e in detail["events"] if e["kind"] == "agent_completed"
                 and e["agent"] == "Evidence Agent" and "1 authorized" in e["summary"]]  # fmt: skip
    assert len(extracted) == 1, extracted
    result = {
        "workers": len(per_worker),
        "jobs": len(all_jobs),
        "claims_per_worker": sorted(per_worker.values()),
        "max_claims_per_job": max(per_job.values()),
        "stale_generation_fenced": True,
        "stale_job_attempts": job.attempts,
    }
    (root / "result.json").write_text(json.dumps(result))
    print("PASS:", json.dumps(result))
    print("Disposable verification directory:", root)
finally:
    for process in processes:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    log.close()
