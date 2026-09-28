# -*- coding: utf-8 -*-
"""Слой 1 — ИЗВЛЕЧЕНИЕ. LLM структурирует ответ и цитирует, но не оценивает.

Контракт слоя (docs/02-solution-spec.md §2):

* на выходе строгий JSON по схеме :class:`Extraction`;
* каждая цитата обязана дословно встречаться в исходном тексте — иначе она
  отбрасывается как галлюцинация;
* поля с уровнем, баллом или суждением в схеме отсутствуют, и если модель
  всё-таки их вернёт, они игнорируются;
* один вызов на ответ, temperature=0, результат кэшируется на диск по хэшу.

Два бэкенда:

* ``groq`` — основной облачный путь для MVP, нужен GROQ_API_KEY;
* ``anthropic`` — альтернативный облачный путь, нужен ANTHROPIC_API_KEY;
* ``heuristic`` — детерминированный оффлайновый разбор по маркерам речи. Нужен,
  чтобы вся цепочка (обучение, метрики, fairness, демо) поднималась без ключа и
  без сети. Он беднее LLM, и в отчёте это указано отдельной строкой.

``backend="auto"`` выбирает Groq, затем Anthropic, иначе ``heuristic``. Если
облачный провайдер недоступен, auto безопасно возвращается к эвристике.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Literal

from pydantic import BaseModel, Field, field_validator

from qadam.data.rubric import ATOLA_ORDER, AtolaElement, LEADERSHIP

PROMPT_VERSION = "extract-v1"
EXTRACT_MODEL = os.environ.get("QADAM_EXTRACT_MODEL", "claude-sonnet-5")
GROQ_MODEL = os.environ.get("QADAM_GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_API_URL = os.environ.get(
    "QADAM_GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
LLM_TIMEOUT = float(os.environ.get("QADAM_LLM_TIMEOUT", "20"))
CACHE_DIR = Path(os.environ.get(
    "QADAM_CACHE_DIR",
    Path(__file__).resolve().parent.parent / "data" / "cache" / "extract"))

Backend = Literal["auto", "groq", "anthropic", "heuristic"]


# --------------------------------------------------------------------------- #
# Схема
# --------------------------------------------------------------------------- #

class AtolaSlot(BaseModel):
    """Один элемент ATOLA: найден или нет, и цитата-подтверждение."""

    present: bool = False
    quote: str | None = None

    @field_validator("quote")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return v or None


class IndicatorHit(BaseModel):
    """Сработавший поведенческий индикатор с цитатой-якорем."""

    text: str
    quote: str
    atola_element: AtolaElement
    indicator_id: str | None = None


class ConcretenessMarkers(BaseModel):
    numbers: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=list)
    first_person_verbs: list[str] = Field(default_factory=list)


class Extraction(BaseModel):
    """Результат слоя извлечения. Уровня и балла здесь нет по построению."""

    atola: dict[AtolaElement, AtolaSlot]
    indicators: list[IndicatorHit] = Field(default_factory=list)
    concreteness_markers: ConcretenessMarkers = Field(default_factory=ConcretenessMarkers)
    backend: str = "heuristic"
    dropped_quotes: int = 0

    @field_validator("atola")
    @classmethod
    def _all_elements(cls, v: dict) -> dict:
        for key in ATOLA_ORDER:
            v.setdefault(key, AtolaSlot())
        return {k: v[k] for k in ATOLA_ORDER}

    def coverage(self) -> dict[AtolaElement, bool]:
        return {k: bool(self.atola[k].present and self.atola[k].quote) for k in ATOLA_ORDER}


# --------------------------------------------------------------------------- #
# Проверка цитат
# --------------------------------------------------------------------------- #

_WS = re.compile(r"\s+")


def _normalize(text: str) -> tuple[str, list[int]]:
    """Нормализованный текст и карта позиций обратно в оригинал."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = True
    for i, ch in enumerate(text):
        c = ch.lower().replace("ё", "е").replace(" ", " ")
        if c.isspace():
            if prev_space:
                continue
            c, prev_space = " ", True
        else:
            prev_space = False
        out.append(c)
        idx.append(i)
    while out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def find_quote(text: str, quote: str) -> str | None:
    """Возвращает дословный фрагмент исходного текста или None.

    Совпадение ищется с точностью до регистра, ё/е и пробелов: это те различия,
    которые LLM меняет при копировании, и они не делают цитату придуманной.
    Всё остальное считается галлюцинацией и отбрасывается.
    """
    if not quote or not quote.strip():
        return None
    norm_text, idx = _normalize(text)
    norm_quote, _ = _normalize(quote.strip(" \n\t«»\"'.,;:!?()"))
    if not norm_quote:
        return None
    pos = norm_text.find(norm_quote)
    if pos < 0:
        return None
    start = idx[pos]
    end = idx[pos + len(norm_quote) - 1]
    return text[start:end + 1]


