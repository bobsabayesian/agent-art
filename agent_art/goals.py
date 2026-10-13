"""Goal shapes: dense template polylines an agent tries to trace without lifting the pen."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


def _polygon(n: int, inner: float | None = None) -> np.ndarray:
    k = n * (2 if inner else 1)
    ang = 2 * math.pi * np.arange(k) / k
    r = np.ones(k) if not inner else np.where(np.arange(k) % 2 == 0, 1.0, inner)
    return np.stack([r * np.cos(ang), r * np.sin(ang)], 1)


def _closed(v: np.ndarray) -> np.ndarray:
    return np.vstack([v, v[:1]])


def _circle() -> np.ndarray:
    t = np.linspace(0, 2 * math.pi, 400)
    return np.stack([np.cos(t), np.sin(t)], 1)


def _figure8() -> np.ndarray:
    t = np.linspace(0, 2 * math.pi, 600)
    return np.stack([np.cos(t) - 1, 0.6 * np.sin(2 * t)], 1)  # starts at origin, loops through x=-2


def _heart() -> np.ndarray:
    t = np.linspace(0, 2 * math.pi, 600)
    x = 16 * np.sin(t) ** 3
    y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
    p = np.stack([x, y], 1) / 16
    return p - p[0]


def _spiral() -> np.ndarray:
    t = np.linspace(0, 3 * 2 * math.pi, 900)
    r = 1 - 0.9 * t / t[-1]
    return np.stack([r * np.cos(t), r * np.sin(t)], 1)


def _wave() -> np.ndarray:
    x = np.linspace(0, 6 * math.pi, 600)
    return np.stack([x / math.pi, 0.5 * np.sin(x)], 1)


def _line() -> np.ndarray:
    return np.stack([np.linspace(0, 2, 50), np.zeros(50)], 1)


# name -> (unit polyline, closed?)
SHAPES: dict[str, tuple[np.ndarray, bool]] = {
    "circle": (_circle(), True),
    "square": (_closed(_polygon(4)), True),
    "triangle": (_closed(_polygon(3)), True),
    "pentagon": (_closed(_polygon(5)), True),
    "hexagon": (_closed(_polygon(6)), True),
    "star": (_closed(_polygon(5, inner=0.4)), True),
    "figure8": (_figure8(), True),
    "heart": (_heart(), True),
    "spiral": (_spiral(), False),
    "wave": (_wave(), False),
    "line": (_line(), False),
}


@dataclass
class Template:
    pts: np.ndarray   # (K,2) dense, starts at the drop point
    closed: bool
    spacing: float

    @property
    def k(self) -> int:
        return len(self.pts)

    def index(self, i: int) -> int:
        return i % (self.k - 1) if self.closed else min(i, self.k - 1)

    def tangent(self, i: int) -> float:
        a, b = self.pts[self.index(i)], self.pts[self.index(i + 1)]
        if np.allclose(a, b):
            a = self.pts[self.index(i - 1)]
        return math.atan2(b[1] - a[1], b[0] - a[0])


def _densify(p: np.ndarray, spacing: float) -> np.ndarray:
    seg = np.hypot(*np.diff(p, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    s = np.arange(0, cum[-1], spacing)
    s = np.append(s, cum[-1])
    return np.stack([np.interp(s, cum, p[:, 0]), np.interp(s, cum, p[:, 1])], 1)


def make_template(name: str, size: float, rotation_deg: float, mirror: bool,
                  start: tuple[float, float]) -> Template:
    """Scale to `size` mm, optionally mirror (reverses direction), rotate, translate so P0 = start."""
    if name not in SHAPES:
        raise ValueError(f"unknown goal {name!r}; choose from {sorted(SHAPES)}")
    unit, closed = SHAPES[name]
    p = unit * size
    if mirror:
        p = p * np.array([1, -1])
    th = math.radians(rotation_deg)
    rot = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
    p = p @ rot.T
    p = p - p[0] + np.array(start)
    spacing = max(size / 150, 0.05)
    return Template(_densify(p, spacing), closed, spacing)
