"""Medications tab: the day's doses as a checklist, plus the list of medications and their schedule."""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk

from ...storage import WEEKDAYS, Dose, HealthData, Medication, format_weekdays, parse_date, parse_times
from ..widgets import DateField, Dialog, ScrollableFrame, day_name, labeled
from .base import MEDICATION_COLOR, Tab


def short_date(day: date, today: date) -> str:
    """'15 Oct', or '15 Oct 2025' when it isn't this year."""
    return f"{day.day} {day:%b}" + ("" if day.year == today.year else f" {day.year}")


def period_text(med: Medication, today: date) -> str:
    """'since 15 Sep', '13 Oct – 19 Oct', 'starts 20 Oct', 'ended 30 Sep'."""
    if med.end is not None and med.end < today:
        return f"ended {short_date(med.end, today)}"
    start = short_date(med.start, today)
    if med.end is not None:
        return f"{start} – {short_date(med.end, today)}"
    return f"starts {start}" if med.start > today else f"since {start}"


class MedicationsTab(Tab):
    label = "Medications"
    tab_icon = "💊"
    tab_color = MEDICATION_COLOR

    def build(self) -> None:
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(2, weight=1)
        self.medications: list[Medication] = []
        self._checks: list[tk.BooleanVar] = []  # keep the checkbuttons' variables alive

        # Left: the checklist of the selected day
        self.title_var = tk.StringVar()
        self.hint_var = tk.StringVar()
        ttk.Label(self, textvariable=self.title_var, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.hint = ttk.Label(self, textvariable=self.hint_var, style="Muted.TLabel")
        self.hint.grid(row=1, column=0, sticky="w", pady=(2, 8))
        self.checklist = ScrollableFrame(self)
        self.checklist.grid(row=2, column=0, sticky="nsew", padx=(0, 16))
        self.checklist.inner.columnconfigure(1, weight=1)

        # Right: every medication and its schedule
        ttk.Label(self, text="Your medications", style="Title.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(self, text="What you're supposed to take, and when.", style="Muted.TLabel").grid(
            row=1, column=1, sticky="w", pady=(2, 8))
        right = ttk.Frame(self)
        right.grid(row=2, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(right, columns=("dose", "times", "days", "period"), selectmode="browse")
        for col, text, width in (("#0", "Medication", 150), ("dose", "Dose", 80), ("times", "Times", 130),
                                 ("days", "Days", 110), ("period", "Period", 130)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=width, anchor="w", stretch=col in ("#0", "period"))
        self.tree.tag_configure("ended", foreground="#9ca3af")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(right, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", lambda _e: self.edit())
        buttons = ttk.Frame(right)
        buttons.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(buttons, command=self.add, style="Accent.TButton",
                   **self.with_icon("➕", "Add medication…")).pack(side="left")
        ttk.Button(buttons, text="Edit…", command=self.edit).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Delete", command=self.delete).pack(side="left", padx=(6, 0))

    # ---------- drawing ----------

    def redraw(self, data: HealthData, day: date) -> None:
        self.medications = data.medications
        self._draw_checklist(data.doses_on(day), day)
        self._draw_list()

    def _draw_checklist(self, doses: list[Dose], day: date) -> None:
        inner = self.checklist.inner
        for child in inner.winfo_children():
            child.destroy()
        self._checks = []
        today = date.today()
        future = day > today
        self.title_var.set(f"To take on {day_name(day)}")
        taken = sum(d.taken for d in doses)
        if not self.medications:
            self.hint_var.set("No medications yet — add one with “Add medication…”.")
        elif not doses:
            self.hint_var.set("Nothing to take on this day.")
        elif future:
            self.hint_var.set("This day hasn't come yet — you can tick its doses once it arrives.")
        elif taken == len(doses):
            self.hint_var.set(f"All {len(doses)} taken ✓")
        else:
            self.hint_var.set(f"{taken} of {len(doses)} taken — tick each dose once you've taken it.")
        self.hint.configure(style="Good.TLabel" if doses and taken == len(doses) else "Muted.TLabel")

        now = datetime.now().strftime("%H:%M")
        for row, dose in enumerate(doses):
            var = tk.BooleanVar(value=dose.taken)
            self._checks.append(var)
            check = ttk.Checkbutton(inner, variable=var, style="Dose.TCheckbutton",
                                    text=f"{dose.time}   {dose.medication.label}",
                                    command=lambda d=dose, v=var: self.toggle(d, v.get()))
            check.grid(row=row * 2, column=0, sticky="w", pady=(6, 0))
            if future:
                check.state(["disabled"])
            status, style = self._dose_status(dose, today, now)
            ttk.Label(inner, text=status, style=style).grid(row=row * 2, column=1, sticky="w", padx=(16, 0), pady=(6, 0))
            if dose.medication.notes:
                ttk.Label(inner, text=dose.medication.notes, style="Muted.TLabel").grid(
                    row=row * 2 + 1, column=0, columnspan=2, sticky="w", padx=(26, 0))

    @staticmethod
    def _dose_status(dose: Dose, today: date, now: str) -> tuple[str, str]:
        if dose.taken_at:
            when = dose.taken_at
            text = f"✓ taken at {when:%H:%M}" if when.date() == dose.date else f"✓ ticked on {when:%Y-%m-%d %H:%M}"
            return text, "Good.TLabel"
        if dose.date < today or (dose.date == today and dose.time <= now):
            return "not taken yet", "Warning.TLabel"
        return "", "Muted.TLabel"

    def _draw_list(self) -> None:
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        today = date.today()
        image = self.icons.get("💊", MEDICATION_COLOR)
        ended = lambda m: m.end is not None and m.end < today  # noqa: E731
        for med in sorted(self.medications, key=lambda m: (ended(m), m.name.lower())):
            name = f" {med.name}" if image else self.icons.text("💊", med.name)
            period = period_text(med, today)
            self.tree.insert("", "end", iid=med.id, text=name, image=image or "",
                             values=(med.dose, ", ".join(med.times), format_weekdays(med.weekdays), period),
                             tags=("ended",) if ended(med) else ())
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_set(iid)

    # ---------- actions ----------

    def toggle(self, dose: Dose, taken: bool) -> None:
        try:
            self.app.store.set_taken(dose.medication.id, dose.date, dose.time, taken)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Medication", str(exc), parent=self)
        else:
            verb = "Taken" if taken else "Not taken"
            self.app.set_status(f"{verb}: {dose.medication.label} at {dose.time} on {dose.date.isoformat()}")
        self.app.refresh()

    def selected(self) -> Medication | None:
        sel = self.tree.selection()
        return next((m for m in self.medications if sel and m.id == sel[0]), None)

    def add(self) -> None:
        MedicationDialog(self)

    def edit(self) -> None:
        med = self.selected()
        if med is None:
            messagebox.showinfo("Edit medication", "Select a medication in the list first.", parent=self)
            return
        MedicationDialog(self, med)

    def delete(self) -> None:
        med = self.selected()
        if med is None:
            messagebox.showinfo("Delete medication", "Select a medication in the list first.", parent=self)
            return
        if not messagebox.askyesno(
            "Delete medication",
            f"Delete “{med.label}”?\n\nThe record of the doses you ticked for it is deleted too. "
            "If you've simply finished taking it, edit it and set an end date instead — that keeps its history.",
            parent=self,
        ):
            return
        try:
            self.app.store.delete_medication(med.id)
        except OSError as exc:
            messagebox.showerror("Delete medication", str(exc), parent=self)
            return
        self.app.set_status(f"Deleted medication: {med.label}")
        self.app.refresh()


class MedicationDialog(Dialog):
    """Add or edit a medication: name, dose, times of day, weekdays, start and optional end."""

    def __init__(self, tab: MedicationsTab, medication: Medication | None = None):
        self.tab = tab
        self.app = tab.app
        self.original = medication
        super().__init__(tab, "Edit medication" if medication else "New medication",
                         ok_text="Save" if medication else "Add")
        m = medication
        today = date.today()
        self.name_var = tk.StringVar(value=m.name if m else "")
        self.dose_var = tk.StringVar(value=m.dose if m else "")
        self.times_var = tk.StringVar(value=", ".join(m.times) if m else "08:00")
        self.day_vars = [tk.BooleanVar(value=(i in m.weekdays) if m else True) for i in range(7)]
        self.start_var = tk.StringVar(value=(m.start if m else today).isoformat())
        self.has_end = tk.BooleanVar(value=bool(m and m.end))
        self.end_var = tk.StringVar(value=(m.end if m and m.end else today + timedelta(days=6)).isoformat())
        self.notes_var = tk.StringVar(value=m.notes if m else "")

        b = self.body
        b.columnconfigure(1, weight=1)
        name = labeled(b, 0, "Name", ttk.Entry(b, textvariable=self.name_var, width=32), sticky="ew")
        labeled(b, 1, "Dose", ttk.Entry(b, textvariable=self.dose_var, width=32), sticky="ew")
        ttk.Label(b, text="e.g. 500 mg, 1 pill, 10 ml", style="Muted.TLabel").grid(row=2, column=1, sticky="w")
        labeled(b, 3, "Times of day", ttk.Entry(b, textvariable=self.times_var, width=32), sticky="ew")
        ttk.Label(b, text="Separate several with commas, e.g. 08:00, 14:00, 20:00",
                  style="Muted.TLabel").grid(row=4, column=1, sticky="w")

        days = ttk.Frame(b)
        for i, (name_, var) in enumerate(zip(WEEKDAYS, self.day_vars)):
            ttk.Checkbutton(days, text=name_, variable=var).grid(row=0, column=i, padx=(0, 4))
        labeled(b, 5, "Days", days, pady=(8, 3))

        labeled(b, 6, "Start", DateField(b, self.start_var, icons=self.app.icons))
        end_row = ttk.Frame(b)
        ttk.Checkbutton(end_row, text="Until", variable=self.has_end, command=self._end_toggled).pack(side="left")
        self.end_field = DateField(end_row, self.end_var, icons=self.app.icons)
        self.end_field.pack(side="left", padx=(6, 0))
        labeled(b, 7, "End", end_row)
        ttk.Label(b, text="Leave “Until” unticked for medication without an end date.",
                  style="Muted.TLabel").grid(row=8, column=1, sticky="w")
        labeled(b, 9, "Notes", ttk.Entry(b, textvariable=self.notes_var, width=32), sticky="ew", pady=(8, 3))
        ttk.Label(b, text="Optional, e.g. with food", style="Muted.TLabel").grid(row=10, column=1, sticky="w")
        self._end_toggled()
        self.show(name)

    def _end_toggled(self) -> None:
        self.end_field.set_enabled(self.has_end.get())

    def on_ok(self) -> bool:
        try:
            medication = Medication(
                name=self.name_var.get(),
                dose=self.dose_var.get(),
                times=parse_times(self.times_var.get()),
                weekdays=[i for i, var in enumerate(self.day_vars) if var.get()],
                start=parse_date(self.start_var.get()),
                end=parse_date(self.end_var.get()) if self.has_end.get() else None,
                notes=self.notes_var.get(),
                **({"id": self.original.id} if self.original else {}),
            )
            self.app.store.save_medication(medication)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Medication", str(exc), parent=self)
            return False
        self.app.set_status(f"{'Saved' if self.original else 'Added'} medication: {medication.label}")
        self.app.refresh()
        self.tab.tree.selection_set(medication.id)
        return True
