import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from health_tracker.storage import (
    DEFAULT_WATER_GOAL,
    HealthStore,
    Medication,
    format_change,
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
