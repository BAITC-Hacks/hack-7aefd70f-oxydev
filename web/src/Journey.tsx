import { useEffect, useRef, useState } from "react";

export type JourneyLanguage = "en" | "kk" | "ru";
export type JourneyMode = "text" | "audio" | "video";
export interface JourneyResult {
  language: JourneyLanguage;
  mode: JourneyMode;
  story: string;
  mediaUrl?: string;
  mediaLink?: string;
  scenarioChoice: string;
  rationale: string;
  consent: boolean;
}

const COPY = {
  en: {
    badge: "QADAM · DISCOVER YOUR IMPACT", title: "Show us how you act.",
    subtitle: "One real story. One small team challenge. No perfect answers.",
    steps: ["Choose a format", "Your story", "Team challenge", "Review"],
    intro: "How would you like to tell your story?", introHint: "Choose the most comfortable way. We look at what you did, not your camera or writing style.",
    modes: { text: ["Write", "A short answer, not an essay"], audio: ["Speak", "Record a voice note"], video: ["Record video", "Or use an existing clip"] },
    storyPrompt: "Think of one time you took responsibility. What happened, what did you do personally, and what changed?",
    storyHint: "A school, family, work or community example all count. One or two sentences are enough.",
    storyPlaceholder: "Our team was stuck because... I decided to... Afterwards...",
    record: "Start recording", stop: "Stop recording", upload: "Or choose an existing audio/video file (up to 30 MB)",
    recordingStatus: "Recording is in progress", recordedStatus: "Recording is ready to review",
    link: "Already have a video link? Paste it here instead of recording again.", linkPlaceholder: "https://...", linkError: "Enter a valid HTTPS video link.",
    permission: "Camera or microphone access was denied or recording is unavailable. You can switch to text.",
    note: "Optional note or transcript in your own words.",
    demo: "Try an example response", sample: "Our school club kept cancelling meetings. I asked five classmates when they were free, made a shared schedule and assigned small roles. We then held four meetings in a row.",
    scenarioTitle: "A decision in the moment", scenario: "Your student team has one day before a project presentation. Two teammates disagree about the plan and work has stopped. What would you do first?",
    options: ["Hear both sides and agree on the next concrete step", "Pick a plan yourself so the team can move", "Ask another team member to help mediate"],
    consequence: ["The team is willing to talk. How will you turn the conversation into action?", "The team can move quickly, but one person feels unheard. What will you do next?", "A new perspective helps, but the deadline remains. What will you do next?"],
    why: "Why this move? What would you do next?", whyPlaceholder: "I would first... Then...",
    notScored: "There is no single correct option. Your reasoning matters more than the choice itself.",
    reviewTitle: "Your impact, in your words", reviewHint: "The reviewer sees your original response and reasoning; the final decision always remains with the admissions team.",
    format: "Format", answer: "Your story", decision: "First move", reasoning: "Your reasoning",
    noTranscript: "Recording attached. No transcript was created; a person must review the recording.",
    privacy: "Your response is stored in the protected Qadam workspace and is available only to authorised reviewers.",
    consent: "I agree that my response and recording may be stored and reviewed by the admissions team.", consentError: "Consent is required to submit the response.",
    back: "Back", next: "Continue", handoff: "Open reviewer view", workspace: "Reviewer workspace",
    requiredStory: "Add a short story or recording to continue.", requiredChoice: "Choose a first move and briefly explain why.", change: "Change response",
  },
  kk: {
    badge: "QADAM · ӨЗ ІЗІҢІЗДІ КӨРСЕТІҢІЗ", title: "Қалай әрекет ететініңізді көрсетіңіз.",
    subtitle: "Бір шынайы оқиға. Бір шағын командалық жағдай. Мінсіз жауап жоқ.",
    steps: ["Форматты таңдау", "Сіздің оқиғаңыз", "Командалық жағдай", "Тексеру"],
    intro: "Оқиғаңызды қалай айтқыңыз келеді?", introHint: "Өзіңізге ыңғайлы тәсілді таңдаңыз. Камера не жазу мәнері емес, әрекетіңіз маңызды.",
    modes: { text: ["Жазу", "Эссе емес, қысқа жауап"], audio: ["Айту", "Дыбыстық хабар жазу"], video: ["Бейне жазу", "Не дайын бейнені таңдау"] },
    storyPrompt: "Жауапкершілік алған бір сәтті еске түсіріңіз. Не болды, өзіңіз не істедіңіз, не өзгерді?",
    storyHint: "Мектеп, отбасы, жұмыс немесе қоғамдағы оқиға жарайды. Бір-екі сөйлем жеткілікті.",
    storyPlaceholder: "Тобымыз ... болғандықтан тоқтап қалды. Мен ... жасадым. Соңында...",
    record: "Жазуды бастау", stop: "Жазуды тоқтату", upload: "Не дайын аудио/бейне файлды таңдаңыз (30 МБ дейін)",
    recordingStatus: "Жазу жүріп жатыр", recordedStatus: "Жазба дайын, тыңдап/көріп шығыңыз",
    link: "Дайын бейне сілтемесі бар ма? Қайта жазудың орнына оны енгізіңіз.", linkPlaceholder: "https://...", linkError: "Дұрыс HTTPS бейне сілтемесін енгізіңіз.",
    permission: "Камераға немесе микрофонға рұқсат берілмеді, не жазу қолжетімсіз. Мәтінге ауыса аласыз.",
    note: "Өз сөзіңізбен қысқа түсініктеме немесе транскрипт (міндетті емес).",
    demo: "Жауап үлгісін көру", sample: "Мектеп үйірмесінің кездесулері жиі болмай қалатын. Бес сыныптасымнан ыңғайлы уақытты сұрап, ортақ кесте жасадым және міндеттерді бөлдім. Содан кейін төрт кездесу қатарынан өтті.",
    scenarioTitle: "Бір сәттегі шешім", scenario: "Студенттік топ жобаны ертең таныстырады. Екі қатысушы жоспарға келіспей, жұмыс тоқтады. Алдымен не істейсіз?",
    options: ["Екі жақты тыңдап, келесі нақты қадамды келісу", "Топ тез жүруі үшін жоспарды өзім таңдау", "Басқа қатысушыдан арағайын болуын сұрау"],
    consequence: ["Топ сөйлесуге дайын. Әңгімені әрекетке қалай айналдырасыз?", "Жұмыс тез жүреді, бірақ бір адам өзін елеусіз сезінді. Не істейсіз?", "Жаңа көзқарас көмектесті, бірақ уақыт аз. Не істейсіз?"],
    why: "Неге осы қадам? Кейін не істейсіз?", whyPlaceholder: "Алдымен мен... Содан кейін...",
    notScored: "Жалғыз дұрыс жауап жоқ. Таңдаудан гөрі сіздің ойыңыз маңызды.",
    reviewTitle: "Өзіңіздің ізіңіз — өз сөзіңізбен", reviewHint: "Комиссия бастапқы жауабыңыз бен ойыңызды көреді; соңғы шешімді әрқашан қабылдау комиссиясы қабылдайды.",
    format: "Формат", answer: "Оқиға", decision: "Алғашқы қадам", reasoning: "Негіздеме",
    noTranscript: "Жазба тіркелді. Транскрипт жоқ; жазбаны адам тыңдауы/көруі керек.",
    privacy: "Жауабыңыз қорғалған Qadam кеңістігінде сақталады және тек уәкілетті комиссия мүшелеріне қолжетімді.",
    consent: "Жауабым мен жазбамды қабылдау комиссиясы сақтап, тексеруіне келісемін.", consentError: "Жауапты жіберу үшін келісім қажет.",
    back: "Артқа", next: "Жалғастыру", handoff: "Комиссия көрінісін ашу", workspace: "Комиссия интерфейсі",
    requiredStory: "Жалғастыру үшін қысқа оқиға не жазба қосыңыз.", requiredChoice: "Алғашқы қадамды таңдап, себебін қысқаша түсіндіріңіз.", change: "Жауапты өзгерту",
  },
  ru: {
    badge: "QADAM · ПОКАЖИ СВОЙ ПУТЬ", title: "Покажи, как ты действуешь.",
    subtitle: "Одна реальная история. Одна небольшая ситуация. Без идеальных ответов.",
    steps: ["Выбор формата", "Твоя история", "Командная ситуация", "Проверка"],
    intro: "Как тебе удобнее рассказать свою историю?", introHint: "Выбери подходящий способ. Нам важны действия, а не качество камеры или стиль письма.",
    modes: { text: ["Написать", "Короткий ответ, не эссе"], audio: ["Рассказать", "Записать голосовое"], video: ["Записать видео", "Или выбрать готовый фрагмент"] },
    storyPrompt: "Вспомни случай, когда ты взял ответственность. Что случилось, что сделал лично ты и что изменилось?",
    storyHint: "Подойдёт пример из школы, семьи, работы или сообщества. Достаточно пары предложений.",
    storyPlaceholder: "Наша команда застряла, потому что... Я решил... После этого...",
    record: "Начать запись", stop: "Остановить запись", upload: "Или выбрать готовый аудио/видеофайл (до 30 МБ)",
    recordingStatus: "Идёт запись", recordedStatus: "Запись готова — прослушайте или просмотрите её",
    link: "Видео уже записано? Вставь ссылку вместо повторной записи.", linkPlaceholder: "https://...", linkError: "Нужна корректная HTTPS-ссылка на видео.",
    permission: "Нет доступа к камере или микрофону либо запись недоступна. Можно перейти на текст.",
    note: "Необязательная заметка или расшифровка своими словами.",
    demo: "Посмотреть пример ответа", sample: "Школьный клуб постоянно отменял встречи. Я спросил пятерых одноклассников, когда им удобно, составил общее расписание и распределил небольшие роли. После этого мы провели четыре встречи подряд.",
    scenarioTitle: "Решение в моменте", scenario: "Твоей команде завтра представлять проект. Двое участников спорят о плане, работа остановилась. Что ты сделаешь сначала?",
    options: ["Выслушаю обоих и договорюсь о следующем конкретном шаге", "Сам выберу план, чтобы команда начала двигаться", "Попрошу другого участника помочь с разговором"],
    consequence: ["Команда готова говорить. Как превратишь разговор в действие?", "Работа пошла быстрее, но один участник чувствует, что его не услышали. Что дальше?", "Новый взгляд помог, но срок всё ещё близко. Что дальше?"],
    why: "Почему именно так? Что сделаешь дальше?", whyPlaceholder: "Сначала я... Затем...",
    notScored: "Единственного правильного варианта нет. Важнее не выбор, а ход рассуждения.",
    reviewTitle: "Твой путь — твоими словами", reviewHint: "Комиссия увидит исходный ответ и ход рассуждения; финальное решение всегда остаётся за человеком.",
    format: "Формат", answer: "История", decision: "Первое действие", reasoning: "Объяснение",
    noTranscript: "Запись приложена. Расшифровки нет — её должен просмотреть человек.",
    privacy: "Ответ хранится в защищённом пространстве Qadam и доступен только уполномоченным членам комиссии.",
    consent: "Я согласен на сохранение и рассмотрение моего ответа приёмной комиссией.", consentError: "Для отправки ответа необходимо согласие.",
    back: "Назад", next: "Продолжить", handoff: "Открыть кабинет комиссии", workspace: "Кабинет комиссии",
    requiredStory: "Добавь короткую историю или запись.", requiredChoice: "Выбери первое действие и коротко объясни почему.", change: "Изменить ответ",
  },
} as const;

