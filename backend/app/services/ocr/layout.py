"""
Document Layout Analysis & Mathematical Content Detection.

Provides geometric layout-based reading order sorting (Recursive XY-Cut)
to ensure multi-column notes, exams, and worksheets are not merged incorrectly,
and mathematical content detection to flag formula limitations.
"""

import re
from typing import Any, Dict, List, Optional, Tuple


def _get_bbox(segment: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """Extracts [x1, y1, x2, y2] from a segment dictionary."""
    box = segment.get("bounding_box")
    if box and len(box) == 4:
        try:
            return float(box[0]), float(box[1]), float(box[2]), float(box[3])
        except (ValueError, TypeError):
            pass
    return 0.0, 0.0, 0.0, 0.0


def order_page_segments(
    segments: List[Dict[str, Any]],
    min_gap_x: float = 10.0,
    min_gap_y: float = 7.0,
) -> List[Dict[str, Any]]:
    """
    Orders OCR segments on a page into natural human reading order
    using Recursive XY-Cut layout analysis.

    Unlike naive (y, x) sorting which interleaves adjacent columns line by line,
    this algorithm:
    1. Identifies horizontal projection cuts (section breaks, spanning headers/footers).
    2. Identifies vertical projection cuts (column gutters).
    3. Traverses columns left-to-right, reading each column top-to-bottom.
    4. Groups tokens on the same visual line based on vertical overlap.
    """
    if not segments or len(segments) <= 1:
        return list(segments)

    boxes = [_get_bbox(s) for s in segments]
    min_x = min(b[0] for b in boxes)
    max_x = max(b[2] for b in boxes)
    min_y = min(b[1] for b in boxes)
    max_y = max(b[3] for b in boxes)
    width = max_x - min_x
    height = max_y - min_y

    if width <= 0 or height <= 0:
        return list(segments)

    # 1. First, isolate spanning headers/dividers (elements spanning >= 50% of current block width)
    spanning_cuts: List[float] = []
    for s in segments:
        b = _get_bbox(s)
        if width > 0 and (b[2] - b[0]) >= 0.50 * width:
            if b[1] - min_y >= 6.0:
                spanning_cuts.append(b[1] - 1.0)
            if max_y - b[3] >= 6.0:
                spanning_cuts.append(b[3] + 1.0)

    if spanning_cuts:
        dedup_y: List[float] = []
        for c in sorted(list(set(spanning_cuts))):
            if min_y + 4.0 < c < max_y - 4.0:
                if not dedup_y or (c - dedup_y[-1]) >= 8.0:
                    dedup_y.append(c)

        if dedup_y:
            bands: List[List[Dict[str, Any]]] = []
            bounds = [min_y - 1.0] + dedup_y + [max_y + 1.0]
            for i in range(len(bounds) - 1):
                y_lo, y_hi = bounds[i], bounds[i + 1]
                sub = [
                    s
                    for s in segments
                    if y_lo <= (_get_bbox(s)[1] + _get_bbox(s)[3]) / 2.0 < y_hi
                ]
                if sub:
                    bands.append(sub)
            if len(bands) > 1:
                res: List[Dict[str, Any]] = []
                for b in bands:
                    res.extend(order_page_segments(b, min_gap_x, min_gap_y))
                return res

    # 2. Check for horizontal projection cuts (section / paragraph gaps along Y)
    y_events = []
    for s in segments:
        bx1, by1, bx2, by2 = _get_bbox(s)
        y_events.append((by1, 1))
        y_events.append((by2, -1))
    y_events.sort(key=lambda e: (e[0], -e[1]))

    active_y = 0
    cuts_y: List[float] = []
    max_gap_y = 0.0
    prev_y = None
    for y, delta in y_events:
        if active_y == 0 and prev_y is not None:
            gap = y - prev_y
            max_gap_y = max(max_gap_y, gap)
            if gap >= min_gap_y:
                cuts_y.append((prev_y + y) / 2.0)
        active_y += delta
        prev_y = y

    # Check for vertical projection cuts (column gutters along X)
    x_events = []
    for s in segments:
        bx1, by1, bx2, by2 = _get_bbox(s)
        x_events.append((bx1, 1))
        x_events.append((bx2, -1))
    x_events.sort(key=lambda e: (e[0], -e[1]))

    active_x = 0
    cuts_x: List[float] = []
    prev_x = None
    for x, delta in x_events:
        if active_x == 0 and prev_x is not None:
            gap = x - prev_x
            if gap >= min_gap_x:
                cuts_x.append((prev_x + x) / 2.0)
        active_x += delta
        prev_x = x

    # Decision logic:
    # If the block has vertical column gutters across its full height,
    # column-first processing isolates columns (e.g. multi-column notes/exams).
    if cuts_x:
        cols: List[List[Dict[str, Any]]] = []
        bounds_x = [min_x - 1.0] + cuts_x + [max_x + 1.0]
        for i in range(len(bounds_x) - 1):
            x_lo, x_hi = bounds_x[i], bounds_x[i + 1]
            sub = [
                s
                for s in segments
                if x_lo <= (_get_bbox(s)[0] + _get_bbox(s)[2]) / 2.0 < x_hi
            ]
            if sub:
                cols.append(sub)
        if len(cols) > 1:
            res = []
            for c in cols:
                res.extend(order_page_segments(c, min_gap_x, min_gap_y))
            return res

    if cuts_y:
        bands_y: List[List[Dict[str, Any]]] = []
        bounds_y = [min_y - 1.0] + cuts_y + [max_y + 1.0]
        for i in range(len(bounds_y) - 1):
            y_lo, y_hi = bounds_y[i], bounds_y[i + 1]
            sub = [
                s
                for s in segments
                if y_lo <= (_get_bbox(s)[1] + _get_bbox(s)[3]) / 2.0 < y_hi
            ]
            if sub:
                bands_y.append(sub)
        if len(bands_y) > 1:
            res_y = []
            for by in bands_y:
                res_y.extend(order_page_segments(by, min_gap_x, min_gap_y))
            return res_y


    # 3. Leaf block: Group lines by vertical overlap and sort tokens left-to-right
    sorted_by_y = sorted(segments, key=lambda s: _get_bbox(s)[1])
    lines: List[List[Dict[str, Any]]] = []
    for s in sorted_by_y:
        b = _get_bbox(s)
        h = max(1.0, b[3] - b[1])
        placed = False
        for line in lines:
            line_b = _get_bbox(line[0])
            line_h = max(1.0, line_b[3] - line_b[1])
            overlap_min = max(b[1], line_b[1])
            overlap_max = min(b[3], line_b[3])
            overlap = max(0.0, overlap_max - overlap_min)
            if overlap >= 0.40 * min(h, line_h):
                line.append(s)
                placed = True
                break
        if not placed:
            lines.append([s])

    ordered_leaf: List[Dict[str, Any]] = []
    for line in sorted(lines, key=lambda ln: min(_get_bbox(item)[1] for item in ln)):
        ordered_leaf.extend(sorted(line, key=lambda item: _get_bbox(item)[0]))
    return ordered_leaf


# Patterns indicative of mathematical notation, calculus, formulas, matrices, exponents
MATH_INDICATOR_PATTERNS = [
    re.compile(r"[∫∑∏√±≠≤≥≈∝∞∂∇]"),  # Math unicode symbols
    re.compile(r"\b(dx|dy|dt|dy/dx|d2y/dx2|d/dx)\b", re.IGNORECASE),  # Derivatives/integrals
    re.compile(r"(\^|\b)\w*(\^|_)\{?[0-9a-zA-Z+-]+\}?"),  # Superscript/subscript markup
    re.compile(r"[a-zA-Z0-9]+[²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ]"),  # Unicode superscripts
    re.compile(r"[a-zA-Z0-9]+[₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎]"),  # Unicode subscripts
    re.compile(r"\b(sin|cos|tan|cot|sec|csc|log|ln|lim)\b", re.IGNORECASE),  # Math functions
    re.compile(r"(\[|\()(\s*\d+\s+){2,}\d*(\]|\))"),  # Matrix row notation [1 2 3]
    re.compile(r"\|[A-Z]\|"),  # Determinant notation |A|
    re.compile(r"[a-zA-Z]\s*[-·×*]\s*[a-zA-Z]"),  # Dot / cross product
]


def detect_math_content(content: Any) -> Tuple[bool, List[str]]:
    """
    Scans extracted OCR text or segments for signs of mathematical content and returns
    (has_math_content, quality_warnings).
    """
    if not content:
        return False, []

    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                text_parts.append(str(item.get("text", "")))
            else:
                text_parts.append(str(item))
        text = "\n".join(text_parts)
    else:
        text = str(content)

    if not text.strip():
        return False, []

    matched_patterns = 0
    for pattern in MATH_INDICATOR_PATTERNS:
        if pattern.search(text):
            matched_patterns += 1

    if matched_patterns >= 1:
        warnings = [
            "Mathematical notation detected. Standard OCR captures layout and text tokens, "
            "but cannot reliably reconstruct 2D formula syntax, fractions, exponents, or matrices. "
            "Please verify mathematical expressions against the original document."
        ]
        return True, warnings

    return False, []
