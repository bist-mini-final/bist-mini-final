import os
from pathlib import Path
from threading import Lock
from typing import List, Protocol, Sequence


class TableExtractor(Protocol):
    def detect(self, image_path: Path) -> List[Sequence[float]]:
        """Return table bounding boxes in image pixel coordinates."""


class DoclingTableExtractor:
    """Lazy Docling image converter that exposes table bounding boxes only."""

    def __init__(self) -> None:
        self._converter = None
        self._lock = Lock()

    def _load_converter(self):
        if self._converter is not None:
            return self._converter
        os.environ.setdefault("DOCLING_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("USE_TORCH", "1")
        os.environ.setdefault("USE_TF", "0")
        os.environ.setdefault("USE_FLAX", "0")
        from docling.backend.image_backend import ImageDocumentBackend
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import (
            DocumentConverter,
            InputFormat,
            PdfFormatOption,
        )

        pipeline_options = PdfPipelineOptions()
        # Rendered Excel text is already present in the image. OCRMac can block
        # its native Vision mutex on Python 3.9, and OCR is unnecessary when the
        # module only needs Docling's table layout bounding boxes.
        pipeline_options.do_ocr = False
        self._converter = DocumentConverter(
            allowed_formats=[InputFormat.IMAGE],
            format_options={
                InputFormat.IMAGE: PdfFormatOption(
                    pipeline_options=pipeline_options,
                    backend=ImageDocumentBackend,
                )
            },
        )
        return self._converter

    def detect(self, image_path: Path) -> List[Sequence[float]]:
        with self._lock:
            converter = self._load_converter()
            result = converter.convert(str(image_path))

        from PIL import Image

        with Image.open(image_path) as image:
            image_width, image_height = image.size

        boxes: List[Sequence[float]] = []
        pages = result.pages
        for table in result.document.tables:
            if not table.prov:
                continue
            provenance = table.prov[0]
            bbox = provenance.bbox
            page_index = provenance.page_no - 1
            page_width = float(image_width)
            page_height = float(image_height)
            if 0 <= page_index < len(pages) and pages[page_index].size is not None:
                page_width = float(pages[page_index].size.width)
                page_height = float(pages[page_index].size.height)
            x1 = float(bbox.l) / page_width * image_width
            y1 = (page_height - float(bbox.t)) / page_height * image_height
            x2 = float(bbox.r) / page_width * image_width
            y2 = (page_height - float(bbox.b)) / page_height * image_height
            boxes.append((x1, min(y1, y2), x2, max(y1, y2)))
        return boxes
