/**
 * 타입이 지정된 API 클라이언트.
 *
 * 단일 진실 공급원은 `docs/05-api-contract.md`다. 이 문서가 바뀌면 이 파일도
 * 즉시 맞춰서 고친다 (필드 제거/개명 시에만 — 추가는 하위호환이라 안전).
 *
 * Base URL은 `NEXT_PUBLIC_API_BASE` 환경변수로 결정된다. 배포 시에는
 * nginx가 `/api/`를 FastAPI로 프록시하므로 상대 경로 `/api`가 기본값이다
 * (CORS 자체를 없애는 구성 — `docs/02-architecture.md`, `tasks/track-d-deploy.md` 참고).
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

// ---------------------------------------------------------------------------
// 공통 타입
// ---------------------------------------------------------------------------

export interface Card {
  id: number;
  project_id: number | null;
  raw_text: string;
  refined_sentence: string;
  skill_tags: string[];
  confidence: number;
  created_at: string;
  /** 9/16 신규 — 홈 화면(Figma 100:692) "오늘 남긴 것" 목록의 "09:40" 표시용
   * "HH:MM". 마이그레이션 이전 카드는 null. */
  created_time?: string | null;
  /** 9/15 신규 — POST 응답에서 LLM 파싱이 실패해 원문 그대로 폴백 저장됐을 때만
   * true. GET/PATCH 응답에서는 항상 false(또는 생략)이다 — DB 컬럼이 아니라
   * 생성 시점에만 서버가 채워 넣는 값이라서. */
  refinement_failed?: boolean;
  /** 9/16 신규 — 결과 출력 모달(Figma 41:139) "오늘 기록은 ~~ 케이스입니다" 문구.
   * refinement_failed와 동일한 패턴: POST 생성 시점에만 채워지고, GET/PATCH
   * 응답에서는 항상 빈 문자열(또는 생략)이다. */
  case_summary?: string;
  /** 9/18 신규 — Figma "02 · 변환 결과" 3.1-d "문장 수정" 시트.
   * `refined_sentence`가 **지금 보이는 문장**(사람이 고쳤으면 고친 것)이고,
   * `ai_sentence`는 **가장 최근에 AI가 만든 문장**이다. "AI 문장으로 되돌리기"
   * 버튼은 `sentence_edited`가 true이고 `ai_sentence`가 있을 때만 띄운다. */
  ai_sentence?: string | null;
  sentence_edited?: boolean;
}

export interface Project {
  id: number;
  name: string;
  started_at: string;
  ended_at: string | null;
  is_current: boolean;
}

/**
 * `result`는 빈 문자열일 수 있다 — 기록에 숫자가 없으면 AI가 지어내지 않고
 * 비워서 반환한다 (CLAUDE.md 2.2). 절대 "결과 없음"으로 렌더링하지 말 것.
 * `source_dates`/`source_card_ids`는 항상 배열이다 (빈 배열일 수는 있어도 undefined는 아님).
 *
 * `source_dates`와 `source_card_ids`는 역할이 다르다 (9/14 신규 필드,
 * docs/05-api-contract.md §3 참고). `source_dates`는 화면 표시용(날짜 문자열,
 * 같은 날짜 카드가 여러 장이면 중복될 수 있음)이고, `source_card_ids`는 실제
 * 카드를 정확히 가리키는 식별자다. **카드와 매칭하는 로직은 반드시
 * `source_card_ids`로 할 것** — 날짜 매칭은 같은 날짜에 카드가 여러 장 있을 때
 * 무관한 카드까지 같이 묶이는 버그가 있다(실제로 발견/수정됨).
 */
