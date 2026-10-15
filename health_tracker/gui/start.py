"""Start screen (choose or create a user) and the shell that switches between screens."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import messagebox, ttk

from .. import APP_NAME, __version__
from ..paths import is_portable
from ..storage import format_weight
from ..users import USER_TYPES, User, UserRegistry, type_look
from . import errors
from .app import HealthApp
from .icons import Icons, enable_dpi_awareness
from .widgets import Dialog, Picker, labeled, setup_style

CARD_BG = "#ffffff"
CARD_HOVER = "#f5f7fa"
CARD_BORDER = "#e5e7eb"
CARD_SELECTED = "#2a9d8f"
CARDS_PER_ROW = 4
LOGO = ("🩺", "#43aa8b")

# Keyboard shortcuts a screen binds on the root window; cleared when switching screens.
SCREEN_BINDINGS = ("<Return>", "<Alt-Left>", "<Alt-Right>", "<Alt-Home>")


class UserDialog(Dialog):
    """Create or edit a user: name and type (the type picks the icon and color)."""

    def __init__(self, screen: StartScreen, user: User | None = None):
        self.screen = screen
        self.original = user
        super().__init__(screen, "Edit user" if user else "New user", ok_text="Save" if user else "Create user")
        self.icons = screen.icons
        b = self.body
        b.columnconfigure(1, weight=1)
        self.name_var = tk.StringVar(value=user.name if user else "")
        self.type_var = tk.StringVar(value=user.type if user else "Personal")

        name = labeled(b, 0, "Name", ttk.Entry(b, textvariable=self.name_var, width=28), sticky="ew")
        labeled(b, 1, "Type", Picker(b, self.icons, self.type_var, lambda: USER_TYPES, width=20), sticky="w")
        ttk.Label(b, text="Each user has their own weight, water and medication records, and backups.",
                  style="Muted.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.show(name)

    def on_ok(self) -> bool:
        registry = self.screen.registry
        icon, color = type_look(self.type_var.get())
        try:
            if self.original:
                user = self.original
                user.name, user.type, user.icon, user.color = self.name_var.get(), self.type_var.get(), icon, color
                registry.update(user)
            else:
                user = registry.create(self.name_var.get(), self.type_var.get(), icon, color)
        except (ValueError, OSError) as exc:
            messagebox.showerror("User", str(exc), parent=self)
            return False
        self.screen.users_changed(select=user.id)
        return True


class StartScreen(ttk.Frame):
    """'Who's checking in today?' — one card per user plus a 'New user' card."""

    def __init__(self, master: tk.Tk, registry: UserRegistry, icons: Icons, on_open: Callable[[User], None]):
        super().__init__(master, padding=30)
        self.registry = registry
        self.icons = icons
        self.on_open = on_open
        self.selected_id: str | None = None
        master.title(APP_NAME)
        self.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(5, weight=2)

        head = ttk.Frame(self)
        head.grid(row=1, column=0)
        logo = icons.get(*LOGO, size=round(icons.size * 2.6))
        ttk.Label(head, image=logo or "", text="" if logo else LOGO[0]).pack(side="left", padx=(0, 14))
        ttk.Label(head, text=APP_NAME, font=("Segoe UI", 26, "bold")).pack(side="left")
        ttk.Label(self, text="Who's checking in today? Choose a user to continue.",
                  style="Muted.TLabel", font=("Segoe UI", 12)).grid(row=2, column=0, pady=(6, 26))
        self.cards = ttk.Frame(self)
        self.cards.grid(row=3, column=0)
        mode = " · portable" if is_portable() else ""
        ttk.Label(self, text=f"{APP_NAME} {__version__}{mode}  ·  Data folder: {registry.data_dir}",
                  style="Muted.TLabel").grid(row=4, column=0, pady=(26, 0))
        master.bind("<Return>", self._open_selected)
        self.users_changed()

    # --- cards ---

    def users_changed(self, select: str | None = None) -> None:
        for child in self.cards.winfo_children():
            child.destroy()
        users = self.registry.users()
        last = self.registry.last_user()
        self.selected_id = select or (last.id if last else None)
        for i, user in enumerate(users):
            self._card(i, user.icon, user.color, user.name, user.type, self._stats(user),
                       on_click=lambda u=user: self.open(u), user=user)
        self._card(len(users), "➕", "#9ca3af", "New user", "Create a profile", "",
                   on_click=lambda: UserDialog(self))

    def _stats(self, user: User) -> str:
        try:
            data = self.registry.store_for(user).load()
        except (ValueError, KeyError, OSError):
            return "Couldn't read data"
        today = date.today()
        s = data.summary(today)
        latest = data.latest_weight(today)
        meds = f"Meds {s.doses_taken}/{s.doses_due}" if s.doses_due else "No meds"
        return f"{format_weight(latest.kg) if latest else 'No weight yet'}\nWater {s.water}/{s.water_goal} · {meds} today"

    def _card(self, index: int, icon: str, color: str, title: str, subtitle: str, stats: str,
              on_click: Callable[[], None], user: User | None = None) -> None:
        selected = user is not None and user.id == self.selected_id
        scale = self.icons.scale
        card = tk.Frame(self.cards, bg=CARD_BG, width=round(190 * scale), height=round(200 * scale),
                        highlightthickness=2, highlightbackground=CARD_SELECTED if selected else CARD_BORDER,
                        cursor="hand2")
        card.grid(row=index // CARDS_PER_ROW, column=index % CARDS_PER_ROW, padx=10, pady=10)
        card.pack_propagate(False)
        image = self.icons.get(icon, color, size=round(self.icons.size * 3.2))
        widgets = [
            tk.Label(card, image=image or "", text="" if image else icon, bg=CARD_BG, font=("Segoe UI Emoji", 30)),
            tk.Label(card, text=title, bg=CARD_BG, font=("Segoe UI", 12, "bold"), wraplength=round(170 * scale)),
            tk.Label(card, text=subtitle, bg=CARD_BG, fg="#6b7280", font=("Segoe UI", 9)),
            tk.Label(card, text=stats, bg=CARD_BG, fg="#9ca3af", font=("Segoe UI", 8), justify="center"),
        ]
        widgets[0].pack(pady=(round(22 * scale), 8))
        for w in widgets[1:]:
            w.pack()
        if user is not None:
            more = tk.Menubutton(card, text="⋯", bg=CARD_BG, activebackground=CARD_HOVER, relief="flat",
                                 font=("Segoe UI", 12, "bold"), fg="#6b7280", cursor="hand2")
            menu = tk.Menu(more, tearoff=False)
            menu.add_command(label="Open", command=on_click)
            menu.add_command(label="Edit…", command=lambda: UserDialog(self, user))
            menu.add_separator()
            menu.add_command(label="Delete…", command=lambda: self.delete(user))
            more["menu"] = menu
            more.place(relx=1.0, x=-4, y=2, anchor="ne")

        def paint(bg: str) -> None:
            card.configure(bg=bg)
            for w in widgets:
                w.configure(bg=bg)

        def leave(event: tk.Event) -> None:
            inside = card.winfo_containing(event.x_root, event.y_root)
            if inside is None or not str(inside).startswith(str(card)):
                paint(CARD_BG)

        card.bind("<Enter>", lambda _e: paint(CARD_HOVER))
        card.bind("<Leave>", leave)
        for w in [card, *widgets]:
            w.bind("<Button-1>", lambda _e: on_click())

    # --- actions ---

    def _open_selected(self, _event: tk.Event | None = None) -> None:
        user = self.registry.get(self.selected_id) if self.selected_id else None
        if user and not self.grab_current():
            self.open(user)

    def open(self, user: User) -> None:
        self.on_open(user)

    def delete(self, user: User) -> None:
        if not messagebox.askyesno(
            "Delete user",
            f"Delete the user '{user.name}'?\n\nTheir data isn't erased: it's moved to "
            f"{self.registry.data_dir / 'users' / '_deleted'}.",
        ):
            return
        try:
            self.registry.delete(user.id)
        except (ValueError, OSError) as exc:
            messagebox.showinfo("Delete user", str(exc))
            return
        self.users_changed()


class Shell:
    """Owns the root window and switches between the start screen and a user's main page."""

    def __init__(self, root: tk.Tk, registry: UserRegistry):
        self.root = root
        self.registry = registry
        self.icons = Icons(root)
        setup_style(root, self.icons)
        app_icon = self.icons.get(*LOGO, size=64)
        if app_icon:
            root.iconphoto(True, app_icon)  # window and taskbar icon
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.current: tk.Widget | None = None
        self.show_start()

    def _clear(self) -> None:
        if self.current is not None:
            self.current.destroy()
        self.root.configure(menu="")
        for sequence in SCREEN_BINDINGS:
            self.root.unbind(sequence)

    def show_start(self) -> None:
        self._clear()
        self.current = StartScreen(self.root, self.registry, self.icons, on_open=self.open_user)

    def open_user(self, user: User) -> None:
        self.registry.set_last_user(user.id)
        self._clear()
        self.current = HealthApp(self.root, self.registry.store_for(user), icons=self.icons, user=user,
                                 on_switch_user=self.show_start)


def run(data_dir=None) -> None:
    enable_dpi_awareness()
    root = tk.Tk()
    errors.install(root)
    root.geometry("1200x760")
    root.minsize(1000, 640)
    registry = UserRegistry(data_dir)
    try:
        registry.ensure_ready()
    except OSError as exc:
        messagebox.showerror(APP_NAME, f"Couldn't prepare the data folder:\n{exc}")
        root.destroy()
        return
    Shell(root, registry)
    root.mainloop()