def verify_quotes(extraction: Extraction, text: str) -> Extraction:
    """Отбрасывает всё, что не подтверждается дословной цитатой."""
    dropped = 0
    for key, slot in extraction.atola.items():
        found = find_quote(text, slot.quote or "")
        if slot.present and not found:
            dropped += 1
            extraction.atola[key] = AtolaSlot(present=False, quote=None)
        else:
            extraction.atola[key] = AtolaSlot(present=bool(found), quote=found)

    kept: list[IndicatorHit] = []
    for hit in extraction.indicators:
        found = find_quote(text, hit.quote)
        if found is None:
            dropped += 1
            continue
        hit.quote = found
        kept.append(hit)
    extraction.indicators = kept

    markers = extraction.concreteness_markers
    for field_name in ("numbers", "roles", "timeframes", "first_person_verbs"):
        values, seen = [], set()
        for raw in getattr(markers, field_name):
            found = find_quote(text, raw)
            if found is None:
                dropped += 1
                continue
            if found.lower() not in seen:
                seen.add(found.lower())
                values.append(found)
        setattr(markers, field_name, values)

    extraction.dropped_quotes = dropped
    return extraction


# --------------------------------------------------------------------------- #
# Оффлайновый бэкенд: маркеры речи, без LLM
# --------------------------------------------------------------------------- #

_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")

#: Речевые маркеры элементов ATOLA. Русский и казахский вперемешку — в корпусе
#: есть оба языка и code-switching.
ATOLA_CUES: dict[AtolaElement, str] = {
    "action": r"(я\s+(собра|запусти|организова|состави|распредели|раздели|договори|"
              r"предложи|поручи|отвеча|взял|взялся|взялась|посади|обзвони|набра|"
              r"закрепи|расписа|публикова|провери|поставил|поставила)|"
              r"участвую|помогаю|не остаюсь в стороне|мне (предложили|поручили)|"
              r"я стал|я стала|занимались этим|"
              r"жинап|іске қостым|ұйымдастыруға жауапты|рөлдерді бөлдім|кесте құрдым|"
              r"сұрап алдым|қатысамын|көмектесемін|келістім|тапсырды|қалыс қалмаймын)",
    "thinking": r"(потому что|поэтому|я решил|я решила|подумал|подумала|исходил|исходила|"
                r"выбрал|выбрала|считаю|я думаю|не задумывался|не задумывалась|"
                r"начать с расписания|по ситуации|надо было убрать причину|"
                r"себебі|шештім|есептедім|ойымша|деп ойлаймын|қарап істедім|деп сенемін)",
    "outcome": r"(в итоге|в результате|результат|стало|стали|вырос|выросла|поднялись|"
               r"поднялась|собрали|получилось|продержались|привезли|работает до сих пор|"
               r"все остались довольны|прошло нормально|"
               r"нәтижесінде|нәтижесі|өсті|көтерілді|жинадық|жеткіздік|бастады|"
               r"жүрдік|өтті|жаман болмады)",
    "learnings": r"(я понял|я поняла|^понял|^поняла|понял, что|поняла, что|вынес|вынесла|"
                 r"научил|тогда я понял|тогда я поняла|для себя|"
                 r"түсіндім|екенін түсіндім)",
    "application": r"(потом\b|позже|через год|в следующ|на следующ|на спартакиаду|"
                   r"применять|применил|применила|пригодится|в любой ситуации|"
                   r"всегда и во всём|всегда и во всем|когда летом|осенью|"
                   r"кейін|келесі|бекітіп қойдым|жаздым|бөлдік)",
}

