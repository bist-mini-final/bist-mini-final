"""Modules subpackage for common."""

from modules.common.base_module import (
    BaseModule,
    DocumentContextDTO,
    EmptyModuleConfigDTO,
    ExecutableModule,
    ModuleConfigDTO,
    ModuleConfigPreset,
    ModuleDefinition,
    ModuleDTO,
    ModuleExecutionError,
    ModuleExecutionRequestDTO,
    ModuleInputDTO,
    ModuleTaskPolicy,
    QueryContextDTO,
    question_id_for,
)

from modules.common.config import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_RETRIEVAL_TOP_K,
    DEFAULT_RRF_K,
    DEFAULT_VLM_MODEL,
    EMBEDDING_MODEL_OPTIONS,
    LLM_MODEL_OPTIONS,
)

__all__ = [
    "BaseModule",
    "DEFAULT_CONTEXT_WINDOW",
    "DEFAULT_EMBEDDING_DIMENSION",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_LLM_MODEL",
    "DEFAULT_RETRIEVAL_TOP_K",
    "DEFAULT_RRF_K",
    "DEFAULT_VLM_MODEL",
    "DocumentContextDTO",
    "EMBEDDING_MODEL_OPTIONS",
    "EmptyModuleConfigDTO",
    "ExecutableModule",
    "LLM_MODEL_OPTIONS",
    "ModuleConfigDTO",
    "ModuleConfigPreset",
    "ModuleDefinition",
    "ModuleDTO",
    "ModuleExecutionError",
    "ModuleExecutionRequestDTO",
    "ModuleInputDTO",
    "ModuleTaskPolicy",
    "QueryContextDTO",
    "question_id_for",
]

