"""SVG chart generation for dashboard visualization.

Builds donut charts (status breakdown) and bar charts (top exception codes).
No external chart libraries — pure SVG.
"""

from __future__ import annotations

import math

# Color scheme
_COLORS = {
    "OK": "#10b981",  # green
    "WARN": "#f59e0b",  # orange
    "ERROR": "#ef4444",  # red
}

_COLOR_CODES = {
    "PAN_DUPLICATE": "#ec4899",
    "AADHAAR_DUPLICATE": "#a855f7",
    "MOBILE_DUPLICATE": "#06b6d4",
    "VOTER_ID_DUPLICATE": "#8b5cf6",
    "ADDRESS_DUPLICATE": "#f97316",
    "BANK_ACCOUNT_DUPLICATE": "#6366f1",
    "NAME_DOB_DUPLICATE": "#14b8a6",
    "UCID_KYC_INCONSISTENT": "#d97706",
    "EMAIL_COMPANY_GENERIC_DOMAIN": "#84cc16",
    "DOB_AGE_OUT_OF_RANGE": "#0891b2",
    "BANK_ACCOUNT_INVALID_LENGTH": "#db2777",
}


def _get_color_for_code(code: str) -> str:
    """Get a stable color for an exception code."""
    return _COLOR_CODES.get(code, "#6b7280")  # gray default


def build_donut_svg(
    status_counts: dict[str, int],
    width: int = 300,
    height: int = 300,
) -> str:
    """Build a donut chart showing status breakdown (OK, WARN, ERROR).

    Args:
        status_counts: {"OK": count, "WARN": count, "ERROR": count}
        width, height: SVG dimensions

    Returns:
        SVG string (inline-safe)
    """
    total = sum(status_counts.values())
    if total == 0:
        return f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-width:{width}px;display:block;" xmlns="http://www.w3.org/2000/svg"></svg>'

    center_x, center_y = width / 2, height / 2
    outer_radius = min(width, height) / 2 - 20
    inner_radius = outer_radius * 0.6

    svg_lines = [
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-width:{width}px;display:block;" xmlns="http://www.w3.org/2000/svg">',
        "<style>",
        ".donut-label { font-size: 12px; fill: #374151; text-anchor: middle; }",
        ".donut-center-text { font-size: 20px; font-weight: bold; fill: #1f2937; text-anchor: middle; }",
        ".donut-center-subtext { font-size: 12px; fill: #6b7280; text-anchor: middle; }",
        "</style>",
    ]

    # Status order and calculation
    statuses = ["OK", "WARN", "ERROR"]
    start_angle = -90  # Start from top

    for status in statuses:
        count = status_counts.get(status, 0)
        if count == 0:
            continue

        percentage = count / total
        angle = percentage * 360

        # Convert to radians for calculation
        start_rad = math.radians(start_angle)
        end_rad = math.radians(start_angle + angle)

        # Outer points
        x1_outer = center_x + outer_radius * math.cos(start_rad)
        y1_outer = center_y + outer_radius * math.sin(start_rad)
        x2_outer = center_x + outer_radius * math.cos(end_rad)
        y2_outer = center_y + outer_radius * math.sin(end_rad)

        # Inner points
        x1_inner = center_x + inner_radius * math.cos(start_rad)
        y1_inner = center_y + inner_radius * math.sin(start_rad)
        x2_inner = center_x + inner_radius * math.cos(end_rad)
        y2_inner = center_y + inner_radius * math.sin(end_rad)

        # SVG arc flag (1 if angle > 180)
        large_arc = 1 if angle > 180 else 0

        # Path: outer arc -> inner arc (reverse)
        path = (
            f"M {x1_outer:.1f} {y1_outer:.1f} "
            f"A {outer_radius:.1f} {outer_radius:.1f} 0 {large_arc} 1 {x2_outer:.1f} {y2_outer:.1f} "
            f"L {x2_inner:.1f} {y2_inner:.1f} "
            f"A {inner_radius:.1f} {inner_radius:.1f} 0 {large_arc} 0 {x1_inner:.1f} {y1_inner:.1f} "
            f"Z"
        )

        svg_lines.append(
            f'<path d="{path}" fill="{_COLORS[status]}" stroke="white" stroke-width="2"/>'
        )

        # Label at midpoint
        mid_angle = math.radians(start_angle + angle / 2)
        label_radius = (outer_radius + inner_radius) / 2
        label_x = center_x + label_radius * math.cos(mid_angle)
        label_y = center_y + label_radius * math.sin(mid_angle)
        label_text = f"{status}: {count}"
        svg_lines.append(
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" class="donut-label">{label_text}</text>'
        )

        start_angle += angle

    # Center text
    svg_lines.append(
        f'<text x="{center_x:.1f}" y="{center_y - 8:.1f}" class="donut-center-text">{total}</text>'
    )
    svg_lines.append(
        f'<text x="{center_x:.1f}" y="{center_y + 12:.1f}" class="donut-center-subtext">total records</text>'
    )

    svg_lines.append("</svg>")
    return "\n".join(svg_lines)


