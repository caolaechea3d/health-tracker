import tempfile
import unittest
from datetime import date
from pathlib import Path

from health_tracker.users import DEFAULT_USER_NAME, UserRegistry

DAY = date(2026, 10, 12)


class UsersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.registry = UserRegistry(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_run_creates_default_user(self):
        self.registry.ensure_ready()
        self.registry.ensure_ready()  # running again changes nothing
        [user] = self.registry.users()
        self.assertEqual((user.name, user.type), (DEFAULT_USER_NAME, "Personal"))
        self.assertEqual(self.registry.last_user().id, user.id)
        self.assertEqual(self.registry.store_for(user).load().weights, [])

    def test_users_have_separate_data(self):
        self.registry.ensure_ready()
        a = self.registry.last_user()
        b = self.registry.create("Grandma", "Senior")
        self.assertEqual((b.icon, b.type), ("🧓", "Senior"))
        store_a, store_b = self.registry.store_for(a), self.registry.store_for(b)
        store_a.set_weight(DAY, "80")
        store_a.add_water(DAY, "08:00")
        store_b.set_weight(DAY, "62.5")

        self.assertEqual(store_a.load().summary(DAY).water, 1)
        self.assertEqual(store_b.load().summary(DAY).water, 0)
        self.assertEqual(str(store_b.load().weights[0].kg), "62.5")
        self.assertNotEqual(store_a.path.parent, store_b.path.parent)

    def test_names_are_unique_and_required(self):
        self.registry.ensure_ready()
        self.registry.create("Ana")
        with self.assertRaises(ValueError):
            self.registry.create("  ana ")
        with self.assertRaises(ValueError):
            self.registry.create("   ")
        user = self.registry.find("ANA")
        user.name = "Ana María"
        self.registry.update(user)
        self.assertEqual(self.registry.get(user.id).name, "Ana María")

    def test_switching_remembers_last_user(self):
        self.registry.ensure_ready()
        b = self.registry.create("Luis", "Fitness")
        self.assertNotEqual(self.registry.last_user().id, b.id)
        self.registry.set_last_user(b.id)
        self.assertEqual(UserRegistry(self.dir).last_user().id, b.id)

    def test_delete_keeps_data_aside(self):
        self.registry.ensure_ready()
        a = self.registry.last_user()
        b = self.registry.create("Luis")
        self.registry.store_for(b).set_weight(DAY, "75")
        self.registry.set_last_user(b.id)

        target = self.registry.delete(b.id)
        self.assertEqual([u.id for u in self.registry.users()], [a.id])
        self.assertEqual(self.registry.last_user().id, a.id)
        self.assertTrue((target / "health.json").exists())
        self.assertEqual(target.parent, self.dir / "users" / "_deleted")
        with self.assertRaises(ValueError):
            self.registry.delete(a.id)  # can't delete the only user


if __name__ == "__main__":
    unittest.main()
