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
 * `source_dates`는 항상 배열이다 (빈 배열일 수는 있어도 undefined는 아님).
 */
export interface StarItem {
  title: string;
  period: string;
  situation: string;
  task: string;
  action: string;
  result: string;
  source_dates: string[];
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
}

export interface UpdateProjectPatch {
  is_current?: boolean;
  name?: string;
  ended_at?: string;
}

/** 고정 칩 세트 — 자유 입력이 아니다 (CLAUDE.md 2.4, `docs/05-api-contract.md` §9). */
export const JOB_FIELDS = ["개발", "기획·PM", "디자인", "마케팅", "영업", "데이터"] as const;
export type JobField = (typeof JOB_FIELDS)[number];

export const YEARS_SEGMENTS = ["1-3", "4-6", "7-10", "10+"] as const;
export type YearsSegment = (typeof YEARS_SEGMENTS)[number];

/** "개발" 직군 하위 세부 직무 — Figma에 구체적으로 나온 유일한 직군이라 여기서만 칩으로 고정한다.
 * 다른 직군은 `job_detail`을 자유 입력(또는 생략)으로 받는다. */
export const DEV_JOB_DETAILS = ["백엔드", "프론트엔드", "안드로이드", "iOS", "DevOps", "데이터엔지니어"] as const;

export interface Profile {
  job_field: JobField | null;
  job_detail: string | null;
  years_segment: YearsSegment | null;
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

/** 메모 한 줄을 파싱해 저장한다. 응답은 3~10초 걸릴 수 있다 (호출부에서 스켈레톤 표시). */
export function createCard(rawText: string): Promise<Card> {
  return request<Card>("/cards", {
    method: "POST",
    body: JSON.stringify({ raw_text: rawText }),
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

/** 프로젝트의 카드를 묶어 STAR 항목으로 변환한다. 무거운 호출 — 로딩 상태 필수. */
export function buildResume(projectId: number, jdText?: string): Promise<StarItem[]> {
  return request<{ items: StarItem[] }>("/resume", {
    method: "POST",
    body: JSON.stringify({
      project_id: projectId,
      ...(jdText ? { jd_text: jdText } : {}),
    }),
  }).then((res) => res.items);
}

// ---------------------------------------------------------------------------
// 5. 노션 (읽기 전용) — docs/05-api-contract.md §5
// ---------------------------------------------------------------------------

export interface NotionSyncResult {
  imported: number;
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

export function updateProfile(
  jobField: JobField,
  yearsSegment: YearsSegment,
  jobDetail?: string,
): Promise<Profile> {
  return request<Profile>("/profile", {
    method: "PUT",
    body: JSON.stringify({
      job_field: jobField,
      years_segment: yearsSegment,
      ...(jobDetail ? { job_detail: jobDetail } : {}),
    }),
  });
}
