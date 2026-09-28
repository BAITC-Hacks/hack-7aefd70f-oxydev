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
const ROUTE_LABEL: Record<Route, string> = {
  manual_review: "Ручная проверка",
  priority_interview: "Приоритетное интервью",
  standard_interview: "Стандартный порядок",
};
type JourneyReview = { route: Route; reason: string; evidence: string; timecode: string; at: string };
const COMPETENCY_MAP = [
  ["01", "Мотивация на университет", "Ожидает рубрику"],
  ["02", "Мотивация на специальность", "Ожидает рубрику"],
  ["03", "Лидерские способности", "Работает в MVP"],
  ["04", "Работа в команде", "Ожидает рубрику"],
  ["05", "Ценности", "Только человек"],
  ["06", "Предыдущий опыт", "Ожидает рубрику"],
  ["07", "Интеллект", "Ожидает рубрику"],
  ["08", "Purpose-driven leadership", "Ожидает рубрику"],
  ["09", "Wounded leadership", "Только человек"],
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
        Разбор ATOLA
        <span className="muted">
          покрыто {Math.round(data.atola_coverage * 5)} из 5
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
        Уровень
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

      <h3>Сработавшие индикаторы</h3>
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

      <h3>Вклад признаков в этот балл</h3>
      <ul className="features">
        {data.features.map((feature) => (
          <li key={feature.name}>
            <span className="feature-label">{feature.label}</span>
            <span className="feature-value">{feature.value}</span>
            <span className="feature-bar">
              <span
                className={
                  feature.contribution >= 0 ? "feature-plus" : "feature-minus"
                }
                style={{
                  width: `${Math.min(Math.abs(feature.contribution) * 45, 100)}%`,
                }}
              />
            </span>
            <span className="feature-contribution">
              {feature.contribution > 0 ? "+" : ""}
              {feature.contribution}
            </span>
          </li>
        ))}
      </ul>
      <p className="muted small">
        Текстовые векторы целиком: {data.text_contribution}. Разбор выполнен
        слоем извлечения «{data.backend}».
      </p>
      <p className="muted small provenance">
        Модель {data.provenance.model_version} · промпт {data.provenance.prompt_version} ·
        методология {data.provenance.methodology} ({data.provenance.methodology_scope})
      </p>
    </section>
  );
}

