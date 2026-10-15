"""Reusable widgets: icon dropdown, date field with calendar, modal dialog base, scrollable frame."""

from __future__ import annotations

import calendar
import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import ttk

from .icons import Icons

# (name, icon, color) for each choice in a Picker.
Option = tuple[str, str, str]

ACCENT = "#2a9d8f"
GOOD = "#2f855a"
WARNING = "#b35c00"


def day_name(day: date) -> str:
    """'Wednesday 15 October' (with the year too when it isn't this year)."""
    text = f"{calendar.day_name[day.weekday()]} {day.day} {calendar.month_name[day.month]}"
    return text if day.year == date.today().year else f"{text} {day.year}"


def relative_day(day: date) -> str:
    """'today', 'yesterday', 'tomorrow', '3 days ago', 'in 2 days'."""
    diff = (day - date.today()).days
    if diff in (-1, 0, 1):
        return ("yesterday", "today", "tomorrow")[diff + 1]
    return f"{-diff} days ago" if diff < 0 else f"in {diff} days"


class CalendarPopup(tk.Toplevel):
    """A small month calendar under a widget; calls `on_pick(date)` when a day is clicked."""

    def __init__(self, anchor: tk.Widget, selected: date, on_pick: Callable[[date], None]):
        super().__init__(anchor)
        self.anchor = anchor
        self.selected = selected
        self.on_pick = on_pick
        self.shown = (selected.year, selected.month)
        self.withdraw()
        self.overrideredirect(True)
        self.transient(anchor.winfo_toplevel())
        self.attributes("-topmost", True)  # always above the window (or dialog) it was opened from
        self.configure(bg="#d1d5db")  # 1px border around the white body
        self.body = tk.Frame(self, bg="white", padx=8, pady=8)
        self.body.pack(padx=1, pady=1)

        head = tk.Frame(self.body, bg="white")
        head.grid(row=0, column=0, columnspan=7, sticky="ew", pady=(0, 6))
        head.columnconfigure(1, weight=1)
        nav = dict(bg="white", relief="flat", bd=0, font=("Segoe UI", 11), cursor="hand2",
                   activebackground="#eef2f7", width=3)
        tk.Button(head, text="◀", command=lambda: self.move(-1), **nav).grid(row=0, column=0)
        self.title_label = tk.Label(head, bg="white", font=("Segoe UI", 10, "bold"))
        self.title_label.grid(row=0, column=1)
        tk.Button(head, text="▶", command=lambda: self.move(1), **nav).grid(row=0, column=2)

        for col, name in enumerate(calendar.day_abbr):
            tk.Label(self.body, text=name[:2], bg="white", fg="#6b7280", font=("Segoe UI", 8),
                     width=4).grid(row=1, column=col)
        self.cells: list[tk.Label] = []
        for i in range(42):
            cell = tk.Label(self.body, width=4, bg="white", font=("Segoe UI", 9), cursor="hand2", pady=3)
            cell.grid(row=2 + i // 7, column=i % 7, padx=1, pady=1)
            self.cells.append(cell)

        footer = tk.Frame(self.body, bg="white")
        footer.grid(row=8, column=0, columnspan=7, sticky="ew", pady=(6, 0))
        tk.Button(footer, text="Today", command=lambda: self.pick(date.today()), relief="flat",
                  bg="#eef2f7", activebackground="#e2e8f0", font=("Segoe UI", 9), cursor="hand2",
                  padx=10).pack(side="left")
        tk.Label(footer, text="Esc to close", bg="white", fg="#9ca3af", font=("Segoe UI", 8)).pack(side="right")

        self.draw()
        self.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 2
        if y + self.winfo_reqheight() > anchor.winfo_screenheight():
            y = anchor.winfo_rooty() - self.winfo_reqheight() - 2  # not enough room below: open above
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<MouseWheel>", lambda e: self.move(-1 if e.delta > 0 else 1))
        self.bind("<Button-1>", self._click_outside)
        self.lift()
        self.focus_force()
        self.grab_set()

    def draw(self) -> None:
        year, month = self.shown
        self.title_label.configure(text=f"{calendar.month_name[month]} {year}")
        today = date.today()
        days = list(calendar.Calendar(firstweekday=0).itermonthdates(year, month))
        days += [date.fromordinal(days[-1].toordinal() + n) for n in range(1, 42 - len(days) + 1)]
        for cell, day in zip(self.cells, days):
            bg, fg, font = "white", "#111827", ("Segoe UI", 9)
            if day.month != month:
                fg = "#c0c4cc"
            if day == today:
                fg, font = ACCENT, ("Segoe UI", 9, "bold")
            if day == self.selected:
                bg, fg, font = ACCENT, "white", ("Segoe UI", 9, "bold")
            cell.configure(text=str(day.day), bg=bg, fg=fg, font=font)
            cell.bind("<Button-1>", lambda _e, d=day: self.pick(d))
            cell.bind("<Enter>", lambda _e, c=cell, d=day: c.configure(bg="#e6f4f1") if d != self.selected else None)
            cell.bind("<Leave>", lambda _e, c=cell, b=bg: c.configure(bg=b))

    def move(self, step: int) -> None:
        year, month = self.shown
        index = year * 12 + month - 1 + step
        self.shown = (index // 12, index % 12 + 1)
        self.draw()

    def pick(self, day: date) -> str:
        self.on_pick(day)
        self.close()
        return "break"  # don't let the click reach anything under the popup

    def _click_outside(self, event: tk.Event) -> None:
        inside = self.winfo_containing(event.x_root, event.y_root)
        if inside is None or not str(inside).startswith(str(self)):
            self.close()

    def close(self) -> None:
        anchor = self.anchor
        self.grab_release()
        self.destroy()
        regrab(anchor)  # if we were opened from a dialog, make it modal again


class DateField(ttk.Frame):
    """A date entry (YYYY-MM-DD) that opens a calendar when clicked. Typing still works."""

    def __init__(self, master: tk.Misc, variable: tk.StringVar, width: int = 11, icons: Icons | None = None):
        super().__init__(master)
        self.variable = variable
        self.entry = ttk.Entry(self, textvariable=variable, width=width, cursor="hand2")
        self.entry.pack(side="left", fill="x", expand=True)
        image = icons.get("📅", "#8d99ae", badge=False) if icons else None
        self.button = ttk.Button(self, image=image or "", text="" if image else "📅", width=0 if image else 3,
                                 command=self.open, style="Icon.TButton", takefocus=False)
        self.button.pack(side="left", padx=(2, 0))
        self.entry.bind("<Button-1>", lambda _e: self.after_idle(self.open))
        self.entry.bind("<Alt-Down>", lambda _e: self.open())
        self._popup: CalendarPopup | None = None
        self.enabled = True

    def set_enabled(self, enabled: bool) -> None:
        """Grey out the field (e.g. an optional end date that's switched off)."""
        self.enabled = enabled
        state = ["!disabled"] if enabled else ["disabled"]
        self.entry.state(state)
        self.button.state(state)

    def open(self) -> None:
        if not self.enabled or (self._popup is not None and self._popup.winfo_exists()):
            return
        try:
            current = date.fromisoformat(self.variable.get().strip())
        except ValueError:
            current = date.today()
        self._popup = CalendarPopup(self, current, self._picked)

    def _picked(self, day: date) -> None:
        self.variable.set(day.isoformat())
        self.entry.focus_set()
        self.entry.icursor("end")


class Picker(ttk.Menubutton):
    """A dropdown whose entries show an icon next to the name.

    `get_options` is called each time the menu opens, so it always shows the current choices.
    """

    def __init__(
        self,
        master: tk.Misc,
        icons: Icons,
        variable: tk.StringVar,
        get_options: Callable[[], list[Option]],
        on_change: Callable[[], None] | None = None,
        width: int = 16,
    ):
        super().__init__(master, width=width, style="Picker.TMenubutton")
        self.icons = icons
        self.variable = variable
        self.get_options = get_options
        self.on_change = on_change
        self.menu = tk.Menu(self, tearoff=False, postcommand=self._rebuild)
        self["menu"] = self.menu
        variable.trace_add("write", lambda *_: self.update_display())
        self.update_display()

    def _choose(self, name: str) -> None:
        self.variable.set(name)
        if self.on_change:
            self.on_change()

    def _rebuild(self) -> None:
        self.menu.delete(0, "end")
        for name, icon, color in self.get_options():
            image = self.icons.get(icon, color)
            self.menu.add_command(
                label=self.icons.text(icon, name) if image is None else f" {name}",
                image=image or "", compound="left",
                command=lambda n=name: self._choose(n),
            )

    def update_display(self) -> None:
        name = self.variable.get()
        option = next((o for o in self.get_options() if o[0].lower() == name.lower()), None)
        icon, color = (option[1], option[2]) if option else ("⭐", "#8d99ae")
        image = self.icons.get(icon, color)
        self.configure(text=f" {name}" if image else self.icons.text(icon, name), image=image or "", compound="left")


class Dialog(tk.Toplevel):
    """Modal dialog: subclasses fill `self.body` and implement `on_ok` (return True to close)."""

    def __init__(self, parent: tk.Misc, title: str, ok_text: str = "Save", cancel_text: str = "Cancel"):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        outer = ttk.Frame(self, padding=14)
        outer.grid(sticky="nsew")
        self.body = ttk.Frame(outer)
        self.body.grid(row=0, column=0, sticky="nsew")
        self.buttons = ttk.Frame(outer)
        self.buttons.grid(row=1, column=0, sticky="e", pady=(12, 0))
        if cancel_text:
            ttk.Button(self.buttons, text=cancel_text, command=self.destroy).pack(side="right")
        if ok_text:
            ttk.Button(self.buttons, text=ok_text, command=self._ok, style="Accent.TButton").pack(
                side="right", padx=(0, 6)
            )
        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def show(self, focus: tk.Widget | None = None, bind_return: bool = True) -> None:
        """Center over the parent window, make modal, and focus a widget."""
        if bind_return:
            self.bind("<Return>", lambda _e: self._ok())
        self.update_idletasks()
        top = self.master.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - self.winfo_reqwidth()) // 2
        y = top.winfo_rooty() + (top.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.deiconify()
        self.grab_set()
        if focus is not None:
            focus.focus_set()
            if isinstance(focus, ttk.Entry):
                focus.select_range(0, "end")

    def _ok(self) -> None:
        if self.on_ok():
            self.destroy()

    def on_ok(self) -> bool:
        return True


class ScrollableFrame(ttk.Frame):
    """A frame with a vertical scrollbar; put children in `.inner`."""

    def __init__(self, master: tk.Misc, **kwargs):
        super().__init__(master, **kwargs)
        style = ttk.Style(self)
        self.canvas = tk.Canvas(self, highlightthickness=0, background=style.lookup("TFrame", "background"))
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(window, width=e.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


def setup_style(widget: tk.Misc, icons: Icons) -> None:
    """Named ttk styles shared by every screen."""
    style = ttk.Style(widget)
    style.configure("Treeview", rowheight=icons.size + round(8 * icons.scale))
    style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
    style.configure("Picker.TMenubutton", anchor="w", padding=(4, 1))
    style.configure("Muted.TLabel", foreground="#6b7280")
    style.configure("Warning.TLabel", foreground=WARNING)
    style.configure("Good.TLabel", foreground=GOOD)
    style.configure("Bold.TLabel", font=("Segoe UI", 10, "bold"))
    style.configure("Title.TLabel", font=("Segoe UI", 12, "bold"))
    style.configure("Big.TLabel", font=("Segoe UI", 20, "bold"))
    style.configure("Good.Big.TLabel", foreground=GOOD, font=("Segoe UI", 20, "bold"))
    style.configure("Day.TLabel", font=("Segoe UI", 12, "bold"))
    style.configure("CardTitle.TLabel", foreground="#6b7280", font=("Segoe UI", 9))
    style.configure("CardValue.TLabel", font=("Segoe UI", 14, "bold"))
    style.configure("Good.CardValue.TLabel", foreground=GOOD, font=("Segoe UI", 14, "bold"))
    style.configure("UserName.TLabel", font=("Segoe UI", 11, "bold"))
    style.configure("Dose.TCheckbutton", font=("Segoe UI", 11))
    style.configure("Link.TButton", padding=(6, 0))
    style.configure("Icon.TButton", padding=2)
    style.configure("TNotebook.Tab", padding=(12, 4))


def regrab(widget: tk.Misc) -> None:
    """After a standard pop-up closes, make our dialog modal again."""
    top = widget.winfo_toplevel()
    if isinstance(top, Dialog) and top.winfo_exists():
        top.grab_set()


def labeled(parent: tk.Misc, row: int, text: str, widget: tk.Widget, sticky: str = "w", pady: int = 3) -> tk.Widget:
    """Grid a label + widget pair in a 2-column form."""
    ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=pady)
    widget.grid(row=row, column=1, sticky=sticky, pady=pady)
    return widget
