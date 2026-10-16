"""Blood pressure tab: readings (systolic/diastolic and pulse) with their category, averages and a chart."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from statistics import mean
from tkinter import ttk

from ...storage import BloodPressure, HealthData, in_last_days
from ..chart import Series
from ..widgets import wrapping_label
from .base import BLOOD_PRESSURE_COLOR
from .readings import ReadingsTab

DIASTOLIC_COLOR = "#577590"
# Text color of each category in the table (normal readings keep the usual color).
CATEGORY_COLORS = {
    "Low": "#277da1",
    "Elevated": "#a16207",
    "High, stage 1": "#c2410c",
    "High, stage 2": "#c0392b",
    "Hypertensive crisis": "#8b0000",
}


def average_text(readings: list[BloodPressure]) -> str:
    if not readings:
        return "—"
    return f"{round(mean(r.systolic for r in readings))}/{round(mean(r.diastolic for r in readings))}"


class BloodPressureTab(ReadingsTab):
    label = "Blood pressure"
    tab_icon = "❤"
    tab_color = BLOOD_PRESSURE_COLOR
    title_text = "Blood pressure"
    unit = "mmHg"
    columns = (("reading", "Reading", 70, "e"), ("pulse", "Pulse", 50, "e"), ("category", "Category", 120, "w"),
               ("notes", "Notes", 120, "w"))
    stats = (("week", "7-day average"), ("month", "30-day average"), ("count", "Readings in 30 days"),
             ("pulse", "Pulse, 7 days"))

    def build_form(self, frame: ttk.Frame) -> ttk.Entry:
        self.systolic_var, self.diastolic_var, self.pulse_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        big = ("Segoe UI", 12)
        systolic = ttk.Entry(frame, textvariable=self.systolic_var, width=5, font=big)
        systolic.pack(side="left")
        ttk.Label(frame, text="/", font=big).pack(side="left", padx=3)
        ttk.Entry(frame, textvariable=self.diastolic_var, width=5, font=big).pack(side="left")
        ttk.Label(frame, text="mmHg").pack(side="left", padx=(4, 16))
        ttk.Label(frame, text="Pulse").pack(side="left")
        ttk.Entry(frame, textvariable=self.pulse_var, width=5, font=big).pack(side="left", padx=4)
        ttk.Label(frame, text="bpm (optional)", style="Muted.TLabel").pack(side="left")
        return systolic

    def build_side(self, frame: ttk.Frame) -> None:
        wrapping_label(frame, "Categories follow the American Heart Association guide: normal is below 120/80, "
                              "high from 130/80. They're for reference only — the targets your doctor gives you "
                              "come first.").pack(fill="x")
        for name, color in CATEGORY_COLORS.items():
            self.tree.tag_configure(name, foreground=color)

    def records(self, data: HealthData) -> list[BloodPressure]:
        return data.blood_pressure

    def row(self, record: BloodPressure, data: HealthData) -> tuple[tuple, tuple[str, ...]]:
        return (record.text, record.pulse or "", record.category, record.notes), (record.category,)

    def save_reading(self, day: date, time: str, notes: str) -> str:
        reading = BloodPressure(day, time, self.systolic_var.get(), self.diastolic_var.get(), self.pulse_var.get(),
                                notes)
        self.app.store.add_blood_pressure(reading)
        return f"Saved blood pressure {reading.text} ({reading.category}) at {reading.time} on {day.isoformat()}"

    def delete_reading(self, reading_id: str) -> None:
        self.app.store.delete_blood_pressure(reading_id)

    def clear_form(self) -> None:
        for var in (self.systolic_var, self.diastolic_var, self.pulse_var):
            var.set("")

    def stat_values(self, data: HealthData, day: date) -> dict[str, str]:
        week, month = in_last_days(data.blood_pressure, day, 7), in_last_days(data.blood_pressure, day, 30)
        pulses = [r.pulse for r in week if r.pulse]
        return {
            "week": average_text(week),
            "month": average_text(month),
            "count": str(len(month)),
            "pulse": f"{round(mean(pulses))} bpm" if pulses else "—",
        }

    def chart_series(self, records: list[BloodPressure]) -> list[Series]:
        return [Series("Systolic", BLOOD_PRESSURE_COLOR, [(r.when, r.systolic) for r in records]),
                Series("Diastolic", DIASTOLIC_COLOR, [(r.when, r.diastolic) for r in records])]
