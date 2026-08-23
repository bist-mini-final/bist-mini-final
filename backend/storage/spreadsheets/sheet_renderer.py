import textwrap
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openpyxl.styles.numbers import is_date_format
from openpyxl.utils.datetime import WINDOWS_EPOCH, from_excel
from PIL import Image, ImageDraw, ImageFont

from .table_geometry import SheetLayout, compute_sheet_layout

# Standard Office Theme Palette (Theme 0 ~ 11)
THEME_COLORS = {
    0: "#FFFFFF",  # Light 1
    1: "#000000",  # Dark 1
    2: "#E7E6E6",  # Light 2
    3: "#44546A",  # Dark 2
    4: "#5B9BD5",  # Accent 1 (Blue)
    5: "#ED7D31",  # Accent 2 (Orange)
    6: "#A5A5A5",  # Accent 3 (Gray)
    7: "#FFC000",  # Accent 4 (Gold/Yellow)
    8: "#4472C4",  # Accent 5 (Dark Blue)
    9: "#70AD47",  # Accent 6 (Green)
    10: "#0563C1", # Hyperlink
    11: "#954F72", # Followed Hyperlink
}

# Standard Excel 64 Indexed Colors Palette (OpenPyXL / ECMA-376)
INDEXED_COLORS = [
    "#000000", "#FFFFFF", "#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF",
    "#000000", "#FFFFFF", "#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF",
    "#800000", "#008000", "#000080", "#808000", "#800080", "#008080", "#C0C0C0", "#808080",
    "#9999FF", "#993366", "#FFFFCC", "#CCFFFF", "#660066", "#FF8080", "#0066CC", "#CCCCFF",
    "#000080", "#FF00FF", "#FFFF00", "#00FFFF", "#800080", "#800000", "#008080", "#0000FF",
    "#00CCFF", "#CCFFFF", "#CCFFCC", "#FFFF99", "#99CCFF", "#FF99CC", "#CC99FF", "#FFCC99",
    "#3366FF", "#33CCCC", "#99CC00", "#FFCC00", "#FF9900", "#FF6600", "#666699", "#969696",
    "#003366", "#339966", "#003300", "#333300", "#993300", "#993366", "#333399", "#333333",
]


def _rgb_color(color: Any, default: str) -> str:
    """
    Resolve an OpenPyXL color to a hexadecimal RGB string.
    
    Parameters:
        color (Any): Color value represented as an OpenPyXL color object or RGB string.
        default (str): Fallback color returned when the value cannot be resolved.
    
    Returns:
        str: Color in `#RRGGBB` format, or the specified default.
    """
    if color is None:
        return default

    # 1. Direct RGB or aRGB string
    if getattr(color, "type", None) == "rgb" or isinstance(color, str):
        value = str(getattr(color, "rgb", color)).lstrip("#")
        if len(value) == 8:
            value = value[2:]  # Strip Alpha channel
        if len(value) == 6:
            return f"#{value.upper()}"

    # 2. Indexed Color
    if getattr(color, "type", None) == "indexed":
        idx = getattr(color, "indexed", -1)
        if isinstance(idx, int) and 0 <= idx < len(INDEXED_COLORS):
            return INDEXED_COLORS[idx]

    # 3. Theme Color with tint calculation
    if getattr(color, "type", None) == "theme":
        theme_idx = getattr(color, "theme", -1)
        base = THEME_COLORS.get(theme_idx, default)
        tint = float(getattr(color, "tint", 0.0) or 0.0)
        if not tint or not base.startswith("#") or len(base) != 7:
            return base
        try:
            channels = [int(base[i : i + 2], 16) for i in (1, 3, 5)]
            adjusted = [
                round(channel * (1 + tint))
                if tint < 0
                else round(channel + (255 - channel) * tint)
                for channel in channels
            ]
            return "#" + "".join(f"{max(0, min(255, c)):02X}" for c in adjusted)
        except ValueError:
            return base

    return default


def _cell_fill(cell: Any) -> str:
    """
    Extracts the cell's background color from its fill definition.
    
    Parameters:
    	cell (Any): Cell whose background fill color is resolved.
    
    Returns:
    	str: The resolved hexadecimal background color, defaulting to white.
    """
    fill = getattr(cell, "fill", None)
    if fill is None or getattr(fill, "fill_type", None) in (None, "none"):
        return "#FFFFFF"

    fg = getattr(fill, "fgColor", None)
    if fg is not None:
        resolved = _rgb_color(fg, "#FFFFFF")
        if resolved and resolved != "#000000":
            return resolved

    start_color = getattr(fill, "start_color", None)
    if start_color is not None:
        resolved = _rgb_color(start_color, "#FFFFFF")
        if resolved and resolved != "#000000":
            return resolved

    return "#FFFFFF"