#: Маркеры поведенческих индикаторов BARS. Ключ — id индикатора из rubric.py.
INDICATOR_CUES: dict[str, str] = {
    "lead.weak.1": r"(часто участвую|обычно не остаюсь|занимались этим все вместе|"
                   r"всегда и во всём|всегда и во всем|в любой ситуации|"
                   r"для меня лидерство|важно уметь|быть активнее|в коллективе|"
                   r"общий язык|лидер должен быть примером|қатысамын|қалыс қалмаймын)",
    "lead.weak.2": r"(особо не задумывался|особо не задумывалась|делал как принято|"
                   r"делала как принято|больше было некому|аса ойланбадым)",
    "lead.weak.3": r"(помогаю там, где нужно|не остаюсь в стороне|көмектесемін)",
    "lead.weak.4": r"(точных цифр я не назову|не назову|не помню|"
                   r"занялся уже кто-то другой|айта алмаймын)",
    "lead.weak.5": r"(мы занимались этим|результат был хороший|прошло нормально|"
                   r"все остались довольны|бәрі жақсы өтті)",
    "lead.normal.1": r"(потом я так же|потом я также|позже пробовал|позже пробовала|"
                     r"получилось так|осылай жинадым|нәтижесі мынадай)",
    "lead.normal.2": r"(я отвечал за|я отвечала за|собирал ребят|собирала ребят|"
                     r"напоминал|напоминала|начать с расписания|"
                     r"жауапты болдым|кестеден бастауды)",
    "lead.normal.3": r"(мне предложили этим заняться|мне поручили|больше было некому|"
                     r"я согласился|я согласилась|я взялся|я взялась|тапсырды|келістім)",
    "lead.normal.4": r"(по ситуации|где-то просил|где-то просила|как-то само|"
                     r"просто попросил|просто попросила|без напоминаний|"
                     r"қарап істедім|ұмытып кететінін)",
    "lead.normal.5": r"(всё-таки продержались|все-таки продержались|всё-таки привезли|"
                     r"стали получше|стали меньше|заметно больше|"
                     r"осылай жүрдік|әйтеуір жеткіздік)",
    "lead.strong.1": r"(надо было убрать причину|понятный график|видимый результат|"
                     r"я выбрал такой порядок|я выбрала такой порядок|"
                     r"түсінікті кесте|көрінетін нәтиже)",
    "lead.strong.2": r"(я собрал|я собрала|я набрал|я набрала|запустил|запустила|"
                     r"сам предложил|сама предложила|жинап|іске қостым)",
    "lead.strong.3": r"(распределил роли|распределила роли|разделил задачи|"
                     r"разделила задачи|кто за что|кто ищет материал|посадил обоих|"
                     r"посадила обоих|договорились о порядке|разобрал это с ними|"
                     r"разобрала это с ними|рөлдерді бөлдім|тапсырманы бөлдім|"
                     r"қатар отырғызып)",
    "lead.strong.4": r"(провалили, потому что|не проверил|не проверила|не распределил|"
                     r"не распределила|почти забросил|почти забросила|тогда я понял|"
                     r"тогда я поняла|самый провальный|толку от этого не было|"
                     r"тексермедім|бөлмедім|сол кезде)",
    "lead.strong.5": r"(вместо|вырос|выросла|поднялись|поднялась|собрали \d|"
                     r"работает до сих пор|обошлось без срывов|"
                     r"өсті|көтерілді|жинадық|жұмыс істеп тұр)",
}

_NUMBER_WORDS = (r"\b(?:\d+|один|одного|два|две|двух|три|трёх|трех|четыре|четверых|"
                 r"пять|шесть|семь|восемь|восьмерых|девять|десять|двенадцать|двадцать|"
                 r"сто|екі|үш|төрт|бес|алты|жеті|сегіз|он екі|жиырма)\b")
