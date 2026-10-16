import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from health_tracker.storage import (
    DEFAULT_GLUCOSE_TARGET,
    DEFAULT_WATER_GOAL,
    BloodPressure,
    GlucoseReading,
    HealthStore,
    Medication,
    blood_pressure_category,
    format_change,
    glucose_status,
    in_last_days,
    format_weekdays,
    parse_time,
    parse_times,
    parse_weight,
)

MON = date(2026, 10, 12)  # a Monday in the past
TUE, WED = MON + timedelta(days=1), MON + timedelta(days=2)


class ParsingTest(unittest.TestCase):
    def test_weight(self):
        self.assertEqual(parse_weight("72.44"), Decimal("72.4"))
        self.assertEqual(parse_weight("72,45"), Decimal("72.5"))
        self.assertEqual(parse_weight(" 80 kg "), Decimal("80.0"))
        for bad in ("", "abc", "0", "-3", "900", "nan", "inf"):
            with self.assertRaises(ValueError, msg=bad):
                parse_weight(bad)

    def test_times(self):
        self.assertEqual(parse_time("8"), "08:00")
        self.assertEqual(parse_time("8:30"), "08:30")
        self.assertEqual(parse_time("20.15"), "20:15")
        for bad in ("", "24:00", "8:5", "8:60", "noon"):
            with self.assertRaises(ValueError, msg=bad):
                parse_time(bad)
        self.assertEqual(parse_times("20:00, 8, 08:00"), ["08:00", "20:00"])
        with self.assertRaises(ValueError):
            parse_times(" , ")

    def test_formatting(self):
        self.assertEqual(format_change(Decimal("0.3")), "+0.3 kg")
        self.assertEqual(format_change(Decimal("-1.2")), "−1.2 kg")
        self.assertEqual(format_change(Decimal("0")), "±0.0 kg")
        self.assertEqual(format_weekdays(list(range(7))), "Every day")
        self.assertEqual(format_weekdays([4, 0, 2]), "Mon, Wed, Fri")


