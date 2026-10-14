"""Paper sizes, units, margin and border geometry. Everything is resolved to millimetres."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

UNITS = {"mm": 1.0, "cm": 10.0, "in": 25.4}
IN = 25.4

# key -> (label, group, short_mm, long_mm). Stored portrait; orientation picks the layout.
SIZES: dict[str, tuple[str, str, float, float]] = {}


def _add(key: str, label: str, group: str, w: float, h: float, inches: bool = False) -> None:
    k = IN if inches else 1.0
    SIZES[key] = (label, group, min(w, h) * k, max(w, h) * k)


for n, (w, h) in enumerate([(841, 1189), (594, 841), (420, 594), (297, 420), (210, 297), (148, 210), (105, 148)]):
    _add(f"a{n}", f"A{n} — {w} × {h} mm", "ISO / metric", w, h)
for k, (w, h) in {"b3": (353, 500), "b4": (250, 353), "b5": (176, 250)}.items():
    _add(k, f"{k.upper()} — {w} × {h} mm", "ISO / metric", w, h)
for w, h in [(10, 15), (13, 18), (20, 30), (30, 40), (40, 50), (50, 70), (70, 100)]:
    _add(f"{w}x{h}cm", f"{w} × {h} cm", "Metric frames", w * 10, h * 10)
for k, label, w, h in [
    ("letter", "Letter", 8.5, 11), ("legal", "Legal", 8.5, 14), ("tabloid", "Tabloid / Ledger", 11, 17),
    ("ansi_c", "ANSI C", 17, 22), ("ansi_d", "ANSI D", 22, 34), ("ansi_e", "ANSI E", 34, 44),
    ("arch_a", "Arch A", 9, 12), ("arch_b", "Arch B", 12, 18), ("arch_c", "Arch C", 18, 24),
    ("arch_d", "Arch D", 24, 36), ("arch_e", "Arch E", 36, 48),
]:
    _add(k, f"{label} — {w:g} × {h:g} in", "US", w, h, inches=True)
for w, h in [(3, 5), (4, 6), (5, 7), (8, 10), (11, 14), (12, 12), (16, 20), (20, 24), (24, 30), (30, 40)]:
    _add(f"{w}x{h}in", f"{w} × {h} in", "US frames / photo", w, h, inches=True)

BORDER_STYLES = ("none", "single", "double", "dotted", "striped")


def size_key(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


@dataclass
class Border:
    style: str = "none"
    width: float = 0.5          # line width, mm (dot diameter for dotted)
    gap: float | None = None    # double: clear space between the two lines (default max(1, 2 x width))
    dash: float = 4.0           # striped: dash length, mm
    dash_gap: float = 2.0       # striped: gap length, mm
    dot_spacing: float = 2.5    # dotted: centre-to-centre distance, mm
    pen: str = "border"
    color: str = "#111111"


def border_extent(b: Border) -> float:
    """Total thickness of the border band, mm (outer edge to inner edge)."""
    if b.style == "none":
        return 0.0
    if b.style == "double":
        return (b.gap if b.gap is not None else max(1.0, 2 * b.width)) + 2 * b.width
    return b.width


@dataclass
class Paper:
    """Layout, outside in: paper edge | margin | border band | padding | drawing area."""
    width: float
    height: float
    margin: float
    border: Border
    label: str
    padding: float = 0.0   # border's inner edge -> drawing area (only used when there is a border)

    @property
    def art_inset(self) -> float:
        """Distance from the paper edge to the drawing area."""
        if self.border.style == "none":
            return self.margin
        return self.margin + border_extent(self.border) + self.padding


def resolve_paper(canvas: dict | None) -> Paper:
    c = dict(canvas or {})
    unit = c.get("unit", "mm")
    if unit not in UNITS:
        raise ValueError(f"canvas.unit must be one of {sorted(UNITS)}, got {unit!r}")
    f = UNITS[unit]
    size = c.get("size")
    if size and size_key(size) != "custom":
        key = size_key(size)
        if key not in SIZES:
            raise ValueError(f"unknown paper size {size!r}; choose from {', '.join(SIZES)} or 'custom'")
        label, _, short, long_ = SIZES[key]
        orient = c.get("orientation", "landscape")
        if orient not in ("landscape", "portrait"):
            raise ValueError("canvas.orientation must be 'landscape' or 'portrait'")
        w, h = (long_, short) if orient == "landscape" else (short, long_)
        label = f"{label.split(' — ')[0]} {orient}"
    else:
        w, h = float(c.get("width", 297 / f)) * f, float(c.get("height", 210 / f)) * f
        label = "custom"
    margin = float(c.get("margin", 10 / f)) * f
    if w <= 0 or h <= 0:
        raise ValueError("canvas width and height must be positive")
    if margin < 0 or 2 * margin >= min(w, h):
        raise ValueError(f"margin {margin:g} mm leaves no drawing area on a {w:g} × {h:g} mm sheet")
    border = _border(c.get("border"))
    padding = float(c.get("padding", 3 / f)) * f
    if padding < 0:
        raise ValueError("canvas.padding must be >= 0")
    paper = Paper(w, h, margin, border, label, padding)
    if 2 * paper.art_inset >= min(w, h):
        raise ValueError(f"margin + border + padding ({paper.art_inset:g} mm each side) leave no drawing area "
                         f"on a {w:g} × {h:g} mm sheet")
    return paper


def _border(b) -> Border:
    if b is None:
        return Border()
    if isinstance(b, str):
        b = {"style": b}
    allowed = set(Border.__dataclass_fields__)
    bad = set(b) - allowed
    if bad:
        raise ValueError(f"border: unknown keys {sorted(bad)}")
    out = Border(**b)
    if out.style not in BORDER_STYLES:
        raise ValueError(f"border.style must be one of {BORDER_STYLES}, got {out.style!r}")
    for k in ("width", "dash", "dash_gap", "dot_spacing"):
        if getattr(out, k) <= 0:
            raise ValueError(f"border.{k} must be positive")
    return out


def _rect(d: float, w: float, h: float) -> np.ndarray:
    return np.array([(d, d), (w - d, d), (w - d, h - d), (d, h - d)], float)  # math coords, y up


def border_paths(paper: Paper) -> list[np.ndarray]:
    """Border as polylines in math coordinates (y up). Its outer edge sits exactly on the margin line."""
    b, w, h = paper.border, paper.width, paper.height
    if b.style == "none":
        return []
    ext = border_extent(b)
    d = paper.margin + ext / 2          # centre line of the band
    if b.style == "single":
        r = _rect(d, w, h)
        return [np.vstack([r, r[:1]])]
    if b.style == "double":
        off = (ext - b.width) / 2          # centre of each line, from the band's centre line
        return [np.vstack([r, r[:1]]) for r in (_rect(d - off, w, h), _rect(d + off, w, h))]
    r = _rect(d, w, h)
    out = []
    for a, c in zip(r, np.roll(r, -1, axis=0)):
        L = float(np.hypot(*(c - a)))
        u = (c - a) / L
        if b.style == "dotted":
            n = max(1, round(L / b.dot_spacing))
            for k in range(n):
                pt = a + u * (L * k / n)
                out.append(np.array([pt, pt + u * 0.01]))   # a dot = a tiny segment with round caps
        else:  # striped
            n = max(1, round(L / (b.dash + b.dash_gap)))
            period = L / n
            dl = period * b.dash / (b.dash + b.dash_gap)
            for k in range(n):
                st = k * period + (period - dl) / 2
                out.append(np.array([a + u * st, a + u * (st + dl)]))
    return out
