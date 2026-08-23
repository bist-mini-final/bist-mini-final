from __future__ import annotations

import pytest

from modules.common.exceptions import ModuleExecutionError
from modules.storage.qa_example_loader import (
    QaExampleLoaderConfigDTO,
    QaExampleLoaderInputDTO,
    QaExampleLoaderModule,
    QaExampleLoaderOutput,
)


def test_qa_loader_builtin_examples():
    module = QaExampleLoaderModule()
    input_dto = QaExampleLoaderInputDTO()
    res = module.execute(input_dto, config=QaExampleLoaderConfigDTO(include_builtin=True))

    validated = QaExampleLoaderOutput.model_validate(res)
    assert validated.total_count > 0
    assert validated.source == "builtin"
    assert len(validated.examples) > 0


def test_qa_loader_path_traversal_prevention():
    module = QaExampleLoaderModule()
    input_dto = QaExampleLoaderInputDTO(file_name="../secret.json")

    with pytest.raises(ModuleExecutionError):
        module.execute(input_dto)
