"""Shared pieces for the tabs of the main page."""

from __future__ import annotations

from datetime import date
from tkinter import ttk
from typing import TYPE_CHECKING

from ...storage import HealthData

if TYPE_CHECKING:
    from ..app import HealthApp

MEDICATION_COLOR = "#8d6cab"
WATER_COLOR = "#277da1"
WEIGHT_COLOR = "#43aa8b"


class Tab(ttk.Frame):
    """One tab of the notebook. Subclasses set the label/icon, build their widgets and redraw."""

    label = ""
    tab_icon = ""
    tab_color = "#8d99ae"

    def __init__(self, app: HealthApp):
        super().__init__(app.notebook, padding=12)
        self.app = app
        self.icons = app.icons
        image = self.icons.get(self.tab_icon, self.tab_color)
        app.notebook.add(self, text=f" {self.label}" if image else self.icons.text(self.tab_icon, self.label),
                         image=image or "", compound="left")
        self.build()

    def build(self) -> None:
        raise NotImplementedError

    def redraw(self, data: HealthData, day: date) -> None:
        """Show `data` for the day selected in the header."""
        raise NotImplementedError

    def with_icon(self, icon: str, text: str, color: str = "#8d99ae") -> dict:
        """Keyword args for a button or label: emoji image + text (or emoji text without Pillow)."""
        image = self.icons.get(icon, color, badge=False)
        return {"image": image or "", "text": f" {text}" if image else self.icons.text(icon, text), "compound": "left"}
