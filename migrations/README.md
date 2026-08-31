# Database migrations

Alembic is the versioned source of truth for production schema changes. Revision
`20260827_0001` composes the schema fragments owned by data sources, workflow,
chatbot, BI, and benchmark without dropping or renaming existing user data. The
current linear head is `20260829_0005`. Add every future schema change as a new
revision; do not edit an applied revision.

Bootstrap schema composition remains a development/test initialization and drift
verification aid. Production deployment paths must run `alembic upgrade head`
before API or worker rollout; runtime initialization does not replace a revision.
The ownership and 22-table baseline are defined in
[`BP-503`](../docs/blueprints/05_interface_blueprints/BP-503_database_erd_and_ddl.md).
