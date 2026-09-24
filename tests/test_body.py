"""Тесты модуля тела: формулы КБЖУ, профиль, замеры, прогресс."""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import body as body_svc, models
from app.db import Base

_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=_test_engine)


class FormulasTest(unittest.TestCase):
    def test_bmr_male(self):
        # 10*80 + 6.25*180 - 5*20 + 5 = 1830
        self.assertEqual(body_svc.calculate_bmr("male", 80, 180, 20), 1830)

    def test_bmr_female(self):
        # 10*60 + 6.25*165 - 5*25 - 161 = 1345.25
        self.assertEqual(body_svc.calculate_bmr("female", 60, 165, 25), 1345.25)

    def test_tdee(self):
        self.assertAlmostEqual(body_svc.calculate_tdee(1830, 3), 1830 * 1.55)

    def test_target(self):
        self.assertAlmostEqual(body_svc.calculate_target(2000, "cut"), 1600)
        self.assertAlmostEqual(body_svc.calculate_target(2000, "bulk"), 2200)
        self.assertAlmostEqual(body_svc.calculate_target(2000, "maintain"), 2000)

    def test_macros(self):
        # вес 80: белки 160 г, жиры 72 г, углеводы (2000-640-648)/4 = 178 г
        m = body_svc.calculate_macros(2000, 80)
        self.assertEqual(m["protein"], 160.0)
        self.assertEqual(m["fat"], 72.0)
        self.assertEqual(m["carbs"], 178.0)

    def test_normalize(self):
        self.assertEqual(body_svc.normalize_sex("М"), "male")
        self.assertEqual(body_svc.normalize_goal("сушка"), "cut")


class BodyServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(_test_engine)

    def setUp(self):
        self.session = TestSession()
        for t in (models.ProgressPhoto, models.BodyMetric, models.BodyProfile, models.User):
            self.session.execute(t.__table__.delete())
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def _user(self):
        u = models.User(tg_id=5)
        self.session.add(u)
        self.session.commit()
        return u.id

    def test_calc_kcal_end_to_end(self):
        uid = self._user()
        body_svc.set_profile(self.session, uid, "male", 180, 2006, 3, "cut")
        body_svc.add_metric(self.session, uid, 80, 15, 45)
        k = body_svc.calc_kcal(self.session, uid)
        self.assertIsNotNone(k)
        self.assertEqual(k["goal"], "cut")
        self.assertEqual(k["protein"], 160.0)
        self.assertEqual(k["fat"], 72.0)
        self.assertTrue(k["tdee"] > k["bmr"])

    def test_profile_update(self):
        uid = self._user()
        body_svc.set_profile(self.session, uid, "male", 180, 2006, 3, "cut")
        body_svc.set_profile(self.session, uid, "male", 181, 2006, 4, "bulk")
        p = body_svc.get_profile(self.session, uid)
        self.assertEqual(p.height_cm, 181)
        self.assertEqual(p.goal, "bulk")

    def test_progress_delta(self):
        uid = self._user()
        body_svc.add_metric(self.session, uid, 80, 18, None)
        body_svc.add_metric(self.session, uid, 78, 15, None)
        p = body_svc.progress(self.session, uid)
        self.assertEqual(p["weight_delta"], -2.0)
        self.assertEqual(p["fat_delta"], -3.0)


if __name__ == "__main__":
    unittest.main()
