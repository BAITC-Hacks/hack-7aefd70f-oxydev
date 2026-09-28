# -*- coding: utf-8 -*-
"""Слой 4 — ОБЪЯСНЕНИЕ.

Собирает то, что комиссия увидит вместо балла: вклад каждого признака, цитату-якорь
под каждый сработавший индикатор, подсказки интервьюеру и черновик обратной связи
кандидату.

Правила, зашитые в модуль:

* под каждым утверждением стоит цитата из ответа — иначе утверждение не выводится;
* признак «текст похож на сгенерированный» не снижает балл, он запускает
  уточняющие вопросы (docs/METHODOLOGY.md);
* по блокам Wounded leadership и Ценности модель не выставляет численный балл,
  а только отмечает, что тема прозвучала (§8.1);
* фоновые признаки не участвуют ни в балле, ни в объяснении.
"""

from __future__ import annotations

import re
from typing import Sequence

from qadam.core.extract import Extraction
from qadam.core.features import FEATURE_BY_NAME, compute
from qadam.core.model import LeadershipModel, Prediction
from qadam.data.rubric import (
    ATOLA,
    ATOLA_ORDER,
    AtolaElement,
    LEADERSHIP,
    LEVEL_LABELS_RU,
    Level,
    NEVER_SCORED_BLOCKS,
)

_INDICATOR_BY_TEXT = {ind.text: ind for ind in LEADERSHIP.indicators()}
_INDICATOR_BY_ID = {ind.id: ind for ind in LEADERSHIP.indicators()}

#: Темы, по которым модель не имеет права выставлять балл. Только отметка,
#: что тема прозвучала, и передача решения человеку.
_SENSITIVE_RE = re.compile(
    r"\b(болезн|больниц|операци|умер|смерт|похорон|развод|развел|детдом|"
    r"интернат|сирот|инвалид|диагноз|долг|нищет|бедност|голод|"
    r"ауру|қайтыс|ажырас|мүгедек|жетім)", re.IGNORECASE)

#: Маркеры «причёсанного» текста. Никогда не влияют на балл.
_POLISHED_RE = re.compile(
    r"(таким образом|прежде всего|помимо этого|в первую очередь|"
    r"важной точкой роста|системно подходить|данный опыт)", re.IGNORECASE)

_LOW_CONCRETENESS = 4.0
_HIGH_VAGUENESS = 0.35


def _quote_or_none(extraction: Extraction, element: AtolaElement) -> str | None:
    slot = extraction.atola.get(element)
    return slot.quote if slot and slot.present else None


def atola_breakdown(extraction: Extraction) -> list[dict]:
    """Пять элементов: найден, цитата, вопрос методологии, что спросить дополнительно."""
    out = []
    for element in ATOLA_ORDER:
        spec = ATOLA[element]
        quote = _quote_or_none(extraction, element)
        out.append({
            "element": element,
            "letter": spec.letter,
            "name": spec.name_ru,
            "present": quote is not None,
            "quote": quote,
            "questions": list(spec.questions),
            "probes": [] if quote else list(spec.probes),
        })
    return out


def indicator_breakdown(extraction: Extraction) -> list[dict]:
    """Сработавшие индикаторы BARS с цитатой-якорем."""
    out = []
    seen: set[str] = set()
    for hit in extraction.indicators:
        indicator = (_INDICATOR_BY_ID.get(hit.indicator_id or "")
                     or _INDICATOR_BY_TEXT.get(hit.text.strip()))
        if indicator is None or indicator.id in seen:
            continue
        seen.add(indicator.id)
        out.append({
            "indicator_id": indicator.id,
            "text": indicator.text,
            "level": indicator.level,
            "level_label": LEVEL_LABELS_RU[indicator.level],
            "quote": hit.quote,
            "atola_element": hit.atola_element,
        })
    order = {"strong": 0, "normal": 1, "weak": 2}
    return sorted(out, key=lambda item: (order[item["level"]], item["indicator_id"]))


def feature_breakdown(prediction: Prediction, values: dict[str, float],
                      top_n: int = 8) -> list[dict]:
    """Вклад признаков в логит выбранного класса, по убыванию модуля."""
    items = []
    for name, contribution in prediction.contributions.items():
        spec = FEATURE_BY_NAME[name]
        items.append({
            "name": name,
            "label": spec.label,
            "group": spec.group,
            "value": round(values[name], 3),
            "contribution": round(contribution, 3),
            "direction": spec.direction,
        })
    items.sort(key=lambda item: -abs(item["contribution"]))
    return items[:top_n]


