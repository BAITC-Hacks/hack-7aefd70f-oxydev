# -*- coding: utf-8 -*-
"""HTTP-интерфейс Qadam AI.

    POST /analyze         — разбор одного ответа
    POST /counterfactual  — проверка на предвзятость: два балла рядом
    GET  /examples        — три заготовленных примера для демонстрации
    GET  /health          — состояние модели и слоя извлечения

Разовый анализ не сохраняет сырой текст. Отдельный добровольный pilot workflow
сохраняет анонимное прохождение и запись локально, чтобы его мог проверить
человек; это ещё не production-ролевой контур.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from qadam.core.explain import explain
from qadam.api.review_store import append_event, events
from qadam.api.pilot_store import (
    append_review as append_pilot_review,
    create_submission,
    delete_submission,
    media_directory,
    reviews as pilot_reviews,
    set_media,
    submission as pilot_submission,
    submissions as pilot_submissions,
)
from qadam.core.extract import PROMPT_VERSION, Extraction, extract, resolve_backend
from qadam.core.fairness import counterfactual_pair, expected_score, HARD_THRESHOLD, TARGET
from qadam.core.model import LeadershipModel, MODEL_FILE
from qadam.data.generate import CORPUS_FILE, read_jsonl
from qadam.data.rubric import LEADERSHIP, LEVELS, LEVEL_LABELS_RU
from qadam.data.evidence_framework import framework_payload

WEB_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"

app = FastAPI(title="Qadam AI — Leader ID",
              description="Калибровка приёмной комиссии по компетенции "
                          "«Лидерские способности»",
              version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def demo_access_gate(request: Request, call_next):
    """Не открывать необезличенный демо-интерфейс без доступа при публикации.

    Локально пароль не требуется. Для публичной демоверсии задайте
    QADAM_DEMO_PASSWORD; это один пароль, а не полноценная ролевая модель.
    """
    password = os.environ.get("QADAM_DEMO_PASSWORD", "")
    request.state.demo_reviewer = "local_demo"
    if password and request.url.path != "/health":
        import base64
        authorization = request.headers.get("authorization", "")
        allowed = False
        if authorization.startswith("Basic "):
            try:
                decoded = base64.b64decode(authorization[6:], validate=True).decode("utf-8")
                username, supplied = decoded.split(":", 1)
                allowed = hmac.compare_digest(supplied, password)
                if allowed:
                    request.state.demo_reviewer = username[:80] or "demo_user"
            except (ValueError, UnicodeDecodeError):
                pass
        if not allowed:
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Qadam AI Demo"',
                         "Cache-Control": "no-store"},
            )
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response

_model: LeadershipModel | None = None


@lru_cache(maxsize=1)
def model_version() -> str:
    """Короткий идентификатор конкретного артефакта модели."""
    if not MODEL_FILE.exists():
        return "not-trained"
    digest = hashlib.sha256()
    with MODEL_FILE.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def model() -> LeadershipModel:
    global _model
    if _model is None:
        if not MODEL_FILE.exists():
            raise HTTPException(
                status_code=503,
                detail="модель не обучена: выполните python -m eval.train")
        _model = LeadershipModel.load(MODEL_FILE)
    return _model


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class DemoReviewRequest(BaseModel):
    example_id: str
    selected_route: str
    reason: str = Field(default="", max_length=1000)


class PilotSubmissionRequest(BaseModel):
    language: str
    mode: str
    story: str = Field(default="", max_length=1500)
    media_link: str | None = Field(default=None, max_length=2000)
    scenario_choice: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=500)
    consent: bool


class PilotReviewRequest(BaseModel):
    selected_route: str
    reason: str = Field(min_length=10, max_length=1000)
    evidence: str = Field(default="", max_length=1500)
    timecode: str = Field(default="", max_length=20)


def _analyze(text: str) -> dict:
    # Извлечение содержит дословные цитаты и может раскрывать персональные
    # данные, поэтому пользовательские ответы API не попадают в дисковый кэш.
    extraction: Extraction = extract(text, use_cache=False)
    result = explain(model(), text, extraction)
    result["provenance"] = {
        "model_version": model_version(),
        "prompt_version": PROMPT_VERSION,
        "methodology": "public-leadership-bars-v1",
        "methodology_scope": "1 of 9 competencies",
    }
    return result


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    """Уровень, вероятности, разбор ATOLA с цитатами, вклад признаков, подсказки."""
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="пустой текст")
    return _analyze(text)


@app.post("/counterfactual")
def counterfactual(request: AnalyzeRequest) -> dict:
    """Тот же ответ с изменённым фоновым признаком: два результата рядом и Δ."""
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="пустой текст")

    pair = counterfactual_pair(text)
    result_a, result_b = _analyze(pair["a"]), _analyze(pair["b"])
    score_a = float(expected_score(
        model().predict_proba(
            [pair["a"]], [extract(pair["a"], use_cache=False)]))[0])
    score_b = float(expected_score(
        model().predict_proba(
            [pair["b"]], [extract(pair["b"], use_cache=False)]))[0])
    delta = score_b - score_a
    return {
        "attribute": pair["attribute"],
        "synthetic_prefix": pair["synthetic_prefix"],
        "a": {"label": pair["label_a"], "text": pair["a"], "score": score_a,
              "level": result_a["level"], "level_label": result_a["level_label"],
              "probabilities": result_a["probabilities"]},
        "b": {"label": pair["label_b"], "text": pair["b"], "score": score_b,
              "level": result_b["level"], "level_label": result_b["level_label"],
              "probabilities": result_b["probabilities"]},
        "delta": delta,
        "abs_delta": abs(delta),
        "level_changed": result_a["level"] != result_b["level"],
        "target": TARGET,
        "hard_threshold": HARD_THRESHOLD,
        "verdict": ("в пределах цели" if abs(delta) <= TARGET
                    else "в пределах порога" if abs(delta) <= HARD_THRESHOLD
                    else "порог превышен"),
        "scale": "0 = Слабо, 1 = Нормально, 2 = Высоко",
    }


#: Три примера для демонстрации. Идентификаторы зафиксированы, чтобы кнопки
#: в интерфейсе всегда показывали один и тот же случай.
EXAMPLE_IDS = {
    # Для live demo используем грамотный полностью русский пример. Стресс-кейсы
    # с ошибками и code-switching остаются в корпусе и fairness-оценке.
    "strong": ("lead-strong-01", "Конкретный пример лидерства"),
    "weak": ("lead-weak-00", "Общий ответ без примера"),
    "polished_weak": ("lead-noise-00", "Развёрнутый ответ без подтверждений"),
}


@app.get("/examples")
def examples() -> list[dict]:
    """Три вымышленных ответа с разной доказательной базой — из корпуса."""
    rows = {row["id"]: row for row in read_jsonl(CORPUS_FILE)}
    out = []
    for key, (row_id, title) in EXAMPLE_IDS.items():
        row = rows.get(row_id)
        if row is None:
            continue
        out.append({
            "key": key,
            "title": title,
            "id": row["id"],
            "text": row["text"],
            "expected_level": row["level"],
            "expected_level_label": LEVEL_LABELS_RU[row["level"]],
            "note": ("развёрнутая формулировка без достаточных подтверждений результата"
                     if key == "polished_weak" else ""),
        })
    return out


@app.get("/demo/candidates")
def demo_candidates() -> list[dict]:
    """Только три вымышленных кейса; это макет очереди, не приёмная БД."""
    return [
        {"id": item["id"], "title": item["title"], "source": "synthetic",
         "latest_review": next(iter(events(item["id"], limit=1)), None)}
        for item in examples()
    ]


@app.get("/demo/candidates/{example_id}/reviews")
def demo_reviews(example_id: str) -> list[dict]:
    if example_id not in {item["id"] for item in examples()}:
        raise HTTPException(404, "вымышленный кейс не найден")
    return events(example_id)


@app.post("/demo/reviews")
def demo_review(body: DemoReviewRequest, request: Request) -> dict:
    """Проверка человеком и append-only журнал только для синтетики."""
    example = next((item for item in examples() if item["id"] == body.example_id), None)
    if example is None:
        raise HTTPException(404, "вымышленный кейс не найден")
    routes = {"manual_review", "priority_interview", "standard_interview"}
    if body.selected_route not in routes:
        raise HTTPException(422, "недопустимый маршрут")
    model_route = _analyze(example["text"])["decision_support"]["route"]
    action = "override" if body.selected_route != model_route else "confirm"
    reason = body.reason.strip()
    if action == "override" and len(reason) < 10:
        raise HTTPException(422, "для изменения маршрута нужна причина от 10 символов")
    return append_event(
        example_id=body.example_id,
        reviewer=request.state.demo_reviewer,
        model_route=model_route,
        selected_route=body.selected_route,
        action=action,
        reason=reason,
        model_version=model_version(),
    )


@app.post("/pilot/submissions", status_code=201)
def pilot_create(body: PilotSubmissionRequest) -> dict:
    """Сохранить добровольное прохождение под анонимным кодом."""
    if not body.consent:
        raise HTTPException(422, "нужно согласие на локальное сохранение демо-ответа")
    if body.language not in {"en", "kk", "ru"}:
        raise HTTPException(422, "неподдерживаемый язык")
    if body.mode not in {"text", "audio", "video"}:
        raise HTTPException(422, "неподдерживаемый формат")
    story = body.story.strip()
    media_link = body.media_link.strip() if body.media_link else None
    if not story and not media_link and body.mode == "text":
        raise HTTPException(422, "нужен ответ кандидата")
    if media_link and not media_link.startswith("https://"):
        raise HTTPException(422, "разрешены только HTTPS-ссылки")
    return create_submission(
        language=body.language,
        mode=body.mode,
        story=story,
        media_link=media_link,
        scenario_choice=body.scenario_choice.strip(),
        rationale=body.rationale.strip(),
        consent_version="pilot-demo-v1",
    )


@app.post("/pilot/submissions/{submission_id}/media", status_code=204)
async def pilot_upload_media(submission_id: str, request: Request) -> Response:
    """Локальная запись до 30 МБ; облачным провайдерам не отправляется."""
    item = pilot_submission(submission_id)
    if item is None:
        raise HTTPException(404, "прохождение не найдено")
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    expected = "video/" if item["mode"] == "video" else "audio/"
    if not content_type.startswith(expected):
        raise HTTPException(415, "тип записи не соответствует выбранному формату")
    payload = await request.body()
    if not payload or len(payload) > 30_000_000:
        raise HTTPException(413, "запись должна быть от 1 байта до 30 МБ")
    directory = media_directory()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{submission_id}.bin").write_bytes(payload)
    set_media(submission_id, content_type)
    return Response(status_code=204)


@app.get("/pilot/submissions")
def pilot_queue() -> list[dict]:
    return pilot_submissions()


@app.get("/pilot/submissions/{submission_id}")
def pilot_get(submission_id: str) -> dict:
    item = pilot_submission(submission_id)
    if item is None:
        raise HTTPException(404, "прохождение не найдено")
    item["reviews"] = pilot_reviews(submission_id)
    item["has_media"] = bool(item["media_content_type"])
    return item


@app.get("/pilot/submissions/{submission_id}/media")
def pilot_media(submission_id: str) -> FileResponse:
    item = pilot_submission(submission_id)
    path = media_directory() / f"{submission_id}.bin"
    if item is None or not item["media_content_type"] or not path.exists():
        raise HTTPException(404, "запись не найдена")
    return FileResponse(path, media_type=item["media_content_type"],
                        headers={"Cache-Control": "no-store"})


@app.delete("/pilot/submissions/{submission_id}", status_code=204)
def pilot_delete(submission_id: str) -> Response:
    """Удалить ровно одно пилотное прохождение по его анонимному коду."""
    if not delete_submission(submission_id):
        raise HTTPException(404, "прохождение не найдено")
    path = media_directory() / f"{submission_id}.bin"
    path.unlink(missing_ok=True)
    return Response(status_code=204)


@app.post("/pilot/submissions/{submission_id}/reviews", status_code=201)
def pilot_review(submission_id: str, body: PilotReviewRequest,
                 request: Request) -> dict:
    if pilot_submission(submission_id) is None:
        raise HTTPException(404, "прохождение не найдено")
    if body.selected_route not in {"manual_review", "priority_interview", "standard_interview"}:
        raise HTTPException(422, "недопустимый маршрут")
    if body.selected_route == "priority_interview" and len(body.evidence.strip()) < 10:
        raise HTTPException(422, "для приоритетного маршрута нужно конкретное свидетельство")
    return append_pilot_review(
        submission_id=submission_id,
        reviewer=request.state.demo_reviewer,
        selected_route=body.selected_route,
        reason=body.reason.strip(),
        evidence=body.evidence.strip(),
        timecode=body.timecode.strip(),
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model_trained": MODEL_FILE.exists(),
        "extract_backend": resolve_backend("auto"),
        "competency": LEADERSHIP.name_ru,
        "levels": {lv: LEVEL_LABELS_RU[lv] for lv in LEVELS},
        "never_scored": ["Wounded leadership", "Ценности"],
        "model_version": model_version(),
        "prompt_version": PROMPT_VERSION,
        "methodology_scope": "1_of_9",
    }


@app.get("/methodology")
def methodology() -> dict:
    """Версионированная гипотеза Qadam; не выдаётся за методику заказчика."""
    return framework_payload()


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
