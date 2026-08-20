# Local Prefect + Docker Work Pool

Prefect is the only batch scheduler. The Docker Worker creates one ephemeral
container per Excel ingestion Flow Run, and every Playground module appears as
a Prefect Task. Interactive Playground execution keeps its existing API path.

```bash
uv pip install --python .venv/bin/python -r requirements.txt
./deploy/prefect/local.sh all
```

The command starts product pgvector plus Prefect metadata PostgreSQL, Server,
and Docker Worker; builds the cached Flow image; stores runtime credentials in
Prefect Secret Blocks; and registers `excel-ingestion/docker`. No additional
cluster tooling or port-forwarding is required. Open the UI at
`http://127.0.0.1:4200`.

```bash
./deploy/prefect/local.sh status
./deploy/prefect/local.sh logs
./deploy/prefect/local.sh build
./deploy/prefect/local.sh deploy
./deploy/prefect/local.sh down
```

`down` removes only the Prefect control-plane containers and network attachment;
the named metadata volume and product pgvector data remain. The Worker mounts
the Docker socket so it can create Flow containers; use this profile only on a
trusted local machine.
