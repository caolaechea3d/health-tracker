"""A simple line chart on a Tk canvas (weight, blood pressure and glucose over time)."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from datetime import date, datetime

Point = tuple[date | datetime, float]  # a datetime places the point at its time of day


@dataclass
class Series:
    name: str
    color: str
    points: list[Point] = field(default_factory=list)


def _x_value(when: date | datetime) -> float:
    """Days since year 1, with the time of day as a fraction."""
    if isinstance(when, datetime):
        return when.toordinal() + (when.hour * 60 + when.minute) / 1440
    return float(when.toordinal())


def _day(when: date | datetime) -> date:
    return when.date() if isinstance(when, datetime) else when


class LineChart(tk.Canvas):
    """One or more lines of values by date; the highlighted day's points are bigger and labeled.

    An optional `band` (low, high) shades a target range behind the lines.
    """

    def __init__(self, master: tk.Misc, unit: str = "", scale: float = 1.0, decimals: int = 1, **kwargs):
        super().__init__(master, background="white", highlightthickness=1, highlightbackground="#e5e7eb", **kwargs)
        self.unit = unit
        self.scale = scale
        self.decimals = decimals
        self.series: list[Series] = []
        self.highlight: date | None = None
        self.band: tuple[float, float] | None = None
        self.title = ""
        self.empty_text = ""
        self.bind("<Configure>", lambda _e: self.draw())

    def set_series(self, series: list[Series], title: str, highlight: date | None = None,
                   empty_text: str = "No data yet", band: tuple[float, float] | None = None) -> None:
        self.series = [Series(s.name, s.color, sorted(s.points, key=lambda p: _x_value(p[0]))) for s in series]
        self.title = title
        self.highlight = highlight
        self.empty_text = empty_text
        self.band = band
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        s = self.scale
        width, height = self.winfo_width(), self.winfo_height()
        if width < 50 or height < 50:
            return
        font, small = ("Segoe UI", 9), ("Segoe UI", 8)
        title = f"{self.title} ({self.unit})" if self.unit else self.title
        self.create_text(round(12 * s), round(10 * s), text=title, anchor="nw", font=("Segoe UI", 10, "bold"))
        points = [p for series in self.series for p in series.points]
        if not any(len(series.points) >= 2 for series in self.series):
            self.create_text(width / 2, height / 2, text=self.empty_text, fill="#6b7280", font=font)
            return
        if len(self.series) > 1:
            self._legend(width, s, small)

        left, right = round(56 * s), width - round(20 * s)
        top, bottom = round(44 * s), height - round(30 * s)
        values = [v for _, v in points] + (list(self.band) if self.band else [])
        low, high = min(values), max(values)
        pad = max((high - low) * 0.12, 0.5)
        low, high = low - pad, high + pad
        xs = [_x_value(when) for when, _ in points]
        first, last = min(xs), max(xs)
        span = max(last - first, 1)

        def x(when: date | datetime) -> float:
            return left + (_x_value(when) - first) / span * (right - left)

        def y(v: float) -> float:
            return bottom - (v - low) / (high - low) * (bottom - top)

        if self.band:
            self.create_rectangle(left, y(self.band[1]), right, y(self.band[0]), fill="#e9f5ef", outline="")
        for i in range(5):  # horizontal grid lines with their values
            value = low + (high - low) * i / 4
            self.create_line(left, y(value), right, y(value), fill="#eef0f3")
            self.create_text(left - 6, y(value), text=f"{value:.{self.decimals}f}", anchor="e", fill="#6b7280",
                             font=small)
        whens = sorted((when for when, _ in points), key=_x_value)
        for when, anchor in ((whens[0], "w"), (whens[-1], "e")):
            d = _day(when)
            self.create_text(x(when), bottom + round(14 * s), text=f"{d.day} {d:%b}", anchor=anchor, fill="#6b7280",
                             font=small)

        r, big = round(3 * s), round(6 * s)
        for series in self.series:
            if len(series.points) >= 2:
                coords = [c for when, v in series.points for c in (x(when), y(v))]
                self.create_line(*coords, fill=series.color, width=max(2, round(2 * s)))
            on_day = [p for p in series.points if _day(p[0]) == self.highlight]
            for when, v in series.points:
                size = big if _day(when) == self.highlight else r
                self.create_oval(x(when) - size, y(v) - size, x(when) + size, y(v) + size, fill=series.color,
                                 outline="white" if size == big else "", width=2)
            if on_day:  # label the highlighted day's last value
                when, v = on_day[-1]
                self.create_text(x(when), y(v) - big - 4, text=f"{v:.{self.decimals}f}", anchor="s",
                                 font=("Segoe UI", 9, "bold"))

    def _legend(self, width: int, s: float, font: tuple) -> None:
        x = width - round(12 * s)
        for series in reversed(self.series):
            label = self.create_text(x, round(17 * s), text=series.name, anchor="e", fill="#374151", font=font)
            x = self.bbox(label)[0] - round(5 * s)
            dot = round(4 * s)
            self.create_oval(x - 2 * dot, round(17 * s) - dot, x, round(17 * s) + dot, fill=series.color, outline="")
            x -= 2 * dot + round(14 * s)
