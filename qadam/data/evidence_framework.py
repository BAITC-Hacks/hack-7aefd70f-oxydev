"""Qadam Evidence Framework v0.1 — provisional, not inVision U methodology.

The framework defines what evidence a structured conversation should collect.
It must not be presented as a validated admission test until content and score
interpretation are reviewed by inVision U and evaluated with expert raters.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EvidenceLevel:
    key: str
    label: str
    anchor: str


@dataclass(frozen=True)
class EvidenceCompetency:
    id: str
    name_en: str
    name_ru: str
    construct: str
    prompt_en: str
    prompt_ru: str
    probes: tuple[str, ...]
    levels: tuple[EvidenceLevel, ...]
    decision_mode: str = "human_review"
    status: str = "qadam_provisional"


def levels(low: str, middle: str, high: str) -> tuple[EvidenceLevel, ...]:
    return (
        EvidenceLevel("insufficient", "Недостаточно свидетельств", low),
        EvidenceLevel("emerging", "Проявляется", middle),
        EvidenceLevel("consistent", "Устойчиво проявляется", high),
    )


FRAMEWORK: tuple[EvidenceCompetency, ...] = (
    EvidenceCompetency(
        "university_motivation", "University motivation", "Мотивация на университет",
        "Осознанность выбора среды inVision U и личная готовность участвовать в ней.",
        "Why is inVision U the right environment for your next step, and what will you contribute?",
        "Почему именно среда inVision U подходит для вашего следующего шага и какой вклад вы внесёте?",
        ("Какой элемент университета связан с вашей конкретной целью?", "Что вы будете делать, если ожидания не совпадут с реальностью?"),
        levels("Только общие похвалы или пересказ сайта.", "Названы конкретная возможность и личная цель.", "Есть проверенная связь целей, среды и собственного вклада, включая реалистичные ограничения."),
    ),
    EvidenceCompetency(
        "field_motivation", "Field motivation", "Мотивация на специальность",
        "Устойчивый интерес к выбранной области, подтверждённый действиями.",
        "What have you already done to explore this field, and what did it teach you?",
        "Что вы уже сделали, чтобы исследовать выбранную область, и чему это вас научило?",
        ("Что оказалось сложнее ожиданий?", "Какой следующий эксперимент или проект вы сделаете?"),
        levels("Интерес заявлен без действий.", "Есть один конкретный опыт и вывод.", "Есть последовательность самостоятельных проб, корректировка выбора и следующий проверяемый шаг."),
    ),
    EvidenceCompetency(
        "leadership", "Leadership", "Лидерские способности",
        "Инициатива, организация других и ответственность за результат.",
        "Tell us about a time you took responsibility and helped others move toward a result.",
        "Расскажите о случае, когда вы взяли ответственность и помогли другим прийти к результату.",
        ("Что сделали лично вы?", "Почему выбрали этот подход?", "Что изменилось и что вы применили позже?"),
        levels("Нет конкретной ситуации или личного вклада.", "Организован ограниченный процесс; результат и рефлексия частично подтверждены.", "Инициатива объединяет людей, доводится до результата, ошибки признаются, вывод переносится в новую ситуацию."),
        decision_mode="experimental_model_plus_human",
        status="published_example_extended_by_qadam",
    ),
    EvidenceCompetency(
        "teamwork", "Teamwork", "Работа в команде",
        "Совместная работа, включение разных позиций и восстановление взаимодействия.",
        "Describe a disagreement in a team and how you helped the team continue working.",
        "Опишите разногласие в команде и как вы помогли команде продолжить работу.",
        ("Чью позицию вы сначала не понимали?", "Как изменился ваш собственный подход?"),
        levels("Ответ обвиняет других или не показывает взаимодействия.", "Кандидат слушает и выполняет свою роль, но решение ситуативно.", "Кандидат соединяет позиции, распределяет ответственность и улучшает способ совместной работы."),
    ),
    EvidenceCompetency(
        "values", "Values in action", "Ценности в действии",
        "Как кандидат принимает сложные решения при конфликте интересов; не оценка «правильной личности».",
        "Tell us about a difficult choice where two important principles conflicted.",
        "Расскажите о сложном выборе, в котором столкнулись два важных принципа.",
        ("Кого затронуло решение?", "Какой риск вы приняли?", "Что бы вы пересмотрели сейчас?"),
        levels("Не применяется: чувствительный блок.", "Фиксируются аргументы и затронутые стороны.", "Интерпретацию выполняет только подготовленный человек, без автоматического балла."),
        decision_mode="human_only",
    ),
    EvidenceCompetency(
        "experience", "Applied experience", "Практический опыт",
        "Способность превращать участие в конкретный личный вклад и проверяемый результат.",
        "Which project or responsibility best shows what you can already do?",
        "Какой проект или ответственность лучше всего показывает, что вы уже умеете?",
        ("Какой артефакт или результат можно показать?", "Что было сделано другими?"),
        levels("Перечислены роли без личных действий.", "Есть конкретная задача, вклад и результат.", "Есть несколько итераций, проверка результата и ясное понимание границ собственного вклада."),
    ),
    EvidenceCompetency(
        "learning_agility", "Learning agility", "Обучаемость и мышление",
        "Как кандидат разбирает незнакомую задачу, проверяет гипотезы и меняет мнение.",
        "Tell us about something difficult you learned without a ready-made path.",
        "Расскажите о сложной вещи, которой вы научились без готового пути.",
        ("Как вы проверяли, что поняли правильно?", "Когда и почему поменяли подход?"),
        levels("Есть только утверждение о способностях.", "Показаны шаги обучения и одна корректировка.", "Показаны гипотезы, обратная связь, смена стратегии и перенос способа обучения."),
    ),
    EvidenceCompetency(
        "purpose_leadership", "Purpose-driven leadership", "Лидерство со смыслом",
        "Связь инициативы с проблемой людей и долгосрочным эффектом, без оценки масштаба привилегий.",
        "What problem affecting other people would you keep working on even when progress is slow?",
        "Над какой проблемой, затрагивающей других людей, вы продолжили бы работать даже при медленном прогрессе?",
        ("Откуда вы знаете, что проблема важна людям?", "Как избежите решения проблемы за них?"),
        levels("Есть лозунг без контакта с проблемой.", "Есть конкретная группа, действие и обратная связь.", "Люди включены в постановку задачи; кандидат учитывает последствия и строит устойчивый способ работы."),
    ),
    EvidenceCompetency(
        "wounded_leadership", "Growth through adversity", "Развитие через трудности",
        "Добровольная рефлексия о трудности и поддержке; травма и раскрытие личного опыта не поощряются баллом.",
        "Optionally, tell us about a challenge that changed how you support yourself or others.",
        "По желанию расскажите о трудности, которая изменила то, как вы поддерживаете себя или других.",
        ("Можно не отвечать или выбрать учебный пример.", "Какая поддержка была полезна?"),
        levels("Не применяется: отсутствие раскрытия не является слабым сигналом.", "Человек может отметить наблюдаемую рефлексию без диагноза.", "Автоматическая оценка и сравнение кандидатов запрещены."),
        decision_mode="human_only_optional",
        status="sensitive_unscored",
    ),
)


FRAMEWORK_VERSION = "qef-0.1.0"
FRAMEWORK_NOTICE = (
    "Provisional Qadam framework. Not approved by inVision U and not valid for "
    "admission decisions. It structures evidence for expert review."
)


def framework_payload() -> dict:
    return {
        "version": FRAMEWORK_VERSION,
        "notice": FRAMEWORK_NOTICE,
        "scale": "insufficient evidence → emerging → consistently demonstrated",
        "competencies": [asdict(item) for item in FRAMEWORK],
    }
