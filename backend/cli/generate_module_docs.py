"""Regenerate checked-in module guides from the live module registry."""

from __future__ import annotations

from backend.bootstrap.container import RuntimeContainer
from backend.cli.documentation.module_docs import write_module_guides


def main() -> int:
    container = RuntimeContainer.create(initialize_schema=False)
    try:
        registry = container.services.module_registry
        paths = write_module_guides(
            registry.get(definition["type"])
            for definition in registry.definitions()
        )
    finally:
        container.close()
    print(f"generated {len(paths) - 1} module guides in {paths[0].parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