export interface StarItem {
  title: string;
  period: string;
  situation: string;
  task: string;
  action: string;
  result: string;
  source_dates: string[];
  source_card_ids: number[];
  /** 9/18 신규 — 마스터 경력기술서(여러 프로젝트를 한 문서로, Figma 4.2.1 "범위 선택")
   * 에서 이 항목이 어느 프로젝트 카드로 만들어졌는지. 프로젝트 헤드(Figma 41:254)를
   * 그리는 데 쓴다. 미분류 기록에서 나온 항목은 `project_id`가 null이고
   * `project_name`이 "미분류 기록"이다. */
  project_id?: number | null;
  project_name?: string | null;
}

export interface HealthStatus {
  status: string;
  db: boolean;
  chroma: boolean;
  llm: boolean;
}

/** `PushSubscription.toJSON()`이 만드는 모양과 동일 — `docs/05-api-contract.md` §7. */
export interface PushSubscriptionPayload {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  /** "HH:MM" — 발송 시각 계산에 쓴다 (9/13 계약에 추가된 필드). */
  leave_time: string;
  /** 9/18 신규 — 주말엔 보내지 않는다 (Figma 온보딩 4/4 "주말에는 쉬어요").
   * 서버 기본값이 false라 안 보내도 기존 동작(매일 발송) 그대로다. */
  skip_weekends?: boolean;
}

export interface UpdateProjectPatch {
  is_current?: boolean;
  name?: string;
  ended_at?: string;
}

/** 고정 칩 세트 — 자유 입력이 아니다 (CLAUDE.md 2.4, `docs/05-api-contract.md` §9).
 *
 * 9/18 — Figma "00 · 온보딩"(268:5731) 재설계로 직군 세트가 바뀌었다.
 * 목록 자체는 `lib/jobTaxonomy.ts`가 단일 진실 공급원이고, 여기선 서버 계약(Literal)과
 * 맞춘 타입만 둔다. */
export const JOB_FIELDS = [
  "마케팅·광고",
  "경영·비즈니스",
  "디자인",
  "개발",
  "영업",
  "고객서비스·리테일",
] as const;
export type JobField = (typeof JOB_FIELDS)[number];

export const YEARS_SEGMENTS = ["1-3", "4-6", "7-10", "10+"] as const;
export type YearsSegment = (typeof YEARS_SEGMENTS)[number];

/** 재직 이력 한 건 (9/18 신규, Figma 3/4 "어디서 얼마나 일하셨어요?").
 * 기간은 월 단위("2024-03")다. `ended_at`이 null이면 재직 중. */
export interface Company {
  name: string;
  started_at: string;
  ended_at: string | null;
}

export interface Profile {
  /** 9/18 이전에 저장된 값("기획·PM", "데이터")이 그대로 올 수 있어서 좁히지 않는다 —
   * 서버도 같은 이유로 응답 쪽은 Literal이 아니다(src/api/schemas.py 참고). */
  job_field: string | null;
  job_detail: string | null;
  years_segment: YearsSegment | null;
  /** 2/4 "어디로 가고 싶으세요?" 다중 선택 결과. 직무 이름만 담긴다. */
  target_jobs: string[];
  companies: Company[];
  /** 회사 기간에서 **서버가** 계산한 총 재직 개월 수 (겹치는 기간은 한 번만 센다). */
  total_months: number;
}

export interface ProfileUpdate {
  jobField: JobField;
  jobDetail?: string | null;
  targetJobs?: string[];
  /** 생략(undefined)하면 서버가 기존 회사 목록을 건드리지 않는다. 빈 배열은 "다 지워라". */
  companies?: Company[];
}

