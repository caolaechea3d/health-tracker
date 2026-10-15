"""Water tab: each time you drank water on the selected day, the daily goal, and the last two weeks."""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox, ttk

from ...storage import MAX_WATER_GOAL, HealthData
from ..widgets import day_name
from .base import WATER_COLOR, Tab

HISTORY_DAYS = 14


class WaterTab(Tab):
    label = "Water"
    tab_icon = "💧"
    tab_color = WATER_COLOR

    def build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(5, weight=1)
        self.day: date | None = None

        # Left: the selected day
        self.title_var = tk.StringVar()
        ttk.Label(self, textvariable=self.title_var, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        count_row = ttk.Frame(self)
        count_row.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.count_var = tk.StringVar()
        self.count_label = ttk.Label(count_row, textvariable=self.count_var, style="Big.TLabel")
        self.count_label.pack(side="left")
        self.goal_var = tk.StringVar()
        ttk.Label(count_row, textvariable=self.goal_var, style="Muted.TLabel").pack(side="left", padx=(8, 0), pady=(8, 0))
        self.progress = ttk.Progressbar(self, length=320, mode="determinate")
        self.progress.grid(row=2, column=0, sticky="w", pady=(4, 2))
        self.hint_var = tk.StringVar()
        ttk.Label(self, textvariable=self.hint_var, style="Muted.TLabel").grid(row=3, column=0, sticky="w")

        add_row = ttk.Frame(self)
        add_row.grid(row=4, column=0, sticky="w", pady=(12, 8))
        self.add_button = ttk.Button(add_row, command=self.add, style="Accent.TButton",
                                     **self.with_icon("💧", "I drank water", WATER_COLOR))
        self.add_button.pack(side="left")
        ttk.Label(add_row, text="at").pack(side="left", padx=(10, 4))
        self.time_var = tk.StringVar()
        self.time_entry = ttk.Entry(add_row, textvariable=self.time_var, width=7)
        self.time_entry.pack(side="left")
        self.time_entry.bind("<Return>", lambda _e: self.add())
        ttk.Label(add_row, text="(HH:MM)", style="Muted.TLabel").pack(side="left", padx=(4, 0))

        drinks = ttk.Frame(self)
        drinks.grid(row=5, column=0, sticky="nsew", padx=(0, 16))
        drinks.rowconfigure(0, weight=1)
        self.drinks = ttk.Treeview(drinks, columns=("n", "time"), show="headings", selectmode="extended", height=8)
        self.drinks.heading("n", text="#", anchor="w")
        self.drinks.heading("time", text="Time", anchor="w")
        self.drinks.column("n", width=50, anchor="w", stretch=False)
        self.drinks.column("time", width=160, anchor="w")
        self.drinks.grid(row=0, column=0, sticky="ns")
        scroll = ttk.Scrollbar(drinks, orient="vertical", command=self.drinks.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.drinks.configure(yscrollcommand=scroll.set)
        self.drinks.bind("<Delete>", lambda _e: self.remove())
        ttk.Button(drinks, text="Remove selected", command=self.remove).grid(row=1, column=0, sticky="w", pady=(8, 0))

        # Right: daily goal and the last two weeks
        ttk.Label(self, text=f"Last {HISTORY_DAYS} days", style="Title.TLabel").grid(row=0, column=1, sticky="w")
        goal_row = ttk.Frame(self)
        goal_row.grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Label(goal_row, text="Daily goal").pack(side="left")
        self.goal_spin_var = tk.StringVar()
        spin = ttk.Spinbox(goal_row, from_=1, to=MAX_WATER_GOAL, width=4, textvariable=self.goal_spin_var,
                           command=self.save_goal)
        spin.pack(side="left", padx=(8, 4))
        spin.bind("<Return>", lambda _e: self.save_goal())
        spin.bind("<FocusOut>", lambda _e: self.save_goal())
        ttk.Label(goal_row, text="times a day").pack(side="left")
        history = ttk.Frame(self)
        history.grid(row=2, column=1, rowspan=4, sticky="nsew", pady=(10, 0))
        history.rowconfigure(0, weight=1)
        self.history = ttk.Treeview(history, columns=("day", "times", "goal"), show="headings",
                                    selectmode="browse", height=HISTORY_DAYS)
        for col, text, width in (("day", "Day", 220), ("times", "Times", 70), ("goal", "Goal", 110)):
            self.history.heading(col, text=text, anchor="w")
            self.history.column(col, width=width, anchor="w")
        self.history.tag_configure("selected_day", background="#e6f4f1")
        self.history.tag_configure("met", foreground="#2f855a")
        self.history.grid(row=0, column=0, sticky="ns")
        self.history.bind("<Double-1>", self._history_open)
        ttk.Label(history, text="Double-click a day to open it.", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 0))

    # ---------- drawing ----------

    def redraw(self, data: HealthData, day: date) -> None:
        if day != self.day:  # a different day: suggest the current time again
            self.time_var.set(datetime.now().strftime("%H:%M"))
        self.day = day
        entries = data.water_on(day)
        goal = data.water_goal
        count = len(entries)
        self.title_var.set(f"Water on {day_name(day)}")
        self.count_var.set(str(count))
        self.goal_var.set(f"of {goal} time{'s' * (goal != 1)}")
        self.count_label.configure(style="Good.Big.TLabel" if count >= goal else "Big.TLabel")
        self.progress.configure(maximum=goal, value=min(count, goal))
        if day > date.today():
            self.hint_var.set("This day hasn't come yet.")
        elif count >= goal:
            self.hint_var.set("Daily goal reached ✓")
        else:
            left = goal - count
            self.hint_var.set(f"{left} more time{'s' * (left != 1)} to reach your goal.")
        self.add_button.state(["disabled"] if day > date.today() else ["!disabled"])

        self.drinks.delete(*self.drinks.get_children())
        for n, entry in enumerate(entries, start=1):
            self.drinks.insert("", "end", iid=entry.id, values=(n, entry.time))
        self.goal_spin_var.set(str(goal))

        self.history.delete(*self.history.get_children())
        last = max(day, date.today())
        for d, times in data.water_by_day(last, HISTORY_DAYS):
            met = "✓ reached" if times >= goal else ""
            tags = (("selected_day",) if d == day else ()) + (("met",) if times >= goal else ())
            self.history.insert("", "end", iid=d.isoformat(), values=(day_name(d), times, met), tags=tags)

    # ---------- actions ----------

    def add(self) -> None:
        try:
            entry = self.app.store.add_water(self.app.day, self.time_var.get())
        except (ValueError, OSError) as exc:
            messagebox.showerror("Water", str(exc), parent=self)
            return
        self.app.set_status(f"Logged water at {entry.time} on {entry.date.isoformat()}")
        self.time_var.set(datetime.now().strftime("%H:%M"))
        self.app.refresh()

    def remove(self) -> None:
        selected = self.drinks.selection()
        if not selected:
            messagebox.showinfo("Water", "Select the time(s) to remove first.", parent=self)
            return
        try:
            for entry_id in selected:
                self.app.store.delete_water(entry_id)
        except OSError as exc:
            messagebox.showerror("Water", str(exc), parent=self)
        else:
            self.app.set_status(f"Removed {len(selected)} water entr{'ies' if len(selected) != 1 else 'y'}")
        self.app.refresh()

    def save_goal(self) -> None:
        current = self.app.data.water_goal
        try:
            goal = int(self.goal_spin_var.get())
        except ValueError:
            goal = 0
        if not 1 <= goal <= MAX_WATER_GOAL:
            self.goal_spin_var.set(str(current))
            self.app.set_status(f"The daily water goal must be a whole number from 1 to {MAX_WATER_GOAL}.")
            return
        if goal == current:
            return
        try:
            self.app.store.set_water_goal(goal)
        except OSError as exc:
            messagebox.showerror("Water goal", str(exc), parent=self)
            return
        self.app.set_status(f"Daily water goal set to {goal} time{'s' * (goal != 1)}")
        self.app.refresh()

    def _history_open(self, _event: tk.Event) -> None:
        sel = self.history.selection()
        if sel:
            self.app.go_to(date.fromisoformat(sel[0]))
