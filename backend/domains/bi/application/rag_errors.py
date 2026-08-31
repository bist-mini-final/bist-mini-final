"""Shared BI-to-RAG boundary errors."""


from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RagPipelineContractError(Exception):
    code: str

    def __str__(self) -> str:
        return self.code


__all__ = ["RagPipelineContractError"]
