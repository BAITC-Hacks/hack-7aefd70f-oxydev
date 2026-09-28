# -*- coding: utf-8 -*-
"""Три baseline, с которыми обязана сравниваться модель (docs/02-solution-spec.md §5.2).

1. ``random_prior`` — случайный уровень по априорному распределению обучающей
   выборки. Нижняя граница: всё, что не лучше него, бесполезно.
2. ``length_only`` — логистическая регрессия на одном признаке: длине ответа.
   Самый честный и самый неприятный baseline. Если модель не бьёт его заметно,
   значит мы меряем многословность, а не лидерство.
3. ``llm_without_rubric`` — «оцени этого кандидата от 1 до 3» без рубрики,
   без ATOLA, без индикаторов. Это то, что построят на промптах, и именно с
   этим надо сравниваться, чтобы показать ценность обученного слоя.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Sequence

import numpy as np
from sklearn.linear_model import LogisticRegression

from qadam.data.rubric import LEVELS, Level

LLM_CACHE = Path(__file__).resolve().parent / "baseline_llm_cache.json"
BASELINE_MODEL = os.environ.get("QADAM_BASELINE_MODEL", "claude-sonnet-5")

#: Промпт baseline намеренно примитивен: в нём нет ни рубрики, ни ATOLA.
#: Так выглядит решение «целиком на промптах», с которым мы сравниваемся.
BASELINE_PROMPT = (
    "Оцени этого кандидата на поступление в университет от 1 до 3, где 1 — "
    "низкий уровень, 3 — высокий. Ответь одной цифрой.\n\nОтвет кандидата:\n"
)


def random_prior(train_labels: Sequence[Level], n_test: int,
                 seed: int = 20260910, repeats: int = 500) -> list[list[Level]]:
    """Несколько прогонов случайного отнесения по априорному распределению."""
    rng = np.random.default_rng(seed)
    levels, counts = np.unique(np.asarray(train_labels), return_counts=True)
    probs = counts / counts.sum()
    return [list(rng.choice(levels, size=n_test, p=probs)) for _ in range(repeats)]


def length_only(train_texts: Sequence[str], train_labels: Sequence[Level],
                test_texts: Sequence[str], seed: int = 20260910) -> list[Level]:
    """Классификатор, которому доступна только длина ответа."""
    def x(texts: Sequence[str]) -> np.ndarray:
        return np.array([[len(t.split())] for t in texts], dtype=float)

    clf = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=seed)
    clf.fit(x(train_texts), np.asarray(train_labels))
    return list(clf.predict(x(test_texts)))


def llm_without_rubric(texts: Sequence[str], use_cache: bool = True) -> list[Level] | None:
    """«Оцени от 1 до 3» без рубрики. Возвращает None, если нет ключа.

    Результаты кэшируются: baseline должен воспроизводиться на защите без
    повторных вызовов и без расходов.
    """
    cache: dict[str, str] = {}
    if use_cache and LLM_CACHE.exists():
        cache = json.loads(LLM_CACHE.read_text(encoding="utf-8"))

    missing = [t for t in texts if t not in cache]
    if missing:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        import anthropic

        client = anthropic.Anthropic()
        for text in missing:
            resp = client.messages.create(
                model=BASELINE_MODEL,
                max_tokens=8,
                temperature=0,
                messages=[{"role": "user", "content": BASELINE_PROMPT + text}],
            )
            raw = "".join(b.text for b in resp.content
                          if getattr(b, "type", "") == "text")
            match = re.search(r"[1-3]", raw)
            cache[text] = LEVELS[int(match.group()) - 1] if match else "normal"
        if use_cache:
            LLM_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    return [cache[t] for t in texts]
