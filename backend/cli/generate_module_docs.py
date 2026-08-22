"""Regenerate checked-in module guides from the live module registry."""

from __future__ import annotations

from backend.engine.runtime.registry import ModuleRegistry
from backend.cli.documentation.module_docs import write_module_guides


def main() -> int:
    registry = ModuleRegistry()
    paths = write_module_guides(
        registry.get(definition["type"])
        for definition in registry.definitions()
    )
    print(f"generated {len(paths) - 1} module guides in {paths[0].parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