// ---------------------------------------------------------------------------
// 요청 래퍼
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      // 9/14 카카오 로그인 도입 — 세션 쿠키를 실어 보내야 한다. 로컬 개발은 프론트(3001)와
      // 백엔드(8000)가 다른 origin이라 기본값(same-origin)으로는 쿠키가 안 실린다.
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    // 네트워크 자체가 실패한 경우 (백엔드 미기동 등) — 에러 상태로 통일해서 던진다.
    throw new ApiError(0, "서버에 연결할 수 없습니다.");
  }

  if (res.status === 204) {
    return undefined as T;
  }

  if (!res.ok) {
    let detail = res.statusText || "요청에 실패했습니다.";
    try {
      const body = (await res.json()) as { detail?: string };
      if (body && typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // JSON이 아닌 에러 응답 — statusText 그대로 사용
    }
    throw new ApiError(res.status, detail);
  }

  // 응답 바디가 없는 2xx (드물지만 방어적으로 처리)
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

// ---------------------------------------------------------------------------
// 1. 카드 — docs/05-api-contract.md §1
// ---------------------------------------------------------------------------

/** 메모 한 줄을 파싱해 저장한다. 응답은 3~10초 걸릴 수 있다 (호출부에서 스켈레톤 표시).
 *
 * `metricAnswer`(9/18)는 변환 전 추가 질문(Figma 3.1-q)에 유저가 **직접 답한** 수치다.
 * 건너뛰면 안 보내면 되고, 그때 동작은 예전과 완전히 같다. */
export function createCard(rawText: string, metricAnswer?: string): Promise<Card> {
  return request<Card>("/cards", {
    method: "POST",
    body: JSON.stringify({
      raw_text: rawText,
      ...(metricAnswer ? { metric_answer: metricAnswer } : {}),
    }),
  });
}

/**
 * "변환 전 추가 질문" (Figma "02 · 변환 결과" 3.1-q, 9/18 신규).
 *
 * CLAUDE.md 2.2가 정한 "숫자가 없으면 ... 유저에게 되묻는다(건너뛰기 가능)" 경로다.
 * **카드를 만들지 않는다** — 질문만 받아오고, 저장은 뒤이은 `createCard()`가 한다.
 * `question`이 빈 문자열이면 물어볼 게 없다는 뜻이라 호출부는 화면을 건너뛴다
 * (매일 쓰는 경로에 화면이 하나 더 끼지 않게 하는 장치 — 2.1).
 */
export interface MetricQuestion {
  question: string;
  placeholder: string;
}

export function getMetricQuestion(rawText: string): Promise<MetricQuestion> {
  return request<MetricQuestion>("/cards/metric-question", {
    method: "POST",
    body: JSON.stringify({ raw_text: rawText }),
  });
}

/**
 * "직무 전환 번역" (Figma 3.1-b / 3.1-c, 9/18 신규) — 같은 기록을 온보딩에서 고른
 * **목표 직무** 관점으로 다시 읽어준다.
 *
 * 결과는 서버에 저장되지 않는다. 카드 하나가 목표 직무마다 다르게 읽힐 수 있는데
 * 그걸 전부 저장하면 관리 UI가 필요해진다(CLAUDE.md 3장이 AI 그룹핑을 저장하지 않는
 * 것과 같은 판단). 남기고 싶으면 복사하거나 "문장 고치기"로 직접 적용하면 된다.
 *
 * `related`가 false면 3.1-c("직무 접점 없음") 화면이다 — 억지로 갖다 붙이는 대신
 * `suggestion`으로 무엇을 기록하면 가까워지는지 알려준다.
 */
export interface CardTranslation {
  related: boolean;
  headline: string;
  translated_sentence: string;
  suggestion: string;
}

export function translateCard(id: number, targetJob: string): Promise<CardTranslation> {
  return request<CardTranslation>(`/cards/${id}/translate`, {
    method: "POST",
    body: JSON.stringify({ target_job: targetJob }),
  });
}

/** `projectId` 생략 시 전체 카드를 최신순으로 반환한다. */
export function listCards(projectId?: number): Promise<Card[]> {
  const query = typeof projectId === "number" ? `?project_id=${projectId}` : "";
  return request<{ cards: Card[] }>(`/cards${query}`).then((res) => res.cards);
}

export function deleteCard(id: number): Promise<void> {
  return request<void>(`/cards/${id}`, { method: "DELETE" });
}

/** 홈 화면(Figma 100:692) "무엇이 쌓였나요" 버블 차트용 (9/16 신규). 카드를 대표
 * 태그(skill_tags[0], 없으면 "미분류") 기준으로 집계한 값 — 태그를 지어내지 않는다
 * (CLAUDE.md 2.2). `count` 합계는 항상 `total_cards`와 같다. */
export interface SkillCategoryCount {
  tag: string;
  count: number;
}

export interface SkillSummary {
  total_cards: number;
  categories: SkillCategoryCount[];
}

/** `topN` 생략 시 서버 기본값(4, 홈 화면 버블용). `/stack` "역량 리스트"(Figma
 * 100:692 "4.1-h")처럼 개수 제한 없이 사실상 전부 받고 싶으면 큰 값을 넘긴다. */
export function getSkillSummary(projectId: number, topN?: number): Promise<SkillSummary> {
  const topNQuery = typeof topN === "number" ? `&top_n=${topN}` : "";
  return request<SkillSummary>(`/cards/skill-summary?project_id=${projectId}${topNQuery}`);
}

/**
 * 카테고리(스킬 태그)/문장을 직접 수정한다 (9/14 태그, 9/15 문장 추가). 매일 쓰는
 * 저장 경로(POST)는 여전히 AI가 자동으로 채우고, 이건 저장 후 가끔(`/stack`에서)
 * 손으로 고치는 별도 경로다(CLAUDE.md 2.1). 둘 다 optional이지만 최소 하나는
 * 있어야 한다(서버가 400으로 검증).
 */
export function updateCard(
  id: number,
  patch: { skillTags?: string[]; refinedSentence?: string; revertToAi?: boolean },
): Promise<Card> {
  return request<Card>(`/cards/${id}`, {
    method: "PATCH",
    body: JSON.stringify({
      ...(patch.skillTags !== undefined && { skill_tags: patch.skillTags }),
      ...(patch.refinedSentence !== undefined && { refined_sentence: patch.refinedSentence }),
      // 9/18 — "AI 문장으로 되돌리기"(Figma 3.1-d). 서버가 카드에 보관된
      // ai_sentence로 되돌리므로 문장을 클라이언트가 실어 보내지 않는다.
      ...(patch.revertToAi && { revert_to_ai: true }),
    }),
  });
}

/** 카드를 다시 AI로 정리한다 (9/15 폴백 복구용으로 신설, 9/18 "다시 만들기"로 확장).
 *
 * 사람이 직접 고친 문장은 덮어쓰지 않는다 — 서버가 새 문장을 `ai_sentence`에만
 * 넣는다(Figma 3.1-d "직접 고친 문장은 다시 변환해도 유지돼요"). */
export function refineCard(id: number): Promise<Card> {
  return request<Card>(`/cards/${id}/refine`, { method: "POST" });
}

/**
 * "4.1.1 AI 프로젝트 자동 제안" (9/14 신규) — project_id가 없는 카드끼리만 비교해서
 * 비슷한 것들을 묶어 후보로 제시한다. 이미 프로젝트가 배정된 카드는 서버가 애초에
 * 조회 대상으로도 삼지 않는다(CLAUDE.md 3장 안전장치).
 */
export interface CardCluster {
  card_ids: number[];
  cards: Card[];
}

export function getUnclassifiedSuggestions(): Promise<CardCluster[]> {
  return request<{ clusters: CardCluster[] }>("/cards/unclassified/suggestions").then(
    (res) => res.clusters,
  );
}

/** 선택된 카드들을 새 프로젝트로 묶는다. 이름/시작일은 사용자가 직접 입력한 값
 * 그대로 보낸다 — AI가 이름을 짓지 않는다(CLAUDE.md 2.2). */
export function bundleCardsIntoProject(
  cardIds: number[],
  name: string,
  startedAt: string,
): Promise<Project> {
  return request<Project>("/cards/bundle-into-project", {
    method: "POST",
    body: JSON.stringify({ card_ids: cardIds, name, started_at: startedAt }),
  });
}

// ---------------------------------------------------------------------------
// 2. 프로젝트 — docs/05-api-contract.md §2
// ---------------------------------------------------------------------------

export function listProjects(): Promise<Project[]> {
  return request<{ projects: Project[] }>("/projects").then((res) => res.projects);
}

/** 이름과 시작일만 받는다 (CLAUDE.md 2.4 — 폴더 CRUD 고도화 금지). 생성 시 자동으로 현재 프로젝트가 된다. */
export function createProject(name: string, startedAt: string): Promise<Project> {
  return request<Project>("/projects", {
    method: "POST",
    body: JSON.stringify({ name, started_at: startedAt }),
  });
}

export function updateProject(id: number, patch: UpdateProjectPatch): Promise<Project> {
  return request<Project>(`/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

// ---------------------------------------------------------------------------
// 3. 경력기술서 — docs/05-api-contract.md §3 (제품의 핵심)
// ---------------------------------------------------------------------------

/**
 * 경력기술서를 만들 범위 (9/18 신규, Figma 4.2.1 "범위 선택").
 *
 * 프로젝트를 여러 개 고를 수 있고, 어느 프로젝트에도 안 들어간 기록(미분류)을
 * 따로 포함시킬 수 있다. 서버는 **프로젝트 경계를 넘어 카드를 합치지 않는다** —
 * A은행의 "결제 API 개선"과 B카드의 "결제 API 개선"은 별개 경력이기 때문
 * (CLAUDE.md 3장, src/agent/pipeline.py의 build_career_doc 참고).
 */
export interface ResumeScope {
  projectIds: number[];
  includeUnassigned: boolean;
}

/** 프로젝트 하나짜리 범위 — 기존 "현재 프로젝트만" 동작을 그대로 표현한다. */
export function singleProjectScope(projectId: number): ResumeScope {
  return { projectIds: [projectId], includeUnassigned: false };
}

export function isScopeEmpty(scope: ResumeScope): boolean {
  return scope.projectIds.length === 0 && !scope.includeUnassigned;
}

/** 범위가 프로젝트 정확히 하나면 그 id, 아니면 null (초안 저장 키 판별용). */
export function singleProjectIdOf(scope: ResumeScope): number | null {
  return scope.projectIds.length === 1 && !scope.includeUnassigned ? scope.projectIds[0] : null;
}

/**
 * 범위를 로컬 저장소 키로 쓸 수 있는 짧은 문자열로 만든다 (캐시/직접수정 override 공용).
 * 프로젝트 하나짜리 범위는 `"12"`처럼 예전(프로젝트 id만 쓰던) 키와 같은 모양이라,
 * 9/18 이전에 저장된 값이 그대로 이어진다. 프로젝트 순서는 결과 순서에 영향을
 * 주므로 정렬하지 않고 고른 순서 그대로 쓴다.
 */
export function resumeScopeKey(scope: ResumeScope): string {
  return `${scope.projectIds.join(",")}${scope.includeUnassigned ? "+u" : ""}`;
}

function scopeBody(scope: ResumeScope): Record<string, unknown> {
  return { project_ids: scope.projectIds, include_unassigned: scope.includeUnassigned };
}

/** 범위 안의 카드를 묶어 STAR 항목으로 변환한다. 무거운 호출 — 로딩 상태 필수.
 * 프로젝트마다 따로 묶이므로 고른 프로젝트 수만큼 시간이 더 걸린다. */
export function buildResume(scope: ResumeScope, jdText?: string): Promise<StarItem[]> {
  return request<{ items: StarItem[] }>("/resume", {
    method: "POST",
    body: JSON.stringify({
      ...scopeBody(scope),
      ...(jdText ? { jd_text: jdText } : {}),
    }),
  }).then((res) => res.items);
}

/**
 * 유저가 AI 초안을 가져다 직접 고친 자유 텍스트(마크다운) — `buildResume()`이
 * 반환하는 구조화된 StarItem과는 별개다(9/14 신규, docs/05-api-contract.md §3).
 * 저장된 초안이 없으면 `content`/`updated_at`이 둘 다 null.
 */
export interface ResumeDraft {
  /** 마스터 초안(여러 프로젝트를 한 문서로)은 프로젝트에 귀속되지 않아 null. */
  project_id: number | null;
  content: string | null;
  updated_at: string | null;
}

/** `projectId`가 null이면 마스터 초안(유저당 1개)을 조회한다 (9/18). */
export function getResumeDraft(projectId: number | null): Promise<ResumeDraft> {
  const query = projectId === null ? "" : `?project_id=${projectId}`;
  return request<ResumeDraft>(`/resume/draft${query}`);
}

export function saveResumeDraft(projectId: number | null, content: string): Promise<ResumeDraft> {
  return request<ResumeDraft>("/resume/draft", {
    method: "PUT",
    body: JSON.stringify({ project_id: projectId, content }),
  });
}

/**
 * "기존 경력기술서 붙여넣기 → Before/After 대조" (9/15 신규, Figma 90:612/90:640).
 * 완전히 선택 사항 — `buildResume()`과 독립적으로 동작한다.
 *
 * 관련 카드가 없으면 `enhanced`는 `original`과 동일하게 오고 `source_dates`/
 * `source_card_ids`/`gap_comment`는 전부 비어 있다 — 근거 없이 보강된 것처럼
 * 보이게 만들지 않는다(CLAUDE.md 2.2). `source_card_ids`로 카드를 매칭할 것.
 */
export interface EnhancedItem {
  original: string;
  enhanced: string;
  gap_comment: string;
  source_dates: string[];
  source_card_ids: number[];
}

export function enhanceResume(
  scope: ResumeScope,
  existingItems: string[],
): Promise<EnhancedItem[]> {
  return request<{ items: EnhancedItem[] }>("/resume/enhance", {
    method: "POST",
    body: JSON.stringify({ ...scopeBody(scope), existing_items: existingItems }),
  }).then((res) => res.items);
}

/**
 * "공고 요구사항 매칭" (9/16 신규, Figma 100:692 "4.2-j2"). `buildResume()`보다 앞선
 * 단계 — JD를 붙여넣으면 먼저 이걸로 "요구사항 N개 중 M개에 기록이 있어요"를 보여준
 * 뒤, "이 공고에 맞춰 초안 만들기"를 누르면 그때 같은 jdText로 buildResume()을 부른다.
 *
 * `source_card_ids`가 빈 요구사항은 "기록 없음"으로 표시한다 — 없는 근거를 지어내
 * 채우지 않는다(CLAUDE.md 2.2).
 */
export interface JdRequirement {
  requirement: string;
  source_dates: string[];
  source_card_ids: number[];
}

export interface JdRequirementsResult {
  job_title: string;
  company: string;
  years_label: string;
  requirements: JdRequirement[];
}

export function getJdRequirements(
  scope: ResumeScope,
  jdText: string,
): Promise<JdRequirementsResult> {
  return request<JdRequirementsResult>("/resume/jd-requirements", {
    method: "POST",
    body: JSON.stringify({ ...scopeBody(scope), jd_text: jdText }),
  });
}

/**
 * "AI 역질문" (9/16 신규, Figma 100:692 "4.2-3"/"4.2-2 모드 B"). StarItem은 서버에
 * 저장되지 않으므로(CLAUDE.md 3장) 화면이 들고 있는 값을 그대로 요청에 실어 보낸다.
 */
export function getStarQuestions(item: StarItem): Promise<string[]> {
  return request<{ questions: string[] }>("/resume/star-questions", {
    method: "POST",
    body: JSON.stringify({ item }),
  }).then((res) => res.questions);
}

export interface StarAnswerResult {
  updated_item: StarItem;
  changed_field: "action" | "result";
}

export function applyStarAnswers(
  item: StarItem,
  answers: { question: string; answer: string }[],
): Promise<StarAnswerResult> {
  return request<StarAnswerResult>("/resume/star-apply-answers", {
    method: "POST",
    body: JSON.stringify({ item, answers }),
  });
}

/**
 * "Word" 내보내기 (9/16 신규 — 그동안 프론트에서 "준비 중"으로 막아뒀던 버튼을
 * 실제로 구현). 응답이 JSON이 아니라 파일 바이너리라 공용 `request()` 대신
 * fetch를 직접 써서 blob으로 받고, 브라우저 다운로드를 그 자리에서 트리거한다.
 */
export async function exportResumeDocx(content: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/resume/export/docx`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
  } catch {
    throw new ApiError(0, "서버에 연결할 수 없습니다.");
  }
  if (!res.ok) {
    // 실패 응답은 파일이 아니라 JSON({detail})이다 — 413(본문 초과)/429(요청 잦음)처럼
    // 서버가 이유를 알려주는 경우가 있어 statusText 대신 detail을 우선 쓴다.
    let detail = res.statusText || "내보내기에 실패했습니다.";
    try {
      const body = (await res.json()) as { detail?: string };
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // JSON이 아니면 statusText 그대로
    }
    throw new ApiError(res.status, detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "resume.docx";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// 5. 노션 (읽기 전용) — docs/05-api-contract.md §5
// ---------------------------------------------------------------------------

export interface NotionSyncResult {
  imported: number;
  /** 9/17 신규 — 한 번에 처리할 페이지 수 상한을 넘겨 이번에 못 가져온 개수.
   * 0이면 전부 가져온 것이고, 0보다 크면 다시 눌러 이어서 가져갈 수 있다. */
  skipped: number;
  cards: Card[];
}

/**
 * 노션 페이지를 가져와 카드로 저장한다. 매일 쓰는 경로가 아니라(연 1회 수준의
 * 설정에 가까움) 로딩이 길어도 무방하다 — 임포트되는 페이지 전부를 그때그때
 * 파싱하므로 느릴 수 있다 (`docs/05-api-contract.md` §5). `page_id`는 선택 —
 * 페이지 선택 UI는 만들지 않는다 (CLAUDE.md 2.4).
 */
export function syncNotion(userToken: string, pageId?: string): Promise<NotionSyncResult> {
  return request<NotionSyncResult>("/notion/sync", {
    method: "POST",
    body: JSON.stringify({
      user_token: userToken,
      ...(pageId ? { page_id: pageId } : {}),
    }),
  });
}

// ---------------------------------------------------------------------------
// 7. 웹푸시 — docs/05-api-contract.md §7
// ---------------------------------------------------------------------------

/**
 * VAPID 공개키를 가져온다. 서버에 `VAPID_PUBLIC_KEY`가 설정되어 있지 않으면
 * 503 `ApiError`가 던져진다 — 호출부에서 잡아서 푸시 UI를 숨기거나 비활성화할 것
 * (`components/PushSetup.tsx`).
 */
export function getVapidPublicKey(): Promise<string> {
  return request<{ public_key: string }>("/push/vapid-public-key").then((res) => res.public_key);
}

/** 같은 `endpoint`로 다시 호출하면 서버에서 upsert된다 — 별도 "이미 구독됨" 분기 불필요. */
export function subscribePush(payload: PushSubscriptionPayload): Promise<void> {
  return request<void>("/push/subscribe", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** 존재하지 않는 구독을 지워도 204(멱등) — 호출부에서 별도 예외 처리 불필요. */
export function unsubscribePush(endpoint: string): Promise<void> {
  return request<void>("/push/subscribe", {
    method: "DELETE",
    body: JSON.stringify({ endpoint }),
  });
}

// ---------------------------------------------------------------------------
// 8. 헬스체크 — docs/05-api-contract.md §8 (배포 검증용, 필수는 아님)
// ---------------------------------------------------------------------------

export function getHealth(): Promise<HealthStatus> {
  return request<HealthStatus>("/health");
}

// ---------------------------------------------------------------------------
// 9. 온보딩 프로필 — docs/05-api-contract.md §9 (P2, 싱글턴 — 로그인 없음)
// ---------------------------------------------------------------------------

export function getProfile(): Promise<Profile> {
  return request<Profile>("/profile");
}

/**
 * 9/18 — 연차(`years_segment`)는 더 이상 보내지 않는다. 회사 기간에서 서버가
 * 계산한다(Figma "연차는 여기서 자동으로 계산해요. 따로 묻지 않을게요").
 * 화면이 보여주는 "6년 3개월"과 저장되는 구간이 갈라지지 않게 하려는 것이다.
 */
export function updateProfile(update: ProfileUpdate): Promise<Profile> {
  return request<Profile>("/profile", {
    method: "PUT",
    body: JSON.stringify({
      job_field: update.jobField,
      ...(update.jobDetail ? { job_detail: update.jobDetail } : {}),
      ...(update.targetJobs ? { target_jobs: update.targetJobs } : {}),
      ...(update.companies !== undefined ? { companies: update.companies } : {}),
    }),
  });
}

// ---------------------------------------------------------------------------
// 10. 카카오 로그인 (9/14 신규) — 계획서(카카오 소셜 로그인 + 진입 게이팅) 참고
// ---------------------------------------------------------------------------

export interface Me {
  id: number;
  nickname: string | null;
  profile_image_url: string | null;
}

/**
 * 지금 로그인 상태인지 확인한다. 로그아웃 상태(401)는 에러가 아니라 정상적인 한 가지
 * 상태이므로 `ApiError`를 던지는 대신 `null`을 반환한다 — 호출부(`AuthGate`)가
 * try/catch 없이 그냥 값으로 분기할 수 있게.
 */
export async function getMe(): Promise<Me | null> {
  try {
    return await request<Me>("/auth/me");
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null;
    throw err;
  }
}

/** 카카오 로그인 화면으로 이동한다. fetch가 아니라 실제 브라우저 네비게이션이어야
 * 카카오 로그인/동의 화면 리다이렉트 체인이 정상 동작한다. */
export function kakaoLoginUrl(): string {
  return `${API_BASE}/auth/kakao/login`;
}

export function logout(): Promise<void> {
  return request<void>("/auth/logout", { method: "POST" });
}

// ---------------------------------------------------------------------------
// 9. 백업 내보내기 / 불러오기 — Figma "5.0 설정" 41:333 / 41:338 (9/18 신규)
//
// 불러오기가 서버 엔드포인트인 이유: `createCard()`는 원문을 LLM에 태워 새로
// 정리하는 경로라 복원에 쓸 수 없다(문장이 바뀌고 카드 수만큼 비용이 든다).
// `POST /api/backup/import`는 저장된 값을 그대로 되살리고 LLM을 타지 않는다.
// ---------------------------------------------------------------------------

export interface BackupProject {
  id: number;
  name: string;
  started_at: string;
  ended_at: string | null;
}

export interface BackupCard {
  id: number;
  project_id: number | null;
  raw_text: string;
  refined_sentence: string;
  skill_tags: string[];
  confidence: number;
  created_at: string;
  created_time: string | null;
}

export interface BackupFile {
  version: number;
  exported_at: string;
  projects: BackupProject[];
  cards: BackupCard[];
}

export function exportBackup(): Promise<BackupFile> {
  return request<BackupFile>("/backup");
}

export interface BackupImportResult {
  imported_projects: number;
  imported_cards: number;
}

/** **덧붙이기다 — 기존 기록을 지우지 않는다.** 같은 파일을 두 번 넣으면 두 벌 생긴다. */
export function importBackup(file: {
  projects: BackupProject[];
  cards: BackupCard[];
}): Promise<BackupImportResult> {
  return request<BackupImportResult>("/backup/import", {
    method: "POST",
    body: JSON.stringify({ projects: file.projects, cards: file.cards }),
  });
}
