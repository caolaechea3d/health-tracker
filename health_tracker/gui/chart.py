"""A simple line chart on a Tk canvas (used for weight over time)."""

from __future__ import annotations

import tkinter as tk
from datetime import date


class LineChart(tk.Canvas):
    """Values by date as a line with dots; the highlighted date gets a bigger dot."""

    def __init__(self, master: tk.Misc, color: str, unit: str = "", scale: float = 1.0, **kwargs):
        super().__init__(master, background="white", highlightthickness=1, highlightbackground="#e5e7eb", **kwargs)
        self.color = color
        self.unit = unit
        self.scale = scale
        self.points: list[tuple[date, float]] = []
        self.highlight: date | None = None
        self.title = ""
        self.empty_text = ""
        self.bind("<Configure>", lambda _e: self.draw())

    def set_points(self, points: list[tuple[date, float]], title: str, highlight: date | None = None,
                   empty_text: str = "No data yet") -> None:
        self.points = sorted(points)
        self.title = title
        self.highlight = highlight
        self.empty_text = empty_text
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
        if len(self.points) < 2:
            self.create_text(width / 2, height / 2, text=self.empty_text, fill="#6b7280", font=font)
            return

        left, right = round(56 * s), width - round(20 * s)
        top, bottom = round(40 * s), height - round(30 * s)
        values = [v for _, v in self.points]
        low, high = min(values), max(values)
        pad = max((high - low) * 0.15, 0.5)
        low, high = low - pad, high + pad
        first, last = self.points[0][0], self.points[-1][0]
        span = max((last - first).days, 1)

        def x(d: date) -> float:
            return left + (d - first).days / span * (right - left)

        def y(v: float) -> float:
            return bottom - (v - low) / (high - low) * (bottom - top)

        for i in range(5):  # horizontal grid lines with their values
            value = low + (high - low) * i / 4
            self.create_line(left, y(value), right, y(value), fill="#eef0f3")
            self.create_text(left - 6, y(value), text=f"{value:.1f}", anchor="e", fill="#6b7280", font=small)
        for d, anchor in ((first, "w"), (last, "e")):
            self.create_text(x(d), bottom + round(14 * s), text=f"{d.day} {d:%b}", anchor=anchor, fill="#6b7280",
                             font=small)

        coords = [c for d, v in self.points for c in (x(d), y(v))]
        self.create_line(*coords, fill=self.color, width=max(2, round(2 * s)))
        r = round(3 * s)
        for d, v in self.points:
            if d == self.highlight:
                big = round(6 * s)
                self.create_oval(x(d) - big, y(v) - big, x(d) + big, y(v) + big, fill=self.color, outline="white",
                                 width=2)
                self.create_text(x(d), y(v) - big - 4, text=f"{v:.1f}", anchor="s", font=("Segoe UI", 9, "bold"))
            else:
                self.create_oval(x(d) - r, y(v) - r, x(d) + r, y(v) + r, fill=self.color, outline="")
