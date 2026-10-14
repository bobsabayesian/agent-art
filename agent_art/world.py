"""Canvas plus a spatial grid of every point drawn so far (numpy arrays per cell).

The world is static while an agent walks (its path is added afterwards), so neighborhood
lookups are cached until the next add_path.
"""
from __future__ import annotations

import numpy as np

_EMPTY = np.empty((0, 3))


class World:
    def __init__(self, width: float, height: float, cell: float = 10.0):
        self.width, self.height, self.cell = width, height, max(cell, 1.0)
        self._cells: dict[tuple[int, int], np.ndarray] = {}   # (n,3): x, y, species_id
        self._nb: dict[tuple[int, int, int], np.ndarray] = {}

    def add_path(self, pts: np.ndarray, species_id: int, spacing: float = 2.0) -> None:
        """Insert points along the path, resampled so long segments are still seen."""
        if len(pts) > 1:
            cum = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
            s = np.append(np.arange(0, cum[-1], spacing), cum[-1])
            pts = np.stack([np.interp(s, cum, pts[:, 0]), np.interp(s, cum, pts[:, 1])], 1)
        cx, cy = (pts[:, 0] // self.cell).astype(int), (pts[:, 1] // self.cell).astype(int)
        rec = np.column_stack([pts, np.full(len(pts), species_id, float)])
        keys, inv = np.unique(np.column_stack([cx, cy]), axis=0, return_inverse=True)
        inv = inv.ravel()
        for i, (kx, ky) in enumerate(keys):
            k = (int(kx), int(ky))
            self._cells[k] = np.vstack([self._cells[k], rec[inv == i]]) if k in self._cells else rec[inv == i]
        self._nb.clear()

    def neighbors(self, x: float, y: float, radius: float) -> np.ndarray:
        """(m,3) array of x, y, species_id for all points in the cells covering `radius` (a superset)."""
        r = int(np.ceil(radius / self.cell))
        cx, cy = int(x // self.cell), int(y // self.cell)
        key = (cx, cy, r)
        hit = self._nb.get(key)
        if hit is None:
            parts = [self._cells[k] for i in range(cx - r, cx + r + 1) for j in range(cy - r, cy + r + 1)
                     if (k := (i, j)) in self._cells]
            hit = np.vstack(parts) if parts else _EMPTY
            self._nb[key] = hit
        return hit
