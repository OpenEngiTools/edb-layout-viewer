"""Pure geometry helpers for scene construction."""

from __future__ import annotations

import math
from itertools import pairwise
from typing import TYPE_CHECKING

from layout_viewer_core.scene import SceneJoin, SceneTrace

if TYPE_CHECKING:
    from ansys.edb.core.geometry.point_data import PointData
    from ansys.edb.core.primitive.primitive import Primitive
    from layout_viewer_core.scene import Point, Ring


def arc_segment_count(
    radius: float,
    sweep: float,
    chord_error: float,
    max_angle: float = math.pi / 18,
    max_segments: int = 65536,
) -> int:
    """Return the chord count required by radius, sweep and maximum sagitta error."""
    if not all(math.isfinite(v) for v in (radius, sweep, chord_error, max_angle)):
        raise ValueError("Arc tessellation inputs must be finite.")
    if radius <= 0 or chord_error <= 0 or not 0 < max_angle <= math.pi:
        raise ValueError("Arc radius, chord error and maximum angle must be positive.")
    ratio = min(chord_error / radius, 2.0)
    step = 4 * math.asin(math.sqrt(ratio / 2))
    if step == 0:
        raise ValueError("Arc chord error is too small for the radius.")
    if abs(sweep) > max_segments * min(step, max_angle):
        raise ValueError("Arc tessellation exceeds the segment limit; increase chord_error.")
    return max(1, math.ceil(abs(sweep) / min(step, max_angle)))


def _contour(primitive: Primitive, arc_segments: int, chord_error: float | None = None) -> Ring:
    from edb_layout_viewer.conversion.geometry import contour_from_points

    return contour_from_points(primitive.polygon_data.points, arc_segments, chord_error)


def _xy(point: PointData) -> Point:
    return point.x.double * 1000, point.y.double * 1000


def _tangent(trace: SceneTrace, end: bool = False) -> Point:
    if trace.center is None:
        x, y = (b - a for a, b in zip(trace.start, trace.end))
    else:
        point = trace.end if end else trace.start
        sign = 1 if trace.sweep > 0 else -1
        x, y = -(point[1] - trace.center[1]) * sign, (point[0] - trace.center[0]) * sign
    length = math.hypot(x, y)
    return (x / length, y / length) if length else (1, 0)


def _trace_geometry(primitive: Primitive, layer: str, net: str | None) -> tuple[list[SceneTrace], list[SceneJoin]]:
    """Preserve source lines/arcs and add only constant-size join geometry."""
    arcs = primitive.center_line.arc_data
    if not arcs:
        raise ValueError("Empty path center line.")
    caps = tuple(cap.name.lower() for cap in primitive.get_end_cap_style())
    if any(cap not in {"flat", "round", "extended"} for cap in caps):
        raise ValueError(f"Unsupported path caps: {caps}.")
    round_join = primitive.corner_style.name.lower() == "round"
    width = primitive.width.double * 1000
    object_id = primitive.id
    traces, joins = [], []
    for index, arc in enumerate(arcs):
        start, end = _xy(arc.start), _xy(arc.end)
        if start == end and arc.is_segment():
            continue
        center, sweep = None, 0.0
        if not arc.is_segment():
            center = _xy(arc.center)
            a = math.atan2(start[1] - center[1], start[0] - center[0])
            b = math.atan2(end[1] - center[1], end[0] - center[0])
            sweep = (b - a) % math.tau if arc.is_ccw() else -((a - b) % math.tau)
            if sweep == 0:
                sweep = math.tau if arc.is_ccw() else -math.tau
        traces.append(
            SceneTrace(
                object_id,
                layer,
                net,
                start,
                end,
                width,
                center,
                sweep,
                (
                    caps[0] if index == 0 else "round",
                    caps[1] if index == len(arcs) - 1 else "round",
                ),
            )
        )
    if not traces:
        raise ValueError("Path has no nonzero segments.")
    if not round_join:
        for before, after in pairwise(traces):
            tx, ty = _tangent(before, end=True)
            ux, uy = _tangent(after)
            turn = tx * uy - ty * ux
            if abs(turn) < 1e-12:
                continue
            x, y = before.end
            r = width * (-0.5 if turn > 0 else 0.5)
            p = (x - ty * r, y + tx * r)
            q = (x - uy * r, y + ux * r)
            divisor = 1 + tx * ux + ty * uy
            if divisor < 1e-8:
                raise ValueError("Nearly reversing sharp path corner requires source boundary coverage.")
            tip = (x - (ty + uy) * r / divisor, y + (tx + ux) * r / divisor)
            joins.append(SceneJoin(object_id, layer, net, (before.end, p, tip, q)))
    return traces, joins


def _rotate(point: Point, angle: float) -> Point:
    c, s = math.cos(angle), math.sin(angle)
    return c * point[0] - s * point[1], s * point[0] + c * point[1]


def _nsided_polygon_points(size: float, num_sides: float) -> Ring:
    """Return a regular polygon's vertices; ``size`` is the circumscribed diameter."""
    sides = max(3, round(num_sides))
    radius = size / 2
    return tuple(
        (radius * math.cos(i * math.tau / sides), radius * math.sin(i * math.tau / sides)) for i in range(sides)
    )


