"""Planar camera -> normalized wall -> projector transformations.

Coordinates supplied to/from UI are normalized [0,1], in TL/TR/BR/BL order.
Camera and projector pixel dimensions are never silently interchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import cv2
import numpy as np

WALL = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], dtype=np.float64)


def quad(points: list[list[float]]) -> np.ndarray:
    a = np.asarray(points, dtype=np.float64)
    if a.shape != (4, 2) or not np.isfinite(a).all():
        raise ValueError("Нужно указать четыре конечные точки x,y")
    if (a < 0).any() or (a > 1).any():
        raise ValueError("Точки должны оставаться в пределах изображения")
    edges = np.roll(a, -1, axis=0) - a
    next_edges = np.roll(edges, -1, axis=0)
    cross = edges[:, 0] * next_edges[:, 1] - edges[:, 1] * next_edges[:, 0]
    area = 0.5 * float(np.sum(a[:, 0] * np.roll(a[:, 1], -1) - np.roll(a[:, 0], -1) * a[:, 1]))
    if not np.all(cross > 1e-5) or area < 0.002:
        raise ValueError("Точки должны образовывать выпуклый четырёхугольник по часовой стрелке")
    if np.min(np.linalg.norm(edges, axis=1)) < 0.025:
        raise ValueError("Контрольные точки расположены слишком близко")
    return a


def homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    h = cv2.getPerspectiveTransform(src.astype(np.float32), dst.astype(np.float32)).astype(np.float64)
    if not np.isfinite(h).all() or abs(np.linalg.det(h)) < 1e-10:
        raise ValueError("Невозможно получить устойчивое преобразование")
    h /= h[2, 2]
    if np.linalg.cond(h) > 1e8:
        raise ValueError("Недостаточно устойчивая геометрия")
    return h


def transform(matrix: np.ndarray, points: list[list[float]] | np.ndarray) -> np.ndarray:
    a = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    projected = np.column_stack((a, np.ones(len(a)))) @ matrix.T
    if np.any(np.abs(projected[:, 2]) < 1e-10):
        raise ValueError("Точка оказалась в бесконечности")
    return projected[:, :2] / projected[:, 2, None]


@dataclass(frozen=True)
class Calibration:
    camera_quad: list[list[float]]
    projector_quad: list[list[float]]
    camera_resolution: tuple[int, int]
    projector_resolution: tuple[int, int]

    def __post_init__(self):
        quad(self.camera_quad)
        quad(self.projector_quad)
        for w, h in (self.camera_resolution, self.projector_resolution):
            if not (0 < w <= 16384 and 0 < h <= 16384):
                raise ValueError("Некорректное разрешение устройства")

    @property
    def camera_to_wall(self) -> np.ndarray:
        return homography(quad(self.camera_quad), WALL)

    @property
    def wall_to_projector(self) -> np.ndarray:
        return homography(WALL, quad(self.projector_quad))

    @property
    def camera_to_projector(self) -> np.ndarray:
        return self.wall_to_projector @ self.camera_to_wall

    def camera_pixels_to_wall(self, pixels: list[list[float]]) -> np.ndarray:
        w, h = self.camera_resolution
        return transform(self.camera_to_wall, np.asarray(pixels, dtype=np.float64) / [w, h])

    def wall_to_projector_pixels(self, points: list[list[float]]) -> np.ndarray:
        w, h = self.projector_resolution
        return transform(self.wall_to_projector, points) * [w, h]

    def camera_pixels_to_projector_pixels(self, pixels: list[list[float]]) -> np.ndarray:
        w, h = self.camera_resolution
        pw, ph = self.projector_resolution
        return transform(self.camera_to_projector, np.asarray(pixels, dtype=np.float64) / [w, h]) * [pw, ph]

    def info(self) -> dict:
        center = self.camera_pixels_to_projector_pixels([[self.camera_resolution[0]/2, self.camera_resolution[1]/2]])
        return {
            "camera_to_wall": self.camera_to_wall.tolist(),
            "wall_to_projector": self.wall_to_projector.tolist(),
            "camera_to_projector": self.camera_to_projector.tolist(),
            "camera_center_on_projector": center[0].tolist(),
            "note": "4 контрольные точки имеют нулевую ошибку интерполяции; проверяйте дополнительные точки и дисторсию объектива"
        }
