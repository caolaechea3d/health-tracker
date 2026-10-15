"""The tabs of the main page, one module each."""

from .base import MEDICATION_COLOR, WATER_COLOR, WEIGHT_COLOR, Tab
from .medications import MedicationsTab
from .water import WaterTab
from .weight import WeightTab

__all__ = ["Tab", "MEDICATION_COLOR", "WATER_COLOR", "WEIGHT_COLOR", "MedicationsTab", "WaterTab", "WeightTab"]
