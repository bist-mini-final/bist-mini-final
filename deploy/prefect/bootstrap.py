"""Create the local Docker work pool and register project deployments."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import SecretStr


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

WORK_POOL_NAME = os.getenv("PREFECT_WORK_POOL_NAME", "bist-docker")
FLOW_IMAGE = os.getenv(
    "PREFECT_FLOW_IMAGE",
    "bist-excel-ingestion-prefect:local",
)
PREFECT_CLI = str(Path(sys.executable).with_name("prefect"))
DATABASE_SECRET_BLOCK = "bist-product-database-url"
OPENAI_SECRET_BLOCK = "bist-openai-api-key"


def _run(*args: str, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def _container_database_url(url: str) -> str:
    """Translate a host-local product DB URL for sibling Docker containers."""

    parsed = urlsplit(url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return url
    credentials = ""
    if parsed.username:
        credentials = parsed.username
        if parsed.password:
            credentials += ":" + parsed.password
        credentials += "@"
    return urlunsplit(
        (
            parsed.scheme,
            credentials + "bist-pgvector:5432",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def _set_default(template: dict[str, Any], name: str, value: Any) -> None:
    properties = template["variables"]["properties"]
    if name not in properties:
        raise KeyError(f"Docker work pool 변수를 찾을 수 없습니다: {name}")
    properties[name]["default"] = value


def main() -> int:
    # Importing settings loads the project .env without printing its secrets.
    from backend.core.settings import PGVECTOR_URL, PREFECT_FLOW_MEMORY_LIMIT
    from prefect.blocks.system import Secret

    database_url = _container_database_url(PGVECTOR_URL)
    Secret(value=SecretStr(database_url)).save(
        DATABASE_SECRET_BLOCK,
        overwrite=True,
    )
    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    if openai_api_key:
        Secret(value=SecretStr(openai_api_key)).save(
            OPENAI_SECRET_BLOCK,
            overwrite=True,
        )

    template_result = _run(
        PREFECT_CLI,
        "work-pool",
        "get-default-base-job-template",
        "--type",
        "docker",
        capture_output=True,
    )
    template = json.loads(template_result.stdout)
    runtime_environment = {
        "PREFECT_API_URL": "http://prefect-server:4200/api",
        "PGVECTOR_URL": (
            f"{{{{ prefect.blocks.secret.{DATABASE_SECRET_BLOCK} }}}}"
        ),
        "OPENAI_API_KEY": (
            f"{{{{ prefect.blocks.secret.{OPENAI_SECRET_BLOCK} }}}}"
            if openai_api_key
            else ""
        ),
        "OPENAI_BASE_URL": os.getenv(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ),
        "USE_PGVECTOR": "true",
        "DB_POOL_MIN_SIZE": "1",
        "DB_POOL_MAX_SIZE": "4",
    }
    _set_default(template, "image", FLOW_IMAGE)
    _set_default(template, "image_pull_policy", "Never")
    _set_default(template, "networks", ["bist-batch"])
    _set_default(template, "auto_remove", True)
    _set_default(
        template,
        "volumes",
        [f"{(PROJECT_ROOT / 'data').resolve()}:/app/data"],
    )
    _set_default(template, "stream_output", True)
    _set_default(template, "env", runtime_environment)
    if PREFECT_FLOW_MEMORY_LIMIT:
        _set_default(template, "mem_limit", PREFECT_FLOW_MEMORY_LIMIT)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        encoding="utf-8",
    ) as base_job_template:
        json.dump(template, base_job_template)
        base_job_template.flush()
        _run(
            PREFECT_CLI,
            "work-pool",
            "create",
            WORK_POOL_NAME,
            "--type",
            "docker",
            "--base-job-template",
            base_job_template.name,
            "--overwrite",
        )

    _run(PREFECT_CLI, "deploy", "--all", "--prefect-file", "prefect.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
