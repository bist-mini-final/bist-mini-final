from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

from PIL import Image, ImageDraw, ImageFont

from .cell_semantics import CELL_TYPE_COLORS
from .table_geometry import SheetLayout


def _font() -> Any:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=7)
        except OSError:
            continue
    return ImageFont.load_default()


def render_cell_type_overlay(
    source_path: Path,
    output_path: Path,
    layout: SheetLayout,
    cells: Iterable[Dict[str, Any]],
) -> None:
    """Tint populated cells by semantic value type without changing geometry."""

    with Image.open(source_path) as source:
        base = source.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    label_font = _font()

    for cell in cells:
        row = int(cell["row"])
        column = int(cell["column"])
        x1 = layout.x_offsets[column - 1]
        y1 = layout.y_offsets[row - 1]
        x2 = layout.x_offsets[column]
        y2 = layout.y_offsets[row]
        color = CELL_TYPE_COLORS[str(cell["type"])]
        rgb = tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))
        draw.rectangle((x1, y1, x2, y2), fill=(*rgb, 54), outline=(*rgb, 215), width=1)
        if cell.get("is_formula"):
            draw.rectangle((x1 + 1, y1 + 1, x2 - 1, y2 - 1), outline=(217, 70, 239, 235), width=2)
        coordinate = str(cell["coord"])
        box = draw.textbbox((x1 + 2, y1 + 1), coordinate, font=label_font)
        draw.rectangle(box, fill=(255, 255, 255, 190))
        draw.text((x1 + 2, y1 + 1), coordinate, fill=(15, 23, 42, 235), font=label_font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(base, overlay).convert("RGB").save(
        output_path,
        format="PNG",
        dpi=(150, 150),
    )