function HintsZone({ data }: { data: Analysis }) {
  return (
    <section className="card">
      <h2>Что спросить на интервью</h2>
      {data.sensitive.map((item) => (
        <div key={item.note} className="sensitive">
          <strong>Модель не выставляет балл по этому блоку.</strong>
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
        Один и тот же ответ, изменён только фоновый признак «{data.attribute}».
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
      setError("Автоматическая оценка этого формата пока не валидирована. Исходный материал доступен комиссии для ручной проверки.");
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
      setError("Файл больше 2 МБ. Для MVP загрузите текстовый файл меньшего размера.");
      return;
    }
    const allowed = [".txt", ".md"];
    if (!allowed.some((extension) => file.name.toLowerCase().endsWith(extension))) {
      setError("Сейчас поддерживаются TXT и MD. Структурированные файлы, PDF/DOCX и видео — следующий этап.");
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
      setError(`Ответ открыт локально, но не сохранён в пилотную очередь: ${String(e)}`);
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
      setError("Для маршрута нужен конкретный комментарий не короче 10 символов.");
      return;
    }
    if (journeyRoute === "priority_interview" && evidence.length < 10) {
      setError("Для приоритетного интервью укажите конкретную фразу или наблюдение из исходного материала.");
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
          <div><strong>Qadam AI</strong><span>Leader ID · inVision U</span></div>
        </div>
        <div className="sidebar-caption">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <nav className="side-nav" aria-label="Разделы">
          <button onClick={() => setView("journey")}><span>✦</span> Путь кандидата</button>
          <button className={view === "overview" ? "selected" : ""} onClick={() => setView("overview")}><span>◫</span> Обзор</button>
          <button className={view === "workspace" ? "selected" : ""} onClick={() => setView("workspace")}><span>◈</span> Анализ ответа</button>
          <button className={view === "history" ? "selected" : ""} onClick={() => setView("history")}><span>◷</span> История проверок</button>
          <button className={view === "methodology" ? "selected" : ""} onClick={() => setView("methodology")}><span>▦</span> Методология</button>
        </nav>
        <div className="sidebar-bottom">
          <div className="secure-note"><span className="secure-dot" /> Локальный пилот · по согласию</div>
          <p>Решение о зачислении всегда остаётся за приёмной комиссией.</p>
        </div>
      </aside>

      <div className="app-main">
        <div className="topbar"><span>inVision U <b>/</b> Recruitment intelligence</span><span className="topbar-right"><i /> Локальный MVP</span></div>
        <div className="page">
          {view === "overview" && <>
            <section className="hero">
              <div className="hero-content">
                <span className="eyebrow">ПРИЁМНАЯ КОМИССИЯ · ДЕМО</span>
                <h1>Увидеть потенциал.<br /><em>Не потерять человека.</em></h1>
                <p>Qadam AI помогает рассмотреть ответ кандидата по понятной рубрике: извлекает доказательства, показывает неопределённость и оставляет решение человеку.</p>
                <div className="hero-actions"><button className="hero-cta" onClick={() => setView("journey")}>Путь кандидата <span>↗</span></button><button className="hero-secondary" onClick={() => setView("workspace")}>Открыть анализ →</button></div>
              </div>
              <div className="hero-art" aria-hidden="true"><div className="art-orbit one" /><div className="art-orbit two" /><div className="art-core">Q</div><div className="art-label">Human judgment<br />+ explainable AI</div></div>
            </section>
            <div className="stat-grid">
              <div className="stat-card"><span>В очереди</span><strong>{(candidates.length + pilotQueue.length).toString().padStart(2, "0")}</strong><small>пилотные и синтетические кейсы</small></div>
              <div className="stat-card"><span>Методология</span><strong>01<span className="stat-denominator">/09</span></strong><small>компетенция реализована</small></div>
              <div className="stat-card"><span>Проверено человеком</span><strong>{(candidates.filter((item) => item.latest_review).length + pilotQueue.filter((item) => item.latest_route).length).toString().padStart(2, "0")}</strong><small>с сохранённым обоснованием</small></div>
              <div className="stat-card stat-highlight"><span>Принцип системы</span><strong>HITL</strong><small>последнее слово — за комиссией</small></div>
            </div>
            <div className="section-title"><div><span className="eyebrow">РАБОЧИЙ ПОТОК</span><h2>Очередь на рассмотрение</h2></div><span className="section-aside">Нажмите на кейс, чтобы открыть полный разбор →</span></div>
            <section className="candidate-list">
          {pilotQueue.map((candidate) => (
              <button key={candidate.id} className="candidate-tile pilot-candidate" onClick={() => openPilot(candidate)}>
                <div className="candidate-tile-top"><span className="candidate-avatar">Q</span><span className="candidate-arrow">↗</span></div>
                <strong>Пилотное прохождение</strong>
                <span className="candidate-id">{candidate.id} · {candidate.language.toUpperCase()} · {candidate.mode.toUpperCase()}</span>
                <small className={candidate.latest_route ? "status-reviewed" : "status-pending"}>{candidate.latest_route ? `● ${ROUTE_LABEL[candidate.latest_route]}` : "● Ожидает рассмотрения"}</small>
              </button>
          ))}
          {candidates.map((candidate) => {
            const example = examples.find((item) => item.id === candidate.id);
            return (
              <button
                key={candidate.id}
                className={`candidate-tile ${selectedExample?.id === candidate.id ? "active" : ""}`}
                disabled={!example}
                onClick={() => example && openExample(example)}
              >
                <div className="candidate-tile-top"><span className="candidate-avatar">{candidate.title.charAt(0)}</span><span className="candidate-arrow">↗</span></div>
                <strong>{candidate.title}</strong>
                <span className="candidate-id">{candidate.id} · Синтетический пример</span>
                <small className={candidate.latest_review ? "status-reviewed" : "status-pending"}>{candidate.latest_review
                  ? `● ${ROUTE_LABEL[candidate.latest_review.selected_route]}`
                  : "● Ожидает рассмотрения"}</small>
              </button>
            );
          })}
            </section>
            <div className="trust-strip"><strong>Почему оценке можно задать вопрос?</strong><span>Каждый вывод связан с цитатой из ответа, версией модели и маршрутом ручной проверки.</span></div>
          </>}

          {view === "workspace" && <>
            <div className="view-heading"><div><span className="eyebrow">РАБОЧЕЕ МЕСТО ИНТЕРВЬЮЕРА</span><h1>Анализ ответа</h1><p>Проверяемые доказательства по компетенции «Лидерские способности».</p></div><span className="scope-pill">01 / 09 компетенций</span></div>

            {journeyResult && <section className="card journey-handoff">
              <div><span className="eyebrow">КАНДИДАТ → КОМИССИЯ</span><h2>История кандидата на языке оригинала</h2>
                <p>Интерактивный сценарий · {journeyResult.language.toUpperCase()} · {journeyResult.mode.toUpperCase()} · {pilotSaving ? "сохраняется…" : pilotId ? `сохранено под кодом ${pilotId}` : "только текущая сессия"}</p></div>
              <div className="handoff-answers">
                <div><span>1 · Исходная история</span><p>{journeyResult.story || "Без текстовой расшифровки — просмотрите запись."}</p></div>
                <div><span>2 · Первый шаг в вымышленной ситуации</span><p>{journeyResult.scenarioChoice}</p></div>
                <div><span>3 · Обоснование и следующий шаг</span><p>{journeyResult.rationale}</p></div>
              </div>
              {journeyResult.mediaUrl && <div className="handoff-media">{journeyResult.mode === "video" ? <video controls src={journeyResult.mediaUrl} /> : <audio controls src={journeyResult.mediaUrl} />}</div>}
              {journeyResult.mediaLink && <div className="handoff-media"><a href={journeyResult.mediaLink} target="_blank" rel="noopener noreferrer">Открыть исходное видео в новой вкладке ↗</a><p className="muted small">Ссылка не анализировалась и не загружалась в Qadam AI. Для реального пилота нужны согласованный доступ и правила хранения.</p></div>}
              <div className="handoff-questions"><strong>Вопросы для интервьюера</strong><ul>
                <li>Что кандидат сделал лично, а что — остальные участники?</li>
                <li>Какой наблюдаемый результат подтвердил бы эту историю?</li>
                <li>Почему в командной ситуации выбран именно этот первый шаг и что кандидат сделал бы, если он не сработает?</li>
              </ul><small>Это общие подсказки для беседы, не вывод официальной методологии.</small></div>
              {(journeyResult.language !== "ru" || journeyResult.mode !== "text") && <div className="handoff-warning">Ручная проверка: автоматическая оценка этого языка или формата не валидирована. Запись сохраняется в локальном пилотном контуре; без расшифровки AI её не анализировал. Ситуационная мини-сцена не оценивается баллом.</div>}
              <div className="journey-review-panel">
                <h3>Маршрут после просмотра человеком</h3>
                <p className="muted small">{pilotId ? `Проверка будет сохранена в неизменяемой истории прохождения ${pilotId}.` : "Учебная проверка текущей сессии исчезнет после обновления страницы."}</p>
                <select aria-label="Маршрут рассмотрения" value={journeyRoute} onChange={(event) => setJourneyRoute(event.target.value as Route)}>{Object.entries(ROUTE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
                <textarea rows={2} value={journeyEvidence} onChange={(event) => setJourneyEvidence(event.target.value)} placeholder="Дословная фраза или наблюдение из записи (обязательно для приоритетного маршрута)" />
                <input value={journeyTimecode} onChange={(event) => setJourneyTimecode(event.target.value)} placeholder="Таймкод записи, если есть: 00:42" aria-label="Таймкод записи" />
                <textarea rows={3} value={journeyReason} onChange={(event) => setJourneyReason(event.target.value)} placeholder="Что именно в исходных материалах обосновывает этот маршрут?" />
                {error && <p className="error" role="alert">{error}</p>}
                <div className="actions"><button className="primary" onClick={submitJourneyReview}>Зафиксировать проверку</button></div>
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
                <button className="secondary" onClick={() => window.print()}>Печать / PDF</button>
              </>
            )}
          </div>
          {error && !journeyResult && <p className="error">{error}</p>}
          {busy && <p className="loading-note">Анализируем ответ и проверяем цитаты…</p>}
          <p className="muted small">
            Система не принимает решений о поступлении и не выставляет балл по
            блокам Wounded leadership и «Ценности». Регион, школа, язык и доход
            семьи в модель не входят.
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
                    Это предварительный маршрут рассмотрения, не решение о поступлении.
                    В журнал записываются ID вымышленного кейса, маршрут и причина —
                    не текст ответа.
                  </p>
                  <label>
                    Маршрут после проверки
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
                      placeholder="При изменении маршрута укажите конкретное основание (от 10 символов)" />
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
            !bias && journeyResult ? <section className="card manual-review-card"><div className="placeholder-icon">◈</div><span className="eyebrow">РУЧНОЕ РАССМОТРЕНИЕ</span><h2>Оригинал важнее предположений</h2><p>История, запись или ссылка и ответ на ситуационную сцену находятся выше. Автоматического балла для этого материала нет. Просмотрите исходный ответ, задайте уточняющий вопрос и зафиксируйте маршрут с причиной.</p></section> : !bias && (
              <section className="card placeholder">
                <div className="placeholder-icon">✳</div>
                <span className="eyebrow">ГОТОВО К АНАЛИЗУ</span>
                <h2>Начните с одного ответа</h2>
                <p>Выберите вымышленный кейс или вставьте свой текст. Мы покажем доказательства, предварительный маршрут и вопросы для интервью.</p>
              </section>
            )
          )}
        </div>
      </main>
          </>}

          {view === "history" && <>
            <div className="view-heading"><div><span className="eyebrow">ПРОЗРАЧНОСТЬ РЕШЕНИЙ</span><h1>История проверок</h1><p>Последнее действие по каждому вымышленному кейсу.</p></div></div>
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
            <p className="muted small history-disclaimer">Журнал содержит только действия над синтетическими кейсами. Это не база заявок и не полноценный аудит доступа.</p>
          </>}

          {view === "methodology" && <>
            <div className="view-heading"><div><span className="eyebrow">ЧЕСТНАЯ ГРАНИЦА MVP</span><h1>Методология</h1><p>Что реализовано, а что требует подтверждения inVision U.</p></div></div>
            <div className="method-grid">
              <section className="card method-ready"><span className="method-index">03</span><span className="method-state">ЭКСПЕРИМЕНТАЛЬНО</span><h2>Лидерские способности</h2><p>Прототип разбора по BARS/ATOLA: цитаты, предварительный уровень и ручная проверка. Полные правила и пороги inVision U ещё не подтверждены.</p><button className="secondary" onClick={() => setView("workspace")}>Открыть анализ →</button></section>
              <section className="card method-pending"><span className="method-index">8 блоков</span><span className="method-state">ОЖИДАЕТ МЕТОДОЛОГИЮ</span><h2>Полный профиль</h2><p>Остальные блоки, вопросы, веса и пороги не выдуманы. Их подключим после получения утверждённых материалов и проверки экспертами.</p><div className="method-line">Нужны: BARS · ATOLA · правила интерпретации · экспертная разметка</div></section>
            </div>
            {framework && <section className="card qef-card">
              <div className="qef-head"><div><span className="eyebrow">QADAM EVIDENCE FRAMEWORK · {framework.version}</span><h2>Предварительная рубрика для экспертной проверки</h2></div><span className="method-state">НЕ УТВЕРЖДЕНО INVISION U</span></div>
              <p className="muted">Это собственная продуктовая гипотеза Qadam. Она структурирует сбор свидетельств, но не является валидированным тестом и не используется для автоматического отказа.</p>
              <div className="qef-grid">{framework.competencies.map((item, index) => <article key={item.id} className="qef-item">
                <div className="qef-title"><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{item.name_ru}</strong><small>{item.name_en}</small></div></div>
                <p>{item.construct}</p><div className="qef-mode">{item.decision_mode.includes("human_only") ? "Только человек" : item.decision_mode.includes("experimental") ? "Эксперимент + человек" : "Ручная проверка"}</div>
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
                    <span className={status === "Работает в MVP" ? "comp-ready" : status === "Только человек" ? "comp-human" : "comp-pending"}>{status}</span>
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
