"""SVG writer: one Inkscape-style layer per pen so plotter-utils/vpype can split by pen."""
from __future__ import annotations

from html import escape

import numpy as np

from .sim import Result


def _rdp(pts: np.ndarray, tol: float) -> np.ndarray:
    """Ramer-Douglas-Peucker (iterative)."""
    if len(pts) < 3 or tol <= 0:
        return pts
    keep = np.zeros(len(pts), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        p, q = pts[a], pts[b]
        d = q - p
        norm = np.hypot(*d)
        seg = pts[a + 1:b] - p
        dist = np.hypot(*seg.T) if norm == 0 else np.abs(d[0] * seg[:, 1] - d[1] * seg[:, 0]) / norm
        i = int(np.argmax(dist))
        if dist[i] > tol:
            keep[a + 1 + i] = True
            stack += [(a, a + 1 + i), (a + 1 + i, b)]
    return pts[keep]


def to_svg(res: Result, simplify: float = 0.0, background: str | None = None) -> str:
    w, h = res.width, res.height
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}">',
    ]
    if background:
        out.append(f'<rect width="{w}" height="{h}" fill="{background}"/>')
    layers: dict[str, list[str]] = {}
    for i, sid in enumerate(res.species_ids):
        sp = res.species[sid]
        p = _rdp(res.paths[i], simplify)
        if len(p) < 2:
            continue
        d = "M" + " L".join(f"{x:.3f},{h - y:.3f}" for x, y in p)  # flip: y up -> SVG y down
        layers.setdefault(sp.pen, []).append(
            f'<path d="{d}" stroke="{escape(sp.color)}" stroke-width="{res.thickness[i]:.3f}" '
            f'data-species="{escape(sp.name)}" data-agent="{i}"/>')
    if res.border:   # all border pieces in one path (many sub-paths for dotted/striped)
        b = res.paper.border
        d = " ".join("M" + " L".join(f"{x:.3f},{h - y:.3f}" for x, y in seg) for seg in res.border)
        layers.setdefault(b.pen, []).append(
            f'<path d="{d}" stroke="{escape(b.color)}" stroke-width="{b.width:.3f}" data-border="{b.style}"/>')
    for pen, items in layers.items():
        out.append(f'<g inkscape:groupmode="layer" inkscape:label="{escape(pen)}" id="pen-{escape(pen)}" '
                   f'fill="none" stroke-linecap="round" stroke-linejoin="round">')
        out.extend(items)
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"