def _cell_text_and_color(cell: Any) -> Tuple[str, str]:
    """
    Format a cell's value according to its Excel number format and determine its font color.
    
    Parameters:
        cell (Any): Cell whose value, number format, font color, and fill are inspected.
    
    Returns:
        Tuple[str, str]: Formatted cell text and its hexadecimal font color.
    """
    value = cell.value
    default_font_color = _rgb_color(getattr(cell.font, "color", None), "#111827")
    if default_font_color == "#FFFFFF":
        # Ensure white text isn't invisible on white background
        bg = _cell_fill(cell)
        if bg.upper() in ("#FFFFFF", "#FFF", ""):
            default_font_color = "#111827"

    if value is None:
        return "", default_font_color

    num_fmt = str(getattr(cell, "number_format", "") or "")

    # Date formatting
    if isinstance(value, (date, datetime)) or (
        isinstance(value, (int, float)) and is_date_format(num_fmt)
    ):
        if not isinstance(value, (date, datetime)):
            workbook = getattr(getattr(cell, "parent", None), "parent", None)
            try:
                converted = from_excel(
                    value,
                    epoch=getattr(workbook, "epoch", WINDOWS_EPOCH),
                )
            except (OverflowError, ValueError):
                return str(value), default_font_color
            if isinstance(converted, (date, datetime)):
                return converted.strftime("%Y.%m.%d"), default_font_color
            return str(converted), default_font_color
        return value.strftime("%Y.%m.%d"), default_font_color

    # Float & Integer formatting with [Red] and negative support
    if isinstance(value, (int, float)):
        is_negative = value < 0
        has_red_fmt = "[Red]" in num_fmt or "[RED]" in num_fmt
        font_color = "#DC2626" if (is_negative and has_red_fmt) else default_font_color

        if "%" in num_fmt:
            decimals = 0
            if "." in num_fmt.split("%")[0]:
                decimals = max(0, min(4, len(num_fmt.split("%")[0].split(".")[1])))
            rendered = f"{abs(value) * 100:.{decimals}f}%"
            if is_negative:
                rendered = f"({rendered})" if "(" in num_fmt else f"-{rendered}"
            return rendered, font_color

        # Currency & Accounting
        has_parens = "(" in num_fmt or "_)" in num_fmt
        decimals = 2
        fmt_after_dot = ""
        if "." in num_fmt:
            fmt_after_dot = num_fmt.split(".")[1].split(";")[0].split(")")[0]
            decimals = max(0, min(4, fmt_after_dot.count("0") + fmt_after_dot.count("#")))
        elif isinstance(value, int):
            decimals = 0

        abs_val = abs(value)
        if decimals > 0:
            rendered = (
                f"{abs_val:,.{decimals}f}".rstrip("0").rstrip(".")
                if "#" in fmt_after_dot
                else f"{abs_val:,.{decimals}f}"
            )
        else:
            rendered = f"{round(abs_val):,}"

        if is_negative:
            rendered = f"({rendered})" if has_parens else f"-{rendered}"

        return rendered, font_color

    return str(value).strip(), default_font_color


def _font(size: int, bold: bool, italic: bool = False) -> Any:
    """
    Select a font matching the requested size and text styles.
    
    Parameters:
        size (int): Font size to load.
        bold (bool): Whether to use bold styling.
        italic (bool): Whether to use italic styling.
    
    Returns:
        Any: The matching system font, or PIL's default font when no candidate is available.
    """
    style_candidates = {
        (False, False): (
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ),
        (True, False): (
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (False, True): (
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
            "/Library/Fonts/Arial Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        ),
        (True, True): (
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
            "/Library/Fonts/Arial Bold Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
        ),
    }
    candidates = (*style_candidates[(bold, italic)], "/System/Library/Fonts/Helvetica.ttc")
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except (OSError, ValueError):
            continue
    return ImageFont.load_default()


def _text_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: Any,
) -> Tuple[int, int]:
    box = draw.multiline_textbbox((0, 0), text, font=font, spacing=1)
    return round(box[2] - box[0]), round(box[3] - box[1])


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: Any,
    max_width: float,
) -> str:
    if not text or max_width <= 4:
        return ""
    lines: List[str] = []
    for source_line in text.splitlines() or [text]:
        words = source_line.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if _text_size(draw, candidate, font)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)

    wrapped: List[str] = []
    for line in lines:
        if _text_size(draw, line, font)[0] <= max_width:
            wrapped.append(line)
            continue
        average_width = max(1.0, _text_size(draw, line, font)[0] / max(1, len(line)))
        character_count = max(1, int(max_width / average_width))
        wrapped.extend(
            textwrap.wrap(
                line,
                width=character_count,
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [""]
        )
    return "\n".join(wrapped)


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_size: int,
    bold: bool,
    italic: bool,
    max_width: float,
    max_height: float,
) -> Tuple[str, ImageFont.ImageFont, int, int]:
    """
    Finds the largest font size that allows text to fit within the specified dimensions.
    
    Parameters:
        max_width (float): Maximum allowed text width.
        max_height (float): Maximum allowed text height.
    
    Returns:
        Tuple[str, ImageFont.ImageFont, int, int]: The wrapped text, selected font, and rendered width and height.
    """
    for candidate_size in range(font_size, 5, -1):
        font = _font(candidate_size, bold, italic)
        wrapped = _wrap_text(draw, text, font, max_width)
        width, height = _text_size(draw, wrapped, font)
        if width <= max_width and height <= max_height:
            return wrapped, font, width, height
    font = _font(5, bold, italic)
    wrapped = _wrap_text(draw, text, font, max_width)
    width, height = _text_size(draw, wrapped, font)
    return wrapped, font, width, height


