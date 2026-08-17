"""Regenerate checked-in module guides from the live module registry."""

from __future__ import annotations

from ..documentation.module_docs import write_module_guides
from ..runtime.registry import ModuleRegistry
from ..storage.answer_cache import AnswerCacheRepository


def main() -> int:
    registry = ModuleRegistry(AnswerCacheRepository())
    paths = write_module_guides(
        registry.get(definition["type"])
        for definition in registry.definitions()
    )
    print(f"generated {len(paths) - 1} module guides in {paths[0].parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
