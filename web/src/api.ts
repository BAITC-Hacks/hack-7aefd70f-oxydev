// Типы ответов API для демо-кабинета; состояние интерфейса пока локальное.

export type Level = "weak" | "normal" | "strong";

export interface AtolaItem {
  element: string;
  letter: string;
  name: string;
  present: boolean;
  quote: string | null;
  questions: string[];
  probes: string[];
}

export interface IndicatorItem {
  indicator_id: string;
  text: string;
  level: Level;
  level_label: string;
  quote: string;
  atola_element: string;
}

export interface FeatureItem {
  name: string;
  label: string;
  group: string;
  value: number;
  contribution: number;
  direction: "up" | "down" | "neutral";
}

export interface HintItem {
  kind: string;
  title: string;
  reason: string;
  questions: string[];
}

export interface SensitiveItem {
  blocks: string[];
  note: string;
  questions: string[];
}

export interface Feedback {
  level: Level;
  level_label: string;
  disclaimer: string;
  strengths: string[];
  growth: string[];
}

export interface Analysis {
  level: Level;
  level_label: string;
  probabilities: Record<Level, number>;
  margin: number;
  atola: AtolaItem[];
  atola_coverage: number;
  indicators: IndicatorItem[];
  features: FeatureItem[];
  text_contribution: number;
  hints: HintItem[];
  sensitive: SensitiveItem[];
  feedback: Feedback;
  backend: string;
  dropped_quotes: number;
  decision_support: {
    route: "manual_review" | "priority_interview" | "standard_interview";
    recommendation: string;
    needs_manual_review: boolean;
    reasons: string[];
    confidence: number;
    policy: string;
    thresholds: {
      min_confidence: number;
      min_margin: number;
      min_atola_coverage: number;
      status: string;
    };
  };
  provenance: {
    model_version: string;
    prompt_version: string;
    methodology: string;
    methodology_scope: string;
  };
}

export interface CounterfactualSide {
  label: string;
  text: string;
  score: number;
  level: Level;
  level_label: string;
  probabilities: Record<Level, number>;
}

export interface Counterfactual {
  attribute: string;
  synthetic_prefix: boolean;
  a: CounterfactualSide;
  b: CounterfactualSide;
  delta: number;
  abs_delta: number;
  level_changed: boolean;
  target: number;
  hard_threshold: number;
  verdict: string;
  scale: string;
}

export interface Example {
  key: string;
  title: string;
  id: string;
  text: string;
  expected_level: Level;
  expected_level_label: string;
  note: string;
}

export type Route = "manual_review" | "priority_interview" | "standard_interview";

export interface ReviewEvent {
  id: number;
  example_id: string;
  reviewer: string;
  model_route: Route;
  selected_route: Route;
  action: "confirm" | "override";
  reason: string;
  model_version: string;
  created_at: string;
}

export interface DemoCandidate {
  id: string;
  title: string;
  source: "synthetic";
  latest_review: ReviewEvent | null;
}

export interface PilotSubmission {
  id: string;
  language: "en" | "kk" | "ru";
  mode: "text" | "audio" | "video";
  story: string;
  media_link: string | null;
  media_content_type: string | null;
  scenario_choice: string;
  rationale: string;
  consent_version: string;
  created_at: string;
  latest_route?: Route | null;
  has_media?: boolean;
  reviews?: PilotReview[];
}

export interface PilotReview {
  id: number; submission_id: string; reviewer: string; selected_route: Route;
  reason: string; evidence: string; timecode: string; created_at: string;
}

export interface EvidenceFramework {
  version: string;
  notice: string;
  scale: string;
  competencies: Array<{
    id: string; name_en: string; name_ru: string; construct: string;
    prompt_en: string; prompt_ru: string; probes: string[];
    levels: Array<{ key: string; label: string; anchor: string }>;
    decision_mode: string; status: string;
  }>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status}: ${detail}`);
  }
  return (await response.json()) as T;
}

export const analyze = (text: string) => post<Analysis>("/analyze", { text });
export const counterfactual = (text: string) =>
  post<Counterfactual>("/counterfactual", { text });

export async function loadExamples(): Promise<Example[]> {
  const response = await fetch("/examples");
  if (!response.ok) return [];
  return (await response.json()) as Example[];
}

export async function loadDemoCandidates(): Promise<DemoCandidate[]> {
  const response = await fetch("/demo/candidates");
  if (!response.ok) throw new Error(`${response.status}: очередь недоступна`);
  return (await response.json()) as DemoCandidate[];
}

export async function loadReviews(exampleId: string): Promise<ReviewEvent[]> {
  const response = await fetch(`/demo/candidates/${encodeURIComponent(exampleId)}/reviews`);
  if (!response.ok) throw new Error(`${response.status}: журнал недоступен`);
  return (await response.json()) as ReviewEvent[];
}

export const saveReview = (exampleId: string, selectedRoute: Route, reason: string) =>
  post<ReviewEvent>("/demo/reviews", {
    example_id: exampleId,
    selected_route: selectedRoute,
    reason,
  });

export const createPilotSubmission = (body: {
  language: "en" | "kk" | "ru"; mode: "text" | "audio" | "video";
  story: string; media_link?: string; scenario_choice: string;
  rationale: string; consent: boolean;
}) => post<PilotSubmission>("/pilot/submissions", body);

export async function uploadPilotMedia(id: string, blob: Blob): Promise<void> {
  const response = await fetch(`/pilot/submissions/${encodeURIComponent(id)}/media`, {
    method: "POST", headers: { "Content-Type": blob.type || "application/octet-stream" }, body: blob,
  });
  if (!response.ok) throw new Error(`${response.status}: запись не сохранена`);
}

export async function loadPilotSubmissions(): Promise<PilotSubmission[]> {
  const response = await fetch("/pilot/submissions");
  if (!response.ok) throw new Error(`${response.status}: пилотная очередь недоступна`);
  return (await response.json()) as PilotSubmission[];
}

export async function loadPilotSubmission(id: string): Promise<PilotSubmission> {
  const response = await fetch(`/pilot/submissions/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error(`${response.status}: прохождение недоступно`);
  return (await response.json()) as PilotSubmission;
}

export const savePilotReview = (id: string, selectedRoute: Route, reason: string,
  evidence: string, timecode: string) => post<Record<string, unknown>>(
  `/pilot/submissions/${encodeURIComponent(id)}/reviews`,
  { selected_route: selectedRoute, reason, evidence, timecode },
);

export async function loadMethodology(): Promise<EvidenceFramework> {
  const response = await fetch("/methodology");
  if (!response.ok) throw new Error(`${response.status}: методология недоступна`);
  return (await response.json()) as EvidenceFramework;
}