def interviewer_hints(extraction: Extraction, values: dict[str, float],
                      text: str) -> list[dict]:
    """Что копнуть на интервью. Каждая подсказка — с причиной и вопросом."""
    hints: list[dict] = []
    for element in ATOLA_ORDER:
        if _quote_or_none(extraction, element) is None:
            spec = ATOLA[element]
            hints.append({
                "kind": "atola_gap",
                "title": f"Не прозвучал элемент «{spec.name_ru}»",
                "reason": "В ответе нет фрагмента, который отвечал бы на вопрос: "
                          + spec.questions[0],
                "questions": list(spec.probes[:2]),
            })

    if values["concreteness_index"] < _LOW_CONCRETENESS:
        hints.append({
            "kind": "low_concreteness",
            "title": "Мало конкретики",
            "reason": f"Индекс конкретности {values['concreteness_index']:.1f}: "
                      "почти нет чисел, сроков и названий ролей.",
            "questions": ["Сколько человек это затронуло и за какой срок?",
                          "Какую роль вы занимали формально?"],
        })

    if values["vagueness_index"] > _HIGH_VAGUENESS:
        hints.append({
            "kind": "vagueness",
            "title": "Похоже на социально ожидаемый ответ",
            "reason": f"Индекс неконкретности {values['vagueness_index']:.2f}: "
                      "утверждения о себе вообще, без ситуации.",
            "questions": ["Вспомните один конкретный случай с датой и местом.",
                          "Что было вашим личным вкладом, а не команды?"],
        })

    if values["i_we_ratio"] < 0.5:
        hints.append({
            "kind": "we_without_i",
            "title": "«Мы» без личного вклада",
            "reason": f"Доля «я» против «мы» — {values['i_we_ratio']:.2f}.",
            "questions": ["Что из перечисленного сделали лично вы?",
                          "Что бы не случилось, если бы вас в той команде не было?"],
        })

    if _POLISHED_RE.search(text) and values["concreteness_index"] < _LOW_CONCRETENESS:
        hints.append({
            "kind": "polished_text",
            "title": "Текст выглядит отредактированным",
            "reason": "Это НЕ снижает балл. Признак используется только как повод "
                      "задать вопросы о деталях собственной истории кандидата.",
            "questions": [ATOLA["action"].probes[0], ATOLA["outcome"].probes[0]],
        })
    return hints


def sensitive_topics(text: str) -> list[dict]:
    """Отметка о темах, которые модель не оценивает (§8.1)."""
    if not _SENSITIVE_RE.search(text):
        return []
    return [{
        "blocks": list(NEVER_SCORED_BLOCKS),
        "note": "В ответе прозвучала тема трудного личного опыта. По блокам "
                "Wounded leadership и Ценности модель не выставляет балл: "
                "оценку даёт человек. Ниже — только уточняющие вопросы методологии.",
        "questions": [ATOLA["learnings"].probes[0], ATOLA["application"].probes[0]],
    }]


def candidate_feedback(level: Level, extraction: Extraction,
                       values: dict[str, float]) -> dict:
    """Черновик обратной связи кандидату: что развивать, без вердикта."""
    strengths: list[str] = []
    growth: list[str] = []

    for element in ATOLA_ORDER:
        spec = ATOLA[element]
        if _quote_or_none(extraction, element):
            strengths.append(f"вы рассказали про «{spec.name_ru.lower()}»")
        else:
            growth.append(
                f"добавьте «{spec.name_ru.lower()}»: {spec.questions[0].lower()}")

    if values["concreteness_index"] >= _LOW_CONCRETENESS:
        strengths.append("в рассказе есть числа, сроки и конкретные роли")
    else:
        growth.append("назовите числа и сроки: сколько человек, за какое время, "
                      "что изменилось количественно")

    if values["i_we_ratio"] < 0.5:
        growth.append("разделите «мы» и «я»: какая часть работы была ваша лично")
    if values["trajectory_delta"] < 0.5:
        growth.append("покажите перенос: где вы применили этот вывод в другой ситуации")

    return {
        "level": level,
        "level_label": LEVEL_LABELS_RU[level],
        "disclaimer": "Черновик для интервьюера. Это не решение о поступлении: "
                      "финальное решение принимает приёмная комиссия.",
        "strengths": strengths[:4],
        "growth": growth[:4],
    }


def explain(model: LeadershipModel, text: str, extraction: Extraction) -> dict:
    """Полный разбор одного ответа для интерфейса и API."""
    prediction = model.explain(text, extraction)
    values = compute(text, extraction)
    confidence = max(prediction.probabilities.values())
    review_reasons: list[str] = []
    if confidence < 0.60:
        review_reasons.append("у модели нет достаточно уверенного ведущего класса")
    if prediction.margin < 0.20:
        review_reasons.append("два наиболее вероятных уровня находятся близко")
    if values["atola_coverage"] < 0.60:
        review_reasons.append("в ответе подтверждено меньше трёх элементов ATOLA")
    if "fallback" in extraction.backend:
        review_reasons.append("облачное извлечение недоступно, использован локальный fallback")
    if extraction.dropped_quotes:
        review_reasons.append("часть предложенных цитат не прошла дословную проверку")

    needs_review = bool(review_reasons)
    if needs_review:
        route = "manual_review"
        recommendation = "Передать интервьюеру на ручную проверку"
    elif prediction.level == "strong":
        route = "priority_interview"
        recommendation = "Приоритетно рассмотреть на интервью"
    else:
        route = "standard_interview"
        recommendation = "Рассмотреть в стандартном порядке"

    return {
        "level": prediction.level,
        "level_label": LEVEL_LABELS_RU[prediction.level],
        "probabilities": prediction.probabilities,
        "margin": round(prediction.margin, 3),
        "atola": atola_breakdown(extraction),
        "atola_coverage": values["atola_coverage"],
        "indicators": indicator_breakdown(extraction),
        "features": feature_breakdown(prediction, values),
        "text_contribution": round(prediction.text_contribution, 3),
        "hints": interviewer_hints(extraction, values, text),
        "sensitive": sensitive_topics(text),
        "feedback": candidate_feedback(prediction.level, extraction, values),
        "backend": extraction.backend,
        "dropped_quotes": extraction.dropped_quotes,
        "decision_support": {
            "route": route,
            "recommendation": recommendation,
            "needs_manual_review": needs_review,
            "reasons": review_reasons,
            "confidence": round(confidence, 3),
            "policy": "Система не отказывает кандидату; финальное решение принимает комиссия.",
            "thresholds": {
                "min_confidence": 0.60,
                "min_margin": 0.20,
                "min_atola_coverage": 0.60,
                "status": "MVP — подлежат калибровке с методологами",
            },
        },
    }