def _draw_border_line(
    draw: ImageDraw.ImageDraw,
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    style: Optional[str],
    color: str,
    side: str,  # 'top', 'bottom', 'left', 'right'
) -> None:
    """
    Draws a worksheet border along a line segment using the specified style and color.
    
    Parameters:
        style (Optional[str]): Border style, such as ``double``, ``medium``, ``thick``,
            ``dashed``, ``dotted``, or ``hair``.
        side (str): Position of the border on the cell: ``top``, ``bottom``, ``left``,
            or ``right``.
    """
    if not style or style in ("none", ""):
        return

    x1, y1 = p1
    x2, y2 = p2

    if style == "double":
        # Draw two distinct 1px lines with 1px space in between
        if side in ("top", "bottom"):
            offset = 1 if side == "top" else -1
            draw.line((x1, y1, x2, y2), fill=color, width=1)
            draw.line((x1, y1 + offset * 2, x2, y2 + offset * 2), fill=color, width=1)
        else:
            offset = 1 if side == "left" else -1
            draw.line((x1, y1, x2, y2), fill=color, width=1)
            draw.line((x1 + offset * 2, y1, x2 + offset * 2, y2), fill=color, width=1)
    elif style in ("thick", "medium"):
        width = 3 if style == "thick" else 2
        draw.line((x1, y1, x2, y2), fill=color, width=width)
    elif style in ("dashed", "mediumDashed", "dotted", "hair"):
        # Dotted / dashed simulated line
        draw.line((x1, y1, x2, y2), fill=color, width=1)
    else:
        # Default thin border
        draw.line((x1, y1, x2, y2), fill=color, width=1)


def _merge_map(worksheet: Any) -> Dict[Tuple[int, int], Optional[Tuple[int, int]]]:
    """
    Map each cell in merged ranges to its bottom-right boundary.
    
    Parameters:
    	worksheet (Any): Worksheet containing the merged cell ranges.
    
    Returns:
    	Dict[Tuple[int, int], Optional[Tuple[int, int]]]: Mapping from cell coordinates to the merged range's bottom-right coordinate for anchor cells, or `None` for other cells.
    """
    merged: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {}
    for cell_range in worksheet.merged_cells.ranges:
        for row in range(cell_range.min_row, cell_range.max_row + 1):
            for column in range(cell_range.min_col, cell_range.max_col + 1):
                merged[(row, column)] = (
                    (cell_range.max_row, cell_range.max_col)
                    if row == cell_range.min_row and column == cell_range.min_col
                    else None
                )
    return merged


