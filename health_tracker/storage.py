"""Data model and local JSON storage.

Each user's data lives in one JSON file (users/<id>/health.json inside the data folder, see
paths.py) next to a backups/ folder holding an automatic copy of it once per day (last 30 kept).

The file holds:
  weights         one weight per day, in kg
  water           one entry per time you drank water (date + time of day)
  medications     what to take: dose, times of day, weekdays, and an optional start/end date
  taken           which scheduled doses were ticked as taken, and when
  blood_pressure  readings (systolic/diastolic in mmHg, optional pulse) with date and time
  glucose         blood sugar readings in mg/dL with date, time and when they were taken (fasting…)
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

DATA_VERSION = 1
BACKUPS_TO_KEEP = 30

DEFAULT_WATER_GOAL = 8  # times per day
MAX_WATER_GOAL = 30
KG_STEP = Decimal("0.1")
MIN_WEIGHT, MAX_WEIGHT = Decimal("1"), Decimal("500")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
EVERY_DAY = list(range(7))  # weekday numbers, 0 = Monday

GLUCOSE_CONTEXTS = ("Fasting", "Before meal", "After meal", "Bedtime", "Other")
# The usual "time in range" target for people with diabetes; each user can set their own.
DEFAULT_GLUCOSE_TARGET = (70, 180)  # mg/dL
GLUCOSE_TARGET_LIMITS = (40, 400)


# ---------- parsing & formatting ----------

def parse_date(value: str | date | None) -> date:
    if value is None or value == "":
        return date.today()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(f"Invalid date {value!r}; use YYYY-MM-DD") from None


def parse_weight(value: str | Decimal) -> Decimal:
    """'72.4', '72,4' or '72.4 kg' -> Decimal('72.4')."""
    text = str(value).strip().lower().removesuffix("kg").strip()
    if "," in text and "." not in text and text.count(",") == 1:
        text = text.replace(",", ".")  # accept a comma as the decimal separator
    try:
        kg = Decimal(text)
        if not kg.is_finite():
            raise InvalidOperation
        kg = kg.quantize(KG_STEP, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError(f"Invalid weight: {value!r}") from None
    if not MIN_WEIGHT <= kg <= MAX_WEIGHT:
        raise ValueError(f"Weight must be between {MIN_WEIGHT} and {MAX_WEIGHT} kg")
    return kg


def parse_time(value: str) -> str:
    """'8' -> '08:00', '8:30' or '8.30' -> '08:30'."""
    text = str(value).strip().replace(".", ":")
    hours, _, minutes = text.partition(":")
    try:
        h, m = int(hours), int(minutes or 0)
    except ValueError:
        raise ValueError(f"Invalid time {value!r}; use HH:MM, e.g. 08:30") from None
    if len(minutes) not in (0, 2) or not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Invalid time {value!r}; use HH:MM, e.g. 08:30")
    return f"{h:02d}:{m:02d}"


def parse_times(value: str | list[str]) -> list[str]:
    """'20:00, 8' -> ['08:00', '20:00'] (comma separated, sorted, no duplicates)."""
    parts = value if isinstance(value, list) else value.replace(";", ",").split(",")
    times = sorted({parse_time(p) for p in parts if str(p).strip()})
    if not times:
        raise ValueError("Give at least one time of day, e.g. 08:00")
    return times


def parse_whole(value: str | int, label: str, low: int, high: int) -> int:
    """A whole number between `low` and `high`, e.g. a blood pressure or glucose value."""
    try:
        number = int(str(value).strip())
    except ValueError:
        raise ValueError(f"Invalid {label}: {value!r}; use a whole number") from None
    if not low <= number <= high:
        raise ValueError(f"{label[0].upper()}{label[1:]} must be between {low} and {high}")
    return number


def blood_pressure_category(systolic: int, diastolic: int) -> str:
    """Category of a reading, following the American Heart Association guide (plus 'Low' below 90/60)."""
    if systolic > 180 or diastolic > 120:
        return "Hypertensive crisis"
    if systolic >= 140 or diastolic >= 90:
        return "High, stage 2"
    if systolic >= 130 or diastolic >= 80:
        return "High, stage 1"
    if systolic < 90 or diastolic < 60:
        return "Low"
    if systolic >= 120:
        return "Elevated"
    return "Normal"


def glucose_status(mg_dl: int, target: tuple[int, int]) -> str:
    low, high = target
    return "Low" if mg_dl < low else "High" if mg_dl > high else "In range"


def in_last_days(records: list, last: date, days: int) -> list:
    """The records dated within the `days` days ending at `last` (both included)."""
    first = last - timedelta(days=days - 1)
    return [r for r in records if first <= r.date <= last]


def format_weight(kg: Decimal | None) -> str:
    return "—" if kg is None else f"{kg:.1f} kg"


def format_change(delta: Decimal | None) -> str:
    """+0.3 kg / −0.5 kg / ±0.0 kg."""
    if delta is None:
        return "—"
    sign = "+" if delta > 0 else "−" if delta < 0 else "±"
    return f"{sign}{abs(delta):.1f} kg"


def format_weekdays(weekdays: list[int]) -> str:
    if sorted(weekdays) == EVERY_DAY:
        return "Every day"
    return ", ".join(WEEKDAYS[d] for d in sorted(weekdays))


def check_not_future(day: date, what: str) -> None:
    if day > date.today():
        raise ValueError(f"You can't {what} for a day that hasn't happened yet ({day.isoformat()})")


def write_json_atomic(path: Path, doc: dict) -> None:
    """Write to a temp file first, then swap it in, so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