_ROLE_WORDS = (r"капитаном команды|капитаном|координатором сбора|координатором|"
               r"редактором канала|редактором|старшим по смене|ответственным за учёбу|"
               r"ответственным|команда капитаны|үйлестірушісі|редакторы|ауысым басшысы|"
               r"жауапты болдым|жауапты")
_TIME_WORDS = (r"за полгода|за три месяца|за две недели|за месяц|за сезон|"
               r"за четыре месяца|через год|две недели|полгода|накануне|вечером|"
               r"летом|осенью|в первый день|до сих пор|каждый вечер|на месяц вперёд|"
               r"жарты жыл|үш ай|екі апта|бір ай|төрт ай|бір маусым|бір жылдан кейін|"
               r"кешке|алдын ала")
_FIRST_PERSON = (r"\bя\s+(?:[а-яё]+\s+){0,2}[а-яё]{2,}(?:лся|лась|л|ла|ю|у)\b|"
                 r"\b[а-яёқғұүөһәі]+(?:дым|дім|тым|тім|мын|мін|дық|дік)\b")

_CUE_RE = {k: re.compile(v, re.IGNORECASE) for k, v in ATOLA_CUES.items()}
_IND_RE = {k: re.compile(v, re.IGNORECASE) for k, v in INDICATOR_CUES.items()}
_MARKER_RE = {
    "numbers": re.compile(_NUMBER_WORDS, re.IGNORECASE),
    "roles": re.compile(_ROLE_WORDS, re.IGNORECASE),
    "timeframes": re.compile(_TIME_WORDS, re.IGNORECASE),
    "first_person_verbs": re.compile(_FIRST_PERSON, re.IGNORECASE),
}


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text.strip()) if s.strip()]


def extract_heuristic(text: str) -> Extraction:
    """Разбор по речевым маркерам. Детерминирован, работает без сети."""
    sents = sentences(text)

    atola: dict[AtolaElement, AtolaSlot] = {}
    for element in ATOLA_ORDER:
        rx = _CUE_RE[element]
        quote = next((s for s in sents if rx.search(s)), None)
        atola[element] = AtolaSlot(present=quote is not None, quote=quote)

    indicators: list[IndicatorHit] = []
    for indicator in LEADERSHIP.indicators():
        rx = _IND_RE.get(indicator.id)
        if rx is None:
            continue
        quote = next((s for s in sents if rx.search(s)), None)
        if quote is None:
            continue
        element: AtolaElement = indicator.atola_focus[0] if indicator.atola_focus else "action"
        indicators.append(IndicatorHit(text=indicator.text, quote=quote,
                                       atola_element=element,
                                       indicator_id=indicator.id))

    markers = ConcretenessMarkers(**{
        name: [m.group(0) for m in rx.finditer(text)]
        for name, rx in _MARKER_RE.items()
    })
    extraction = Extraction(atola=atola, indicators=indicators,
                            concreteness_markers=markers, backend="heuristic")
    return verify_quotes(extraction, text)


# --------------------------------------------------------------------------- #
# Бэкенд Anthropic
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = (
    "Ты стенографист интервью, а не член приёмной комиссии. Твоя работа — "
    "разметить ответ кандидата по структуре ATOLA и выписать дословные цитаты. "
    "Ты не выставляешь уровень, не ставишь балл, не пишешь, насколько ответ "
    "удачен, и не даёшь советов. Любое суждение о кандидате — нарушение задачи."
)

#: Все 15 формулировок индикаторов одним списком, без разбиения по уровням.
#: Экстрактор не должен знать, какой индикатор к какому уровню относится:
#: иначе выбор индикатора станет скрытой оценкой.
def _flat_indicators() -> list[str]:
    items = [ind.text for ind in LEADERSHIP.indicators()]
    return sorted(items, key=lambda t: hashlib.md5(t.encode()).hexdigest())


