"""Тесты сервисного слоя питания (апсерт, агрегация, нормы) на SQLite в памяти."""

import unittest
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models, nutrition as svc
from app.db import Base
from app.parser import Macros

# Отдельный in-memory движок для тестов (не трогаем файловую БД приложения).
_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=_test_engine)


class NutritionServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(_test_engine)

    def setUp(self):
        self.session = TestSession()
        # Чистая таблица на каждый тест.
        for t in (models.NutritionDay, models.Goal, models.User):
            self.session.execute(t.__table__.delete())
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_ensure_user_no_duplicates(self):
        u1 = svc.ensure_user(self.session, 123, "max")
        u2 = svc.ensure_user(self.session, 123, "max")
        self.assertEqual(u1.id, u2.id)
        self.assertEqual(self.session.query(models.User).count(), 1)

    def test_upsert_is_idempotent(self):
        user = svc.ensure_user(self.session, 123)
        day = svc.today()
        svc.upsert_day(self.session, user.id, day, Macros(150, 80, 200, 2100))
        # Повторная отправка за тот же день — перезапись, а не новая строка.
        svc.upsert_day(self.session, user.id, day, Macros(160, 90, 220, 2300))
        self.assertEqual(self.session.query(models.NutritionDay).count(), 1)
        row = svc.get_day(self.session, user.id, day)
        self.assertEqual(row.calories, 2300)

    def test_summary_aggregates_three_days(self):
        user = svc.ensure_user(self.session, 123)
        for i in range(3):
            svc.upsert_day(
                self.session, user.id,
                svc.today() - timedelta(days=i),
                Macros(150, 80, 200, 2100),
            )
        s = svc.summary(self.session, user.id, days=7)
        self.assertEqual(s["days_recorded"], 3)
        self.assertEqual(s["totals"]["calories"], 6300)
        self.assertEqual(s["daily_avg"]["calories"], 2100)
        self.assertEqual(s["daily_avg"]["protein"], 150)

    def test_summary_vs_goal(self):
        user = svc.ensure_user(self.session, 123)
        svc.upsert_day(self.session, user.id, svc.today(), Macros(150, 80, 200, 2100))
        svc.set_goal(self.session, user.id, Macros(170, 90, 250, 2600))
        s = svc.summary(self.session, user.id, days=7)
        self.assertEqual(s["diff_vs_goal"]["calories"], -500)
        self.assertEqual(s["diff_vs_goal"]["protein"], -20)


if __name__ == "__main__":
    unittest.main()
