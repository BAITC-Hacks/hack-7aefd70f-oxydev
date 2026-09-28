# -*- coding: utf-8 -*-
"""Слой 3 — СКОРИНГ. Обученный классификатор уровня, а не промпт к LLM.

Три класса: weak / normal / strong. Логистическая регрессия на признаках слоя 2
плюс текстовые векторы, калибровка вероятностей, детерминированный инференс.

Почему обученная модель, а не «спроси LLM, дай балл»:
воспроизводимость (одинаковый вход — одинаковый балл), честная объяснимость
(вклад признака считается, а не пересказывается) и требование п. 10.3 общего ТЗ
GovTech к наличию собственной модели.

Текстовые векторы подключаются конфигом:

* ``char_tfidf`` — символьные n-граммы плюс SVD. Работает без сети и без
  тяжёлых зависимостей, не зависит от языка ответа. Значение по умолчанию.
* ``sbert`` — многоязычные эмбеддинги sentence-transformers
  (paraphrase-multilingual-MiniLM-L12-v2): в корпусе есть казахский и
  code-switching. Требует загрузки модели.
* ``none`` — только признаки слоя 2. Самая интерпретируемая конфигурация.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal, Sequence

import joblib
import numpy as np
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import StandardScaler

from qadam.core.extract import Extraction
from qadam.core.features import FEATURE_NAMES, compute
from qadam.data.rubric import LEVELS, Level

Embeddings = Literal["char_tfidf", "sbert", "none"]

MODEL_DIR = Path(os.environ.get(
    "QADAM_MODEL_DIR", Path(__file__).resolve().parent.parent / "data" / "model"))
MODEL_FILE = MODEL_DIR / "leadership.joblib"
SBERT_NAME = os.environ.get("QADAM_SBERT",
                            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
EMBED_CACHE = MODEL_DIR / "sbert_cache.joblib"


@dataclass
class ModelConfig:
    embeddings: Embeddings = "char_tfidf"
    svd_dim: int = 40
    #: Вес текстового блока. Признаки слоя 2 — основа, векторы — добавка;
    #: без ослабления они забивают интерпретируемую часть.
    text_weight: float = 0.5
    C: float = 1.0
    calibrate: bool = True
    seed: int = 20260910
    #: Какие признаки слоя 2 использовать. Нужно для ablation-таблицы в отчёте.
    feature_names: tuple[str, ...] = FEATURE_NAMES

    def to_dict(self) -> dict:
        data = asdict(self)
        data["feature_names"] = list(self.feature_names)
        return data


# --------------------------------------------------------------------------- #
# Текстовые векторы
# --------------------------------------------------------------------------- #

class TextVectorizer:
    """Обёртка над способом векторизации текста."""

    def __init__(self, config: ModelConfig):
        self.config = config
        self.tfidf: TfidfVectorizer | None = None
        self.svd: TruncatedSVD | None = None
        self._sbert = None
        self._cache: dict[str, np.ndarray] = {}
        if config.embeddings == "sbert" and EMBED_CACHE.exists():
            self._cache = joblib.load(EMBED_CACHE)

    # -- sbert -------------------------------------------------------------- #
    def _model(self):
        if self._sbert is None:
            from sentence_transformers import SentenceTransformer
            self._sbert = SentenceTransformer(SBERT_NAME)
        return self._sbert

    def _encode_sbert(self, texts: Sequence[str]) -> np.ndarray:
        missing = [t for t in texts if _key(t) not in self._cache]
        if missing:
            vectors = self._model().encode(missing, normalize_embeddings=True,
                                           show_progress_bar=False)
            for text, vec in zip(missing, vectors):
                self._cache[_key(text)] = np.asarray(vec, dtype=np.float32)
            EMBED_CACHE.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(self._cache, EMBED_CACHE)
        return np.vstack([self._cache[_key(t)] for t in texts])

    # -- api ---------------------------------------------------------------- #
    def fit_transform(self, texts: Sequence[str]) -> np.ndarray:
        mode = self.config.embeddings
        if mode == "none":
            return np.zeros((len(texts), 0), dtype=np.float32)
        if mode == "char_tfidf":
            self.tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                         min_df=2, max_features=30000,
                                         sublinear_tf=True)
            raw = self.tfidf.fit_transform(texts)
            dim = min(self.config.svd_dim, max(raw.shape[1] - 1, 1), len(texts) - 1)
            self.svd = TruncatedSVD(n_components=dim, random_state=self.config.seed)
            return self.svd.fit_transform(raw).astype(np.float32)
        return self._encode_sbert(texts)

    def transform(self, texts: Sequence[str]) -> np.ndarray:
        mode = self.config.embeddings
        if mode == "none":
            return np.zeros((len(texts), 0), dtype=np.float32)
        if mode == "char_tfidf":
            assert self.tfidf is not None and self.svd is not None
            return self.svd.transform(self.tfidf.transform(texts)).astype(np.float32)
        return self._encode_sbert(texts)


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Модель
# --------------------------------------------------------------------------- #

@dataclass
class Prediction:
    level: Level
    probabilities: dict[Level, float]
    #: Вклад каждого признака слоя 2 в логит выбранного класса.
    contributions: dict[str, float] = field(default_factory=dict)
    #: Вклад текстового блока целиком — одним числом, чтобы не выдавать
    #: непрозрачные оси эмбеддингов за объяснение.
    text_contribution: float = 0.0
    margin: float = 0.0


class LeadershipModel:
    """Классификатор уровня по компетенции «Лидерские способности»."""

    def __init__(self, config: ModelConfig | None = None):
        self.config = config or ModelConfig()
        self.vectorizer = TextVectorizer(self.config)
        self.scaler = StandardScaler()
        self.clf = LogisticRegression(max_iter=2000, C=self.config.C,
                                      class_weight="balanced",
                                      random_state=self.config.seed)
        self.calibrated: CalibratedClassifierCV | None = None
        self.classes_: list[Level] = list(LEVELS)

    # -- сборка матрицы ----------------------------------------------------- #
    def _feature_block(self, texts: Sequence[str],
                       extractions: Sequence[Extraction]) -> np.ndarray:
        names = self.config.feature_names
        rows = []
        for text, extraction in zip(texts, extractions):
            values = compute(text, extraction)
            rows.append([values[name] for name in names])
        return np.asarray(rows, dtype=np.float64)

    def _matrix(self, texts: Sequence[str], extractions: Sequence[Extraction],
                fit: bool) -> np.ndarray:
        feats = self._feature_block(texts, extractions)
        feats = self.scaler.fit_transform(feats) if fit else self.scaler.transform(feats)
        text_block = (self.vectorizer.fit_transform(texts) if fit
                      else self.vectorizer.transform(texts))
        if text_block.shape[1]:
            text_block = text_block * self.config.text_weight
        return np.hstack([feats, text_block])

    # -- обучение ----------------------------------------------------------- #
    def fit(self, texts: Sequence[str], extractions: Sequence[Extraction],
            labels: Sequence[Level]) -> "LeadershipModel":
        X = self._matrix(texts, extractions, fit=True)
        y = np.asarray(labels)
        self.clf.fit(X, y)
        self.classes_ = list(self.clf.classes_)
        if self.config.calibrate:
            n_min = int(min(np.bincount(np.unique(y, return_inverse=True)[1])))
            cv = max(2, min(5, n_min))
            self.calibrated = CalibratedClassifierCV(
                clone(self.clf), method="sigmoid", cv=cv)
            self.calibrated.fit(X, y)
        return self

    # -- инференс ----------------------------------------------------------- #
    def predict_proba(self, texts: Sequence[str],
                      extractions: Sequence[Extraction]) -> np.ndarray:
        X = self._matrix(texts, extractions, fit=False)
        estimator = self.calibrated or self.clf
        proba = estimator.predict_proba(X)
        order = [list(estimator.classes_).index(lv) for lv in LEVELS]
        return proba[:, order]

    def predict(self, texts: Sequence[str],
                extractions: Sequence[Extraction]) -> list[Level]:
        proba = self.predict_proba(texts, extractions)
        return [LEVELS[i] for i in proba.argmax(axis=1)]

    def explain(self, text: str, extraction: Extraction) -> Prediction:
        """Уровень, вероятности и честный вклад каждого признака.

        Вклад считается как coef * стандартизованное значение признака для
        выбранного класса — то есть арифметика логита, а не пересказ модели.
        """
        proba = self.predict_proba([text], [extraction])[0]
        best = int(proba.argmax())
        level: Level = LEVELS[best]
        probabilities = {lv: float(p) for lv, p in zip(LEVELS, proba)}

        X = self._matrix([text], [extraction], fit=False)[0]
        class_index = list(self.clf.classes_).index(level)
        coefs = self.clf.coef_[class_index] if len(self.clf.classes_) > 2 else self.clf.coef_[0]
        n_feats = len(self.config.feature_names)
        contributions = {name: float(coefs[i] * X[i])
                         for i, name in enumerate(self.config.feature_names)}
        text_contribution = float(np.dot(coefs[n_feats:], X[n_feats:]))
        ordered = sorted(proba, reverse=True)
        return Prediction(level=level, probabilities=probabilities,
                          contributions=contributions,
                          text_contribution=text_contribution,
                          margin=float(ordered[0] - ordered[1]))

    # -- сохранение --------------------------------------------------------- #
    def save(self, path: Path = MODEL_FILE) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "config": self.config.to_dict(),
            "scaler": self.scaler,
            "clf": self.clf,
            "calibrated": self.calibrated,
            "tfidf": self.vectorizer.tfidf,
            "svd": self.vectorizer.svd,
        }
        joblib.dump(payload, path)
        path.with_suffix(".json").write_text(
            json.dumps(self.config.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path = MODEL_FILE) -> "LeadershipModel":
        payload = joblib.load(path)
        cfg = payload["config"]
        cfg["feature_names"] = tuple(cfg["feature_names"])
        model = cls(ModelConfig(**cfg))
        model.scaler = payload["scaler"]
        model.clf = payload["clf"]
        model.calibrated = payload["calibrated"]
        model.vectorizer.tfidf = payload["tfidf"]
        model.vectorizer.svd = payload["svd"]
        model.classes_ = list(model.clf.classes_)
        return model


# --------------------------------------------------------------------------- #
# Разбиение выборки
# --------------------------------------------------------------------------- #

def strata_key(row: dict) -> str:
    """Слой стратификации: уровень И тип вариации.

    «Шумовые» примеры (слабое содержание в отличной обёртке и наоборот) обязаны
    попасть в тест — иначе метрика ничего не проверяет.
    """
    meta = row.get("variation_meta", {})
    noise = meta.get("noise") or "plain"
    return f"{row['level']}|{noise}"


def stratified_split(rows: Sequence[dict], test_size: float = 0.3,
                     seed: int = 20260910) -> tuple[list[int], list[int]]:
    strata = [strata_key(r) for r in rows]
    splitter = StratifiedShuffleSplit(n_splits=1, test_size=test_size,
                                      random_state=seed)
    train_idx, test_idx = next(splitter.split(np.zeros(len(rows)), strata))
    return sorted(train_idx.tolist()), sorted(test_idx.tolist())