def build_extraction_prompt(text: str) -> str:
    atola_block = "\n".join(
        f"- {key}: {', '.join(q for q in _ATOLA_QUESTIONS[key])}" for key in ATOLA_ORDER)
    indicators_block = "\n".join(f"- {t}" for t in _flat_indicators())
    schema = json.dumps({
        "atola": {key: {"present": "true|false", "quote": "дословная цитата или null"}
                  for key in ATOLA_ORDER},
        "indicators": [{"text": "формулировка из списка ниже",
                        "quote": "дословная цитата",
                        "atola_element": "action|thinking|outcome|learnings|application"}],
        "concreteness_markers": {"numbers": ["..."], "roles": ["..."],
                                 "timeframes": ["..."], "first_person_verbs": ["..."]},
    }, ensure_ascii=False, indent=2)
    return f"""Разметь ответ кандидата.

ЭЛЕМЕНТЫ ATOLA и вопросы, которым они соответствуют:
{atola_block}

ФОРМУЛИРОВКИ ПОВЕДЕНЧЕСКИХ ИНДИКАТОРОВ (список закрытый, порядок ничего не значит):
{indicators_block}

ПРАВИЛА
1. Для каждого элемента ATOLA укажи, есть ли он в ответе, и приведи цитату.
2. Перечисли только те индикаторы из списка, которые подтверждаются цитатой.
   Формулировку индикатора копируй из списка дословно.
3. Каждая цитата обязана дословно встречаться в тексте ответа. Не перефразируй,
   не исправляй ошибки и опечатки, не сокращай внутри цитаты.
4. Маркеры конкретности выписывай как фрагменты текста: числа и количества,
   названия ролей и должностей, сроки и периоды, глаголы первого лица.
5. Если элемента нет — present: false, quote: null. Пустое поле лучше догадки.
6. Не добавляй никаких полей, кроме описанных. Уровень, балл, оценку и выводы
   о кандидате не пиши.

ФОРМАТ ОТВЕТА — только JSON:
{schema}

ОТВЕТ КАНДИДАТА:
\"\"\"{text}\"\"\""""


_ATOLA_QUESTIONS: dict[AtolaElement, tuple[str, ...]] = {}


def _init_questions() -> None:
    from qadam.data.rubric import atola_questions
    _ATOLA_QUESTIONS.update(atola_questions())


_init_questions()

#: Поля, которые модель не имеет права возвращать. Если вернёт — выбрасываем.
FORBIDDEN_KEYS = ("level", "score", "rating", "уровень", "балл", "оценка",
                  "assessment", "verdict", "recommendation")


def _strip_forbidden(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k.lower() not in FORBIDDEN_KEYS}