# ---------- records ----------

@dataclass
class WeightEntry:
    date: date
    kg: Decimal

    def to_dict(self) -> dict:
        return {"date": self.date.isoformat(), "kg": str(self.kg)}

    @classmethod
    def from_dict(cls, d: dict) -> WeightEntry:
        return cls(parse_date(d["date"]), parse_weight(d["kg"]))


@dataclass
class WaterEntry:
    """One time you drank water."""

    date: date
    time: str  # HH:MM
    id: str = field(default_factory=_new_id)

    def to_dict(self) -> dict:
        return {"id": self.id, "date": self.date.isoformat(), "time": self.time}

    @classmethod
    def from_dict(cls, d: dict) -> WaterEntry:
        return cls(parse_date(d["date"]), parse_time(d["time"]), d["id"])


class _Reading:
    """Something measured at a time of day (blood pressure, glucose)."""

    date: date
    time: str  # HH:MM

    @property
    def when(self) -> datetime:
        return datetime.fromisoformat(f"{self.date.isoformat()}T{self.time}")


@dataclass
class BloodPressure(_Reading):
    date: date
    time: str
    systolic: int  # mmHg, the upper number
    diastolic: int  # mmHg, the lower number
    pulse: int | None = None  # beats per minute
    notes: str = ""
    id: str = field(default_factory=_new_id)

    def __post_init__(self) -> None:
        self.time = parse_time(self.time)
        self.systolic = parse_whole(self.systolic, "systolic (upper) pressure", 50, 300)
        self.diastolic = parse_whole(self.diastolic, "diastolic (lower) pressure", 20, 200)
        if self.diastolic >= self.systolic:
            raise ValueError("The systolic (upper) number must be higher than the diastolic (lower) one")
        empty = self.pulse is None or str(self.pulse).strip() == ""
        self.pulse = None if empty else parse_whole(self.pulse, "pulse", 20, 250)
        self.notes = self.notes.strip()

    @property
    def text(self) -> str:
        return f"{self.systolic}/{self.diastolic}"

    @property
    def category(self) -> str:
        return blood_pressure_category(self.systolic, self.diastolic)

    def to_dict(self) -> dict:
        return {"id": self.id, "date": self.date.isoformat(), "time": self.time, "systolic": self.systolic,
                "diastolic": self.diastolic, "pulse": self.pulse, "notes": self.notes}

    @classmethod
    def from_dict(cls, d: dict) -> BloodPressure:
        return cls(parse_date(d["date"]), d["time"], d["systolic"], d["diastolic"], d.get("pulse"),
                   d.get("notes") or "", d["id"])


@dataclass
class GlucoseReading(_Reading):
    date: date
    time: str
    mg_dl: int
    context: str = "Other"  # one of GLUCOSE_CONTEXTS
    notes: str = ""
    id: str = field(default_factory=_new_id)

    def __post_init__(self) -> None:
        self.time = parse_time(self.time)
        self.mg_dl = parse_whole(self.mg_dl, "glucose level", 10, 1000)
        context = next((c for c in GLUCOSE_CONTEXTS if c.lower() == str(self.context).strip().lower()), None)
        if context is None:
            raise ValueError(f"When it was taken must be one of: {', '.join(GLUCOSE_CONTEXTS)}")
        self.context = context
        self.notes = self.notes.strip()

    def to_dict(self) -> dict:
        return {"id": self.id, "date": self.date.isoformat(), "time": self.time, "mg_dl": self.mg_dl,
                "context": self.context, "notes": self.notes}

    @classmethod
    def from_dict(cls, d: dict) -> GlucoseReading:
        return cls(parse_date(d["date"]), d["time"], d["mg_dl"], d.get("context") or "Other",
                   d.get("notes") or "", d["id"])


