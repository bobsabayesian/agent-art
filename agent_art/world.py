"""Canvas plus a spatial hash of every point drawn so far."""
from __future__ import annotations

from collections import defaultdict

import numpy as np


class World:
    def __init__(self, width: float, height: float, cell: float = 10.0):
        self.width, self.height, self.cell = width, height, cell
        self._grid: dict[tuple[int, int], list[tuple[float, float, int, int]]] = defaultdict(list)

    def _key(self, x: float, y: float) -> tuple[int, int]:
        return int(x // self.cell), int(y // self.cell)

    def add_path(self, pts: np.ndarray, species_id: int, agent_id: int, spacing: float = 2.0) -> None:
        """Insert points along the path (resampled so sparse long segments are still seen)."""
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            k = max(1, int(np.hypot(x1 - x0, y1 - y0) // spacing))
            for t in np.linspace(0, 1, k, endpoint=False):
                x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                self._grid[self._key(x, y)].append((x, y, species_id, agent_id))
        x, y = pts[-1]
        self._grid[self._key(x, y)].append((x, y, species_id, agent_id))

    def near(self, x: float, y: float, radius: float):
        cx, cy = self._key(x, y)
        r = int(radius // self.cell) + 1
        r2 = radius * radius
        for i in range(cx - r, cx + r + 1):
            for j in range(cy - r, cy + r + 1):
                for px, py, sp, ag in self._grid.get((i, j), ()):
                    d2 = (px - x) ** 2 + (py - y) ** 2
                    if d2 <= r2:
                        yield px, py, sp, ag, d2 ** 0.5
