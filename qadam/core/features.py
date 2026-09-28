# -*- coding: utf-8 -*-
"""Слой 2 — ПРИЗНАКИ. Чистый Python, никаких обращений к LLM.

Признаки считаются детерминированно из текста и результата слоя извлечения.
Это то, что делает балл воспроизводимым и предъявляемым: каждое число здесь
можно пересчитать руками на глазах у комиссии.

Чего в признаках нет и не будет (docs/METHODOLOGY.md): региона, типа школы,
языка ответа, дохода семьи, пола говорящего и любых их прокси. Проверяется
функцией :func:`assert_no_background_features` и контрфактическим аудитом.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from qadam.core.extract import Extraction
from qadam.data.rubric import ATOLA_ORDER, LEADERSHIP, LEVELS, Level

FeatureGroup = Literal["atola", "concreteness", "vagueness", "agency",
                       "trajectory", "indicators", "control"]


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    label: str
    group: FeatureGroup
    #: Как читать вклад признака: рост признака работает в плюс или в минус.
    direction: Literal["up", "down", "neutral"] = "up"


FEATURE_SPECS: tuple[FeatureSpec, ...] = (
    FeatureSpec("atola_action", "ATOLA: Действие", "atola"),
    FeatureSpec("atola_thinking", "ATOLA: Мышление", "atola"),
    FeatureSpec("atola_outcome", "ATOLA: Результат", "atola"),
    FeatureSpec("atola_learnings", "ATOLA: Выводы", "atola"),
    FeatureSpec("atola_application", "ATOLA: Применение", "atola"),
    FeatureSpec("atola_coverage", "Покрытие ATOLA, доля", "atola"),
    FeatureSpec("numbers_density", "Плотность чисел и количеств", "concreteness"),
    FeatureSpec("timeframes_density", "Плотность сроков", "concreteness"),
    FeatureSpec("roles_density", "Плотность ролей и должностей", "concreteness"),
    FeatureSpec("first_person_density", "Плотность глаголов 1 лица", "concreteness"),
    FeatureSpec("concreteness_index", "Индекс конкретности", "concreteness"),
    FeatureSpec("cliche_density", "Плотность клише", "vagueness", "down"),
    FeatureSpec("abstract_noun_density", "Плотность отглагольных абстракций", "vagueness", "down"),
    FeatureSpec("vagueness_index", "Индекс неконкретности", "vagueness", "down"),
    FeatureSpec("i_we_ratio", "Доля личного «я» против «мы»", "agency"),
    FeatureSpec("trajectory_delta", "Дельта траектории «было → стало»", "trajectory"),
    FeatureSpec("indicator_hits_weak", "Индикаторы уровня «Слабо»", "indicators", "down"),
    FeatureSpec("indicator_hits_normal", "Индикаторы уровня «Нормально»", "indicators", "neutral"),
    FeatureSpec("indicator_hits_strong", "Индикаторы уровня «Высоко»", "indicators"),
    FeatureSpec("indicator_balance", "Перевес индикаторов в сторону «Высоко»", "indicators"),
    FeatureSpec("length_tokens", "Длина ответа, токенов", "control", "neutral"),
)

FEATURE_NAMES: tuple[str, ...] = tuple(spec.name for spec in FEATURE_SPECS)
FEATURE_BY_NAME: dict[str, FeatureSpec] = {s.name: s for s in FEATURE_SPECS}

#: Признак-контроль. Нужен, чтобы честно сравниться с baseline «только длина»,
#: и чтобы было видно, что модель не сводится к многословности.
CONTROL_FEATURES: tuple[str, ...] = ("length_tokens",)

#: Слова, по которым можно догадаться о регионе, школе, языке или поле.
#: Ни одно из них не имеет права стать признаком.
_BACKGROUND_MARKERS = ("settlement", "village", "city", "school_type", "language",
                       "gender", "income", "село", "город", "школа", "язык", "пол")


def assert_no_background_features() -> None:
    """Фоновых признаков среди фич быть не должно."""
    bad = [name for name in FEATURE_NAMES
           if any(marker in name.lower() for marker in _BACKGROUND_MARKERS)]
    if bad:
        raise AssertionError(f"фоновый признак попал в модель: {bad}")


assert_no_background_features()


# --------------------------------------------------------------------------- #
# Лексиконы
# --------------------------------------------------------------------------- #

#: Клише и социально ожидаемые формулировки: утверждения без содержания.
#: Сюда сознательно НЕ включены стилевые связки («в рамках данной работы»,
#: «прежде всего», «ну», «короче») и вежливые концовки. Они характеризуют
#: манеру речи, а не содержание ответа, и наказывать за них — значит наказывать
#: за канцелярит или за разговорную речь (см. docs/METHODOLOGY.md).
_CLICHES = (
    r"для меня лидерство",
    r"лидер должен быть примером",
    r"главное\s*—?\s*быть",
    r"важно уметь",
    r"надо быть активнее",
    r"работать в коллективе",
    r"находить общий язык",
    r"не остаюсь в стороне",
    r"помогаю там, где нужно",
    r"всегда и во вс[её]м",
    r"в любой ситуации",
    r"по жизни",
    r"все остались довольны",
    r"прошло нормально",
    r"результат был хороший",
    r"получилось неплохо",
    r"занимались этим все вместе",
    r"подходить к ней системно",
    r"считаю приоритетом",
    r"раст[её]т вместе со своей командой",
    r"качество, которое я в себе развиваю",
    r"быть ответственным",
    r"не подводить",
    r"көшбасшылық\s*—?\s*ең алдымен жауапкершілік",
    r"маңызды деп ойлаймын",
    r"жүйелі шешуге болады",
    r"белсендірек болу керек",
    r"үлгі болуы керек",
    r"бәрі жақсы өтті",
    r"қалыс қалмаймын",
    r"көмек керек жерде көмектесемін",
)
_CLICHE_RE = re.compile("|".join(_CLICHES), re.IGNORECASE)

#: Отглагольные существительные и абстракции: «развитие», «ответственность»,
#: «взаимодействие». Признак «воды», не зависящий от конкретного лексикона.
_ABSTRACT_RE = re.compile(
    r"\b[а-яё]{4,}(?:ание|ения|ение|ений|ениями|ость|ости|остью|ство|ства|нность)\b",
    re.IGNORECASE)

_I_RE = re.compile(
    r"\b(я|мне|меня|мной|мой|моя|мои|моего|своей|своего)\b|"
    r"\bмен(?:ің|де|і)?\b|"
    r"\b[а-яёқғұүөһәі]+(?:дым|дім|тым|тім|мын|мін)\b", re.IGNORECASE)
_WE_RE = re.compile(
    r"\b(мы|нас|нам|наш|наша|наши|нами)\b|\bбіз(?:де|дің)?\b|"
    r"\b[а-яёқғұүөһәі]+(?:дық|дік|тық|тік)\b", re.IGNORECASE)

#: Признак перехода «было → стало». Только внутри собственной истории кандидата:
#: сравнение с другими кандидатами или с их фоном здесь невозможно по построению.
_CHANGE_RE = re.compile(
    r"с \d+\s+(?:до|на)\s+\d+|вместо|вырос|выросла|поднял|подняла|поднялись|"
    r"стало\s+\d+|стал[оа]?\s+(?:больше|меньше|получше)|"
    r"работает до сих пор|обошлось без срывов|"
    r"өсті|көтерілді|дейін|бастады|орнына", re.IGNORECASE)

_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)
_SENT_RE = re.compile(r"[^.!?…]+")

_INDICATOR_LEVEL: dict[str, Level] = {ind.text: ind.level
                                      for ind in LEADERSHIP.indicators()}
_INDICATOR_LEVEL_BY_ID: dict[str, Level] = {ind.id: ind.level
                                            for ind in LEADERSHIP.indicators()}


def tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def _per_100(count: int, n_tokens: int) -> float:
    return 100.0 * count / max(n_tokens, 1)


def _indicator_level(hit) -> Level | None:
    if hit.indicator_id and hit.indicator_id in _INDICATOR_LEVEL_BY_ID:
        return _INDICATOR_LEVEL_BY_ID[hit.indicator_id]
    return _INDICATOR_LEVEL.get(hit.text.strip())


def compute(text: str, extraction: Extraction) -> dict[str, float]:
    """Все признаки одного ответа. Значения — только из текста и разбора."""
    toks = tokens(text)
    n_tokens = len(toks)
    n_sent = max(len([s for s in _SENT_RE.findall(text) if s.strip()]), 1)
    coverage = extraction.coverage()
    markers = extraction.concreteness_markers

    numbers_density = _per_100(len(markers.numbers), n_tokens)
    timeframes_density = _per_100(len(markers.timeframes), n_tokens)
    roles_density = _per_100(len(markers.roles), n_tokens)
    first_person_density = _per_100(len(markers.first_person_verbs), n_tokens)
    concreteness_index = (
        1.5 * numbers_density + 1.0 * timeframes_density
        + 1.0 * roles_density + 0.5 * first_person_density
    )

    cliche_hits = len(_CLICHE_RE.findall(text))
    abstract_hits = len(_ABSTRACT_RE.findall(text))
    cliche_density = cliche_hits / n_sent
    abstract_noun_density = _per_100(abstract_hits, n_tokens)
    vagueness_index = cliche_density + 0.1 * abstract_noun_density

    i_count = len(_I_RE.findall(text))
    we_count = len(_WE_RE.findall(text))
    i_we_ratio = i_count / (i_count + we_count) if (i_count + we_count) else 0.0

    has_change = bool(_CHANGE_RE.search(text))
    trajectory_delta = (0.5 * (coverage["outcome"] and has_change)
                        + 0.5 * coverage["application"])

    hits = {lv: 0 for lv in LEVELS}
    for hit in extraction.indicators:
        level = _indicator_level(hit)
        if level:
            hits[level] += 1
    total_hits = sum(hits.values())
    indicator_balance = ((hits["strong"] - hits["weak"]) / total_hits
                         if total_hits else 0.0)

    return {
        "atola_action": float(coverage["action"]),
        "atola_thinking": float(coverage["thinking"]),
        "atola_outcome": float(coverage["outcome"]),
        "atola_learnings": float(coverage["learnings"]),
        "atola_application": float(coverage["application"]),
        "atola_coverage": sum(coverage.values()) / len(ATOLA_ORDER),
        "numbers_density": numbers_density,
        "timeframes_density": timeframes_density,
        "roles_density": roles_density,
        "first_person_density": first_person_density,
        "concreteness_index": concreteness_index,
        "cliche_density": cliche_density,
        "abstract_noun_density": abstract_noun_density,
        "vagueness_index": vagueness_index,
        "i_we_ratio": i_we_ratio,
        "trajectory_delta": float(trajectory_delta),
        "indicator_hits_weak": float(hits["weak"]),
        "indicator_hits_normal": float(hits["normal"]),
        "indicator_hits_strong": float(hits["strong"]),
        "indicator_balance": indicator_balance,
        "length_tokens": float(n_tokens),
    }


def vector(text: str, extraction: Extraction) -> list[float]:
    values = compute(text, extraction)
    return [values[name] for name in FEATURE_NAMES]


def matrix(texts: list[str], extractions: list[Extraction]) -> list[list[float]]:
    return [vector(t, e) for t, e in zip(texts, extractions)]


if __name__ == "__main__":
    import json
    from statistics import mean

    from qadam.core.extract import extract
    from qadam.data.generate import CORPUS_FILE, read_jsonl

    rows = read_jsonl(CORPUS_FILE)
    by_level: dict[str, list[dict[str, float]]] = {lv: [] for lv in LEVELS}
    for row in rows:
        by_level[row["level"]].append(compute(row["text"], extract(row["text"])))

    print(f"{'признак':<26}" + "".join(f"{lv:>10}" for lv in LEVELS))
    for name in FEATURE_NAMES:
        line = f"{name:<26}"
        for lv in LEVELS:
            line += f"{mean(v[name] for v in by_level[lv]):>10.2f}"
        print(line)
    print(json.dumps({"n": len(rows), "features": len(FEATURE_NAMES)}, ensure_ascii=False))