@dataclass
class Medication:
    """Something to take: at which times of day, on which weekdays, and from/until when."""

    name: str
    dose: str = ""  # free text, e.g. "500 mg" or "1 pill"
    times: list[str] = field(default_factory=lambda: ["08:00"])
    weekdays: list[int] = field(default_factory=lambda: list(EVERY_DAY))
    start: date = field(default_factory=date.today)
    end: date | None = None  # last day to take it (e.g. a 7-day course); None = no end
    notes: str = ""
    id: str = field(default_factory=_new_id)

    def __post_init__(self) -> None:
        self.name = " ".join(self.name.split())
        self.dose = self.dose.strip()
        self.notes = self.notes.strip()
        if not self.name:
            raise ValueError("The medication needs a name")
        self.times = parse_times(self.times)
        self.weekdays = sorted({int(d) for d in self.weekdays if 0 <= int(d) <= 6})
        if not self.weekdays:
            raise ValueError("Choose at least one day of the week")
        if self.end is not None and self.end < self.start:
            raise ValueError("The end date can't be before the start date")

    @property
    def label(self) -> str:
        return f"{self.name} · {self.dose}" if self.dose else self.name

    def is_due(self, day: date) -> bool:
        return self.start <= day and (self.end is None or day <= self.end) and day.weekday() in self.weekdays

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "dose": self.dose,
            "times": self.times,
            "weekdays": self.weekdays,
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Medication:
        return cls(
            id=d["id"],
            name=d["name"],
            dose=d.get("dose") or "",
            times=d.get("times") or ["08:00"],
            weekdays=d.get("weekdays", EVERY_DAY),
            start=parse_date(d.get("start")),
            end=parse_date(d["end"]) if d.get("end") else None,
            notes=d.get("notes") or "",
        )


@dataclass
class Dose:
    """One scheduled dose of a medication on one day, and when it was ticked as taken."""

    medication: Medication
    date: date
    time: str
    taken_at: datetime | None = None

    @property
    def taken(self) -> bool:
        return self.taken_at is not None


@dataclass
class DaySummary:
    weight: Decimal | None
    weight_change: Decimal | None  # vs the previous weight entry before this day
    water: int
    water_goal: int
    doses_taken: int
    doses_due: int
    blood_pressure: BloodPressure | None = None  # the day's last reading
    glucose: GlucoseReading | None = None  # the day's last reading
    glucose_target: tuple[int, int] = DEFAULT_GLUCOSE_TARGET


def _taken_key(medication_id: str, day: date, time: str) -> tuple[str, str, str]:
    return medication_id, day.isoformat(), time