class ReadingsTest(unittest.TestCase):
    def test_blood_pressure_categories(self):
        cases = {
            (115, 75): "Normal",
            (125, 78): "Elevated",
            (132, 78): "High, stage 1",
            (118, 85): "High, stage 1",
            (145, 85): "High, stage 2",
            (125, 92): "High, stage 2",
            (185, 100): "Hypertensive crisis",
            (150, 125): "Hypertensive crisis",
            (85, 55): "Low",
        }
        for (systolic, diastolic), category in cases.items():
            self.assertEqual(blood_pressure_category(systolic, diastolic), category, (systolic, diastolic))

    def test_blood_pressure_validation(self):
        reading = BloodPressure(MON, "7:30", " 128 ", "82", "")
        self.assertEqual((reading.time, reading.text, reading.pulse), ("07:30", "128/82", None))
        self.assertEqual(BloodPressure(MON, "07:30", 120, 80, "64").pulse, 64)
        for systolic, diastolic, pulse in ((80, 90, None), ("12o", 80, None), (400, 80, None), (120, 80, 5)):
            with self.assertRaises(ValueError, msg=(systolic, diastolic, pulse)):
                BloodPressure(MON, "07:30", systolic, diastolic, pulse)

    def test_glucose(self):
        reading = GlucoseReading(MON, "7", "95", "fasting")
        self.assertEqual((reading.time, reading.mg_dl, reading.context), ("07:00", 95, "Fasting"))
        with self.assertRaises(ValueError):
            GlucoseReading(MON, "07:00", 95, "lunch")
        with self.assertRaises(ValueError):
            GlucoseReading(MON, "07:00", "5.4")  # mmol/L isn't accepted; mg/dL only
        self.assertEqual([glucose_status(v, DEFAULT_GLUCOSE_TARGET) for v in (69, 70, 180, 181)],
                         ["Low", "In range", "In range", "High"])

    def test_in_last_days(self):
        readings = [GlucoseReading(MON + timedelta(days=i), "08:00", 100) for i in range(-8, 2)]
        self.assertEqual([r.date for r in in_last_days(readings, TUE, 7)],
                         [TUE - timedelta(days=i) for i in range(6, -1, -1)])


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = HealthStore(Path(self.tmp.name) / "health.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_file(self):
        data = self.store.load()
        self.assertEqual((data.weights, data.water, data.medications), ([], [], []))
        self.assertEqual(data.water_goal, DEFAULT_WATER_GOAL)
        summary = data.summary(MON)
        self.assertEqual((summary.weight, summary.water, summary.doses_due), (None, 0, 0))

    # --- weight ---

    def test_one_weight_per_day(self):
        self.store.set_weight(MON, "72.0")
        self.store.set_weight(WED, "71.2")
        self.store.set_weight(MON, "72.4")  # replaces Monday's
        data = self.store.load()
        self.assertEqual([(w.date, w.kg) for w in data.weights], [(MON, Decimal("72.4")), (WED, Decimal("71.2"))])
        summary = data.summary(WED)
        self.assertEqual((summary.weight, summary.weight_change), (Decimal("71.2"), Decimal("-1.2")))
        self.assertEqual(data.summary(MON).weight_change, None)  # first entry
        self.assertIsNone(data.weight_on(TUE))
        self.assertEqual(data.latest_weight(TUE).kg, Decimal("72.4"))

        self.assertTrue(self.store.delete_weight(MON))
        self.assertFalse(self.store.delete_weight(MON))
        self.assertEqual([w.date for w in self.store.load().weights], [WED])

    def test_no_entries_for_future_days(self):
        tomorrow = date.today() + timedelta(days=1)
        with self.assertRaises(ValueError):
            self.store.set_weight(tomorrow, "70")
        with self.assertRaises(ValueError):
            self.store.add_water(tomorrow, "10:00")
        med = Medication("Vitamin D")
        self.store.save_medication(med)
        with self.assertRaises(ValueError):
            self.store.set_taken(med.id, tomorrow, "08:00")

    # --- water ---

    def test_water_by_day(self):
        first = self.store.add_water(MON, "9:15")
        self.store.add_water(MON, "08:00")
        self.store.add_water(TUE, "12:00")
        data = self.store.load()
        self.assertEqual([w.time for w in data.water_on(MON)], ["08:00", "09:15"])  # sorted by time
        self.assertEqual(data.water_by_day(WED, 3), [(WED, 0), (TUE, 1), (MON, 2)])

        self.assertTrue(self.store.delete_water(first.id))
        self.assertFalse(self.store.delete_water(first.id))
        self.assertEqual(self.store.load().summary(MON).water, 1)

    def test_water_goal(self):
        self.store.set_water_goal(10)
        self.assertEqual(self.store.load().water_goal, 10)
        for bad in (0, 31):
            with self.assertRaises(ValueError):
                self.store.set_water_goal(bad)

    # --- blood pressure & glucose ---

    def test_blood_pressure_readings(self):
        morning = self.store.add_blood_pressure(BloodPressure(MON, "08:00", 135, 85, 70, "left arm"))
        self.store.add_blood_pressure(BloodPressure(MON, "21:00", 122, 79))
        self.store.add_blood_pressure(BloodPressure(MON, "07:00", 118, 76))
        data = self.store.load()
        self.assertEqual([r.time for r in data.blood_pressure_on(MON)], ["07:00", "08:00", "21:00"])
        self.assertEqual(data.blood_pressure_on(TUE), [])
        self.assertEqual(data.summary(MON).blood_pressure.text, "122/79")  # the day's last reading
        self.assertEqual(data.blood_pressure_on(MON)[1], morning)  # survives saving and loading
        self.assertEqual(data.blood_pressure_on(MON)[1].when, datetime(2026, 10, 12, 8, 0))

        self.assertTrue(self.store.delete_blood_pressure(morning.id))
        self.assertFalse(self.store.delete_blood_pressure(morning.id))
        self.assertEqual(len(self.store.load().blood_pressure), 2)
        with self.assertRaises(ValueError):
            self.store.add_blood_pressure(BloodPressure(date.today() + timedelta(days=1), "08:00", 120, 80))

    def test_glucose_readings_and_target(self):
        fasting = self.store.add_glucose(GlucoseReading(TUE, "07:00", 110, "Fasting"))
        self.store.add_glucose(GlucoseReading(TUE, "14:00", 190, "After meal", "pasta"))
        data = self.store.load()
        self.assertEqual(data.glucose_target, DEFAULT_GLUCOSE_TARGET)
        self.assertEqual([(r.mg_dl, r.context, r.notes) for r in data.glucose_on(TUE)],
                         [(110, "Fasting", ""), (190, "After meal", "pasta")])
        self.assertEqual(data.summary(TUE).glucose.mg_dl, 190)
        self.assertIsNone(data.summary(MON).glucose)

        self.store.set_glucose_target(80, 200)
        self.assertEqual(self.store.load().glucose_target, (80, 200))
        for low, high in ((150, 120), (10, 180), (70, 900)):
            with self.assertRaises(ValueError, msg=(low, high)):
                self.store.set_glucose_target(low, high)
        self.assertTrue(self.store.delete_glucose(fasting.id))
        self.assertEqual([r.mg_dl for r in self.store.load().glucose], [190])

    # --- medications ---

    def test_medication_validation(self):
        with self.assertRaises(ValueError):
            Medication("  ")
        with self.assertRaises(ValueError):
            Medication("Ibuprofen", weekdays=[])
        with self.assertRaises(ValueError):
            Medication("Ibuprofen", start=WED, end=MON)
        med = Medication("  Ibuprofen   400 ", dose=" 400 mg ", times=["20:00", "8"])
        self.assertEqual((med.name, med.dose, med.times), ("Ibuprofen 400", "400 mg", ["08:00", "20:00"]))

    def test_medication_schedule(self):
        course = Medication("Amoxicillin", "500 mg", times=["08:00", "20:00"], start=MON, end=TUE)
        weekly = Medication("Vitamin B12", times=["09:00"], weekdays=[2], start=MON)  # Wednesdays
        self.assertEqual([course.is_due(d) for d in (MON - timedelta(days=1), MON, TUE, WED)],
                         [False, True, True, False])
        self.assertEqual([weekly.is_due(d) for d in (MON, TUE, WED)], [False, False, True])

        self.store.save_medication(course)
        self.store.save_medication(weekly)
        data = self.store.load()
        self.assertEqual([(d.time, d.medication.name) for d in data.doses_on(MON)],
                         [("08:00", "Amoxicillin"), ("20:00", "Amoxicillin")])
        self.assertEqual([d.medication.name for d in data.doses_on(WED)], ["Vitamin B12"])

    def test_tick_and_untick_doses(self):
        med = Medication("Amoxicillin", times=["08:00", "20:00"], start=MON)
        self.store.save_medication(med)
        when = datetime(2026, 10, 12, 8, 5, 30)
        self.store.set_taken(med.id, MON, "08:00", now=when)
        data = self.store.load()
        self.assertEqual([(d.time, d.taken_at) for d in data.doses_on(MON)],
                         [("08:00", when), ("20:00", None)])
        self.assertEqual((data.summary(MON).doses_taken, data.summary(MON).doses_due), (1, 2))
        self.assertEqual(data.summary(TUE).doses_taken, 0)  # ticks belong to one day only

        self.store.set_taken(med.id, MON, "08:00", taken=False)
        self.assertEqual(self.store.load().summary(MON).doses_taken, 0)
        with self.assertRaises(ValueError):
            self.store.set_taken("missing", MON, "08:00")

    def test_editing_keeps_ticks_and_deleting_removes_them(self):
        med = Medication("Metformin", times=["08:00"], start=MON)
        other = Medication("Vitamin D", times=["08:00"], start=MON)
        self.store.save_medication(med)
        self.store.save_medication(other)
        self.store.set_taken(med.id, MON, "08:00")
        self.store.set_taken(other.id, MON, "08:00")

        med.dose = "850 mg"
        self.store.save_medication(med)  # update in place, same id
        data = self.store.load()
        self.assertEqual([m.dose for m in data.medications], ["850 mg", ""])
        self.assertEqual(data.summary(MON).doses_taken, 2)

        self.assertTrue(self.store.delete_medication(med.id))
        self.assertFalse(self.store.delete_medication(med.id))
        doc = json.loads(self.store.path.read_text(encoding="utf-8"))
        self.assertEqual([t["medication_id"] for t in doc["taken"]], [other.id])

    # --- backups ---

    def test_daily_backup(self):
        self.store.set_weight(MON, "70")  # first write: nothing to back up yet
        self.assertFalse(self.store.backups_dir.exists())
        self.store.set_weight(TUE, "70.5")
        self.store.set_weight(WED, "71")
        [backup] = self.store.backups_dir.iterdir()
        self.assertEqual(backup.name, f"health-{date.today().isoformat()}.json")
        self.assertEqual(len(json.loads(backup.read_text(encoding="utf-8"))["weights"]), 1)


if __name__ == "__main__":
    unittest.main()
