import os
from threading import Lock
from typing import Any, List, Optional

from modules.common.base_module import ModuleExecutionError


DEFAULT_BGE_MODEL = "BAAI/bge-large-en-v1.5"


class BgeEncoder:
    """Lazy, process-local BGE encoder using CLS pooling and L2 normalization."""

    def __init__(self, model_name: str = DEFAULT_BGE_MODEL) -> None:
        self.model_name = model_name
        self._tokenizer: Optional[Any] = None
        self._model: Optional[Any] = None
        self._device: Optional[Any] = None
        self._lock = Lock()

    def _load(self) -> None:
        if self._tokenizer is not None and self._model is not None:
            return
        os.environ.setdefault("USE_TORCH", "1")
        os.environ.setdefault("USE_TF", "0")
        os.environ.setdefault("USE_FLAX", "0")
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as error:
            raise ModuleExecutionError(
                "BGE 임베딩 실행에 필요한 torch와 transformers가 설치되지 않았습니다"
            ) from error

        try:
            tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                local_files_only=True,
            )
            model = AutoModel.from_pretrained(
                self.model_name,
                local_files_only=True,
            )
        except OSError as error:
            raise ModuleExecutionError(
                f"로컬에서 임베딩 모델을 불러올 수 없습니다: {self.model_name}"
            ) from error

        device = torch.device(
            "mps" if torch.backends.mps.is_available() else "cpu"
        )
        self._tokenizer = tokenizer
        self._model = model.to(device).eval()
        self._device = device

    def encode(self, queries: List[str]) -> List[List[float]]:
        if not queries:
            return []
        with self._lock:
            self._load()
            try:
                import torch

                inputs = self._tokenizer(
                    queries,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                ).to(self._device)
                with torch.no_grad():
                    output = self._model(**inputs)
                    vectors = output.last_hidden_state[:, 0]
                    vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
                return vectors.cpu().tolist()
            except (RuntimeError, ValueError, TypeError) as error:
                raise ModuleExecutionError("BGE 질의 임베딩 생성에 실패했습니다") from error
