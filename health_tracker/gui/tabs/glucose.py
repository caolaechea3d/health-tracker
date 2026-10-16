"""Glucose tab: blood sugar readings for diabetes, with a target range, averages and a chart."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from statistics import mean
from tkinter import messagebox, ttk

from ...storage import GLUCOSE_CONTEXTS, GLUCOSE_TARGET_LIMITS, GlucoseReading, HealthData, glucose_status, in_last_days
from ..chart import Series
from ..widgets import wrapping_label
from .base import GLUCOSE_COLOR
from .readings import ReadingsTab

STATUS_COLORS = {"Low": "#c0392b", "High": "#c2410c"}  # in-range readings keep the usual color


class GlucoseTab(ReadingsTab):
    label = "Glucose"
    tab_icon = "🩸"
    tab_color = GLUCOSE_COLOR
    title_text = "Glucose"
    unit = "mg/dL"
    columns = (("value", "mg/dL", 55, "e"), ("context", "When", 90, "w"), ("status", "Status", 70, "w"),
               ("notes", "Notes", 120, "w"))
    stats = (("week", "7-day average"), ("in_range", "In range, 7 days"), ("lows", "Lows, 7 days"),
             ("month", "30-day average"))

    def build_form(self, frame: ttk.Frame) -> ttk.Entry:
        self.value_var = tk.StringVar()
        self.context_var = tk.StringVar(value=GLUCOSE_CONTEXTS[0])
        value = ttk.Entry(frame, textvariable=self.value_var, width=6, font=("Segoe UI", 12))
        value.pack(side="left")
        ttk.Label(frame, text="mg/dL").pack(side="left", padx=(4, 16))
        ttk.Label(frame, text="When").pack(side="left")
        ttk.Combobox(frame, textvariable=self.context_var, values=GLUCOSE_CONTEXTS, state="readonly",
                     width=12).pack(side="left", padx=4)
        return value

    def build_side(self, frame: ttk.Frame) -> None:
        row = ttk.Frame(frame)
        row.pack(anchor="w")
        ttk.Label(row, text="Target range").pack(side="left")
        self.low_var, self.high_var = tk.StringVar(), tk.StringVar()
        lowest, highest = GLUCOSE_TARGET_LIMITS
        for i, var in enumerate((self.low_var, self.high_var)):
            if i:
                ttk.Label(row, text="–").pack(side="left")
            spin = ttk.Spinbox(row, from_=lowest, to=highest, increment=5, width=5, textvariable=var,
                               command=self.save_target)
            spin.pack(side="left", padx=4)
            spin.bind("<Return>", lambda _e: self.save_target())
            spin.bind("<FocusOut>", lambda _e: self.save_target())
        ttk.Label(row, text="mg/dL").pack(side="left")
        wrapping_label(frame, "Readings below the range are marked Low and above it High; the shaded band on the "
                              "chart is the range. 70–180 is a common target for people with diabetes — ask your "
                              "doctor which range is right for you.").pack(fill="x", pady=(6, 0))
        for name, color in STATUS_COLORS.items():
            self.tree.tag_configure(name, foreground=color)

    def records(self, data: HealthData) -> list[GlucoseReading]:
        return data.glucose

    def row(self, record: GlucoseReading, data: HealthData) -> tuple[tuple, tuple[str, ...]]:
        status = glucose_status(record.mg_dl, data.glucose_target)
        return (record.mg_dl, record.context, status, record.notes), (status,)

    def save_reading(self, day: date, time: str, notes: str) -> str:
        reading = GlucoseReading(day, time, self.value_var.get(), self.context_var.get(), notes)
        self.app.store.add_glucose(reading)
        status = glucose_status(reading.mg_dl, self.app.data.glucose_target)
        return (f"Saved glucose {reading.mg_dl} mg/dL ({reading.context.lower()}, {status.lower()}) "
                f"at {reading.time} on {day.isoformat()}")

    def delete_reading(self, reading_id: str) -> None:
        self.app.store.delete_glucose(reading_id)

    def clear_form(self) -> None:
        self.value_var.set("")  # keep "When": consecutive readings are often of the same kind

    def redraw(self, data: HealthData, day: date) -> None:
        low, high = data.glucose_target
        self.low_var.set(str(low))
        self.high_var.set(str(high))
        super().redraw(data, day)

    def stat_values(self, data: HealthData, day: date) -> dict[str, str]:
        week, month = in_last_days(data.glucose, day, 7), in_last_days(data.glucose, day, 30)
        statuses = [glucose_status(r.mg_dl, data.glucose_target) for r in week]
        return {
            "week": f"{round(mean(r.mg_dl for r in week))} mg/dL" if week else "—",
            "in_range": f"{round(100 * statuses.count('In range') / len(week))}%" if week else "—",
            "lows": str(statuses.count("Low")) if week else "—",
            "month": f"{round(mean(r.mg_dl for r in month))} mg/dL" if month else "—",
        }

    def chart_series(self, records: list[GlucoseReading]) -> list[Series]:
        return [Series("Glucose", GLUCOSE_COLOR, [(r.when, r.mg_dl) for r in records])]

    def chart_band(self, data: HealthData) -> tuple[float, float]:
        return data.glucose_target

    def save_target(self) -> None:
        current = self.app.data.glucose_target
        try:
            low, high = int(self.low_var.get()), int(self.high_var.get())
        except ValueError:
            low, high = current
        if (low, high) == current:
            self.low_var.set(str(current[0]))
            self.high_var.set(str(current[1]))
            return
        try:
            self.app.store.set_glucose_target(low, high)
        except ValueError as exc:  # e.g. halfway through changing both ends: keep what's typed
            self.app.set_status(f"Target range not saved: {exc}")
            return
        except OSError as exc:
            messagebox.showerror("Target range", str(exc), parent=self)
            return
        self.app.set_status(f"Glucose target range set to {low}–{high} mg/dL")
        self.app.refresh()