export default function Journey({ onComplete, onReview }: { onComplete: (result: JourneyResult) => void; onReview: () => void }) {
  const [language, setLanguage] = useState<JourneyLanguage>("en");
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<JourneyMode>("text");
  const [story, setStory] = useState("");
  const [mediaUrl, setMediaUrl] = useState<string>();
  const [mediaLink, setMediaLink] = useState("");
  const [choice, setChoice] = useState<number>();
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState("");
  const [recording, setRecording] = useState(false);
  const [consent, setConsent] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const mediaRef = useRef<string>();
  const handedOffRef = useRef(false);
  const abandonedRef = useRef(false);
  const t = COPY[language];

  useEffect(() => {
    abandonedRef.current = false;
    return () => {
      abandonedRef.current = true;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      if (!handedOffRef.current && mediaRef.current) URL.revokeObjectURL(mediaRef.current);
    };
  }, []);
  useEffect(() => { document.documentElement.lang = language === "kk" ? "kk" : language; }, [language]);

  function setNewMedia(url: string) {
    if (mediaUrl) URL.revokeObjectURL(mediaUrl);
    setMediaUrl(url);
    mediaRef.current = url;
    setMediaLink("");
  }
  async function startRecording() {
    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") throw new Error("unavailable");
      const stream = await navigator.mediaDevices.getUserMedia(mode === "video" ? { audio: true, video: true } : { audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => { if (event.data.size) chunksRef.current.push(event.data); };
      recorder.onstop = () => {
        if (!abandonedRef.current && chunksRef.current.length) setNewMedia(URL.createObjectURL(new Blob(chunksRef.current, { type: recorder.mimeType || (mode === "video" ? "video/webm" : "audio/webm") })));
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        setRecording(false);
      };
      recorder.start();
      setRecording(true);
      setError("");
    } catch {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setError(t.permission);
    }
  }
  function stopRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  }
  function chooseFile(file?: File) {
    if (!file) return;
    if (file.size > 30_000_000 || !file.type.startsWith(mode === "video" ? "video/" : "audio/")) {
      setError(language === "ru" ? "Нужен файл выбранного типа до 30 МБ." : language === "kk" ? "Таңдалған түрдегі файл 30 МБ-тан аспауы керек." : "Choose a matching file under 30 MB.");
      return;
    }
    setNewMedia(URL.createObjectURL(file));
    setError("");
  }
  function advance() {
    if (step === 1 && mode === "video" && mediaLink.trim()) {
      try { const parsed = new URL(mediaLink.trim()); if (parsed.protocol !== "https:") throw new Error("insecure"); }
      catch { setError(t.linkError); return; }
    }
    if (step === 1 && !story.trim() && !mediaUrl && !(mode === "video" && mediaLink.trim())) { setError(t.requiredStory); return; }
    if (step === 2 && (choice === undefined || !rationale.trim())) { setError(t.requiredChoice); return; }
    setError("");
    setStep(Math.min(3, step + 1));
  }
  function handoff() {
    if (!consent) { setError(t.consentError); return; }
    handedOffRef.current = true;
    onComplete({ language, mode, story: story.trim(), mediaUrl, mediaLink: mode === "video" ? mediaLink.trim() || undefined : undefined, scenarioChoice: choice === undefined ? "" : t.options[choice], rationale: rationale.trim(), consent });
  }

  return <div className="journey-page">
    <header className="journey-topbar">
      <div className="journey-brand"><span className="journey-mark">Q</span><span><strong>Qadam AI</strong><small>for inVision U</small></span></div>
      <div className="journey-top-actions">
        <div className="language-switch" role="group" aria-label="Language">{(["en", "kk", "ru"] as JourneyLanguage[]).map((option) => <button key={option} aria-pressed={language === option} className={language === option ? "active" : ""} onClick={() => { setLanguage(option); setError(""); }}>{option.toUpperCase()}</button>)}</div>
        <button className="journey-review-link" onClick={() => { abandonedRef.current = true; onReview(); }}>{t.workspace} ↗</button>
      </div>
    </header>
    <main className="journey-main">
      <div className="journey-intro"><span className="eyebrow">{t.badge}</span><h1>{t.title}</h1><p>{t.subtitle}</p></div>
      <div className="journey-grid">
        <section className="journey-form">
          <div className="journey-progress-head"><span>{step + 1} / 4</span><strong>{t.steps[step]}</strong></div>
          <div className="journey-progress" role="progressbar" aria-label={t.steps[step]} aria-valuemin={0} aria-valuemax={4} aria-valuenow={step + 1}><span style={{ width: `${((step + 1) / 4) * 100}%` }} /></div>
          {step === 0 && <>
            <h2>{t.intro}</h2><p className="journey-summary-subtitle">{t.introHint}</p>
            <div className="journey-mode-grid">{(["text", "audio", "video"] as JourneyMode[]).map((item) => <button key={item} aria-pressed={mode === item} disabled={recording} className={mode === item ? "active" : ""} onClick={() => { if (item !== mode && mediaUrl) { URL.revokeObjectURL(mediaUrl); setMediaUrl(undefined); mediaRef.current = undefined; } setMode(item); setError(""); }}>
              <span aria-hidden="true">{item === "text" ? "✎" : item === "audio" ? "◉" : "▣"}</span><strong>{t.modes[item][0]}</strong><small>{t.modes[item][1]}</small>
            </button>)}</div>
          </>}
          {step === 1 && <>
            <h2>{t.storyPrompt}</h2><p className="journey-summary-subtitle">{t.storyHint}</p>
            {mode === "text" ? <textarea aria-label={t.storyPrompt} value={story} maxLength={1500} rows={6} onChange={(event) => setStory(event.target.value)} placeholder={t.storyPlaceholder} /> : <>
              <div className="journey-record-controls"><button className={recording ? "journey-stop" : "journey-next"} onClick={recording ? stopRecording : startRecording}>{recording ? "● " + t.stop : "● " + t.record}</button><label>{t.upload}<input type="file" accept={mode === "video" ? "video/*" : "audio/*"} onChange={(event) => chooseFile(event.target.files?.[0])} /></label></div>
              {mode === "video" && <div className="journey-link"><label htmlFor="existing-video">{t.link}</label><input id="existing-video" type="url" value={mediaLink} onChange={(event) => { if (event.target.value.trim() && mediaUrl) { URL.revokeObjectURL(mediaUrl); setMediaUrl(undefined); mediaRef.current = undefined; } setMediaLink(event.target.value); setError(""); }} placeholder={t.linkPlaceholder} /></div>}
              {mediaUrl && (mode === "video" ? <video className="journey-media" controls src={mediaUrl} /> : <audio className="journey-media" controls src={mediaUrl} />)}
              <p className="journey-record-status" role="status" aria-live="polite">{recording ? t.recordingStatus : mediaUrl ? t.recordedStatus : ""}</p>
              <p className="journey-limit">{t.note}</p><textarea aria-label={t.note} value={story} maxLength={1500} rows={3} onChange={(event) => setStory(event.target.value)} placeholder={t.storyPlaceholder} />
            </>}
            <button className="journey-demo-fill" onClick={() => { setStory(t.sample); setMode("text"); if (mediaUrl) { URL.revokeObjectURL(mediaUrl); setMediaUrl(undefined); mediaRef.current = undefined; } setError(""); }}>{t.demo} ↗</button>
          </>}
          {step === 2 && <>
            <span className="eyebrow">{t.scenarioTitle}</span><h2>{t.scenario}</h2>
            <div className="journey-options">{t.options.map((option, index) => <button key={index} aria-pressed={choice === index} className={choice === index ? "active" : ""} onClick={() => { setChoice(index); setError(""); }}><span>{String.fromCharCode(65 + index)}</span>{option}</button>)}</div>
            {choice !== undefined && <><p className="journey-consequence">{t.consequence[choice]}</p><label htmlFor="scenario-why">{t.why}</label><textarea id="scenario-why" value={rationale} rows={3} maxLength={500} onChange={(event) => setRationale(event.target.value)} placeholder={t.whyPlaceholder} /></>}
            <p className="journey-limit">{t.notScored}</p>
          </>}
          {step === 3 && <>
            <div className="journey-complete-icon">✓</div><h2>{t.reviewTitle}</h2><p className="journey-summary-subtitle">{t.reviewHint}</p>
            <div className="journey-summary">
              <div><small>{t.format}</small><p>{t.modes[mode][0]}</p></div>
              <div><small>{t.answer}</small><p>{story || t.noTranscript}</p></div>
              <div><small>{t.decision}</small><p>{choice === undefined ? "" : t.options[choice]}</p></div>
              <div><small>{t.reasoning}</small><p>{rationale}</p></div>
            </div>
            {mediaUrl && (mode === "video" ? <video className="journey-media" controls src={mediaUrl} /> : <audio className="journey-media" controls src={mediaUrl} />)}
            {mode === "video" && mediaLink.trim() && <p className="journey-summary-subtitle"><a href={mediaLink} target="_blank" rel="noopener noreferrer">{mediaLink}</a></p>}
            <label className="journey-consent"><input type="checkbox" checked={consent} onChange={(event) => { setConsent(event.target.checked); setError(""); }} /> <span>{t.consent}</span></label>
          </>}
          {error && <p className="journey-error" role="alert">{error}</p>}
          <div className="journey-buttons">{step > 0 && <button className="journey-back" onClick={() => { if (recording) stopRecording(); setStep(step - 1); setError(""); }}>{t.back}</button>}
            <button className="journey-next" disabled={recording} onClick={step === 3 ? handoff : advance}>{step === 3 ? t.handoff : t.next} <span>→</span></button></div>
        </section>
        <aside className="journey-side">
          <div className="journey-side-art"><span>Q</span><i /><i /></div>
          <div><span className="eyebrow">YOUR STORY, YOUR WORDS</span><h2>{t.steps[step]}</h2><p>{step === 2 ? t.notScored : t.introHint}</p></div>
          <div className="journey-privacy">◈ {t.privacy}</div>
        </aside>
      </div>
    </main>
  </div>;
}
