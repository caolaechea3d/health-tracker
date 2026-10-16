"""Weight tab: enter the weight of the selected day, see every entry with its change, and a chart."""

from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from tkinter import messagebox, ttk

from ...storage import HealthData, WeightEntry, format_change, format_weight
from ..chart import LineChart, Series
from ..widgets import day_name
from .base import WEIGHT_COLOR, Tab

CHART_DAYS = 90


def change_over(weights: list[WeightEntry], until: date, days: int) -> tuple[WeightEntry, WeightEntry] | None:
    """(older, newer) entries to compare: the latest up to `until` and the latest `days` days before it."""
    upto = [w for w in weights if w.date <= until]
    if not upto:
        return None
    newer = upto[-1]
    older = [w for w in upto if w.date <= newer.date - timedelta(days=days)]
    return (older[-1], newer) if older else None


class WeightTab(Tab):
    label = "Weight"
    tab_icon = "⚖"
    tab_color = WEIGHT_COLOR

    def build(self) -> None:
        self.columnconfigure(0, weight=2)
        self.columnconfigure(1, weight=3)
        self.rowconfigure(4, weight=1)
        self.day: date | None = None
        self.entry_today: WeightEntry | None = None

        self.title_var = tk.StringVar()
        ttk.Label(self, textvariable=self.title_var, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        form = ttk.Frame(self)
        form.grid(row=1, column=0, sticky="w", pady=(8, 2))
        self.weight_var = tk.StringVar()
        self.weight_entry = ttk.Entry(form, textvariable=self.weight_var, width=8, font=("Segoe UI", 12))
        self.weight_entry.pack(side="left")
        self.weight_entry.bind("<Return>", lambda _e: self.save())
        ttk.Label(form, text="kg").pack(side="left", padx=(4, 10))
        self.save_button = ttk.Button(form, text="Save", command=self.save, style="Accent.TButton")
        self.save_button.pack(side="left")
        self.delete_button = ttk.Button(form, text="Delete", command=self.delete_day)
        self.delete_button.pack(side="left", padx=(6, 0))
        self.hint_var = tk.StringVar()
        ttk.Label(self, textvariable=self.hint_var, style="Muted.TLabel").grid(row=2, column=0, sticky="w")

        stats = ttk.Frame(self)
        stats.grid(row=3, column=0, sticky="w", pady=(14, 10))
        self.stat_vars = {}
        for i, (key, title) in enumerate((("latest", "Latest"), ("week", "Last 7 days"),
                                          ("month", "Last 30 days"), ("total", "Since first entry"))):
            box = ttk.Frame(stats, padding=(0 if i == 0 else 18, 0, 0, 0))
            box.grid(row=0, column=i, sticky="w")
            ttk.Label(box, text=title, style="CardTitle.TLabel").pack(anchor="w")
            var = tk.StringVar()
            ttk.Label(box, textvariable=var, style="Bold.TLabel").pack(anchor="w")
            self.stat_vars[key] = var

        table = ttk.Frame(self)
        table.grid(row=4, column=0, sticky="nsew", padx=(0, 16))
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("day", "weight", "change"), show="headings", selectmode="extended")
        for col, text, width, anchor in (("day", "Day", 200, "w"), ("weight", "Weight", 90, "e"),
                                         ("change", "Change", 90, "e")):
            self.tree.heading(col, text=text, anchor=anchor)
            self.tree.column(col, width=width, anchor=anchor)
        self.tree.tag_configure("selected_day", background="#e6f4f1")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", self._open_row)
        self.tree.bind("<Delete>", lambda _e: self.delete_selected())
        below = ttk.Frame(table)
        below.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(below, text="Delete selected", command=self.delete_selected).pack(side="left")
        ttk.Label(below, text="Double-click a row to open that day.", style="Muted.TLabel").pack(side="left", padx=(10, 0))

        self.chart = LineChart(self, unit="kg", scale=self.icons.scale)
        self.chart.grid(row=0, column=1, rowspan=5, sticky="nsew")

    # ---------- drawing ----------

    def redraw(self, data: HealthData, day: date) -> None:
        weights = data.weights
        self.entry_today = data.weight_on(day)
        if day != self.day or self.entry_today is not None:  # keep a half-typed value while on the same day
            self.weight_var.set(f"{self.entry_today.kg:.1f}" if self.entry_today else "")
        self.day = day
        future = day > date.today()
        self.title_var.set(f"Weight on {day_name(day)}")
        before = data.weight_before(day)
        if future:
            self.hint_var.set("This day hasn't come yet.")
        elif self.entry_today and before:
            self.hint_var.set(f"Saved. {format_change(self.entry_today.kg - before.kg)} since {day_name(before.date)}.")
        elif self.entry_today:
            self.hint_var.set("Saved. This is your first weight entry.")
        else:
            self.hint_var.set("No weight saved for this day yet." +
                              (f" Last one: {format_weight(before.kg)} on {day_name(before.date)}." if before else ""))
        self.save_button.configure(text="Update" if self.entry_today else "Save")
        self.save_button.state(["disabled"] if future else ["!disabled"])
        self.delete_button.state(["!disabled"] if self.entry_today else ["disabled"])

        latest = data.latest_weight(day)
        self.stat_vars["latest"].set(format_weight(latest.kg) if latest else "—")
        for key, days in (("week", 7), ("month", 30)):
            pair = change_over(weights, day, days)
            self.stat_vars[key].set(format_change(pair[1].kg - pair[0].kg) if pair else "—")
        first = weights[0] if weights else None
        self.stat_vars["total"].set(format_change(latest.kg - first.kg) if latest and first and latest != first else "—")

        self.tree.delete(*self.tree.get_children())
        previous: WeightEntry | None = None
        rows = []
        for entry in weights:
            delta = entry.kg - previous.kg if previous else None
            rows.append((entry, delta, ("selected_day",) if entry.date == day else ()))
            previous = entry
        for entry, delta, tags in reversed(rows):  # newest first
            self.tree.insert("", "end", iid=entry.date.isoformat(), tags=tags,
                             values=(day_name(entry.date), format_weight(entry.kg), format_change(delta)))

        end = max(day, weights[-1].date) if weights else day
        shown = [(w.date, float(w.kg)) for w in weights if end - timedelta(days=CHART_DAYS) <= w.date <= end]
        self.chart.set_series([Series("Weight", WEIGHT_COLOR, shown)], f"Weight · last {CHART_DAYS} days",
                              highlight=day, empty_text="Save your weight on at least two days to see a chart here.")

    # ---------- actions ----------

    def save(self) -> None:
        try:
            entry = self.app.store.set_weight(self.app.day, self.weight_var.get())
        except (ValueError, OSError) as exc:
            messagebox.showerror("Weight", str(exc), parent=self)
            return
        self.app.set_status(f"Saved weight {format_weight(entry.kg)} for {entry.date.isoformat()}")
        self.app.refresh()

    def delete_day(self) -> None:
        if self.entry_today:
            self._delete([self.entry_today.date])

    def delete_selected(self) -> None:
        selected = [date.fromisoformat(iid) for iid in self.tree.selection()]
        if not selected:
            messagebox.showinfo("Weight", "Select the entries to delete first.", parent=self)
            return
        self._delete(selected)

    def _delete(self, days: list[date]) -> None:
        what = day_name(days[0]) if len(days) == 1 else f"{len(days)} days"
        if not messagebox.askyesno("Delete weight", f"Delete the weight of {what}?", parent=self):
            return
        try:
            for d in days:
                self.app.store.delete_weight(d)
        except OSError as exc:
            messagebox.showerror("Weight", str(exc), parent=self)
        else:
            self.app.set_status(f"Deleted the weight of {what}")
        self.weight_var.set("")
        self.app.refresh()

    def _open_row(self, _event: tk.Event) -> None:
        sel = self.tree.selection()
        if sel:
            self.app.go_to(date.fromisoformat(sel[0]))
