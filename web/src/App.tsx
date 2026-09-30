import { useEffect, useState } from "react";
import Journey, { JourneyResult } from "./Journey";
import {
  Analysis,
  Counterfactual,
  DemoCandidate,
  Example,
  Level,
  ReviewEvent,
  Route,
  PilotSubmission,
  EvidenceFramework,
  analyze,
  counterfactual,
  loadDemoCandidates,
  loadExamples,
  loadReviews,
  saveReview,
  createPilotSubmission,
  loadPilotSubmission,
  loadPilotSubmissions,
  savePilotReview,
  uploadPilotMedia,
  loadMethodology,
} from "./api";

const LEVEL_ORDER: Level[] = ["weak", "normal", "strong"];
const LEVEL_LABEL: Record<Level, string> = {
  weak: "Слабо",
  normal: "Нормально",
  strong: "Высоко",
};
const ATTRIBUTE_LABEL: Record<string, string> = {
  settlement: "место проживания",
  language: "язык ответа",
  gender: "пол кандидата",
  polish: "стиль изложения",
};
const ROUTE_LABEL: Record<Route, string> = {
  manual_review: "Уточнить ответ",
  priority_interview: "Пригласить в первую очередь",
  standard_interview: "Пригласить на интервью",
};
type JourneyReview = { route: Route; reason: string; evidence: string; timecode: string; at: string };
const COMPETENCY_MAP = [
  ["01", "Мотивация на университет", "Требует настройки"],
  ["02", "Мотивация на специальность", "Требует настройки"],
  ["03", "Лидерские способности", "Настроено"],
  ["04", "Работа в команде", "Требует настройки"],
  ["05", "Ценности", "Оценка комиссией"],
  ["06", "Предыдущий опыт", "Требует настройки"],
  ["07", "Интеллект", "Требует настройки"],
  ["08", "Лидерство с ясной целью", "Требует настройки"],
  ["09", "Развитие через трудности", "Оценка комиссией"],
] as const;

function Quote({ children }: { children: string }) {
  return <blockquote className="quote">{children}</blockquote>;
}

function Probabilities({ values }: { values: Record<Level, number> }) {
  return (
    <div className="probabilities">
      {LEVEL_ORDER.map((level) => (
        <div key={level} className="probability-row">
          <span className="probability-name">{LEVEL_LABEL[level]}</span>
          <span className="bar">
            <span
              className={`bar-fill bar-${level}`}
              style={{ width: `${Math.round(values[level] * 100)}%` }}
            />
          </span>
          <span className="probability-value">
            {Math.round(values[level] * 100)}%
          </span>
        </div>
      ))}
    </div>
  );
}

