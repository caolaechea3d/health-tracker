"""Main page of a user: header (user, selected day, the day's numbers), menu and the tabs.

Each tab lives in its own module under `gui/tabs/`. This page owns what they share: the selected
day, the file actions, and `refresh()`, which loads the data once and asks every tab to redraw.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

from .. import APP_NAME
from ..storage import HealthData, HealthStore, format_change, format_weight
from ..users import User
from .icons import Icons
from .tabs import MedicationsTab, WaterTab, WeightTab
from .widgets import DateField, day_name, relative_day, setup_style


def open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - opens Explorer on our own data folder
    else:
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(path)], check=False)


class HealthApp(ttk.Frame):
    def __init__(
        self,
        master: tk.Tk,
        store: HealthStore,
        icons: Icons | None = None,
        user: User | None = None,
        on_switch_user: Callable[[], None] | None = None,
    ):
        super().__init__(master)
        self.store = store
        self.icons = icons or Icons(master)
        self.user = user
        self.on_switch_user = on_switch_user
        master.title(f"{APP_NAME} — {user.name}" if user else APP_NAME)
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        setup_style(self, self.icons)

        self.day = date.today()
        self.data = HealthData([], [], [], {})
        self.day_var = tk.StringVar(value=self.day.isoformat())
        self.day_var.trace_add("write", lambda *_: self._day_typed())
        self.status_var = tk.StringVar(value=f"Data file: {store.path}")

        self._build_menu(master)
        self._build_header()
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 4))
        self.medications_tab = MedicationsTab(self)
        self.water_tab = WaterTab(self)
        self.weight_tab = WeightTab(self)
        self.tabs = [self.medications_tab, self.water_tab, self.weight_tab]
        ttk.Label(self, textvariable=self.status_var, style="Muted.TLabel").grid(
            row=2, column=0, sticky="w", padx=12, pady=(0, 6))
        self.refresh()
        self.after(400, self.remind_doses)

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    # ---------- menu & header ----------

    def _build_menu(self, master: tk.Tk) -> None:
        menubar = tk.Menu(master)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Back up now", command=self.backup_now)
        file_menu.add_command(label="Open data folder", command=self.open_data_folder)
        file_menu.add_separator()
        if self.on_switch_user:
            file_menu.add_command(label="Switch user…", command=self.on_switch_user)
        file_menu.add_command(label="Exit", command=master.destroy)
        menubar.add_cascade(label="File", menu=file_menu)
        go_menu = tk.Menu(menubar, tearoff=False)
        go_menu.add_command(label="Previous day", accelerator="Alt+Left", command=lambda: self.shift_day(-1))
        go_menu.add_command(label="Next day", accelerator="Alt+Right", command=lambda: self.shift_day(1))
        go_menu.add_command(label="Today", accelerator="Alt+Home", command=lambda: self.go_to(date.today()))
        menubar.add_cascade(label="Go", menu=go_menu)
        master.configure(menu=menubar)
        master.bind("<Alt-Left>", lambda _e: self.shift_day(-1))
        master.bind("<Alt-Right>", lambda _e: self.shift_day(1))
        master.bind("<Alt-Home>", lambda _e: self.go_to(date.today()))

    def _build_header(self) -> None:
        header = ttk.Frame(self, padding=(10, 10, 10, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        # Row 0: who is using the app
        badge = ttk.Frame(header)
        badge.grid(row=0, column=0, sticky="w", pady=(0, 10))
        if self.user:
            image = self.icons.get(self.user.icon, self.user.color, size=round(self.icons.size * 1.9))
            ttk.Label(badge, image=image or "", text="" if image else self.user.icon,
                      font=("Segoe UI Emoji", 20)).grid(row=0, column=0, rowspan=2, padx=(0, 10))
            ttk.Label(badge, text=self.user.name, style="UserName.TLabel").grid(row=0, column=1, sticky="sw")
            ttk.Label(badge, text=self.user.type, style="Muted.TLabel").grid(row=1, column=1, sticky="nw")
        if self.on_switch_user:
            switch_icon = self.icons.get("🔄", "#8d99ae", badge=False)
            ttk.Button(badge, text=" Switch user", image=switch_icon or "", compound="left", style="Link.TButton",
                       command=self.on_switch_user).grid(row=0, column=2, rowspan=2, padx=(16, 0))

        # Row 1: the selected day
        nav = ttk.Frame(header)
        nav.grid(row=1, column=0, columnspan=2, sticky="w")
        ttk.Button(nav, text="◀", width=3, command=lambda: self.shift_day(-1)).pack(side="left")
        DateField(nav, self.day_var, icons=self.icons).pack(side="left", padx=4)
        ttk.Button(nav, text="▶", width=3, command=lambda: self.shift_day(1)).pack(side="left")
        self.today_button = ttk.Button(nav, text="Today", command=lambda: self.go_to(date.today()))
        self.today_button.pack(side="left", padx=(8, 0))
        self.day_label_var = tk.StringVar()
        ttk.Label(nav, textvariable=self.day_label_var, style="Day.TLabel").pack(side="left", padx=(14, 0))

        # Right: the selected day's numbers
        cards = ttk.Frame(header)
        cards.grid(row=0, column=2, rowspan=2, sticky="e")
        self.cards = {}
        for i, (key, title) in enumerate((("weight", "Weight"), ("water", "Water"), ("medication", "Medication"))):
            card = ttk.Frame(cards, padding=(22, 0, 0, 0))
            card.grid(row=0, column=i)
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="e")
            value, note = tk.StringVar(), tk.StringVar()
            label = ttk.Label(card, textvariable=value, style="CardValue.TLabel")
            label.pack(anchor="e")
            ttk.Label(card, textvariable=note, style="Muted.TLabel").pack(anchor="e")
            self.cards[key] = (value, note, label)

    def _set_card(self, key: str, value: str, note: str, good: bool = False) -> None:
        value_var, note_var, label = self.cards[key]
        value_var.set(value)
        note_var.set(note)
        label.configure(style="Good.CardValue.TLabel" if good else "CardValue.TLabel")

    # ---------- selected day ----------

    def go_to(self, day: date) -> None:
        self.day_var.set(day.isoformat())  # the trace below picks it up

    def shift_day(self, step: int) -> None:
        self.go_to(self.day + timedelta(days=step))

    def _day_typed(self) -> None:
        try:
            day = date.fromisoformat(self.day_var.get().strip())
        except ValueError:
            return  # still typing
        if day != self.day:
            self.day = day
            self.refresh()

    # ---------- reminders & file actions ----------

    def remind_doses(self) -> None:
        """On opening: a status-bar note when today's doses are due but not ticked yet."""
        if not self.winfo_exists():  # the user switched away before this delayed check ran
            return
        now = datetime.now().strftime("%H:%M")
        missed = [d for d in self.data.doses_on(date.today()) if not d.taken and d.time <= now]
        if missed:
            self.set_status(f"⚠ {len(missed)} dose{'s' * (len(missed) != 1)} due earlier today "
                            f"{'are' if len(missed) != 1 else 'is'} not ticked yet — see the Medications tab.")

    def backup_now(self) -> None:
        try:
            path = self.store.backup_now()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Backup", str(exc))
            return
        self.set_status(f"Backup saved: {path}")

    def open_data_folder(self) -> None:
        folder = self.store.path.parent
        folder.mkdir(parents=True, exist_ok=True)
        open_folder(folder)

    # ---------- refresh everything ----------

    def refresh(self) -> None:
        """Load the data once, update the header, and ask every tab to redraw."""
        try:
            self.data = self.store.load()
        except (ValueError, KeyError, OSError) as exc:
            messagebox.showerror("Could not read data file", f"{self.store.path}\n\n{exc}")
            return
        day = self.day
        self.day_label_var.set(f"{day_name(day)} · {relative_day(day)}")
        self.today_button.state(["disabled"] if day == date.today() else ["!disabled"])

        s = self.data.summary(day)
        if s.weight is not None:
            self._set_card("weight", format_weight(s.weight),
                           f"{format_change(s.weight_change)} vs last entry" if s.weight_change is not None else "first entry")
        else:
            self._set_card("weight", "—", "not entered")
        self._set_card("water", f"{s.water} / {s.water_goal}", "times", good=s.water >= s.water_goal)
        if s.doses_due:
            self._set_card("medication", f"{s.doses_taken} / {s.doses_due}", "doses taken",
                           good=s.doses_taken == s.doses_due)
        else:
            self._set_card("medication", "—", "nothing to take")

        for tab in self.tabs:
            tab.redraw(self.data, day)
