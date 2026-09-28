# -*- coding: utf-8 -*-
"""Контрфактический аудит справедливости (модуль M3).

Механика: берём пару текстов, у которых содержание, факты и структура совпадают,
а отличается ровно один фоновый признак — регион, язык оригинала,
«отполированность» речи, род говорящего. Прогоняем оба через скоринг и меряем Δ.

Заказчик просит «исключение предвзятости, проверяемое на данных»
(docs/01-context.md §7). Это и есть проверка на данных.

Шкала: уровень кодируется как 0 (weak), 1 (normal), 2 (strong), балл ответа —
матожидание уровня по калиброванным вероятностям. Значит расстояние между
соседними уровнями равно 1.0, и это естественный порог: сдвиг от фонового
признака не имеет права дотягивать до разницы между уровнями. Внутренняя цель
строже — 0.25, четверть ступени.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from statistics import median
from typing import Sequence

import numpy as np

from qadam.core.extract import Backend, extract_many
from qadam.core.model import LeadershipModel, MODEL_FILE
from qadam.data.generate import PAIRS_FILE, read_jsonl
from qadam.data.rubric import LEVEL_ORDINAL, LEVELS

REPORT_FILE = Path(__file__).resolve().parent.parent.parent / "eval" / "fairness.json"

#: Порог, который нельзя превышать: расстояние между соседними уровнями.
HARD_THRESHOLD = 1.0
#: Внутренняя цель.
TARGET = 0.25

#: Что означает положительная Δ по каждому признаку.
DIRECTION_LABEL = {
    "settlement": "город выше села",
    "language": "казахский выше русского",
    "polish": "отполированная речь выше речи с ошибками",
    "gender": "женский род выше мужского",
}


def expected_score(proba: np.ndarray) -> np.ndarray:
    """Балл ответа в единицах уровней: 0.0 … 2.0."""
    weights = np.array([LEVEL_ORDINAL[lv] for lv in LEVELS], dtype=float)
    return proba @ weights


def audit(model: LeadershipModel, pairs: Sequence[dict],
          backend: Backend = "auto") -> dict:
    """Δ по каждой паре и сводка по каждому фоновому признаку."""
    texts_a = [p["a"]["text"] for p in pairs]
    texts_b = [p["b"]["text"] for p in pairs]
    ex_a = extract_many(texts_a, backend=backend)
    ex_b = extract_many(texts_b, backend=backend)

    proba_a = model.predict_proba(texts_a, ex_a)
    proba_b = model.predict_proba(texts_b, ex_b)
    score_a, score_b = expected_score(proba_a), expected_score(proba_b)
    level_a = [LEVELS[i] for i in proba_a.argmax(axis=1)]
    level_b = [LEVELS[i] for i in proba_b.argmax(axis=1)]

    rows = []
    for i, pair in enumerate(pairs):
        rows.append({
            "pair_id": pair["pair_id"],
            "attribute": pair["attribute"],
            "level": pair["level"],
            "score_a": float(score_a[i]),
            "score_b": float(score_b[i]),
            "delta": float(score_b[i] - score_a[i]),
            "abs_delta": float(abs(score_b[i] - score_a[i])),
            "level_a": level_a[i],
            "level_b": level_b[i],
            "flipped": level_a[i] != level_b[i],
        })

    by_attribute: dict[str, dict] = {}
    for attribute in sorted({r["attribute"] for r in rows}):
        subset = [r for r in rows if r["attribute"] == attribute]
        deltas = [r["abs_delta"] for r in subset]
        by_attribute[attribute] = {
            "n": len(subset),
            "median_abs_delta": float(median(deltas)),
            "p95_abs_delta": float(np.percentile(deltas, 95)),
            "max_abs_delta": float(max(deltas)),
            "mean_signed_delta": float(np.mean([r["delta"] for r in subset])),
            "direction": DIRECTION_LABEL.get(attribute, ""),
            "flip_rate": sum(r["flipped"] for r in subset) / len(subset),
        }

    worst = max(by_attribute.values(), key=lambda v: v["p95_abs_delta"])
    worst_attribute = next(k for k, v in by_attribute.items() if v is worst)
    headline = worst["p95_abs_delta"]

    return {
        "n_pairs": len(rows),
        "scale": "0 = weak, 1 = normal, 2 = strong; шаг между уровнями = 1.0",
        "headline_p95_abs_delta": headline,
        "headline_attribute": worst_attribute,
        "hard_threshold": HARD_THRESHOLD,
        "target": TARGET,
        "passes_hard_threshold": headline <= HARD_THRESHOLD,
        "passes_target": headline <= TARGET,
        "by_attribute": by_attribute,
        "pairs": rows,
    }


def to_markdown(result: dict, heading: str = "## 8. Fairness: контрфактический аудит") -> str:
    """Секция отчёта. Главное число — первой строкой."""
    headline = result["headline_p95_abs_delta"]
    verdict = ("в пределах цели" if result["passes_target"]
               else "в пределах жёсткого порога" if result["passes_hard_threshold"]
               else "ПОРОГ ПРЕВЫШЕН")
    lines = [
        heading,
        "",
        f"**Максимальный сдвиг балла от фонового признака: {headline:.3f} "
        f"ступени уровня** (95-й перцентиль, худший признак — "
        f"«{result['headline_attribute']}»). Порог — 1.000, цель — 0.250. "
        f"Результат: {verdict}.",
        "",
        f"Пар: {result['n_pairs']}. Шкала: {result['scale']}.",
        "",
        "| Фоновый признак | Пар | Медиана \\|Δ\\| | 95-й перцентиль | Максимум "
        "| Средняя Δ со знаком | Смена уровня |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for attribute, stats in result["by_attribute"].items():
        lines.append(
            f"| {attribute} ({stats['direction']}) | {stats['n']} "
            f"| {stats['median_abs_delta']:.3f} | {stats['p95_abs_delta']:.3f} "
            f"| {stats['max_abs_delta']:.3f} | {stats['mean_signed_delta']:+.3f} "
            f"| {stats['flip_rate']:.0%} |")
    lines += [
        "",
        "Положительная Δ означает, что выше оказался вариант, названный в скобках. "
        "Фоновые признаки не входят в модель как предикторы: остаточная Δ берётся "
        "только из текстовых векторов и из того, как маркеры речи попадают в "
        "признаки слоя 2.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Пара «на лету» для демонстрации в интерфейсе
# --------------------------------------------------------------------------- #

#: Маркеры населённого пункта в тексте кандидата. Меняем только их.
_SETTLEMENT_SWAPS = (
    ("сельской школе", "городской школе"),
    ("сельская школа", "городская школа"),
    ("в селе", "в городе"),
    ("из села", "из города"),
    ("наше село", "наш город"),
    ("село", "город"),
    ("ауылдық мектепте", "қалалық мектепте"),
    ("ауылда", "қалада"),
)

_VILLAGE_PREFIX = "Я учусь в сельской школе. "
_CITY_PREFIX = "Я учусь в городской школе. "


def counterfactual_pair(text: str) -> dict:
    """Два варианта одного ответа, различающиеся только фоновым признаком.

    Если в тексте есть упоминание села или города — меняется только оно.
    Если упоминания нет, к обоим вариантам добавляется одно и то же
    предложение с разным значением признака, и об этом говорится явно:
    подменять содержание ответа ради красивой демонстрации нельзя.
    """
    lowered = text.lower()
    for village, city in _SETTLEMENT_SWAPS:
        if village in lowered:
            pattern = re.compile(re.escape(village), re.IGNORECASE)
            return {"attribute": "settlement", "synthetic_prefix": False,
                    "a": text, "b": pattern.sub(city, text, count=1),
                    "label_a": "как в ответе (село)", "label_b": "заменено на город"}
        if city in lowered:
            pattern = re.compile(re.escape(city), re.IGNORECASE)
            return {"attribute": "settlement", "synthetic_prefix": False,
                    "a": pattern.sub(village, text, count=1), "b": text,
                    "label_a": "заменено на село", "label_b": "как в ответе (город)"}
    return {"attribute": "settlement", "synthetic_prefix": True,
            "a": _VILLAGE_PREFIX + text, "b": _CITY_PREFIX + text,
            "label_a": "добавлено: сельская школа",
            "label_b": "добавлено: городская школа"}


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Контрфактический аудит справедливости")
    ap.add_argument("--model", default=str(MODEL_FILE))
    ap.add_argument("--backend", choices=("auto", "groq", "anthropic", "heuristic"),
                    default="auto")
    args = ap.parse_args(argv)

    path = Path(args.model)
    if not path.exists():
        print(f"нет обученной модели: {path}\nсначала: python -m eval.train")
        return 1

    model = LeadershipModel.load(path)
    result = audit(model, read_jsonl(PAIRS_FILE), args.backend)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(to_markdown(result))
    print(f"числа: {REPORT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
