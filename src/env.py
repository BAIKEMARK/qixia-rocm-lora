from __future__ import annotations

import os
from pathlib import Path


def load_repo_env(repo_dir: Path, filename: str = ".env", override: bool = False) -> Path | None:
    env_path = repo_dir / filename
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (override or key not in os.environ):
            os.environ[key] = value
    return env_path