@dataclass
class HealthData:
    """Everything in one user's file, read once so every tab draws from the same snapshot."""

    weights: list[WeightEntry]  # sorted by date
    water: list[WaterEntry]  # sorted by date and time
    medications: list[Medication]
    taken: dict[tuple[str, str, str], datetime]  # (medication id, date, time) -> when it was ticked
    water_goal: int = DEFAULT_WATER_GOAL
    blood_pressure: list[BloodPressure] = field(default_factory=list)  # sorted by date and time
    glucose: list[GlucoseReading] = field(default_factory=list)  # sorted by date and time
    glucose_target: tuple[int, int] = DEFAULT_GLUCOSE_TARGET  # (low, high) in mg/dL

    def weight_on(self, day: date) -> WeightEntry | None:
        return next((w for w in self.weights if w.date == day), None)

    def weight_before(self, day: date) -> WeightEntry | None:
        """The last weight entered before `day`."""
        earlier = [w for w in self.weights if w.date < day]
        return earlier[-1] if earlier else None

    def latest_weight(self, until: date) -> WeightEntry | None:
        """The last weight entered on or before `until`."""
        return self.weight_on(until) or self.weight_before(until)

    def water_on(self, day: date) -> list[WaterEntry]:
        return [w for w in self.water if w.date == day]

    def water_by_day(self, last: date, days: int) -> list[tuple[date, int]]:
        """How many times water was drunk on each of the `days` days ending at `last`, newest first."""
        counts: dict[date, int] = {}
        for entry in self.water:
            counts[entry.date] = counts.get(entry.date, 0) + 1
        return [(d, counts.get(d, 0)) for d in (last - timedelta(days=i) for i in range(days))]

    def blood_pressure_on(self, day: date) -> list[BloodPressure]:
        return [r for r in self.blood_pressure if r.date == day]

    def glucose_on(self, day: date) -> list[GlucoseReading]:
        return [r for r in self.glucose if r.date == day]

    def doses_on(self, day: date) -> list[Dose]:
        doses = [
            Dose(med, day, time, self.taken.get(_taken_key(med.id, day, time)))
            for med in self.medications if med.is_due(day) for time in med.times
        ]
        return sorted(doses, key=lambda d: (d.time, d.medication.name.lower()))

    def summary(self, day: date) -> DaySummary:
        entry, before = self.weight_on(day), self.weight_before(day)
        doses = self.doses_on(day)
        pressure, glucose = self.blood_pressure_on(day), self.glucose_on(day)
        return DaySummary(
            weight=entry.kg if entry else None,
            weight_change=entry.kg - before.kg if entry and before else None,
            water=len(self.water_on(day)),
            water_goal=self.water_goal,
            doses_taken=sum(d.taken for d in doses),
            doses_due=len(doses),
            blood_pressure=pressure[-1] if pressure else None,
            glucose=glucose[-1] if glucose else None,
            glucose_target=self.glucose_target,
        )


# ---------- store ----------

