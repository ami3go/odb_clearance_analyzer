"""Geometry helpers for converting common ODB++ feature symbols to Shapely geometry."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from .models import SymbolDef

_MICRONS_TO_MM = 0.001


def _um_to_mm(value: str | float) -> float:
    return float(value) * _MICRONS_TO_MM


def parse_symbol(index: int, raw_name: str) -> SymbolDef:
    """Parse a common ODB++ symbol definition.

    The implementation covers the symbols commonly exported by KiCad for copper
    tracks, pads and vias: round, rectangle and oval. Unknown symbols are kept as
    a small round shape so the analyzer can continue and report a warning rather
    than fail the whole job.
    """

    name = raw_name.strip()

    m = re.fullmatch(r"r([0-9.]+)", name)
    if m:
        d = _um_to_mm(m.group(1))
        return SymbolDef(index=index, raw_name=name, kind="round", width_mm=d, height_mm=d)

    m = re.fullmatch(r"rect([0-9.]+)x([0-9.]+)(?:xr([0-9.]+))?", name)
    if m:
        w = _um_to_mm(m.group(1))
        h = _um_to_mm(m.group(2))
        r = _um_to_mm(m.group(3)) if m.group(3) else None
        return SymbolDef(index=index, raw_name=name, kind="rect", width_mm=w, height_mm=h, radius_mm=r)

    m = re.fullmatch(r"oval([0-9.]+)x([0-9.]+)", name)
    if m:
        w = _um_to_mm(m.group(1))
        h = _um_to_mm(m.group(2))
        return SymbolDef(index=index, raw_name=name, kind="oval", width_mm=w, height_mm=h)

    # Conservative fallback: tiny round aperture. The caller can add a warning.
    return SymbolDef(index=index, raw_name=name, kind="unknown", width_mm=0.001, height_mm=0.001)


def odb_pad_orientation_to_degrees(token: str | float | int | None) -> float:
    """Convert an ODB++ pad orientation token to rotation degrees.

    ODB++ feature records commonly store pad orientation as a compact integer
    orient_def value rather than a literal angle.  The previous implementation
    interpreted ``3`` as 3 degrees; for rectangular pads this can create false
    overlaps on 1.27 mm pitch footprints because the intended 90/270 degree
    rotation is not applied.

    The standard orient_def values 0..7 combine rotation and mirroring.  For
    clearance geometry of symmetric standard pad symbols, mirroring does not
    change the physical outline, so this helper applies the rotation component
    and intentionally ignores mirror state. Literal angle values such as 270.0
    are passed through unchanged.
    """

    if token is None:
        return 0.0
    text = str(token).strip()
    if not text:
        return 0.0
    try:
        value = float(text)
    except ValueError:
        return 0.0
    if not math.isfinite(value):
        return 0.0

    # Compact ODB++ orient_def code.  Codes 4..7 are mirrored variants; for
    # round/rect/oval copper outlines the mirror does not change the clearance
    # body, while the rotation still matters for non-square pads.
    if re.fullmatch(r"[+-]?\d+", text):
        code = int(value)
        orient_map = {
            0: 0.0,
            1: 90.0,
            2: 180.0,
            3: 270.0,
            4: 0.0,
            5: 90.0,
            6: 180.0,
            7: 270.0,
        }
        if code in orient_map:
            return orient_map[code]

    # Literal degrees, used by some exporters as values like 90.0 or 270.0.
    return value


def pad_geometry(symbol: SymbolDef, x: float, y: float, rotation_deg: float = 0.0, resolution: int = 16):
    """Create a centered pad/flash geometry from a parsed ODB++ symbol."""

    if symbol.kind in {"round", "unknown"}:
        geom = Point(0, 0).buffer(symbol.width_mm / 2.0, resolution=resolution)
    elif symbol.kind == "rect":
        w = symbol.width_mm
        h = symbol.height_mm or symbol.width_mm
        r = symbol.radius_mm or 0.0
        if r > 0.0:
            # ODB++/KiCad symbols such as rect1600.0x1600.0xr400.0 are rounded
            # rectangles.  Using the bounding rectangle creates artificial copper
            # at the square corners and can produce false sub-0.1 mm clearances.
            r = min(r, w / 2.0, h / 2.0)
            core = box(
                -w / 2.0 + r,
                -h / 2.0 + r,
                w / 2.0 - r,
                h / 2.0 - r,
            )
            geom = core.buffer(r, resolution=resolution)
        else:
            geom = box(-w / 2.0, -h / 2.0, w / 2.0, h / 2.0)
    elif symbol.kind == "oval":
        w = symbol.width_mm
        h = symbol.height_mm or symbol.width_mm
        if w >= h:
            straight = max(0.0, w - h)
            geom = LineString([(-straight / 2.0, 0), (straight / 2.0, 0)]).buffer(
                h / 2.0, resolution=resolution
            )
        else:
            straight = max(0.0, h - w)
            geom = LineString([(0, -straight / 2.0), (0, straight / 2.0)]).buffer(
                w / 2.0, resolution=resolution
            )
    else:
        geom = Point(0, 0).buffer(0.0005, resolution=resolution)

    if rotation_deg:
        geom = affinity.rotate(geom, rotation_deg, origin=(0, 0), use_radians=False)
    return affinity.translate(geom, xoff=x, yoff=y)


def track_geometry(symbol: SymbolDef, x1: float, y1: float, x2: float, y2: float, resolution: int = 16):
    """Create copper geometry for a line/track feature."""

    width = symbol.width_mm
    if symbol.kind in {"rect", "oval"} and symbol.height_mm:
        width = min(symbol.width_mm, symbol.height_mm)
    cap_style = 1  # round cap, suitable for round apertures and conservative for tracks.
    return LineString([(x1, y1), (x2, y2)]).buffer(width / 2.0, cap_style=cap_style, resolution=resolution)


def arc_points(
    start: tuple[float, float],
    end: tuple[float, float],
    center: tuple[float, float],
    clockwise: bool | None,
    resolution: int = 16,
) -> list[tuple[float, float]]:
    """Approximate an ODB++ ``OC`` arc command with intermediate points.

    ODB++ surface contours use ``OC x_end y_end x_center y_center cw`` after an
    ``OB``/``OS`` start point.  Earlier versions ignored ``OC`` records, which
    turned curved copper-pour boundaries and rounded anti-pad openings into
    broken straight-line polygons.  That can create false near-zero clearances
    from large surface pours to pads.

    The returned list excludes ``start`` and includes ``end``.  ``clockwise`` is
    interpreted as the ODB++ Y/N direction flag.  If direction is missing or the
    arc is numerically invalid, a conservative straight segment to ``end`` is
    returned so parsing can continue.
    """

    sx, sy = start
    ex, ey = end
    cx, cy = center
    rs = math.hypot(sx - cx, sy - cy)
    re = math.hypot(ex - cx, ey - cy)
    if rs <= 1e-12 or re <= 1e-12 or not all(math.isfinite(v) for v in (sx, sy, ex, ey, cx, cy)):
        return [end]

    radius = (rs + re) / 2.0
    start_ang = math.atan2(sy - cy, sx - cx)
    end_ang = math.atan2(ey - cy, ex - cx)

    if clockwise is True:
        # Walk in the negative angular direction.
        while end_ang >= start_ang:
            end_ang -= 2.0 * math.pi
    elif clockwise is False:
        # Walk in the positive angular direction.
        while end_ang <= start_ang:
            end_ang += 2.0 * math.pi
    else:
        # Unknown direction: use the shorter arc.
        delta = (end_ang - start_ang + math.pi) % (2.0 * math.pi) - math.pi
        end_ang = start_ang + delta

    sweep = end_ang - start_ang
    # Approximate at roughly 90/resolution degrees per segment.  With the
    # default resolution=16 this is about 5.6 degrees, good enough for clearance
    # debugging without exploding polygon size.
    max_step = math.radians(max(1.0, 90.0 / max(1, resolution)))
    segments = max(2, int(math.ceil(abs(sweep) / max_step)))
    points: list[tuple[float, float]] = []
    for i in range(1, segments + 1):
        t = i / segments
        ang = start_ang + sweep * t
        points.append((cx + radius * math.cos(ang), cy + radius * math.sin(ang)))
    # Preserve the exact ODB++ endpoint instead of the rounded approximation.
    points[-1] = end
    return points


def surface_geometry(boundaries: list[tuple[str, list[tuple[float, float]]]]):
    """Create a Shapely geometry from ODB++ surface boundaries.

    Boundaries marked with `I` are treated as copper islands. Boundaries marked
    with `H` are treated as holes and subtracted from all islands. If a file uses
    a non-standard marker, the first boundary is treated as an island and later
    boundaries as holes.
    """

    islands = []
    holes = []

    for marker, coords in boundaries:
        if len(coords) < 3:
            continue
        if coords[0] != coords[-1]:
            coords = [*coords, coords[0]]
        try:
            poly = Polygon(coords)
            if not poly.is_valid:
                poly = poly.buffer(0)
        except Exception:
            continue
        if poly.is_empty:
            continue
        marker_upper = marker.upper()
        if marker_upper == "H":
            holes.append(poly)
        elif marker_upper == "I" or not islands:
            islands.append(poly)
        else:
            holes.append(poly)

    if not islands:
        return None
    geom = unary_union(islands)
    if holes:
        geom = geom.difference(unary_union(holes))
    if geom.is_empty:
        return None
    return geom


def safe_union(geometries: Iterable[object], precision_grid_mm: float | None = None):
    """Union geometries while repairing occasional invalid polygons."""

    valid = []
    for geom in geometries:
        if geom is None or getattr(geom, "is_empty", True):
            continue
        try:
            if not geom.is_valid:
                geom = geom.buffer(0)
            if precision_grid_mm:
                try:
                    from shapely import set_precision

                    geom = set_precision(geom, precision_grid_mm)
                except Exception:
                    pass
            if not geom.is_empty:
                valid.append(geom)
        except Exception:
            continue
    if not valid:
        return None
    try:
        return unary_union(valid)
    except Exception:
        repaired = [g.buffer(0) for g in valid]
        return unary_union(repaired)


def parse_float(token: str) -> float:
    """Parse an ODB++ numeric token."""

    # ODB++ generated by some tools uses values like -0.0 and high precision strings.
    return float(token)


def last_float_before_attributes(tokens: list[str], default: float = 0.0) -> float:
    """Return the last float before ODB++ attribute text beginning with ';'."""

    for token in reversed(tokens):
        if token.startswith(";"):
            continue
        try:
            value = float(token)
        except ValueError:
            continue
        if math.isfinite(value):
            return value
    return default
