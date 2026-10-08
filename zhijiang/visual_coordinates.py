"""A shared Euclidean viewport: equal lengths stay equal in both renderers."""
from dataclasses import dataclass


@dataclass(frozen=True)
class EuclideanViewport:
    x_range: list[float]
    y_range: list[float]
    width: float
    height: float
    center: tuple[float, float]
    flip_y: bool = False

    @property
    def scale(self) -> float:
        return min(self.width / (self.x_range[1] - self.x_range[0]),
                   self.height / (self.y_range[1] - self.y_range[0]))

    def point(self, x: float, y: float) -> tuple[float, float]:
        return (self.center[0] + (x - sum(self.x_range) / 2) * self.scale,
                self.center[1] + (-1 if self.flip_y else 1) *
                (y - sum(self.y_range) / 2) * self.scale)
