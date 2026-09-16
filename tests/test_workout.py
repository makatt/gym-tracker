"""Тесты сервиса тренировок: шаблоны, активная тренировка, сравнение с прошлым."""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models, strength as strength_svc, workout as workout_svc
from app.db import Base

_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=_test_engine)


class WorkoutServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(_test_engine)

    def setUp(self):
        self.session = TestSession()
        for t in (models.StrengthLog, models.TemplateExercise, models.WorkoutTemplate,
                  models.Workout, models.Exercise, models.User):
            self.session.execute(t.__table__.delete())
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def _user(self):
        u = models.User(tg_id=7)
        self.session.add(u)
        self.session.commit()
        return u.id

    def test_templates_seeded(self):
        uid = self._user()
        ts = workout_svc.list_templates(self.session, uid)
        self.assertEqual([t["name"] for t in ts], ["спина", "грудь", "руки"])
        self.assertEqual(len(ts[0]["exercises"]), 8)   # спина
        self.assertEqual(len(ts[2]["exercises"]), 4)   # руки

    def test_create_workout_closes_previous(self):
        uid = self._user()
        workout_svc.create_workout(self.session, uid, "спина")
        w2 = workout_svc.create_workout(self.session, uid, "грудь")
        active = workout_svc.active_workout(self.session, uid)
        self.assertEqual(active.id, w2.id)

    def test_log_to_workout_upserts(self):
        uid = self._user()
        workout_svc.create_workout(self.session, uid, "спина")
        workout_svc.log_to_workout(self.session, uid, "жим", 80, 5)
        workout_svc.log_to_workout(self.session, uid, "жим", 90, 3)  # перезапись
        w = workout_svc.active_workout(self.session, uid)
        logs = workout_svc.workout_logs(self.session, w)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].weight, 90)

    def test_previous_entry(self):
        uid = self._user()
        strength_svc.log_strength(self.session, uid, "жим", 80, 5)  # свободный подход
        workout_svc.create_workout(self.session, uid, "грудь")
        prev = workout_svc.previous_entry(self.session, uid, "жим")
        self.assertEqual(prev["weight"], 80)

    def test_finish_report_delta(self):
        uid = self._user()
        strength_svc.log_strength(self.session, uid, "жим", 80, 5)   # прошлый 1ПМ 93.3
        workout_svc.create_workout(self.session, uid, "грудь")
        workout_svc.log_to_workout(self.session, uid, "жим", 90, 3)  # текущий 1ПМ 99.0
        rep = workout_svc.finish_workout(self.session, uid)
        self.assertIn("жим", rep["exercises"])
        self.assertAlmostEqual(rep["exercises"]["жим"]["delta_e1rm"], 5.7)


if __name__ == "__main__":
    unittest.main()