def _thermal_relief_outline(round_outer: bool, inner: float, isolation_gap: float, arc_segments: int) -> Ring:
    """Approximate a thermal-relief pad's outer boundary.

    ``round45``/``round90``/``square45``/``square90`` pads connect an inner pad to
    surrounding copper through spokes whose exact placement depends on the anti-pad
    geometry, which is not available from the padstack definition alone. The spokes
    themselves are therefore not modeled; only the plain circular or square outline
    reachable by the pad (``inner`` plus ``isolation_gap`` on each side) is rendered.
    """
    radius = inner / 2 + isolation_gap
    if round_outer:
        return tuple(
            (radius * math.cos(i * math.tau / arc_segments), radius * math.sin(i * math.tau / arc_segments))
            for i in range(arc_segments)
        )
    return ((radius, radius), (-radius, radius), (-radius, -radius), (radius, -radius))


def _rounded_outline(shape: str, size_x: float, size_y: float, corner: float, arc_segments: int) -> Ring:
    """Local outline of a rectangle, oval (all corners rounded) or bullet (+X side rounded), centered at origin."""
    hx, hy = size_x / 2, size_y / 2
    radius = min(corner, hx, hy)
    if shape == "rectangle" or radius <= 0:
        return ((hx, hy), (-hx, hy), (-hx, -hy), (hx, -hy))
    steps = max(2, arc_segments // 4)

    def arc(cx: float, cy: float, start: float) -> list[Point]:
        return [
            (
                cx + radius * math.cos(start + i * math.pi / 2 / steps),
                cy + radius * math.sin(start + i * math.pi / 2 / steps),
            )
            for i in range(steps + 1)
        ]

    ring = arc(hx - radius, hy - radius, 0.0)
    ring += arc(-hx + radius, hy - radius, math.pi / 2) if shape == "oval" else [(-hx, hy), (-hx, -hy)]
    if shape == "oval":
        ring += arc(-hx + radius, -hy + radius, math.pi)
    ring += arc(hx - radius, -hy + radius, 3 * math.pi / 2)
    return tuple(ring)


def compute_arc_points(
    p1: list[float], p2: list[float], h: float, n: int = 6, tol: float = 1e-12, *, chord_error: float | None = None
) -> tuple[list[float], list[float]]:
    """Get the points of the arc.

    Parameters
    ----------
    p1 : list[float]
        Arc starting point.
    p2 : list[float]
        Arc ending point.
    h : float
        Arc height (sagitta). Positive values arc upward from p1 to p2,
        negative values arc downward.
    n : int, optional
        Number of points to generate along the arc.
        The default is ``6``.
    tol : float, optional
        Geometric tolerance.
        The default is ``1e-12``.
    chord_error : float, optional
        Maximum chord sagitta in the same units as the coordinates. When set,
        choose the count from radius and total sweep instead of ``n``.

    Returns
    -------
    tuple[list[float], list[float]]
        Points generated along the arc as (x_coordinates, y_coordinates).

    Notes
    -----
    Correctly handles arcs that subtend more than 180° (h > r case).

    Examples
    --------
    >>> from edb_layout_viewer.scene._builder.geometry import compute_arc_points
    >>> p1 = [0.0, 0.0]
    >>> p2 = [1.0, 0.0]
    >>> h = 0.2
    >>> xr, yr = compute_arc_points(p1, p2, h, n=6)
    >>> len(xr) == len(yr) == 6
    True

    """
    if abs(h) < tol:
        return [], []

    if h > 0:
        x1, y1, x2, y2 = p1[0], p1[1], p2[0], p2[1]
        reverse = False
    else:
        x1, y1, x2, y2 = p2[0], p2[1], p1[0], p1[1]
        h = -h
        reverse = True

    xa = (x2 - x1) / 2
    ya = (y2 - y1) / 2
    a = math.sqrt(xa**2 + ya**2)
    if a < tol:
        return [], []

    r = (a**2) / (2 * h) + h / 2
    b = math.sqrt(max(r**2 - a**2, 0.0))

    # h > r means arc > semicircle: center is on the same side as the bulge
    sign = -1.0 if h > r else 1.0
    xc = x1 + xa + sign * b * ya / a
    yc = y1 + ya - sign * b * xa / a

    alpha = math.atan2(y1 - yc, x1 - xc)
    beta = math.atan2(y2 - yc, x2 - xc)

    dangle = alpha - beta
    if dangle <= 0:
        dangle += 2 * math.pi
    if h > r and dangle < math.pi:
        dangle = 2 * math.pi - dangle

    if chord_error is not None:
        n = arc_segment_count(r, dangle, chord_error) - 1

    xr, yr = [], []
    for i in range(1, n + 1):
        t = i / (n + 1)
        angle = alpha - t * dangle
        xr.append(xc + r * math.cos(angle))
        yr.append(yc + r * math.sin(angle))

    if reverse:
        xr.reverse()
        yr.reverse()

    return xr, yr
