"""Generate Halo CE's seeded random-direction lookup table.

This mirrors ``geosphere_new(16)`` and its helper traversal in the pinned
``halo-ce-universal/source/math/geometry.c``.  It is an offline converter
helper: table order is gameplay data because random seeds select by index.
"""
from __future__ import annotations

import math
import struct

SEGMENTS = 16
BASE_VERTICES = (
    (0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0),
    (0.0, -1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, -1.0),
)
BASE_TRIANGLES = (
    (0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1),
    (5, 1, 4), (5, 4, 3), (5, 3, 2), (5, 2, 1),
)
VERTEX_COUNT = 8 * (SEGMENTS - 2) * (SEGMENTS - 1) // 2 + 12 * (SEGMENTS - 1) + 6


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _vertex(a: tuple[float, float, float], b: tuple[float, float, float],
            count: int, index: int) -> tuple[float, float, float]:
    t = _f32(_f32(float(index)) / _f32(float(count)))
    omt = _f32(1.0 - t)
    p = tuple(_f32(_f32(omt * x) + _f32(t * y)) for x, y in zip(a, b))
    magnitude_squared = _f32(_f32(_f32(p[0] * p[0]) + _f32(p[1] * p[1])) + _f32(p[2] * p[2]))
    magnitude = _f32(math.sqrt(magnitude_squared))
    return tuple(_f32(x * _f32(1.0 / magnitude)) for x in p)


def direction_table() -> tuple[tuple[float, float, float], ...]:
    """Return the 1,026 vectors in the source generator's exact insertion order."""
    vertices = list(BASE_VERTICES)
    edge_first = [[-1] * 8 for _ in range(8)]

    def edge(v1: int, v2: int, subdivision: int) -> int:
        va, vb = min(v1, v2), max(v1, v2)
        reversed_edge = v1 > v2
        if subdivision == 0:
            return v1
        if subdivision == SEGMENTS:
            return v2
        first = edge_first[va][vb]
        if first < 0:
            first = len(vertices)
            edge_first[va][vb] = first
            for i in range(1, SEGMENTS):
                vertices.append(_vertex(vertices[va], vertices[vb], SEGMENTS, i))
        offset = SEGMENTS - subdivision if reversed_edge else subdivision
        return first + offset - 1

    for v1, v2, v3 in BASE_TRIANGLES:
        face = [-1] * ((SEGMENTS + 1) * (SEGMENTS + 1))

        def face_vertex(row: int, column: int) -> int:
            at = row * (SEGMENTS + 1) + column
            if face[at] >= 0:
                return face[at]
            if column == 0:
                result = edge(v1, v3, row)
            elif row == SEGMENTS:
                result = edge(v3, v2, column)
            elif column == row:
                result = edge(v1, v2, row)
            else:
                result = len(vertices)
                vertices.append((0.0, 0.0, 0.0))
                p1 = edge(v1, v3, row)
                p2 = edge(v1, v2, row)
                vertices[result] = _vertex(vertices[p1], vertices[p2], row, column)
            face[at] = result
            return result

        for row in range(1, SEGMENTS + 1):
            for column in range(1, row + 1):
                face_vertex(row - 1, column - 1)
                face_vertex(row, column - 1)
                face_vertex(row, column)
                if column < row:
                    face_vertex(row - 1, column)

    if len(vertices) != VERTEX_COUNT:
        raise RuntimeError(f"geosphere generated {len(vertices)} vertices; expected {VERTEX_COUNT}")
    return tuple(vertices)
