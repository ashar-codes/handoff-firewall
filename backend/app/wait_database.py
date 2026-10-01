import time

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from .db import engine

head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
for _attempt in range(60):
    try:
        with engine.connect() as connection:
            version = connection.scalar(text("SELECT version_num FROM alembic_version"))
        if version == head:
            break
        time.sleep(1)
    except Exception:
        time.sleep(1)
else:
    raise SystemExit("Database migrations did not become ready")
