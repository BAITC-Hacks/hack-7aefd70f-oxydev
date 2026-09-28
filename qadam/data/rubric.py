# -*- coding: utf-8 -*-
"""Рубрика компетенции «Лидерские способности».

Единственный источник истины по методологии для всего проекта.
Формулировки поведенческих индикаторов и уточняющих вопросов ATOLA взяты
дословно из материалов заказчика (см. docs/01-context.md, разделы 5.2 и 5.4;
первоисточник — презентация «AI Leader ID», inVision U × Talent Craft).

Модуль намеренно декларативный: здесь нет ни логики сопоставления текста
с индикаторами (см. qadam/core/features.py), ни оценивания.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SOURCE_BARS = "docs/01-context.md §5.4 (презентация «AI Leader ID», слайд BARS)"
SOURCE_ATOLA = "docs/01-context.md §5.2 (методология интервью ATOLA)"

Level = Literal["weak", "normal", "strong"]

#: Порядок уровней. Используется для квадратично-взвешенной каппы и матрицы ошибок.
LEVELS: tuple[Level, ...] = ("weak", "normal", "strong")

#: Числовой код уровня для метрик, где нужна упорядоченная шкала.
LEVEL_ORDINAL: dict[Level, int] = {"weak": 0, "normal": 1, "strong": 2}

#: Подписи уровней для интерфейса. Соответствуют шкале заказчика.
LEVEL_LABELS_RU: dict[Level, str] = {
    "weak": "Слабо",
    "normal": "Нормально",
    "strong": "Высоко",
}

AtolaElement = Literal["action", "thinking", "outcome", "learnings", "application"]

ATOLA_ORDER: tuple[AtolaElement, ...] = (
    "action",
    "thinking",
    "outcome",
    "learnings",
    "application",
)


@dataclass(frozen=True)
class AtolaSpec:
    """Один элемент модели ATOLA."""

    key: AtolaElement
    letter: str
    name_ru: str
    name_en: str
    #: Вопросы методологии — дословно из §5.2.
    questions: tuple[str, ...]
    #: Уточняющие вопросы для режима «возвращения голоса» (модуль M5)
    #: и для подсказок интервьюеру (модуль M4).
    probes: tuple[str, ...]

    @property
    def label(self) -> str:
        return f"{self.letter} · {self.name_ru}"


ATOLA: dict[AtolaElement, AtolaSpec] = {
    "action": AtolaSpec(
        key="action",
        letter="A",
        name_ru="Действие",
        name_en="Action",
        questions=(
            "Что конкретно вы сделали?",
            "Как подошли к этому?",
        ),
        probes=(
            "С чего именно вы начали в тот день?",
            "Что было вашим личным вкладом, а не команды?",
            "Кто ещё участвовал и что делали именно вы?",
        ),
    ),
    "thinking": AtolaSpec(
        key="thinking",
        letter="T",
        name_ru="Мышление",
        name_en="Thinking",
        questions=(
            "Можете объяснить своё мышление?",
            "Почему выбрали такой подход?",
        ),
        probes=(
            "Какие варианты вы рассматривали и почему отказались от остальных?",
            "Что вы посчитали главным риском?",
            "Как вы поняли, что действовать надо именно так?",
        ),
    ),
    "outcome": AtolaSpec(
        key="outcome",
        letter="O",
        name_ru="Результат",
        name_en="Outcome",
        questions=(
            "Какой был результат?",
            "Каким было влияние тогда и сейчас?",
        ),
        probes=(
            "Что стало по-другому после ваших действий?",
            "Как вы измеряли результат?",
            "Что из этого работает до сих пор?",
        ),
    ),
    "learnings": AtolaSpec(
        key="learnings",
        letter="L",
        name_ru="Выводы",
        name_en="Learnings",
        questions=(
            "Что вы поняли, чему научились?",
        ),
        probes=(
            "Что вы сделали бы иначе, если бы начинали заново?",
            "Какая ваша ошибка в той истории оказалась самой полезной?",
        ),
    ),
    "application": AtolaSpec(
        key="application",
        letter="A",
        name_ru="Применение",
        name_en="Application",
        questions=(
            "Приведите пример, когда вы применили эти выводы в другой ситуации.",
        ),
        probes=(
            "Где вы применили этот вывод потом — в другой ситуации?",
            "Что вы изменили в своём подходе в следующем проекте?",
        ),
    ),
}


@dataclass(frozen=True)
class Indicator:
    """Поведенческий индикатор BARS.

    ``text`` — дословная формулировка заказчика, менять нельзя: на неё
    ссылаются и генерация корпуса, и объяснение балла в интерфейсе.
    """

    id: str
    level: Level
    text: str
    #: Элементы ATOLA, в которых индикатор обычно наблюдаем.
    #: Служебное поле для подсказок интервьюеру, не часть рубрики заказчика.
    atola_focus: tuple[AtolaElement, ...] = ()
    source: str = SOURCE_BARS


@dataclass(frozen=True)
class LevelSpec:
    """Один уровень проявления компетенции."""

    level: Level
    label_ru: str
    #: Дословная сводная формулировка уровня из §5.4.
    verbatim: str
    indicators: tuple[Indicator, ...]


@dataclass(frozen=True)
class Competency:
    """Компетенция с трёхуровневой BARS-шкалой."""

    id: str
    name_ru: str
    name_en: str
    #: Что именно проверяет компетенция — формулировка из §5.3.
    definition_ru: str
    levels: dict[Level, LevelSpec] = field(default_factory=dict)
    scorable: bool = True

    def indicators(self, level: Level | None = None) -> tuple[Indicator, ...]:
        if level is not None:
            return self.levels[level].indicators
        return tuple(ind for lv in LEVELS for ind in self.levels[lv].indicators)

    def indicator(self, indicator_id: str) -> Indicator:
        for ind in self.indicators():
            if ind.id == indicator_id:
                return ind
        raise KeyError(indicator_id)


_WEAK = (
    Indicator("lead.weak.1", "weak", "нет конкретных ситуаций, общие фразы",
              ("action",)),
    Indicator("lead.weak.2", "weak", "инициативу не проявляет",
              ("action", "thinking")),
    Indicator("lead.weak.3", "weak", "не организует других",
              ("action",)),
    Indicator("lead.weak.4", "weak", "избегает ответственности",
              ("outcome", "learnings")),
    Indicator("lead.weak.5", "weak", "не может описать свой вклад",
              ("action", "outcome")),
)

_NORMAL = (
    Indicator("lead.normal.1", "normal", "отдельные примеры лидерства ограниченного масштаба",
              ("action", "outcome")),
    Indicator("lead.normal.2", "normal", "может организовать небольшой процесс",
              ("action",)),
    Indicator("lead.normal.3", "normal", "берёт ответственность чаще по необходимости",
              ("action", "thinking")),
    Indicator("lead.normal.4", "normal", "справляется с трудностями без системного подхода",
              ("thinking", "learnings")),
    Indicator("lead.normal.5", "normal", "роль в результатах умеренная",
              ("outcome",)),
)

_STRONG = (
    Indicator("lead.strong.1", "strong", "чёткие конкретные примеры",
              ("action", "outcome")),
    Indicator("lead.strong.2", "strong", "запускает проекты и объединяет людей",
              ("action",)),
    Indicator("lead.strong.3", "strong", "распределяет задачи, поддерживает, решает конфликты",
              ("action", "thinking")),
    Indicator("lead.strong.4", "strong", "берёт ответственность за последствия и исправляет ошибки",
              ("outcome", "learnings")),
    Indicator("lead.strong.5", "strong", "доводит до результата в сложных обстоятельствах",
              ("outcome", "application")),
)


LEADERSHIP = Competency(
    id="leadership",
    name_ru="Лидерские способности",
    name_en="Leadership",
    definition_ru="уже проявленное лидерство через реальные действия",
    levels={
        "weak": LevelSpec(
            level="weak",
            label_ru="Слабо",
            verbatim=(
                "нет конкретных ситуаций, общие фразы; инициативу не проявляет; "
                "не организует других; избегает ответственности; "
                "не может описать свой вклад"
            ),
            indicators=_WEAK,
        ),
        "normal": LevelSpec(
            level="normal",
            label_ru="Нормально",
            verbatim=(
                "отдельные примеры лидерства ограниченного масштаба; "
                "может организовать небольшой процесс; "
                "берёт ответственность чаще по необходимости; "
                "справляется с трудностями без системного подхода; "
                "роль в результатах умеренная"
            ),
            indicators=_NORMAL,
        ),
        "strong": LevelSpec(
            level="strong",
            label_ru="Высоко",
            verbatim=(
                "чёткие конкретные примеры; запускает проекты и объединяет людей; "
                "распределяет задачи, поддерживает, решает конфликты; "
                "берёт ответственность за последствия и исправляет ошибки; "
                "доводит до результата в сложных обстоятельствах"
            ),
            indicators=_STRONG,
        ),
    },
)

#: Компетенции MVP. Остальные восемь добавляются на этапе внедрения.
COMPETENCIES: dict[str, Competency] = {LEADERSHIP.id: LEADERSHIP}

#: Этическая граница (docs/01-context.md §8.1): по этим блокам модель
#: не выставляет численный балл ни при каких условиях. Она только отмечает,
#: что тема прозвучала, и предлагает интервьюеру уточняющие вопросы.
NEVER_SCORED_BLOCKS: tuple[str, ...] = ("wounded_leadership", "values")

#: Фоновые признаки (docs/01-context.md §8.2). Никогда не входят в модель
#: как предикторы. Хранятся только как метаданные корпуса для fairness-аудита.
BACKGROUND_ATTRIBUTES: tuple[str, ...] = (
    "settlement",   # город / село
    "school_type",  # сильная школа / обычная
    "language",     # русский / казахский / смешанный
    "polish",       # «отполированность» речи
    "income",       # статус семьи
)


def competency(competency_id: str = LEADERSHIP.id) -> Competency:
    """Компетенция по идентификатору."""
    return COMPETENCIES[competency_id]


def indicator_texts(level: Level, competency_id: str = LEADERSHIP.id) -> tuple[str, ...]:
    """Только формулировки индикаторов одного уровня.

    Именно это — и ничего больше — попадает в промпт генерации корпуса:
    слова «слабый», «сильный», «хороший кандидат» в промпт не передаются,
    иначе метка станет пересказом суждения модели, а не свойством текста.
    """
    return tuple(ind.text for ind in competency(competency_id).indicators(level))


def atola_questions() -> dict[AtolaElement, tuple[str, ...]]:
    """Вопросы методологии по каждому элементу ATOLA."""
    return {key: ATOLA[key].questions for key in ATOLA_ORDER}


def atola_probes() -> dict[AtolaElement, tuple[str, ...]]:
    """Уточняющие вопросы по каждому элементу ATOLA."""
    return {key: ATOLA[key].probes for key in ATOLA_ORDER}


if __name__ == "__main__":
    comp = competency()
    print(f"{comp.name_ru} ({comp.name_en}) — {comp.definition_ru}")
    print(f"источник: {SOURCE_BARS}\n")
    for lv in LEVELS:
        spec = comp.levels[lv]
        print(f"[{lv}] {spec.label_ru}")
        for ind in spec.indicators:
            focus = "/".join(ATOLA[e].letter for e in ind.atola_focus)
            print(f"   {ind.id:<17} {ind.text}  ({focus})")
        print()
    print("ATOLA —", SOURCE_ATOLA)
    for key in ATOLA_ORDER:
        spec = ATOLA[key]
        print(f"  {spec.letter} · {spec.name_ru} / {spec.name_en}")
        for q in spec.questions:
            print(f"      вопрос:    {q}")
        for p in spec.probes:
            print(f"      уточнение: {p}")
    print("\nне скорится:", ", ".join(NEVER_SCORED_BLOCKS))
    print("не входит в модель:", ", ".join(BACKGROUND_ATTRIBUTES))
