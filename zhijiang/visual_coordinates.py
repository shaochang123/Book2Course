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


def extend_line_to_window(start,end,window,*,ray=False):
    """Extend a mathematical line/ray to a finite drawing window.

    A ray retains its real origin; an infinite line gets both boundary tips.
    Segment geometry and generic diagram arrows never use this operation.
    """
    import math
    if len(window)!=4 or not all(math.isfinite(q) for q in window):
        raise ValueError('Invalid line window')
    lower=[window[0],window[2]];upper=[window[1],window[3]]
    if any(a>=b for a,b in zip(lower,upper)):raise ValueError('Empty line window')
    direction=[b-a for a,b in zip(start,end)]
    if math.hypot(*direction)<1e-12:raise ValueError('Degenerate line direction')
    entry,exit=-math.inf,math.inf
    for axis,delta in enumerate(direction):
        if abs(delta)<1e-12:
            if not lower[axis]<=start[axis]<=upper[axis]:return [start,end]
            continue
        first=(lower[axis]-start[axis])/delta;last=(upper[axis]-start[axis])/delta
        entry=max(entry,min(first,last));exit=min(exit,max(first,last))
    if entry>exit or ray and exit<0:return [start,end]
    def at(t):return [a+t*d for a,d in zip(start,direction)]
    return [list(start) if ray else at(entry),at(exit)]