class ExcelSheetRenderer:
    """Render one styled Excel worksheet to a high-fidelity PNG image matching Excel local view."""

    def render(
        self,
        worksheet: Any,
        output_path: Path,
        max_rows: int,
        max_columns: int,
    ) -> SheetLayout:
        """
        Render a worksheet as a PNG image.
        
        Parameters:
            worksheet (Any): Worksheet to render.
            output_path (Path): Destination path for the PNG image.
            max_rows (int): Maximum number of rows to include.
            max_columns (int): Maximum number of columns to include.
        
        Returns:
            SheetLayout: Computed layout of the rendered worksheet.
        """
        layout = compute_sheet_layout(worksheet, max_rows, max_columns)

        # Check if Excel gridlines should be shown
        show_gridlines = True
        if hasattr(worksheet, "views") and worksheet.views and hasattr(worksheet.views, "sheetView") and worksheet.views.sheetView:
            show_gridlines = getattr(worksheet.views.sheetView[0], "showGridLines", True) is not False

        image = Image.new("RGB", (layout.width, layout.height), "#FFFFFF")
        draw = ImageDraw.Draw(image)
        merged = _merge_map(worksheet)

        # ── Step 1: Draw Default Gridlines if enabled ─────────────────────────
        if show_gridlines:
            grid_color = "#E5E7EB"
            for row in range(1, layout.max_row + 1):
                y = layout.y_offsets[row]
                draw.line((0, y, layout.width, y), fill=grid_color, width=1)
            for col in range(1, layout.max_column + 1):
                x = layout.x_offsets[col]
                draw.line((x, 0, x, layout.height), fill=grid_color, width=1)

        # ── Step 2: Render Cell Fills, Borders, and Content ───────────────────
        for row in range(1, layout.max_row + 1):
            if layout.row_heights[row - 1] <= 0:
                continue
            for column in range(1, layout.max_column + 1):
                if layout.column_widths[column - 1] <= 0:
                    continue
                merge_end = merged.get((row, column), (row, column))
                if merge_end is None:
                    continue
                max_r, max_c = merge_end
                max_r = min(max_r, layout.max_row)
                max_c = min(max_c, layout.max_column)
                x1 = layout.x_offsets[column - 1]
                y1 = layout.y_offsets[row - 1]
                x2 = layout.x_offsets[max_c]
                y2 = layout.y_offsets[max_r]
                cell = worksheet.cell(row=row, column=column)

                # Fill
                fill_color = _cell_fill(cell)
                if fill_color.upper() not in ("#FFFFFF", "#FFF"):
                    draw.rectangle((x1, y1, x2, y2), fill=fill_color)

                # Borders
                border = getattr(cell, "border", None)
                if border:
                    default_border_color = "#000000"
                    if border.top and border.top.style:
                        _draw_border_line(
                            draw,
                            (x1, y1),
                            (x2, y1),
                            border.top.style,
                            _rgb_color(border.top.color, default_border_color),
                            "top",
                        )
                    if border.bottom and border.bottom.style:
                        _draw_border_line(
                            draw,
                            (x1, y2),
                            (x2, y2),
                            border.bottom.style,
                            _rgb_color(border.bottom.color, default_border_color),
                            "bottom",
                        )
                    if border.left and border.left.style:
                        _draw_border_line(
                            draw,
                            (x1, y1),
                            (x1, y2),
                            border.left.style,
                            _rgb_color(border.left.color, default_border_color),
                            "left",
                        )
                    if border.right and border.right.style:
                        _draw_border_line(
                            draw,
                            (x2, y1),
                            (x2, y2),
                            border.right.style,
                            _rgb_color(border.right.color, default_border_color),
                            "right",
                        )

                # Text & Typography
                text, font_color = _cell_text_and_color(cell)
                if not text:
                    continue

                font_sz = max(6, min(20, round(float(getattr(cell.font, "sz", 10) or 10))))
                is_bold = bool(getattr(cell.font, "bold", False))
                is_italic = bool(getattr(cell.font, "italic", False))

                text, font, text_width, text_height = _fit_text(
                    draw,
                    text,
                    font_sz,
                    is_bold,
                    is_italic,
                    max(1.0, x2 - x1 - 6),
                    max(1.0, y2 - y1 - 4),
                )

                # Alignment
                alignment = getattr(cell, "alignment", None)
                horiz = getattr(alignment, "horizontal", None)
                vert = getattr(alignment, "vertical", None)
                indent = int(getattr(alignment, "indent", 0) or 0) * 8

                if horiz == "right" or (isinstance(cell.value, (int, float)) and horiz not in ("left", "center", "centerContinuous")):
                    text_x = x2 - text_width - 4
                elif horiz in ("center", "centerContinuous"):
                    text_x = x1 + ((x2 - x1) - text_width) / 2
                else:
                    text_x = x1 + 4 + indent

                if vert == "top":
                    text_y = y1 + 2
                elif vert == "bottom":
                    text_y = y2 - text_height - 2
                else:
                    text_y = y1 + max(1.0, ((y2 - y1) - text_height) / 2)

                draw.multiline_text(
                    (text_x, text_y),
                    text,
                    fill=font_color,
                    font=font,
                    spacing=1,
                    align="center" if horiz in ("center", "centerContinuous") else "left",
                )

                # Underline
                underline_style = getattr(cell.font, "underline", None)
                if underline_style:
                    underline_y = min(y2 - 1, text_y + text_height + 1)
                    draw.line(
                        (text_x, underline_y, text_x + text_width, underline_y),
                        fill=font_color,
                        width=1,
                    )
                    if underline_style in ("double", "doubleAccounting"):
                        draw.line(
                            (text_x, underline_y + 2, text_x + text_width, underline_y + 2),
                            fill=font_color,
                            width=1,
                        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG", dpi=(150, 150))
        return layout
