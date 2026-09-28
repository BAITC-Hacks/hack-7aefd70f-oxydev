# -*- coding: utf-8 -*-
"""Обучение модели и машинно-читаемый отчёт о валидации.

Запуск: ``python -m eval.train``. Результат сохраняется в
``eval/metrics.json`` и ``eval/fairness.json``.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
)

from eval.baselines import length_only, llm_without_rubric, random_prior
from qadam.core import fairness as fairness_module
from qadam.core.extract import ATOLA_ORDER, Extraction, extract_many, resolve_backend
from qadam.core.features import FEATURE_BY_NAME, FEATURE_NAMES
from qadam.core.model import (
    LeadershipModel,
    MODEL_FILE,
    ModelConfig,
    stratified_split,
)
from qadam.data.generate import (
    CORPUS_FILE,
    PAIRS_FILE,
    build_robustness_sets,
    read_jsonl,
)
from qadam.data.rubric import LEVELS, LEVEL_LABELS_RU, LEVEL_ORDINAL, Level

EVAL_DIR = Path(__file__).resolve().parent
METRICS_FILE = EVAL_DIR / "metrics.json"


def ordinals(labels: Sequence[Level]) -> list[int]:
    return [LEVEL_ORDINAL[lv] for lv in labels]


def qwk(gold: Sequence[Level], pred: Sequence[Level]) -> float:
    return float(cohen_kappa_score(ordinals(gold), ordinals(pred), weights="quadratic"))


def basic_scores(gold: Sequence[Level], pred: Sequence[Level]) -> dict:
    return {
        "n": len(gold),
        "accuracy": float(accuracy_score(gold, pred)),
        "qwk": qwk(gold, pred),
        "macro_f1": float(f1_score(gold, pred, average="macro", labels=list(LEVELS),
                                   zero_division=0)),
    }


def calibration_scores(proba: np.ndarray, gold: Sequence[Level],
                       bins: int = 10) -> dict:
    """Brier и ECE: насколько вероятностям можно верить."""
    onehot = np.zeros_like(proba)
    for i, level in enumerate(gold):
        onehot[i, LEVELS.index(level)] = 1.0
    brier = float(np.mean(np.sum((proba - onehot) ** 2, axis=1)))

    confidence = proba.max(axis=1)
    correct = np.array([LEVELS[i] == g for i, g in zip(proba.argmax(axis=1), gold)],
                       dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (confidence > lo) & (confidence <= hi)
        if mask.sum():
            ece += mask.mean() * abs(correct[mask].mean() - confidence[mask].mean())
    return {"brier": brier, "ece": float(ece),
            "mean_confidence": float(confidence.mean())}


# --------------------------------------------------------------------------- #
# Тесты устойчивости
# --------------------------------------------------------------------------- #

def robustness(model: LeadershipModel, backend: str) -> dict:
    """Перефраз, ИИ-полировка и усечение для robustness-проверки."""
    sets = build_robustness_sets()
    out: dict[str, dict] = {}
    for name, pairs in sets.items():
        texts_a = [p["a"] for p in pairs]
        texts_b = [p["b"] for p in pairs]
        ex_a = extract_many(texts_a, backend=backend)
        ex_b = extract_many(texts_b, backend=backend)
        score_a = fairness_module.expected_score(model.predict_proba(texts_a, ex_a))
        score_b = fairness_module.expected_score(model.predict_proba(texts_b, ex_b))
        delta = score_b - score_a
        level_a = model.predict(texts_a, ex_a)
        level_b = model.predict(texts_b, ex_b)
        out[name] = {
            "n": len(pairs),
            "mean_delta": float(delta.mean()),
            "median_abs_delta": float(np.median(np.abs(delta))),
            "p95_abs_delta": float(np.percentile(np.abs(delta), 95)),
            "share_increased": float((delta > 0.05).mean()),
            "share_decreased": float((delta < -0.05).mean()),
            "level_unchanged": float(np.mean([a == b for a, b in zip(level_a, level_b)])),
        }
    checks = {
        "перефраз не меняет балл": out["paraphrase"]["median_abs_delta"] <= 0.25,
        "ИИ-полировка не поднимает балл": out["polish"]["mean_delta"] <= 0.05,
        "усечение Outcome и Application роняет балл": out["truncation"]["mean_delta"] < -0.05,
    }
    out["checks"] = checks
    out["all_passed"] = all(checks.values())
    return out


# --------------------------------------------------------------------------- #
# Качество слоя извлечения
# --------------------------------------------------------------------------- #

def extraction_quality(rows: Sequence[dict],
                       extractions: Sequence[Extraction]) -> dict:
    """Сверка разметки ATOLA с планом, по которому ответ был порождён.

    Ground truth здесь честный: план известен до того, как текст написан.
    """
    tp = fp = fn = tn = 0
    for row, extraction in zip(rows, extractions):
        plan = set(row["variation_meta"].get("atola_plan") or [])
        if not plan:
            continue
        coverage = extraction.coverage()
        for element in ATOLA_ORDER:
            expected, found = element in plan, coverage[element]
            tp += expected and found
            fp += (not expected) and found
            fn += expected and (not found)
            tn += (not expected) and (not found)
    total = tp + fp + fn + tn
    return {
        "n_elements": total,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "accuracy": (tp + tn) / total if total else 0.0,
        "dropped_quotes": sum(e.dropped_quotes for e in extractions),
    }


# --------------------------------------------------------------------------- #
# Ablation
# --------------------------------------------------------------------------- #

def _feature_subset(exclude_group: str | None) -> tuple[str, ...]:
    if exclude_group is None:
        return FEATURE_NAMES
    return tuple(n for n in FEATURE_NAMES if FEATURE_BY_NAME[n].group != exclude_group)


def ablation(texts: Sequence[str], extractions: Sequence[Extraction],
             labels: Sequence[Level], train_idx: Sequence[int],
             test_idx: Sequence[int], base: ModelConfig,
             with_sbert: bool = False) -> list[dict]:
    """Что будет, если убрать группу признаков или сменить векторизацию."""
    variants: list[tuple[str, ModelConfig]] = [
        ("все признаки", base),
        ("без индикаторов BARS",
         ModelConfig(**{**base.to_dict(), "feature_names": _feature_subset("indicators")})),
        ("без покрытия ATOLA",
         ModelConfig(**{**base.to_dict(), "feature_names": _feature_subset("atola")})),
        ("без конкретности",
         ModelConfig(**{**base.to_dict(), "feature_names": _feature_subset("concreteness")})),
        ("только длина ответа",
         ModelConfig(**{**base.to_dict(), "feature_names": ("length_tokens",),
                        "embeddings": "none"})),
        ("без текстовых векторов",
         ModelConfig(**{**base.to_dict(), "embeddings": "none"})),
    ]
    if with_sbert:
        variants.append(("векторы sentence-transformers",
                         ModelConfig(**{**base.to_dict(), "embeddings": "sbert"})))

    results = []
    for name, config in variants:
        config.feature_names = tuple(config.feature_names)
        model = LeadershipModel(config).fit(
            [texts[i] for i in train_idx], [extractions[i] for i in train_idx],
            [labels[i] for i in train_idx])
        pred = model.predict([texts[i] for i in test_idx],
                             [extractions[i] for i in test_idx])
        gold = [labels[i] for i in test_idx]
        results.append({"variant": name, "embeddings": config.embeddings,
                        "n_features": len(config.feature_names), **basic_scores(gold, pred)})
    return results


# --------------------------------------------------------------------------- #
# Отчёт
# --------------------------------------------------------------------------- #

def _matrix_md(gold: Sequence[Level], pred: Sequence[Level]) -> str:
    matrix = confusion_matrix(gold, pred, labels=list(LEVELS))
    head = "| факт \\ модель | " + " | ".join(LEVEL_LABELS_RU[lv] for lv in LEVELS) + " |"
    sep = "|---|" + "---:|" * len(LEVELS)
    rows = [f"| **{LEVEL_LABELS_RU[lv]}** | " + " | ".join(str(v) for v in row) + " |"
            for lv, row in zip(LEVELS, matrix)]
    return "\n".join([head, sep, *rows])


def build_report(m: dict, gold: Sequence[Level], pred: Sequence[Level]) -> str:
    main = m["holdout"]
    lines = [
        "# Отчёт о валидации — компетенция «Лидерские способности»",
        "",
        f"Сгенерирован автоматически: `python -m eval.train`. Дата: {m['meta']['date']}.",
        "",
        f"- корпус: {m['meta']['n_corpus']} ответов, из них шумовых "
        f"{m['meta']['n_noise']}, со смешанными уровнями блоков {m['meta']['n_mixed']}",
        f"- разбиение: train {m['meta']['n_train']} / test {m['meta']['n_test']}, "
        "стратификация по уровню и по типу вариации",
        f"- слой извлечения: {m['meta']['extract_backend']}",
        f"- векторизация текста: {m['meta']['embeddings']}",
        "",
        "## 1. Согласованность с рубрикой",
        "",
        f"| Метрика | Значение |",
        "|---|---:|",
        f"| Accuracy | {main['accuracy']:.3f} |",
        f"| Quadratic weighted kappa | {main['qwk']:.3f} |",
        f"| Macro F1 | {main['macro_f1']:.3f} |",
        "",
        "Матрица ошибок на отложенной выборке:",
        "",
        _matrix_md(gold, pred),
        "",
        "По классам:",
        "",
        "| Уровень | Precision | Recall | F1 | Примеров |",
        "|---|---:|---:|---:|---:|",
    ]
    for level in LEVELS:
        stats = m["per_class"][level]
        lines.append(f"| {LEVEL_LABELS_RU[level]} | {stats['precision']:.2f} "
                     f"| {stats['recall']:.2f} | {stats['f1-score']:.2f} "
                     f"| {int(stats['support'])} |")

    lines += [
        "",
        "## 2. Трудные подвыборки",
        "",
        "«Шумовые» примеры — слабое содержание в отличной обёртке и сильное "
        "содержание в корявой формулировке. Именно они проверяют, не путает ли "
        "модель красноречие с потенциалом.",
        "",
        "| Подвыборка | Примеров | Accuracy |",
        "|---|---:|---:|",
    ]
    for name, stats in m["subsets"].items():
        lines.append(f"| {name} | {stats['n']} | {stats['accuracy']:.3f} |")

    lines += [
        "",
        "## 3. Сравнение с baseline",
        "",
        "| Решение | Accuracy | QWK |",
        "|---|---:|---:|",
    ]
    for row in m["baselines"]:
        acc = "—" if row["accuracy"] is None else f"{row['accuracy']:.3f}"
        kappa = "—" if row["qwk"] is None else f"{row['qwk']:.3f}"
        lines.append(f"| {row['name']} | {acc} | {kappa} |")
    if any(r["accuracy"] is None for r in m["baselines"]):
        lines += ["", "Прочерк означает, что baseline требует ANTHROPIC_API_KEY. "
                      "Команда для дозаполнения: `ANTHROPIC_API_KEY=... python -m eval.train`."]

    rb = m["robustness"]
    lines += [
        "",
        "## 4. Устойчивость",
        "",
        "Все три набора строятся из одного и того же плана ответа, поэтому "
        "«содержание сохранено» — свойство конструкции, а не обещание.",
        "",
        "| Тест | Пар | Средняя Δ балла | Медиана \\|Δ\\| | Уровень не изменился |",
        "|---|---:|---:|---:|---:|",
        f"| Перефраз | {rb['paraphrase']['n']} | {rb['paraphrase']['mean_delta']:+.3f} "
        f"| {rb['paraphrase']['median_abs_delta']:.3f} "
        f"| {rb['paraphrase']['level_unchanged']:.0%} |",
        f"| ИИ-полировка | {rb['polish']['n']} | {rb['polish']['mean_delta']:+.3f} "
        f"| {rb['polish']['median_abs_delta']:.3f} "
        f"| {rb['polish']['level_unchanged']:.0%} |",
        f"| Удаление Outcome и Application | {rb['truncation']['n']} "
        f"| {rb['truncation']['mean_delta']:+.3f} "
        f"| {rb['truncation']['median_abs_delta']:.3f} "
        f"| {rb['truncation']['level_unchanged']:.0%} |",
        "",
    ]
    for check, passed in rb["checks"].items():
        lines.append(f"- {'✓' if passed else '✗'} {check}")

    cal = m["calibration"]
    lines += [
        "",
        "## 5. Калибровка",
        "",
        f"- Brier score: {cal['brier']:.3f}",
        f"- Ожидаемая ошибка калибровки (ECE, 10 корзин): {cal['ece']:.3f}",
        f"- Средняя уверенность: {cal['mean_confidence']:.3f}",
        "",
        "## 6. Вклад групп признаков (ablation)",
        "",
        "| Конфигурация | Признаков | Векторы | Accuracy | QWK |",
        "|---|---:|---|---:|---:|",
    ]
    for row in m["ablation"]:
        lines.append(f"| {row['variant']} | {row['n_features']} | {row['embeddings']} "
                     f"| {row['accuracy']:.3f} | {row['qwk']:.3f} |")

    eq = m["extraction"]
    lines += [
        "",
        "## 7. Качество слоя извлечения",
        "",
        "Разметка ATOLA сверена с планом, по которому ответ был порождён: план "
        "известен до того, как написан текст, поэтому это честный ground truth.",
        "",
        f"- precision: {eq['precision']:.3f}",
        f"- recall: {eq['recall']:.3f}",
        f"- accuracy по 5 элементам: {eq['accuracy']:.3f}",
        f"- отброшено цитат, не найденных в тексте дословно: {eq['dropped_quotes']}",
        "",
    ]
    lines.append(fairness_module.to_markdown(m["fairness"]))
    lines += [
        "## 9. Ограничения этих чисел",
        "",
        "Читать отчёт нужно вместе с этим разделом.",
        "",
        "1. **Корпус синтетический.** Обезличенные реальные оценки заказчик "
        "открывает на этапе внедрения. Все метрики измеряют согласие с рубрикой, "
        "а не с решением приёмной комиссии.",
        "2. **Часть признаков разделяет словарь с генератором.** Индикаторы BARS "
        "ищутся по маркерам речи, а генератор собирал ответы из блоков, "
        "привязанных к тем же индикаторам. Поэтому в таблице ablation отдельной "
        "строкой приведён результат без этой группы признаков — он и есть "
        "консервативная оценка.",
        "3. **Слой извлечения в оффлайне эвристический.** Рабочий путь — LLM с "
        "проверкой дословности цитат; он включается при наличии ANTHROPIC_API_KEY. "
        "Без ключа поднимается детерминированный разбор по маркерам речи.",
        "4. **Ручная слепая разметка ещё не внесена.** Файл для неё генерируется "
        "(`qadam/data/corpus/blind_sample.jsonl`); согласие человека с рубрикой "
        "считается отдельно и в эти числа пока не входит.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Обучение и валидация")
    ap.add_argument("--embeddings", choices=("char_tfidf", "sbert", "none"),
                    default="char_tfidf")
    ap.add_argument("--test-size", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--backend", choices=("auto", "groq", "anthropic", "heuristic"),
                    default="auto")
    ap.add_argument("--with-sbert-ablation", action="store_true",
                    help="добавить в ablation строку с sentence-transformers")
    args = ap.parse_args(argv)

    rows = read_jsonl(CORPUS_FILE)
    texts = [r["text"] for r in rows]
    labels: list[Level] = [r["level"] for r in rows]
    backend = resolve_backend(args.backend)
    print(f"извлечение ({backend}) для {len(rows)} ответов…")
    extractions = extract_many(texts, backend=args.backend, progress=True)

    train_idx, test_idx = stratified_split(rows, args.test_size, args.seed)
    config = ModelConfig(embeddings=args.embeddings, seed=args.seed)
    model = LeadershipModel(config).fit(
        [texts[i] for i in train_idx], [extractions[i] for i in train_idx],
        [labels[i] for i in train_idx])
    model.save(MODEL_FILE)

    test_texts = [texts[i] for i in test_idx]
    test_ex = [extractions[i] for i in test_idx]
    gold = [labels[i] for i in test_idx]
    pred = model.predict(test_texts, test_ex)
    proba = model.predict_proba(test_texts, test_ex)

    subsets: dict[str, dict] = {}
    for name, selector in (
        ("все", lambda r: True),
        ("шумовые: вода в отличной обёртке",
         lambda r: r["variation_meta"]["noise"] == "polished_weak"),
        ("шумовые: сильное содержание в корявой речи",
         lambda r: r["variation_meta"]["noise"] == "rough_strong"),
        ("смешанные уровни блоков", lambda r: bool(r["variation_meta"].get("mix"))),
        ("казахский и смешанный язык",
         lambda r: r["variation_meta"]["language"] in ("kk", "mixed")),
    ):
        picked = [(g, p) for i, g, p in zip(test_idx, gold, pred) if selector(rows[i])]
        if picked:
            subsets[name] = {"n": len(picked),
                             "accuracy": float(accuracy_score([g for g, _ in picked],
                                                              [p for _, p in picked]))}

    random_runs = random_prior([labels[i] for i in train_idx], len(test_idx), args.seed)
    random_acc = float(np.mean([accuracy_score(gold, r) for r in random_runs]))
    random_qwk = float(np.mean([qwk(gold, r) for r in random_runs]))
    length_pred = length_only([texts[i] for i in train_idx],
                              [labels[i] for i in train_idx], test_texts, args.seed)
    llm_pred = llm_without_rubric(test_texts)

    baselines = [
        {"name": "Случайно по априорному распределению", "accuracy": random_acc,
         "qwk": random_qwk},
        {"name": "Только длина ответа", "accuracy": float(accuracy_score(gold, length_pred)),
         "qwk": qwk(gold, length_pred)},
        {"name": "LLM без рубрики «оцени от 1 до 3»",
         "accuracy": float(accuracy_score(gold, llm_pred)) if llm_pred else None,
         "qwk": qwk(gold, llm_pred) if llm_pred else None},
        {"name": "**Qadam AI: признаки + обученный классификатор**",
         "accuracy": float(accuracy_score(gold, pred)), "qwk": qwk(gold, pred)},
    ]

    report = classification_report(gold, pred, labels=list(LEVELS),
                                   output_dict=True, zero_division=0)
    metrics = {
        "meta": {
            "date": date.today().isoformat(),
            "python": platform.python_version(),
            "n_corpus": len(rows),
            "n_noise": sum(1 for r in rows if r["variation_meta"]["noise"]),
            "n_mixed": sum(1 for r in rows if r["variation_meta"].get("mix")),
            "n_train": len(train_idx),
            "n_test": len(test_idx),
            "extract_backend": backend,
            "embeddings": args.embeddings,
            "seed": args.seed,
        },
        "holdout": basic_scores(gold, pred),
        "per_class": {lv: report[lv] for lv in LEVELS},
        "subsets": subsets,
        "baselines": baselines,
        "calibration": calibration_scores(proba, gold),
        "robustness": robustness(model, args.backend),
        "extraction": extraction_quality(rows, extractions),
        "ablation": ablation(texts, extractions, labels, train_idx, test_idx,
                             config, args.with_sbert_ablation),
        "fairness": fairness_module.audit(model, read_jsonl(PAIRS_FILE), args.backend),
    }

    METRICS_FILE.write_text(json.dumps(metrics, ensure_ascii=False, indent=2),
                            encoding="utf-8", newline="\n")
    fairness_module.REPORT_FILE.write_text(
        json.dumps(metrics["fairness"], ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n")

    print(f"\naccuracy {metrics['holdout']['accuracy']:.3f} | "
          f"QWK {metrics['holdout']['qwk']:.3f} | "
          f"fairness p95 |Δ| {metrics['fairness']['headline_p95_abs_delta']:.3f}")
    print(f"модель:  {MODEL_FILE}")
    print(f"числа:   {METRICS_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