class HealthStore:
    """Loads and saves one user's data to one JSON file, with daily backups."""

    def __init__(self, path: Path):
        self.path = Path(path)

    @property
    def backups_dir(self) -> Path:
        return self.path.parent / "backups"

    # --- raw file access ---

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, doc: dict) -> None:
        self._daily_backup()
        doc["version"] = DATA_VERSION
        write_json_atomic(self.path, doc)

    # --- backups ---

    def _daily_backup(self) -> None:
        if not self.path.exists():
            return
        target = self.backups_dir / f"{self.path.stem}-{date.today().isoformat()}.json"
        if not target.exists():
            self.backups_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.path, target)
            self._prune_backups()

    def _prune_backups(self) -> None:
        backups = sorted(self.backups_dir.glob(f"{self.path.stem}-*.json"), key=lambda p: p.stat().st_mtime)
        for old in backups[:-BACKUPS_TO_KEEP]:
            old.unlink(missing_ok=True)

    def backup_now(self) -> Path:
        if not self.path.exists():
            raise ValueError("There is no data to back up yet")
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        target = self.backups_dir / f"{self.path.stem}-{datetime.now():%Y-%m-%d_%H%M%S}.json"
        shutil.copy2(self.path, target)
        return target

    # --- reading everything ---

    def load(self) -> HealthData:
        doc = self._read()
        return HealthData(
            weights=sorted((WeightEntry.from_dict(w) for w in doc.get("weights", [])), key=lambda w: w.date),
            water=sorted((WaterEntry.from_dict(w) for w in doc.get("water", [])), key=lambda w: (w.date, w.time)),
            medications=[Medication.from_dict(m) for m in doc.get("medications", [])],
            taken={
                (t["medication_id"], t["date"], t["time"]): datetime.fromisoformat(t["taken_at"])
                for t in doc.get("taken", [])
            },
            water_goal=int(doc.get("settings", {}).get("water_goal", DEFAULT_WATER_GOAL)),
            blood_pressure=sorted((BloodPressure.from_dict(r) for r in doc.get("blood_pressure", [])),
                                  key=lambda r: (r.date, r.time)),
            glucose=sorted((GlucoseReading.from_dict(r) for r in doc.get("glucose", [])),
                           key=lambda r: (r.date, r.time)),
            glucose_target=tuple(doc.get("settings", {}).get("glucose_target", DEFAULT_GLUCOSE_TARGET)),
        )

    # --- records kept in a list (water, blood pressure, glucose) ---

    def _append(self, section: str, record) -> None:
        doc = self._read()
        doc.setdefault(section, []).append(record.to_dict())
        self._write(doc)

    def _remove(self, section: str, record_id: str) -> bool:
        doc = self._read()
        records = doc.get(section, [])
        kept = [r for r in records if r["id"] != record_id]
        if len(kept) == len(records):
            return False
        doc[section] = kept
        self._write(doc)
        return True

    # --- weight ---

    def set_weight(self, day: date, kg: Decimal) -> WeightEntry:
        """Save the weight of a day, replacing any weight already saved for that day."""
        check_not_future(day, "enter a weight")
        entry = WeightEntry(day, parse_weight(kg))
        doc = self._read()
        doc["weights"] = [w for w in doc.get("weights", []) if w["date"] != day.isoformat()] + [entry.to_dict()]
        doc["weights"].sort(key=lambda w: w["date"])
        self._write(doc)
        return entry

    def delete_weight(self, day: date) -> bool:
        doc = self._read()
        weights = doc.get("weights", [])
        kept = [w for w in weights if w["date"] != day.isoformat()]
        if len(kept) == len(weights):
            return False
        doc["weights"] = kept
        self._write(doc)
        return True

    # --- water ---

    def add_water(self, day: date, time: str) -> WaterEntry:
        check_not_future(day, "log water")
        entry = WaterEntry(day, parse_time(time))
        self._append("water", entry)
        return entry

    def delete_water(self, entry_id: str) -> bool:
        return self._remove("water", entry_id)

    def set_water_goal(self, times: int) -> None:
        times = int(times)
        if not 1 <= times <= MAX_WATER_GOAL:
            raise ValueError(f"The daily goal must be between 1 and {MAX_WATER_GOAL} times")
        doc = self._read()
        doc.setdefault("settings", {})["water_goal"] = times
        self._write(doc)

    # --- blood pressure ---

    def add_blood_pressure(self, reading: BloodPressure) -> BloodPressure:
        check_not_future(reading.date, "enter a blood pressure reading")
        self._append("blood_pressure", reading)
        return reading

    def delete_blood_pressure(self, reading_id: str) -> bool:
        return self._remove("blood_pressure", reading_id)

    # --- glucose ---

    def add_glucose(self, reading: GlucoseReading) -> GlucoseReading:
        check_not_future(reading.date, "enter a glucose reading")
        self._append("glucose", reading)
        return reading

    def delete_glucose(self, reading_id: str) -> bool:
        return self._remove("glucose", reading_id)

    def set_glucose_target(self, low: int, high: int) -> None:
        lowest, highest = GLUCOSE_TARGET_LIMITS
        low = parse_whole(low, "lower end of the target range", lowest, highest)
        high = parse_whole(high, "upper end of the target range", lowest, highest)
        if low >= high:
            raise ValueError("The lower end of the target range must be below the upper end")
        doc = self._read()
        doc.setdefault("settings", {})["glucose_target"] = [low, high]
        self._write(doc)

    # --- medications ---

    def save_medication(self, medication: Medication) -> None:
        """Add a medication, or update it if one with the same id exists."""
        doc = self._read()
        meds = doc.setdefault("medications", [])
        for i, m in enumerate(meds):
            if m["id"] == medication.id:
                meds[i] = medication.to_dict()
                break
        else:
            meds.append(medication.to_dict())
        self._write(doc)

    def delete_medication(self, medication_id: str) -> bool:
        """Remove a medication together with its record of taken doses."""
        doc = self._read()
        meds = doc.get("medications", [])
        kept = [m for m in meds if m["id"] != medication_id]
        if len(kept) == len(meds):
            return False
        doc["medications"] = kept
        doc["taken"] = [t for t in doc.get("taken", []) if t["medication_id"] != medication_id]
        self._write(doc)
        return True

    def set_taken(self, medication_id: str, day: date, time: str, taken: bool = True,
                  now: datetime | None = None) -> None:
        """Tick (or untick) one scheduled dose as taken."""
        if taken:
            check_not_future(day, "tick a dose as taken")
        doc = self._read()
        if not any(m["id"] == medication_id for m in doc.get("medications", [])):
            raise ValueError("This medication no longer exists")
        key = _taken_key(medication_id, day, parse_time(time))
        records = [t for t in doc.get("taken", []) if (t["medication_id"], t["date"], t["time"]) != key]
        if taken:
            when = (now or datetime.now()).replace(microsecond=0)
            records.append({"medication_id": key[0], "date": key[1], "time": key[2], "taken_at": when.isoformat()})
        doc["taken"] = records
        self._write(doc)