def _parse_extraction(raw: str, text: str, backend: str) -> Extraction:
    """Проверить JSON провайдера и все цитаты единым способом."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("ответ не содержит JSON-объект")
    payload = _strip_forbidden(json.loads(raw[start:end + 1]))
    extraction = Extraction(**payload, backend=backend)
    return verify_quotes(extraction, text)


def extract_groq(text: str) -> Extraction:
    """Один OpenAI-compatible вызов Groq с JSON mode и Pydantic-проверкой."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("нужен GROQ_API_KEY для бэкенда groq")

    prompt = build_extraction_prompt(text)
    last_error: Exception | None = None
    for attempt in range(2):
        body = json.dumps({
            "model": GROQ_MODEL,
            "temperature": 0,
            "max_completion_tokens": 2000,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            GROQ_API_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=LLM_TIMEOUT) as response:
                result = json.loads(response.read().decode("utf-8"))
            raw = result["choices"][0]["message"]["content"].strip()
            return _parse_extraction(raw, text, "groq")
        except Exception as exc:  # noqa: BLE001 — одна исправляющая попытка
            last_error = exc
            prompt = (build_extraction_prompt(text) +
                      f"\n\nПредыдущий ответ не прошёл проверку схемы: {exc}. "
                      "Верни строго JSON по формату.")
    raise ValueError(f"Groq не вернул валидное извлечение: {last_error}")


def extract_anthropic(text: str) -> Extraction:
    """Один вызов Anthropic API, temperature=0, строгий JSON."""
    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("нужен ANTHROPIC_API_KEY для бэкенда anthropic")
    client = anthropic.Anthropic()
    prompt = build_extraction_prompt(text)

    last_error: Exception | None = None
    for attempt in range(2):
        resp = client.messages.create(
            model=EXTRACT_MODEL,
            max_tokens=2000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in resp.content
                      if getattr(b, "type", "") == "text").strip()
        try:
            return _parse_extraction(raw, text, "anthropic")
        except Exception as exc:                       # noqa: BLE001 — вторая попытка
            last_error = exc
            prompt = (build_extraction_prompt(text) +
                      f"\n\nПредыдущий ответ не прошёл проверку схемы: {exc}. "
                      "Верни строго JSON по формату.")
    raise ValueError(f"не удалось получить валидный JSON извлечения: {last_error}")


# --------------------------------------------------------------------------- #
# Кэш и точка входа
# --------------------------------------------------------------------------- #

def cache_key(text: str, backend: str) -> str:
    model_name = (EXTRACT_MODEL if backend == "anthropic" else
                  GROQ_MODEL if backend == "groq" else "-")
    payload = f"{PROMPT_VERSION}|{backend}|{model_name}|{text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def resolve_backend(backend: Backend) -> str:
    if backend != "auto":
        return backend
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "heuristic"


def extract(text: str, backend: Backend = "auto", use_cache: bool = True) -> Extraction:
    """Разобрать ответ, опционально используя дисковый кэш.

    Кэш содержит проверенные дословные цитаты, поэтому он допустим только для
    синтетических или явно разрешённых данных. Публичный API всегда передаёт
    ``use_cache=False``.
    """
    resolved = resolve_backend(backend)
    path = CACHE_DIR / f"{cache_key(text, resolved)}.json"
    if use_cache and path.exists():
        return Extraction(**json.loads(path.read_text(encoding="utf-8")))

    try:
        extraction = (extract_groq(text) if resolved == "groq" else
                      extract_anthropic(text) if resolved == "anthropic" else
                      extract_heuristic(text))
    except (OSError, ValueError, RuntimeError, urllib.error.HTTPError) as exc:
        if backend != "auto" or resolved == "heuristic":
            raise
        # Демо не должно падать из-за сети, лимита или невалидного JSON.
        extraction = extract_heuristic(text)
        extraction.backend = f"heuristic-fallback ({resolved}: {type(exc).__name__})"
    if use_cache and extraction.backend == resolved:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(extraction.model_dump_json(indent=2), encoding="utf-8")
    return extraction


def extract_many(texts: Iterable[str], backend: Backend = "auto",
                 use_cache: bool = True, progress: bool = False) -> list[Extraction]:
    texts = list(texts)
    out: list[Extraction] = []
    for i, text in enumerate(texts, 1):
        out.append(extract(text, backend=backend, use_cache=use_cache))
        if progress and (i % 20 == 0 or i == len(texts)):
            print(f"  извлечение: {i}/{len(texts)}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Слой извлечения ATOLA")
    ap.add_argument("--text", help="разобрать один ответ")
    ap.add_argument("--corpus", action="store_true",
                    help="прогреть кэш по всему корпусу")
    ap.add_argument("--backend", choices=("auto", "groq", "anthropic", "heuristic"),
                    default="auto")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args(argv)

    if args.corpus:
        from qadam.data.generate import CORPUS_FILE, read_jsonl
        rows = read_jsonl(CORPUS_FILE)
        extractions = extract_many((r["text"] for r in rows), args.backend,
                                   not args.no_cache, progress=True)
        dropped = sum(e.dropped_quotes for e in extractions)
        covered = sum(sum(e.coverage().values()) for e in extractions)
        print(f"бэкенд: {resolve_backend(args.backend)}")
        print(f"разобрано: {len(extractions)}")
        print(f"среднее покрытие ATOLA: {covered / len(extractions):.2f} из 5")
        print(f"отброшено недословных цитат: {dropped}")
        return 0

    if not args.text:
        ap.error("нужен --text или --corpus")
    extraction = extract(args.text, args.backend, not args.no_cache)
    print(extraction.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
