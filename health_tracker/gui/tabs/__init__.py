"""The tabs of the main page, one module each."""

from .base import BLOOD_PRESSURE_COLOR, GLUCOSE_COLOR, MEDICATION_COLOR, WATER_COLOR, WEIGHT_COLOR, Tab
from .blood_pressure import BloodPressureTab
from .glucose import GlucoseTab
from .medications import MedicationsTab
from .water import WaterTab
from .weight import WeightTab

__all__ = [
    "Tab", "MEDICATION_COLOR", "WATER_COLOR", "WEIGHT_COLOR", "BLOOD_PRESSURE_COLOR", "GLUCOSE_COLOR",
    "MedicationsTab", "WaterTab", "WeightTab", "BloodPressureTab", "GlucoseTab",
]
