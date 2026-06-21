"""Centralized Excel styling for audit workpapers (CM and EAD).

One house style across all sheets and both modules: frozen headers, consistent
fonts, number formats, borders, and column widths.
"""

from __future__ import annotations

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ─────────────────────────────────────────────────────────────────────────────
# Colors & fills
# ─────────────────────────────────────────────────────────────────────────────

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
DATA_FONT = Font(size=10)

# ─────────────────────────────────────────────────────────────────────────────
# Borders
# ─────────────────────────────────────────────────────────────────────────────

THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

# ─────────────────────────────────────────────────────────────────────────────
# Number formats
# ─────────────────────────────────────────────────────────────────────────────

# ₹ with thousands separator, 2 decimals
RUPEE_FORMAT = '"₹"#,##0.00'

# ₹ with thousands separator, no decimals (for whole amounts)
RUPEE_FORMAT_INT = '"₹"#,##0'

# Percentage with 2 decimals
PERCENT_FORMAT = '0.00"%"'

# Thousands separator, 2 decimals (for quantities)
QUANTITY_FORMAT = "#,##0.00"

# Thousands separator, no decimals
QUANTITY_FORMAT_INT = "#,##0"


def apply_header_style(ws, row: int = 1):
    """Apply header styling to the first row of a worksheet.

    Args:
        ws: openpyxl worksheet
        row: Row number to style as header (default 1)
    """
    for col_idx, col_letter in enumerate(
        [get_column_letter(i) for i in range(1, ws.max_column + 1)], 1
    ):
        cell = ws[f"{col_letter}{row}"]
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def freeze_header(ws):
    """Freeze the first row and enable autofilter."""
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def set_column_width(ws, col_idx: int, width: int | None = None):
    """Set a column width, capping at 40 for readability.

    Args:
        ws: openpyxl worksheet
        col_idx: Column index (1-based)
        width: Desired width; if None, auto-set to 20
    """
    w = width or 20
    ws.column_dimensions[get_column_letter(col_idx)].width = min(w, 40)


def auto_column_widths(ws, max_width: int = 20):
    """Auto-set all column widths, capped at max_width."""
    for col_idx in range(1, ws.max_column + 1):
        set_column_width(ws, col_idx, max_width)