def build_bar_chart(
    exception_counts: dict[str, int],
    width: int = 700,
    height: int = 400,
    top_n: int = 10,
) -> str:
    """Build a horizontal bar chart showing top exception codes.

    Args:
        exception_counts: {code: count} (will sort and take top_n)
        width, height: SVG dimensions
        top_n: Max bars to show

    Returns:
        SVG string (inline-safe)
    """
    if not exception_counts:
        return f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-width:{width}px;display:block;" xmlns="http://www.w3.org/2000/svg"><text x="10" y="20" font-size="14" fill="#999">No exception data</text></svg>'

    # Sort by count descending, take top N
    sorted_items = sorted(exception_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
    max_count = sorted_items[0][1] if sorted_items else 1

    margin_left = 200
    margin_right = 20
    margin_top = 30
    margin_bottom = 30

    chart_width = width - margin_left - margin_right
    bar_height = (height - margin_top - margin_bottom) / len(sorted_items)

    svg_lines = [
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-width:{width}px;display:block;" xmlns="http://www.w3.org/2000/svg">',
        "<style>",
        ".bar-label { font-size: 11px; fill: #374151; text-anchor: end; }",
        ".bar-value { font-size: 11px; fill: #1f2937; font-weight: bold; }",
        ".chart-title { font-size: 14px; font-weight: bold; fill: #1f2937; }",
        "</style>",
        '<text x="10" y="20" class="chart-title">Top Exception Codes</text>',
    ]

    for i, (code, count) in enumerate(sorted_items):
        y = margin_top + i * bar_height
        bar_width = (count / max_count) * chart_width if max_count > 0 else 0

        # Bar background
        svg_lines.append(
            f'<rect x="{margin_left}" y="{y + 2}" width="{bar_width}" height="{bar_height - 4}" '
            f'fill="{_get_color_for_code(code)}" rx="2" opacity="0.8"/>'
        )

        # Label (code name, right-aligned at left margin)
        svg_lines.append(
            f'<text x="{margin_left - 10}" y="{y + bar_height / 2 + 4}" class="bar-label">{code}</text>'
        )

        # Count value (inside bar or to the right)
        value_x = margin_left + bar_width + 5 if bar_width > 0 else margin_left + 5
        svg_lines.append(
            f'<text x="{value_x:.1f}" y="{y + bar_height / 2 + 4}" class="bar-value">{count}</text>'
        )

    svg_lines.append("</svg>")
    return "\n".join(svg_lines)


def build_lorenz_curve(
    cumulative_data: list[float],
    width: int = 500,
    height: int = 500,
) -> str:
    """Build a Lorenz concentration curve (cumulative distribution).

    Args:
        cumulative_data: Cumulative percentages [0, 10, 25, ..., 100]
        width, height: SVG dimensions

    Returns:
        SVG string (inline-safe)
    """
    if not cumulative_data or len(cumulative_data) < 2:
        return f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg"></svg>'

    margin = 50
    plot_width = width - 2 * margin
    plot_height = height - 2 * margin

    svg_lines = [
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-width:{width}px;display:block;" xmlns="http://www.w3.org/2000/svg">',
        "<style>",
        ".curve { stroke: #0891b2; stroke-width: 2; fill: none; }",
        ".diagonal { stroke: #d1d5db; stroke-width: 1; stroke-dasharray: 4; }",
        ".axis-label { font-size: 11px; fill: #6b7280; text-anchor: middle; }",
        "</style>",
    ]

    # Diagonal line (reference)
    svg_lines.append(
        f'<line x1="{margin}" y1="{margin + plot_height}" x2="{margin + plot_width}" y2="{margin}" '
        f'class="diagonal"/>'
    )

    # Lorenz curve
    points = []
    for i, cumul_pct in enumerate(cumulative_data):
        x_pct = (i / (len(cumulative_data) - 1)) * 100 if len(cumulative_data) > 1 else 0
        x = margin + (x_pct / 100) * plot_width
        y = margin + plot_height - (cumul_pct / 100) * plot_height
        points.append(f"{x:.1f},{y:.1f}")

    path = f"M {' L '.join(points)}"
    svg_lines.append(f'<path d="{path}" class="curve"/>')

    # Axes
    svg_lines.append(
        f'<line x1="{margin}" y1="{margin + plot_height}" x2="{margin + plot_width}" y2="{margin + plot_height}" '
        f'stroke="#9ca3af" stroke-width="1"/>'
    )
    svg_lines.append(
        f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{margin + plot_height}" '
        f'stroke="#9ca3af" stroke-width="1"/>'
    )

    # Axis labels
    svg_lines.append(
        f'<text x="{margin + plot_width / 2}" y="{height - 10}" class="axis-label">% of Customers</text>'
    )
    svg_lines.append(
        f'<text x="15" y="{margin + plot_height / 2}" class="axis-label" transform="rotate(-90 15 {margin + plot_height / 2})">% of Exceptions</text>'
    )

    svg_lines.append("</svg>")
    return "\n".join(svg_lines)


def build_kyc_completeness_bar(
    field_coverage: dict[str, float],
    width: int = 600,
    height: int = 400,
) -> str:
    """Build a bar chart showing KYC field completeness percentages.

    Args:
        field_coverage: {field_name: coverage_percent (0-100)}
        width, height: SVG dimensions

    Returns:
        SVG string (inline-safe)
    """
    if not field_coverage:
        return f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg"><text x="10" y="20" font-size="14" fill="#999">No KYC data</text></svg>'

    sorted_fields = sorted(field_coverage.items(), key=lambda x: x[1], reverse=True)

    margin_left = 140
    margin_right = 40
    margin_top = 30
    margin_bottom = 30

    chart_width = width - margin_left - margin_right
    bar_height = (height - margin_top - margin_bottom) / len(sorted_fields)

    svg_lines = [
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-width:{width}px;display:block;" xmlns="http://www.w3.org/2000/svg">',
        "<style>",
        ".kyc-label { font-size: 11px; fill: #374151; text-anchor: end; }",
        ".kyc-value { font-size: 11px; fill: #1f2937; font-weight: bold; }",
        ".kyc-title { font-size: 14px; font-weight: bold; fill: #1f2937; }",
        "</style>",
        '<text x="10" y="20" class="kyc-title">KYC Field Completeness</text>',
    ]

    for i, (field, coverage) in enumerate(sorted_fields):
        y = margin_top + i * bar_height
        bar_width = (coverage / 100) * chart_width if coverage > 0 else 0

        # Color: green if > 90%, orange if > 70%, red otherwise
        if coverage >= 90:
            color = "#10b981"  # green
        elif coverage >= 70:
            color = "#f59e0b"  # orange
        else:
            color = "#ef4444"  # red

        svg_lines.append(
            f'<rect x="{margin_left}" y="{y + 2}" width="{bar_width}" height="{bar_height - 4}" '
            f'fill="{color}" rx="2" opacity="0.8"/>'
        )

        svg_lines.append(
            f'<text x="{margin_left - 10}" y="{y + bar_height / 2 + 4}" class="kyc-label">{field}</text>'
        )

        value_x = margin_left + bar_width + 5 if bar_width > 0 else margin_left + 5
        svg_lines.append(
            f'<text x="{value_x:.1f}" y="{y + bar_height / 2 + 4}" class="kyc-value">{coverage:.1f}%</text>'
        )

    svg_lines.append("</svg>")
    return "\n".join(svg_lines)


def build_duplicates_pie(
    duplicate_counts: dict[str, int],
    width: int = 400,
    height: int = 300,
) -> str:
    """Build a pie chart showing duplicate type breakdown.

    Args:
        duplicate_counts: {dup_type: count} (PAN, Aadhaar, Mobile, etc.)
        width, height: SVG dimensions

    Returns:
        SVG string (inline-safe)
    """
    total = sum(duplicate_counts.values())
    if total == 0:
        return f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg"><text x="10" y="20" font-size="14" fill="#999">No duplicates</text></svg>'

    center_x, center_y = width / 2, height / 2
    radius = min(width, height) / 2 - 30

    svg_lines = [
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;max-width:{width}px;display:block;" xmlns="http://www.w3.org/2000/svg">',
        "<style>",
        ".pie-label { font-size: 11px; fill: #fff; text-anchor: middle; font-weight: bold; }",
        "</style>",
    ]

    start_angle = -90
    for dup_type, count in duplicate_counts.items():
        percentage = count / total
        angle = percentage * 360

        start_rad = math.radians(start_angle)
        end_rad = math.radians(start_angle + angle)

        x1 = center_x + radius * math.cos(start_rad)
        y1 = center_y + radius * math.sin(start_rad)
        x2 = center_x + radius * math.cos(end_rad)
        y2 = center_y + radius * math.sin(end_rad)

        large_arc = 1 if angle > 180 else 0

        path = (
            f"M {center_x:.1f} {center_y:.1f} "
            f"L {x1:.1f} {y1:.1f} "
            f"A {radius:.1f} {radius:.1f} 0 {large_arc} 1 {x2:.1f} {y2:.1f} "
            f"Z"
        )

        color = _get_color_for_code(dup_type)
        svg_lines.append(f'<path d="{path}" fill="{color}" stroke="white" stroke-width="1"/>')

        # Label
        mid_angle = math.radians(start_angle + angle / 2)
        label_radius = radius * 0.65
        label_x = center_x + label_radius * math.cos(mid_angle)
        label_y = center_y + label_radius * math.sin(mid_angle)
        svg_lines.append(
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" class="pie-label">{count}</text>'
        )

        start_angle += angle

    svg_lines.append("</svg>")
    return "\n".join(svg_lines)