function AtolaZone({ data }: { data: Analysis }) {
  return (
    <section className="card">
      <h2>
        Структура ответа
        <span className="muted">
          найдено {Math.round(data.atola_coverage * 5)} из 5 элементов
        </span>
      </h2>
      <ul className="atola">
        {data.atola.map((item) => (
          <li key={item.element} className={item.present ? "found" : "missing"}>
            <div className="atola-head">
              <span className="letter">{item.letter}</span>
              <span className="atola-name">{item.name}</span>
              <span className="atola-state">
                {item.present ? "есть" : "не прозвучало"}
              </span>
            </div>
            {item.quote ? (
              <Quote>{item.quote}</Quote>
            ) : (
              <div className="probe">
                Спросить: {item.probes[0] ?? item.questions[0]}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function LevelZone({ data }: { data: Analysis }) {
  return (
    <section className="card">
      <h2>
        Предварительная оценка
        <span className="muted">решение принимает человек</span>
      </h2>
      <div className={`level level-${data.level}`}>{data.level_label}</div>
      <div className={`route ${data.decision_support.needs_manual_review ? "route-review" : "route-ok"}`}>
        <strong>{data.decision_support.recommendation}</strong>
        <span>Уверенность {Math.round(data.decision_support.confidence * 100)}%</span>
        {data.decision_support.reasons.length > 0 && (
          <ul>
            {data.decision_support.reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        )}
        <small>{data.decision_support.policy}</small>
      </div>
      <Probabilities values={data.probabilities} />

      <h3>Что подтверждает результат</h3>
      {data.indicators.length === 0 && (
        <p className="muted">Ни один индикатор не подтверждён цитатой.</p>
      )}
      <ul className="indicators">
        {data.indicators.map((indicator) => (
          <li key={indicator.indicator_id}>
            <div className="indicator-head">
              <span className={`tag tag-${indicator.level}`}>
                {indicator.level_label}
              </span>
              <span>{indicator.text}</span>
            </div>
            <Quote>{indicator.quote}</Quote>
          </li>
        ))}
      </ul>

    </section>
  );
}

function HintsZone({ data }: { data: Analysis }) {
  return (
    <section className="card">
      <h2>Что спросить на интервью</h2>
      {data.sensitive.map((item) => (
        <div key={item.note} className="sensitive">
          <strong>Этот блок оценивает комиссия.</strong>
          <p>{item.note}</p>
          <ul>
            {item.questions.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </div>
      ))}
      {data.hints.length === 0 && (
        <p className="muted">Пробелов, требующих уточнения, не найдено.</p>
      )}
      <ul className="hints">
        {data.hints.map((hint) => (
          <li key={hint.kind + hint.title}>
            <strong>{hint.title}</strong>
            <p className="muted small">{hint.reason}</p>
            <ul>
              {hint.questions.map((question) => (
                <li key={question}>{question}</li>
              ))}
            </ul>
          </li>
        ))}
      </ul>

      <h3>Черновик обратной связи кандидату</h3>
      <p className="muted small">{data.feedback.disclaimer}</p>
      <div className="feedback">
        <div>
          <h4>Сильные стороны</h4>
          <ul>
            {data.feedback.strengths.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4>Что развивать</h4>
          <ul>
            {data.feedback.growth.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

function BiasZone({ data }: { data: Counterfactual }) {
  return (
    <section className="card bias">
      <h2>
        Проверка на предвзятость
        <span className="muted">{data.scale}</span>
      </h2>
      <p className="muted small">
        Один и тот же ответ, изменён только один параметр: «{ATTRIBUTE_LABEL[data.attribute] ?? data.attribute}».
        {data.synthetic_prefix
          ? " В тексте не было упоминания села или города, поэтому к обоим вариантам добавлено одно предложение с разным значением признака."
          : " Изменено только упоминание места в самом ответе."}
      </p>
      <div className="bias-grid">
        {[data.a, data.b].map((side) => (
          <div key={side.label} className="bias-side">
            <div className="bias-label">{side.label}</div>
            <div className={`level level-${side.level}`}>{side.level_label}</div>
            <div className="bias-score">балл {side.score.toFixed(3)}</div>
            <Probabilities values={side.probabilities} />
          </div>
        ))}
      </div>
      <div
        className={`bias-delta ${
          data.abs_delta <= data.target ? "ok" : "warn"
        }`}
      >
        Δ = {data.abs_delta.toFixed(3)} ступени уровня · {data.verdict} · цель{" "}
        {data.target} · порог {data.hard_threshold}
        {data.level_changed ? " · уровень изменился" : " · уровень не изменился"}
      </div>
    </section>
  );
}

export default function App() {
  const [view, setView] = useState<"journey" | "overview" | "workspace" | "history" | "methodology">(() => {
    const requested = new URLSearchParams(window.location.search).get("view");
    return requested === "workspace" || requested === "history" || requested === "methodology" || requested === "overview"
      ? requested : "journey";
  });
  const [journeyResult, setJourneyResult] = useState<JourneyResult | null>(null);
  const [journeyRoute, setJourneyRoute] = useState<Route>("manual_review");
  const [journeyReason, setJourneyReason] = useState("");
  const [journeyEvidence, setJourneyEvidence] = useState("");
  const [journeyTimecode, setJourneyTimecode] = useState("");
  const [journeyReviews, setJourneyReviews] = useState<JourneyReview[]>([]);
  const [pilotId, setPilotId] = useState<string | null>(null);
  const [pilotQueue, setPilotQueue] = useState<PilotSubmission[]>([]);
  const [pilotSaving, setPilotSaving] = useState(false);
  const [framework, setFramework] = useState<EvidenceFramework | null>(null);
  const [text, setText] = useState("");
  const [examples, setExamples] = useState<Example[]>([]);
  const [candidates, setCandidates] = useState<DemoCandidate[]>([]);
  const [selectedExample, setSelectedExample] = useState<Example | null>(null);
  const [reviews, setReviews] = useState<ReviewEvent[]>([]);
  const [selectedRoute, setSelectedRoute] = useState<Route>("manual_review");
  const [reviewReason, setReviewReason] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [bias, setBias] = useState<Counterfactual | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadExamples().then(setExamples).catch(() => setExamples([]));
    loadDemoCandidates().then(setCandidates).catch(() => setCandidates([]));
    loadPilotSubmissions().then(setPilotQueue).catch(() => setPilotQueue([]));
    loadMethodology().then(setFramework).catch(() => setFramework(null));
  }, []);

  function discardJourney() {
    if (journeyResult?.mediaUrl) URL.revokeObjectURL(journeyResult.mediaUrl);
    setJourneyResult(null);
  }

  async function openExample(example: Example) {
    discardJourney();
    setText(example.text);
    setSelectedExample(example);
    setAnalysis(null);
    setBias(null);
    setReviewReason("");
    setError(null);
    setView("workspace");
    setBusy(true);
    try {
      const [result, history] = await Promise.all([
        analyze(example.text),
        loadReviews(example.id).catch(() => []),
      ]);
      setAnalysis(result);
      setSelectedRoute(result.decision_support.route);
      setReviews(history);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function run(action: "analyze" | "bias") {
    if (!text.trim()) return;
    if (journeyResult && (journeyResult.language !== "ru" || journeyResult.mode !== "text")) {
      setError("Для этого формата предусмотрена проверка комиссией по исходной записи.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (action === "analyze") {
        setBias(null);
        const result = await analyze(text);
        setAnalysis(result);
        setSelectedRoute(result.decision_support.route);
      } else {
        setBias(await counterfactual(text));
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function loadFile(file: File | undefined) {
    if (!file) return;
    if (file.size > 2_000_000) {
      setError("Файл больше 2 МБ. Загрузите текстовый файл меньшего размера.");
      return;
    }
    const allowed = [".txt", ".md"];
    if (!allowed.some((extension) => file.name.toLowerCase().endsWith(extension))) {
      setError("Для текстового ответа поддерживаются файлы TXT и MD. Аудио и видео можно добавить через путь кандидата.");
      return;
    }
    setText(await file.text());
    discardJourney();
    setSelectedExample(null);
    setReviews([]);
    setAnalysis(null);
    setBias(null);
    setError(null);
  }

  async function completeJourney(result: JourneyResult) {
    const combined = result.story.trim();
    if (journeyResult?.mediaUrl && journeyResult.mediaUrl !== result.mediaUrl) URL.revokeObjectURL(journeyResult.mediaUrl);
    setJourneyResult(result);
    setJourneyRoute("manual_review");
    setJourneyReason("");
    setJourneyEvidence("");
    setJourneyTimecode("");
    setJourneyReviews([]);
    setPilotId(null);
    setSelectedExample(null);
    setText(combined);
    setBias(null);
    setAnalysis(null);
    setError(null);
    setView("workspace");
    setPilotSaving(true);
    try {
      const saved = await createPilotSubmission({
        language: result.language, mode: result.mode, story: result.story,
        media_link: result.mediaLink, scenario_choice: result.scenarioChoice,
        rationale: result.rationale, consent: result.consent,
      });
      if (result.mediaUrl) {
        const media = await fetch(result.mediaUrl).then((response) => response.blob());
        await uploadPilotMedia(saved.id, media);
      }
      setPilotId(saved.id);
      setPilotQueue(await loadPilotSubmissions());
    } catch (e) {
      setError(`Ответ открыт для проверки, но не добавлен в очередь: ${String(e)}`);
    } finally {
      setPilotSaving(false);
    }
    if (result.language === "ru" && result.mode === "text" && combined) {
      setBusy(true);
      try {
        const evaluated = await analyze(combined);
        setAnalysis(evaluated);
        setSelectedRoute(evaluated.decision_support.route);
      } catch (e) {
        setError(String(e));
      } finally {
        setBusy(false);
      }
    }
  }

  async function openPilot(item: PilotSubmission) {
    discardJourney();
    setError(null);
    setBusy(true);
    setView("workspace");
    try {
      const detail = await loadPilotSubmission(item.id);
      setPilotId(detail.id);
      setJourneyResult({
        language: detail.language, mode: detail.mode, story: detail.story,
        mediaLink: detail.media_link || undefined,
        mediaUrl: detail.has_media ? `/pilot/submissions/${encodeURIComponent(detail.id)}/media` : undefined,
        scenarioChoice: detail.scenario_choice, rationale: detail.rationale, consent: true,
      });
      setJourneyReviews((detail.reviews || []).map((review) => ({
        route: review.selected_route, reason: review.reason, evidence: review.evidence,
        timecode: review.timecode, at: review.created_at,
      })));
      setText(detail.story);
      setAnalysis(null);
      setBias(null);
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  async function submitReview() {
    if (!selectedExample || !analysis) return;
    setReviewBusy(true);
    setError(null);
    try {
      await saveReview(selectedExample.id, selectedRoute, reviewReason);
      setReviews(await loadReviews(selectedExample.id));
      setCandidates(await loadDemoCandidates());
      setReviewReason("");
    } catch (e) {
      setError(String(e));
    } finally {
      setReviewBusy(false);
    }
  }

  async function submitJourneyReview() {
    const reason = journeyReason.trim();
    const evidence = journeyEvidence.trim();
    if (reason.length < 10) {
      setError("Добавьте короткое объяснение решения — не менее 10 символов.");
      return;
    }
    if (journeyRoute === "priority_interview" && evidence.length < 10) {
      setError("Чтобы пригласить кандидата в первую очередь, добавьте конкретную фразу или наблюдение.");
      return;
    }
    const next = { route: journeyRoute, reason, evidence, timecode: journeyTimecode.trim(), at: new Date().toISOString() };
    if (pilotId) {
      try {
        await savePilotReview(pilotId, journeyRoute, reason, evidence, journeyTimecode.trim());
        const detail = await loadPilotSubmission(pilotId);
        setJourneyReviews((detail.reviews || []).map((review) => ({ route: review.selected_route, reason: review.reason, evidence: review.evidence, timecode: review.timecode, at: review.created_at })));
        setPilotQueue(await loadPilotSubmissions());
      } catch (e) { setError(String(e)); return; }
    } else setJourneyReviews((previous) => [next, ...previous]);
    setJourneyReason("");
    setJourneyEvidence("");
    setJourneyTimecode("");
    setError(null);
  }

  if (view === "journey") {
    return <Journey onComplete={completeJourney} onReview={() => setView("overview")} />;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-symbol" aria-hidden="true"><i /><i /><i /><i /></div>
          <div><strong>Qadam AI</strong><span>Отбор кандидатов · inVision U</span></div>
        </div>
        <div className="sidebar-caption">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <nav className="side-nav" aria-label="Разделы">
          <button onClick={() => setView("journey")}><span>✦</span> Анкета кандидата</button>
          <button className={view === "overview" ? "selected" : ""} onClick={() => setView("overview")}><span>◫</span> Кандидаты</button>
          <button className={view === "workspace" ? "selected" : ""} onClick={() => setView("workspace")}><span>◈</span> Проверка ответа</button>
          <div className="nav-divider">ДОПОЛНИТЕЛЬНО</div>
          <button className={view === "history" ? "selected" : ""} onClick={() => setView("history")}><span>◷</span> История проверок</button>
          <button className={view === "methodology" ? "selected" : ""} onClick={() => setView("methodology")}><span>▦</span> Правила оценки</button>
        </nav>
        <div className="sidebar-bottom">
          <div className="secure-note"><span className="secure-dot" /> Доступ для приёмной комиссии</div>
          <p>Итоговое решение принимает комиссия.</p>
        </div>
      </aside>

      <div className="app-main">
        <div className="topbar"><span>inVision U <b>/</b> Отбор кандидатов</span><span className="topbar-right"><i /> Онлайн</span></div>
        <div className="page">
          {view === "overview" && <>
            <section className="hero">
              <div className="hero-content">
                <span className="eyebrow">РАБОЧЕЕ МЕСТО ПРИЁМНОЙ КОМИССИИ</span>
                <h1>Увидеть потенциал.<br /><em>Не потерять человека.</em></h1>
                <p>Qadam AI находит в ответе конкретные действия и результаты, показывает подтверждающие цитаты и помогает комиссии подготовиться к интервью.</p>
                <div className="hero-actions"><button className="hero-cta" onClick={() => setView("journey")}>Открыть анкету <span>↗</span></button><button className="hero-secondary" onClick={() => setView("workspace")}>Проверить ответ →</button></div>
              </div>
              <div className="hero-art" aria-hidden="true"><div className="art-orbit one" /><div className="art-orbit two" /><div className="art-core">Q</div><div className="art-label">Факты в ответе<br />Решение комиссии</div></div>
            </section>
            <div className="process-grid" aria-label="Как работает сервис">
              <div className="process-step"><b>1</b><div><strong>Кандидат отвечает</strong><span>Текстом, голосом или видео</span></div></div>
              <div className="process-step"><b>2</b><div><strong>Qadam находит факты</strong><span>Действия, результаты и цитаты</span></div></div>
              <div className="process-step"><b>3</b><div><strong>Комиссия решает</strong><span>И сохраняет своё объяснение</span></div></div>
            </div>
            <div className="section-title"><div><span className="eyebrow">КАНДИДАТЫ</span><h2>Ожидают проверки</h2></div><span className="section-aside">Выберите кандидата, чтобы открыть ответ →</span></div>
            <section className="candidate-list">
          {pilotQueue.map((candidate) => (
              <button key={candidate.id} className="candidate-tile pilot-candidate" onClick={() => openPilot(candidate)}>
                <div className="candidate-tile-top"><span className="candidate-avatar">Q</span><span className="candidate-arrow">↗</span></div>
                <strong>Ответ кандидата</strong>
                <span className="candidate-id">{candidate.id} · {candidate.language.toUpperCase()} · {candidate.mode.toUpperCase()}</span>
                <small className={candidate.latest_route ? "status-reviewed" : "status-pending"}>{candidate.latest_route ? `● ${ROUTE_LABEL[candidate.latest_route]}` : "● Ожидает рассмотрения"}</small>
              </button>
          ))}
          {candidates.map((candidate, index) => {
            const example = examples.find((item) => item.id === candidate.id);
            return (
              <button
                key={candidate.id}
                className={`candidate-tile ${selectedExample?.id === candidate.id ? "active" : ""}`}
                disabled={!example}
                onClick={() => example && openExample(example)}
              >
                <div className="candidate-tile-top"><span className="candidate-avatar">{String(index + 1).padStart(2, "0")}</span><span className="candidate-arrow">↗</span></div>
                <strong>Кандидат {String(index + 1).padStart(2, "0")}</strong>
                <span className="candidate-id">Лидерские способности</span>
                <small className={candidate.latest_review ? "status-reviewed" : "status-pending"}>{candidate.latest_review
                  ? `● ${ROUTE_LABEL[candidate.latest_review.selected_route]}`
                  : "● Ожидает рассмотрения"}</small>
              </button>
            );
          })}
            </section>
            <div className="trust-strip"><strong>На чём основан результат?</strong><span>Для каждого вывода показана цитата из ответа, а решение комиссии сохраняется в истории.</span></div>
          </>}

          {view === "workspace" && <>
            <div className="view-heading"><div><span className="eyebrow">РАБОЧЕЕ МЕСТО ИНТЕРВЬЮЕРА</span><h1>Анализ ответа</h1><p>Конкретные действия, результаты и цитаты по компетенции «Лидерские способности».</p></div><span className="scope-pill">С ЦИТАТАМИ</span></div>

            {journeyResult && <section className="card journey-handoff">
              <div><span className="eyebrow">КАНДИДАТ → КОМИССИЯ</span><h2>История кандидата на языке оригинала</h2>
                <p>Интерактивный сценарий · {journeyResult.language.toUpperCase()} · {journeyResult.mode.toUpperCase()} · {pilotSaving ? "сохраняется…" : pilotId ? `сохранено под кодом ${pilotId}` : "только текущая сессия"}</p></div>
              <div className="handoff-answers">
                <div><span>1 · Исходная история</span><p>{journeyResult.story || "Без текстовой расшифровки — просмотрите запись."}</p></div>
                <div><span>2 · Первый шаг в командной ситуации</span><p>{journeyResult.scenarioChoice}</p></div>
                <div><span>3 · Обоснование и следующий шаг</span><p>{journeyResult.rationale}</p></div>
              </div>
              {journeyResult.mediaUrl && <div className="handoff-media">{journeyResult.mode === "video" ? <video controls src={journeyResult.mediaUrl} /> : <audio controls src={journeyResult.mediaUrl} />}</div>}
              {journeyResult.mediaLink && <div className="handoff-media"><a href={journeyResult.mediaLink} target="_blank" rel="noopener noreferrer">Открыть исходное видео в новой вкладке ↗</a><p className="muted small">Исходная запись доступна комиссии для проверки ответа.</p></div>}
              <div className="handoff-questions"><strong>Вопросы для интервьюера</strong><ul>
                <li>Что кандидат сделал лично, а что — остальные участники?</li>
                <li>Какой наблюдаемый результат подтвердил бы эту историю?</li>
                <li>Почему в командной ситуации выбран именно этот первый шаг и что кандидат сделал бы, если он не сработает?</li>
              </ul><small>Комиссия может изменить или дополнить эти вопросы перед интервью.</small></div>
              {(journeyResult.language !== "ru" || journeyResult.mode !== "text") && <div className="handoff-warning">Ответ направлен на проверку комиссии по исходной записи. Ситуационная мини-сцена используется как дополнительный материал и не заменяет решение интервьюера.</div>}
              <div className="journey-review-panel">
                <h3>Следующий шаг</h3>
                <p className="muted small">{pilotId ? `Решение будет сохранено в истории кандидата ${pilotId}.` : "Выберите следующий шаг и добавьте краткое объяснение."}</p>
                <select aria-label="Следующий шаг" value={journeyRoute} onChange={(event) => setJourneyRoute(event.target.value as Route)}>{Object.entries(ROUTE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
                <textarea rows={2} value={journeyEvidence} onChange={(event) => setJourneyEvidence(event.target.value)} placeholder="Цитата или наблюдение, на котором основано решение" />
                <input value={journeyTimecode} onChange={(event) => setJourneyTimecode(event.target.value)} placeholder="Таймкод записи, если есть: 00:42" aria-label="Таймкод записи" />
                <textarea rows={3} value={journeyReason} onChange={(event) => setJourneyReason(event.target.value)} placeholder="Коротко объясните решение комиссии" />
                {error && <p className="error" role="alert">{error}</p>}
                <div className="actions"><button className="primary" onClick={submitJourneyReview}>Сохранить решение</button></div>
                {journeyReviews.length > 0 && <ul className="review-events">{journeyReviews.map((item, index) => <li key={item.at + index}><strong>{ROUTE_LABEL[item.route]}</strong> · {new Date(item.at).toLocaleString("ru-RU")}<p>{item.reason}</p>{item.evidence && <p>Свидетельство: «{item.evidence}»{item.timecode && ` · ${item.timecode}`}</p>}</li>)}</ul>}
              </div>
            </section>}

      <main className={journeyResult && !analysis ? "layout journey-manual-layout" : "layout"}>
        {(!journeyResult || analysis) && <section className="card input-zone">
          <h2>Ответ кандидата <span className="muted">01 · Исходные данные</span></h2>
          <div className="examples">
            {examples.map((example) => (
              <button
                key={example.key}
                className="ghost"
                onClick={() => {
                  openExample(example);
                }}
              >
                {example.title}
              </button>
            ))}
          </div>
          <textarea
            value={text}
            onChange={(event) => { setText(event.target.value); discardJourney(); }}
            placeholder="Вставьте ответ кандидата на вопрос: «Расскажите о случае, когда вы вели за собой других»"
            rows={10}
          />
          {selectedExample && text !== selectedExample.text && (
            <p className="muted small">
              Текст изменён. Для записи действия в учебный журнал снова выберите
              исходный пример из очереди.
            </p>
          )}
          <label className="file-upload">
            Загрузить текстовый файл
            <input
              type="file"
              accept=".txt,.md,text/plain,text/markdown"
              onChange={(event) => loadFile(event.target.files?.[0])}
            />
          </label>
          <div className="actions">
            <button
              className="primary"
              disabled={busy || !text.trim() || Boolean(journeyResult && (journeyResult.language !== "ru" || journeyResult.mode !== "text"))}
              onClick={() => run("analyze")}
            >
              {busy ? "Считаю…" : "Разобрать ответ"}
            </button>
            <button
              className="secondary"
              disabled={busy || !text.trim() || Boolean(journeyResult && (journeyResult.language !== "ru" || journeyResult.mode !== "text"))}
              onClick={() => run("bias")}
            >
              Проверить на предвзятость
            </button>
            {analysis && (
              <>
                <button className="secondary" onClick={() => window.print()}>Скачать отчёт</button>
              </>
            )}
          </div>
          {error && !journeyResult && <p className="error">{error}</p>}
          {busy && <p className="loading-note">Анализируем ответ и проверяем цитаты…</p>}
          <p className="muted small">
            Система не принимает решений о поступлении и не выставляет балл по
            блокам личного опыта и «Ценности». Регион, школа, язык и доход
            семьи не влияют на рекомендацию.
          </p>
        </section>}

        <div className="results">
          {bias && <BiasZone data={bias} />}
          {analysis ? (
            <>
              <LevelZone data={analysis} />
              <AtolaZone data={analysis} />
              {selectedExample && text === selectedExample.text && (
                <section className="card review-zone">
                  <h2>Решение интервьюера <span className="muted">учебный журнал</span></h2>
                  <p className="muted small">
                    Это рекомендация для следующего этапа, а не решение о поступлении.
                    В журнал записываются ID кейса, выбранное действие и причина —
                    не текст ответа.
                  </p>
                  <label>
                    Следующий шаг
                    <select value={selectedRoute}
                      onChange={(event) => setSelectedRoute(event.target.value as Route)}>
                      {Object.entries(ROUTE_LABEL).map(([value, label]) =>
                        <option key={value} value={value}>{label}</option>)}
                    </select>
                  </label>
                  <label>
                    Причина изменения / комментарий
                    <textarea rows={3} value={reviewReason}
                      onChange={(event) => setReviewReason(event.target.value)}
                      placeholder="Если вы меняете рекомендацию, коротко объясните почему" />
                  </label>
                  <button className="primary" disabled={reviewBusy} onClick={submitReview}>
                    {reviewBusy ? "Сохраняю…" : "Сохранить проверку"}
                  </button>
                  <h3>История действий</h3>
                  {reviews.length === 0 && <p className="muted">Пока нет записей.</p>}
                  <ul className="review-events">
                    {reviews.map((item) => (
                      <li key={item.id}>
                        <strong>{item.action === "override" ? "Изменено" : "Подтверждено"}:</strong>{" "}
                        {ROUTE_LABEL[item.selected_route]} · {item.reviewer} · {item.created_at}
                        {item.reason && <p>{item.reason}</p>}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              <HintsZone data={analysis} />
            </>
          ) : (
            !bias && journeyResult ? <section className="card manual-review-card"><div className="placeholder-icon">◈</div><span className="eyebrow">ОТВЕТ КАНДИДАТА</span><h2>Посмотрите исходную запись</h2><p>История и ответ на командную ситуацию находятся выше. Просмотрите материал, при необходимости задайте уточняющий вопрос и сохраните решение с коротким объяснением.</p></section> : !bias && (
              <section className="card placeholder">
                <div className="placeholder-icon">✳</div>
                <span className="eyebrow">ГОТОВО К АНАЛИЗУ</span>
                <h2>Начните с одного ответа</h2>
                <p>Выберите кандидата из очереди или вставьте текст ответа. Вы увидите подтверждающие цитаты, рекомендацию и вопросы для интервью.</p>
              </section>
            )
          )}
        </div>
      </main>
          </>}

          {view === "history" && <>
            <div className="view-heading"><div><span className="eyebrow">ПРОЗРАЧНОСТЬ РЕШЕНИЙ</span><h1>История проверок</h1><p>Последнее действие комиссии по каждому рассмотренному ответу.</p></div></div>
            <section className="card history-card">
              {candidates.map((candidate) => <button key={candidate.id} className="history-row" onClick={() => {
                const example = examples.find((item) => item.id === candidate.id);
                if (example) openExample(example);
              }}>
                <span className="candidate-avatar">{candidate.title.charAt(0)}</span>
                <span><strong>{candidate.title}</strong><small>{candidate.id}</small></span>
                <span className="history-status">{candidate.latest_review ? ROUTE_LABEL[candidate.latest_review.selected_route] : "Не проверено"}</span>
                <span className="history-action">Открыть ↗</span>
              </button>)}
            </section>
            <p className="muted small history-disclaimer">Каждое решение сохраняется вместе с объяснением, временем проверки и версией правил оценки.</p>
          </>}

          {view === "methodology" && <>
            <div className="view-heading"><div><span className="eyebrow">ПРИНЦИПЫ ОЦЕНКИ</span><h1>Методика</h1><p>Какие признаки учитываются и где решение принимает комиссия.</p></div></div>
            <div className="method-grid">
              <section className="card method-ready"><span className="method-index">03</span><span className="method-state">НАСТРОЕНО</span><h2>Лидерские способности</h2><p>Ответ разбирается по структуре ATOLA. Уровень, цитаты и вопросы для интервью собраны в одном отчёте, а итог подтверждает комиссия.</p><button className="secondary" onClick={() => setView("workspace")}>Открыть анализ →</button></section>
              <section className="card method-pending"><span className="method-index">8 блоков</span><span className="method-state">ОЖИДАЕТ МЕТОДОЛОГИЮ</span><h2>Полный профиль</h2><p>Остальные блоки, вопросы, веса и пороги не выдуманы. Их подключим после получения утверждённых материалов и проверки экспертами.</p><div className="method-line">Нужны: BARS · ATOLA · правила интерпретации · экспертная разметка</div></section>
            </div>
            {framework && <section className="card qef-card">
              <div className="qef-head"><div><span className="eyebrow">ПРАВИЛА ОЦЕНКИ · {framework.version}</span><h2>Карта компетенций</h2></div><span className="method-state">ДЛЯ СОГЛАСОВАНИЯ</span></div>
              <p className="muted">Эта версия помогает согласовать вопросы, признаки и уровни оценки с командой inVision U. Она не используется для автоматического отказа кандидату.</p>
              <div className="qef-grid">{framework.competencies.map((item, index) => <article key={item.id} className="qef-item">
                <div className="qef-title"><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{item.name_ru}</strong><small>{item.name_en}</small></div></div>
                <p>{item.construct}</p><div className="qef-mode">{item.decision_mode.includes("human_only") ? "Решает комиссия" : item.decision_mode.includes("experimental") ? "Рекомендация для комиссии" : "Проверяет комиссия"}</div>
                <details><summary>Вопрос и якоря</summary><p><b>Вопрос:</b> {item.prompt_ru}</p><ul>{item.levels.map((level) => <li key={level.key}><strong>{level.label}:</strong> {level.anchor}</li>)}</ul></details>
              </article>)}</div>
            </section>}
            <section className="card competency-card">
              <h2>Карта компетенций <span className="muted">статус реализации</span></h2>
              <div className="competency-list">
                {COMPETENCY_MAP.map(([number, name, status]) => (
                  <div key={number} className="competency-row">
                    <span className="competency-number">{number}</span>
                    <strong>{name}</strong>
                    <span className={status === "Настроено" ? "comp-ready" : status === "Оценка комиссией" ? "comp-human" : "comp-pending"}>{status}</span>
                  </div>
                ))}
              </div>
            </section>
            <div className="trust-strip"><strong>Принцип: доказательство раньше балла.</strong><span>LLM извлекает и цитирует. Модель предлагает уровень. Человек принимает решение.</span></div>
          </>}
        </div>
      </div>
    </div>
  );
}
