"""Тесты модуля силовых: парсер, 1ПМ, логи, динамика."""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models, strength as strength_svc
from app.db import Base
from app.parser import ParseError, StrengthEntry, parse_strength

_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=_test_engine)


class StrengthParserTest(unittest.TestCase):
    def test_basic(self):
        e = parse_strength("жим 80x2")
        self.assertEqual(e, StrengthEntry("жим", 80.0, 2))

    def test_multiword_name(self):
        e = parse_strength("жим лёжа 100 x 1")
        self.assertEqual(e, StrengthEntry("жим лёжа", 100.0, 1))

    def test_cyrillic_x(self):
        e = parse_strength("присед 100х5")
        self.assertEqual(e, StrengthEntry("присед", 100.0, 5))

    def test_decimal_weight(self):
        e = parse_strength("тяга 82.5x3")
        self.assertEqual(e, StrengthEntry("тяга", 82.5, 3))

    def test_no_x_rejected(self):
        with self.assertRaises(ParseError):
            parse_strength("жим 80")

    def test_weight_out_of_range(self):
        with self.assertRaises(ParseError):
            parse_strength("жим 9999x2")


class E1rmTest(unittest.TestCase):
    def test_single_rep_is_weight(self):
        self.assertEqual(strength_svc.estimate_1rm(100, 1), 100.0)

    def test_epley(self):
        self.assertEqual(strength_svc.estimate_1rm(80, 2), 85.3)
        self.assertEqual(strength_svc.estimate_1rm(80, 5), 93.3)


class StrengthServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(_test_engine)

    def setUp(self):
        self.session = TestSession()
        for t in (models.StrengthLog, models.Exercise, models.User):
            self.session.execute(t.__table__.delete())
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_log_and_history(self):
        user_id = self._add_user()
        strength_svc.log_strength(self.session, user_id, "жим", 80, 5)
        strength_svc.log_strength(self.session, user_id, "жим", 85, 3)
        h = strength_svc.history(self.session, user_id, "жим")
        self.assertEqual(len(h), 2)
        self.assertEqual(h[0]["weight"], 80)
        self.assertAlmostEqual(h[1]["e1rm"], strength_svc.estimate_1rm(85, 3))

    def test_progress_best_and_delta(self):
        user_id = self._add_user()
        strength_svc.log_strength(self.session, user_id, "жим", 80, 5)   # e1rm 93.3
        strength_svc.log_strength(self.session, user_id, "жим", 100, 1)  # e1rm 100.0
        p = strength_svc.progress(self.session, user_id, "жим")
        self.assertEqual(p["records"], 2)
        self.assertEqual(p["best_e1rm"], 100.0)
        self.assertAlmostEqual(p["delta_e1rm"], 6.7)

    def test_exercises_listed_and_normalized(self):
        user_id = self._add_user()
        strength_svc.log_strength(self.session, user_id, "Жим Лёжа", 80, 5)
        strength_svc.log_strength(self.session, user_id, "жим лёжа", 90, 3)
        names = strength_svc.list_exercises(self.session, user_id)
        self.assertEqual(names, ["жим лёжа"])  # одна нормализованная запись

    def _add_user(self):
        u = models.User(tg_id=42)
        self.session.add(u)
        self.session.commit()
        return u.id


if __name__ == "__main__":
    unittest.main()
