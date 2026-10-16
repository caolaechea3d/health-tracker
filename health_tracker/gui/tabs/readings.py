"""Shared layout for tabs that log readings taken at a time of day (blood pressure, glucose).

Left: a form for a new reading, a few stats, and every reading (newest first, the selected day
highlighted). Right: a chart of the last 90 days, plus anything a tab adds below it.
"""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk

from ...storage import HealthData
from ..chart import LineChart, Series
from ..widgets import day_name, short_day
from .base import Tab

CHART_DAYS = 90


class ReadingsTab(Tab):
    title_text = ""  # e.g. "Blood pressure"
    unit = ""  # shown on the chart
    columns: tuple[tuple[str, str, int, str], ...] = ()  # (id, heading, width, anchor) after Day and Time
    stats: tuple[tuple[str, str], ...] = ()  # (key, title) of the numbers above the table

    def build(self) -> None:
        self.columnconfigure(0, weight=2)
        self.columnconfigure(1, weight=3)
        self.rowconfigure(5, weight=1)
        self.day: date | None = None
        self.readings: dict[str, date] = {}  # id -> date of every reading in the table

        self.title_var = tk.StringVar()
        ttk.Label(self, textvariable=self.title_var, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        values = ttk.Frame(self)
        values.grid(row=1, column=0, sticky="w", pady=(8, 4))
        self.first_field = self.build_form(values)
        details = ttk.Frame(self)
        details.grid(row=2, column=0, sticky="w")
        ttk.Label(details, text="at").pack(side="left")
        self.time_var = tk.StringVar()
        ttk.Entry(details, textvariable=self.time_var, width=7).pack(side="left", padx=(4, 12))
        ttk.Label(details, text="Notes").pack(side="left")
        self.notes_var = tk.StringVar()
        ttk.Entry(details, textvariable=self.notes_var, width=22).pack(side="left", padx=(4, 12))
        self.save_button = ttk.Button(details, text="Save reading", command=self.save, style="Accent.TButton")
        self.save_button.pack(side="left")
        for frame in (values, details):
            for child in frame.winfo_children():
                if isinstance(child, ttk.Entry):
                    child.bind("<Return>", lambda _e: self.save())
        self.hint_var = tk.StringVar()
        ttk.Label(self, textvariable=self.hint_var, style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(4, 0))

        stats = ttk.Frame(self)
        stats.grid(row=4, column=0, sticky="w", pady=(12, 10))
        self.stat_vars = {}
        for i, (key, title) in enumerate(self.stats):
            box = ttk.Frame(stats, padding=(0 if i == 0 else 18, 0, 0, 0))
            box.grid(row=0, column=i, sticky="w")
            ttk.Label(box, text=title, style="CardTitle.TLabel").pack(anchor="w")
            var = tk.StringVar()
            ttk.Label(box, textvariable=var, style="Bold.TLabel").pack(anchor="w")
            self.stat_vars[key] = var

        table = ttk.Frame(self)
        table.grid(row=5, column=0, sticky="nsew", padx=(0, 16))
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        columns = (("day", "Day", 95, "w"), ("time", "Time", 50, "w"), *self.columns)
        self.tree = ttk.Treeview(table, columns=[c[0] for c in columns], show="headings", selectmode="extended")
        for col, text, width, anchor in columns:
            self.tree.heading(col, text=text, anchor=anchor)
            self.tree.column(col, width=width, anchor=anchor, stretch=col == "notes")
        self.tree.tag_configure("selected_day", background="#e6f4f1")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", self._open_row)
        self.tree.bind("<Delete>", lambda _e: self.remove())
        below = ttk.Frame(table)
        below.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(below, text="Delete selected", command=self.remove).pack(side="left")
        ttk.Label(below, text="Double-click a row to open that day.", style="Muted.TLabel").pack(side="left", padx=(10, 0))

        right = ttk.Frame(self)
        right.grid(row=0, column=1, rowspan=6, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self.chart = LineChart(right, unit=self.unit, scale=self.icons.scale, decimals=0)
        self.chart.grid(row=0, column=0, sticky="nsew")
        side = ttk.Frame(right)
        side.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.build_side(side)

    # ---------- for subclasses ----------

    def build_form(self, frame: ttk.Frame) -> ttk.Entry:
        """Add the value fields to `frame`; return the one to focus after saving."""
        raise NotImplementedError

    def build_side(self, frame: ttk.Frame) -> None:
        """Anything to show under the chart."""

    def records(self, data: HealthData) -> list:
        raise NotImplementedError

    def row(self, record, data: HealthData) -> tuple[tuple, tuple[str, ...]]:
        """(values for self.columns, tags) of one reading in the table."""
        raise NotImplementedError

    def save_reading(self, day: date, time: str, notes: str) -> str:
        """Save a reading from the form; return the status-bar message. Raises ValueError for bad input."""
        raise NotImplementedError

    def delete_reading(self, reading_id: str) -> None:
        raise NotImplementedError

    def clear_form(self) -> None:
        raise NotImplementedError

    def stat_values(self, data: HealthData, day: date) -> dict[str, str]:
        raise NotImplementedError

    def chart_series(self, records: list) -> list[Series]:
        raise NotImplementedError

    def chart_band(self, data: HealthData) -> tuple[float, float] | None:
        return None

    # ---------- drawing ----------

    def redraw(self, data: HealthData, day: date) -> None:
        if day != self.day:  # a different day: suggest the current time again
            self.time_var.set(datetime.now().strftime("%H:%M"))
        self.day = day
        records = self.records(data)
        on_day = [r for r in records if r.date == day]
        self.title_var.set(f"{self.title_text} on {day_name(day)}")
        if day > date.today():
            self.hint_var.set("This day hasn't come yet.")
        elif on_day:
            self.hint_var.set(f"{len(on_day)} reading{'s' * (len(on_day) != 1)} on this day (highlighted below).")
        else:
            self.hint_var.set("No readings on this day yet.")
        self.save_button.state(["disabled"] if day > date.today() else ["!disabled"])
        for key, text in self.stat_values(data, day).items():
            self.stat_vars[key].set(text)

        self.tree.delete(*self.tree.get_children())
        self.readings = {}
        for record in reversed(records):  # newest first
            values, tags = self.row(record, data)
            tags = (("selected_day",) if record.date == day else ()) + tags
            self.tree.insert("", "end", iid=record.id, values=(short_day(record.date), record.time, *values), tags=tags)
            self.readings[record.id] = record.date
        first_on_day = next((r for r in reversed(records) if r.date == day), None)
        if first_on_day:
            self.tree.see(first_on_day.id)

        end = max(day, records[-1].date) if records else day
        shown = [r for r in records if end - timedelta(days=CHART_DAYS) <= r.date <= end]
        self.chart.set_series(self.chart_series(shown), f"{self.title_text} · last {CHART_DAYS} days", highlight=day,
                              band=self.chart_band(data),
                              empty_text="Save readings on at least two occasions to see a chart here.")

    # ---------- actions ----------

    def save(self) -> None:
        try:
            message = self.save_reading(self.app.day, self.time_var.get(), self.notes_var.get())
        except (ValueError, OSError) as exc:
            messagebox.showerror(self.title_text, str(exc), parent=self)
            return
        self.clear_form()
        self.notes_var.set("")
        self.time_var.set(datetime.now().strftime("%H:%M"))
        self.app.set_status(message)
        self.app.refresh()
        self.first_field.focus_set()

    def remove(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(self.title_text, "Select the readings to delete first.", parent=self)
            return
        what = "this reading" if len(selected) == 1 else f"these {len(selected)} readings"
        if not messagebox.askyesno(self.title_text, f"Delete {what}?", parent=self):
            return
        try:
            for reading_id in selected:
                self.delete_reading(reading_id)
        except OSError as exc:
            messagebox.showerror(self.title_text, str(exc), parent=self)
        else:
            self.app.set_status(f"Deleted {len(selected)} {self.title_text.lower()} reading{'s' * (len(selected) != 1)}")
        self.app.refresh()

    def _open_row(self, _event: tk.Event) -> None:
        sel = self.tree.selection()
        if sel and sel[0] in self.readings:
            self.app.go_to(self.readings[sel[0]])
