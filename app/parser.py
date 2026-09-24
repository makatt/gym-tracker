"""Парсер сообщения с БЖУ. Принимает несколько форматов и валидирует.

Поддерживаемые форматы (порядок всегда Б → Ж → У → К):
    Б150 Ж80 У200 К2100        (с метками)
    150 80 200 2100            (четыре числа подряд)
    150/80/200/2100
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Реалистичные границы значений (отсекаем случайный мусор).
_RANGES = {
    "protein": (0.0, 500.0),
    "fat": (0.0, 300.0),
    "carbs": (0.0, 800.0),
    "calories": (0.0, 10000.0),
}

# Метка -> поле. Русские и английские.
_LABEL_MAP = {
    "б": "protein",
    "ж": "fat",
    "у": "carbs",
    "к": "calories",
    "p": "protein",
    "f": "fat",
    "c": "carbs",
    "cal": "calories",
    "protein": "protein",
    "fat": "fat",
    "carbs": "carbs",
    "calories": "calories",
    "ккал": "calories",
}


class ParseError(ValueError):
    """Не удалось распознать сообщение — текст ошибки показывается пользователю."""


@dataclass
class Macros:
    protein: float
    fat: float
    carbs: float
    calories: float

    def rounded(self) -> "Macros":
        return Macros(
            protein=round(self.protein, 1),
            fat=round(self.fat, 1),
            carbs=round(self.carbs, 1),
            calories=round(self.calories, 0),
        )


def _to_float(raw: str) -> float:
    return float(raw.replace(",", "."))


def _validate(values: dict[str, float]) -> Macros:
    """Проверяет, что все 4 поля на месте и в разумных границах."""
    for field in ("protein", "fat", "carbs", "calories"):
        if field not in values:
            raise ParseError(
                "Не хватает данных. Нужны белки, жиры, углеводы и калории "
                "(например: Б150 Ж80 У200 К2100)."
            )
    for field, (lo, hi) in _RANGES.items():
        v = values[field]
        if not (lo < v <= hi):
            raise ParseError(
                f"Значение {field} = {v} вне разумных границ "
                f"({lo:.0f}–{hi:.0f}). Проверь цифры."
            )
    return Macros(**values).rounded()


def _parse_labeled(text: str) -> dict[str, float] | None:
    """Формат с метками: Б150 Ж80 У200 К2100."""
    found: dict[str, float] = {}
    # Метка (буква/слово) + необязательно двоеточие/равно + число.
    pattern = re.compile(
        r"(?i)\b(б|ж|у|к|ккал|protein|fat|carbs|calories|cal|p|f|c)"
        r"\s*[:=]?\s*(\d+(?:[.,]\d+)?)"
    )
    for m in pattern.finditer(text):
        label = _LABEL_MAP[m.group(1).lower()]
        if label in found:
            # Повторная метка — используем последнюю, но не ругаемся.
            continue
        found[label] = _to_float(m.group(2))
    return found if len(found) == 4 else None


def _parse_plain(text: str) -> dict[str, float] | None:
    """Формат без меток: ровно 4 числа через пробел/слэш/запятую."""
    nums = re.findall(r"\d+(?:[.,]\d+)?", text)
    if len(nums) != 4:
        return None
    p, f, c, k = (_to_float(n) for n in nums)
    return {"protein": p, "fat": f, "carbs": c, "calories": k}


def parse_macros(text: str) -> Macros:
    """Разбирает сообщение в Macros. Кидает ParseError с понятным текстом."""
    if not text or not text.strip():
        raise ParseError("Пустое сообщение. Пришли БЖУ, например: Б150 Ж80 У200 К2100.")

    values = _parse_labeled(text)
    if values is None:
        values = _parse_plain(text)

    if values is None:
        raise ParseError(
            "Не понял формат. Пришли одним из способов:\n"
            "• Б150 Ж80 У200 К2100\n"
            "• 150 80 200 2100\n"
            "• 150/80/200/2100\n"
            "(порядок: белки → жиры → углеводы → калории)"
        )

    return _validate(values)


@dataclass
class StrengthEntry:
    exercise: str
    weight: float
    reps: int


_STRENGTH_RE = re.compile(
    r"^\s*(.+?)\s+(\d+(?:[.,]\d+)?)\s*[xх*]\s*(\d+)\s*$",
    re.IGNORECASE,
)


def parse_strength(text: str) -> StrengthEntry:
    """Парсит силовой подход: 'жим лёжа 80x2' → (жим лёжа, 80, 2)."""
    if not text or not text.strip():
        raise ParseError("Пусто. Формат силовой: /log жим лёжа 80x2")

    m = _STRENGTH_RE.match(text)
    if not m:
        raise ParseError(
            "Не понял силовую. Формат: <упражнение> <вес>x<повторы>, "
            "например «жим лёжа 80x2»."
        )

    name = " ".join(m.group(1).strip().split()).lower()
    weight = _to_float(m.group(2))
    reps = int(m.group(3))

    if not (0 < weight <= 500):
        raise ParseError(f"Вес {weight:g} вне разумных границ (0–500 кг).")
    if not (1 <= reps <= 100):
        raise ParseError(f"Повторы {reps} вне разумных границ (1–100).")

    return StrengthEntry(exercise=name, weight=weight, reps=reps)


def parse_strength_batch(text: str) -> list[StrengthEntry]:
    """Парсит несколько подходов через запятую/точку с запятой/перенос строки.

    «жим 80x2, присед 100x5, тяга 120x3» → [жим, присед, тяга].
    """
    parts = [p.strip() for p in re.split(r"[,;\n]+", text) if p.strip()]
    if not parts:
        raise ParseError("Пусто. Формат: жим 80x2, присед 100x5")
    return [parse_strength(p) for p in parts]


def parse_weight_reps(text: str) -> tuple[float, int]:
    """Парсит только «вес x повторы» без имени упражнения (например «70x5»)."""
    m = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*[xх*]\s*(\d+)\s*$", text, re.IGNORECASE)
    if not m:
        raise ParseError("Формат: <вес>x<повторы>, например 70x5")
    weight = _to_float(m.group(1))
    reps = int(m.group(2))
    if not (0 < weight <= 500):
        raise ParseError(f"Вес {weight:g} вне разумных границ (0–500 кг).")
    if not (1 <= reps <= 100):
        raise ParseError(f"Повторы {reps} вне разумных границ (1–100).")
    return weight, reps
