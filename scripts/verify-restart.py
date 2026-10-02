"""Actual process death/restart drill in a new, disposable SQLite test workspace.

Run from backend: uv run python ../scripts/verify-restart.py
The lease is deliberately expired after killing a worker, avoiding a minutes-long wait.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

backend = Path(__file__).resolve().parents[1] / "backend"
root = Path(tempfile.mkdtemp(prefix="handoff-restart-"))
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
env = {
    **os.environ,
    "APP_ENV": "test",
    "MODEL_PROVIDER": "test",
    "DATABASE_URL": f"sqlite:///{root}/test.db",
    "STORAGE_PATH": str(root / "files"),
    "SEED_PASSWORD": "Restart-fixture-password-42",
    "FRONTEND_ORIGIN": "http://localhost:5173",
}
processes = []
log = (root / "process.log").open("wb")


def command(code):
    return subprocess.run(
        [sys.executable, "-c", code], cwd=backend, env=env, check=True, stdout=log, stderr=log
    )


def start_api():
    p = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=backend,
        env=env,
        stdout=log,
        stderr=log,
    )
    processes.append(p)
    for _ in range(100):
        try:
            if httpx.get(
                f"http://127.0.0.1:{port}/api/health", timeout=1, trust_env=False
            ).is_success:
                return p
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError("API failed to start; see " + str(root / "process.log"))


def worker():
    command("from app.worker import tick; assert tick()")


try:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend,
        env=env,
        check=True,
        stdout=log,
        stderr=log,
    )
    command('from app.seed import seed; import os; seed(os.environ["SEED_PASSWORD"])')
    api = start_api()
    with httpx.Client(
        base_url=f"http://127.0.0.1:{port}/api",
        headers={"Origin": env["FRONTEND_ORIGIN"]},
        timeout=20,
        trust_env=False,
    ) as client:
        response = client.post(
            "/auth/login", json={"email": "admin@example.test", "password": env["SEED_PASSWORD"]}
        )
        response.raise_for_status()
        client.headers["X-CSRF-Token"] = client.cookies["hf_csrf"]
        template = client.post(
            "/templates",
            json={
                "name": "Restart drill",
                "source": "A",
                "destination": "B",
                "rules": [{"id": "po", "label": "PO", "fields": ["po"]}],
            },
        ).json()
        case = client.post(
            "/cases",
            json={
                "title": "Restart drill",
                "business_key": "RESTART",
                "template_id": template["id"],
                "goal": "Ready",
            },
        ).json()
        case_id = case["id"]
        # Prose makes the Evidence Agent call the model, which is where the worker is killed.
        client.post(
            f"/cases/{case_id}/documents",
            files={"file": ("note.txt", b"The buyer will send the order shortly.", "text/plain")},
        ).raise_for_status()
        client.post(f"/cases/{case_id}/run", json={}).raise_for_status()
        marker = root / "inside-model-call"
        # Kill a real worker inside its evidence-extraction transaction, after earlier checkpoints.
        code = f"""from app import agents, worker
from app.providers import TestProvider
from pathlib import Path
import time
class Slow(TestProvider):
 def structured(self,*args):
  Path({str(marker)!r}).write_text('entered')
  time.sleep(60)
  return super().structured(*args)
agents.provider=lambda:Slow()
worker.tick()
"""
        slow = subprocess.Popen(
            [sys.executable, "-c", code], cwd=backend, env=env, stdout=log, stderr=log
        )
        processes.append(slow)
        for _ in range(100):
            if marker.exists():
                break
            if slow.poll() is not None:
                raise RuntimeError("Worker stopped unexpectedly")
            time.sleep(0.1)
        assert marker.exists()
        slow.kill()
        slow.wait(timeout=5)
        command(
            "from app.db import SessionLocal; from app.models import Job; from sqlalchemy import select; "
            "db=SessionLocal(); job=db.scalar(select(Job).where(Job.status=='RUNNING')); job.lease_until=0; db.commit(); db.close()"
        )
        worker()
        waiting = client.get(f"/cases/{case_id}").json()
        assert waiting["state"] == "WAITING" and len(waiting["actions"]) == 1
        assert waiting["jobs"][0]["attempts"] == 2
        api.terminate()
        api.wait(timeout=10)
        api = start_api()
        assert client.get(f"/cases/{case_id}").json()["state"] == "WAITING"
        action = waiting["actions"][0]
        client.post(
            f"/actions/{action['id']}/reply",
            json={"values": {"po": "PO-RESTART"}, "comment": "Original source confirmed"},
        ).raise_for_status()
        worker()
        detail = client.get(f"/cases/{case_id}").json()
        review = next(
            a
            for a in detail["actions"]
            if a["kind"] == "review_evidence" and a["status"] == "PROPOSED"
        )
        client.post(
            f"/actions/{review['id']}/decision",
            json={
                "fingerprint": review["fingerprint"],
                "decision": "APPROVED",
                "comment": "Source reviewed",
            },
        ).raise_for_status()
        worker()
        assert client.get(f"/cases/{case_id}").json()["state"] == "READY"
        api.terminate()
        api.wait(timeout=10)
        api = start_api()
        result = client.get(f"/cases/{case_id}/export").json()
        assert result["state"] == "READY" and len(result["approvals"]) == 1
        assert (
            len(
                [
                    e
                    for e in result["events"]
                    if e["kind"] == "action_executed" and e["data"]["action_id"] == action["id"]
                ]
            )
            == 1
        )
        (root / "result.json").write_text(
            json.dumps(
                {
                    "state": result["state"],
                    "actions": len(result["actions"]),
                    "worker_claims": waiting["jobs"][0]["attempts"],
                }
            )
        )
    print(
        "PASS: killed worker recovery, one internal request, WAITING/API restart, approval/resume and READY/API restart."
    )
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
