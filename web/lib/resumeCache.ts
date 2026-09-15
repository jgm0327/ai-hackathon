/**
 * `buildResume()`(POST /api/resume, LLM 호출) 결과의 프론트 캐시.
 *
 * **왜 필요한가**: CLAUDE.md 3장은 "AI가 만드는 작업 묶음은 DB에 저장하지 않는다"고
 * 못 박는다 — 저장하면 그룹을 정정/관리하는 CRUD UI가 필요해지고 그 순간 2.1이
 * 깨지기 때문. 하지만 이 원칙은 "묶음을 정식 데이터로 만들지 말라"는 뜻이지, "같은
 * 입력에 같은 LLM 호출을 반복해도 된다"는 뜻은 아니다. `/stack`의 "인과관계로
 * 묶어보기"를 새로고침할 때마다, 혹은 `/resume`을 다시 열 때마다 카드가 하나도
 * 안 바뀌었는데 유료 LLM API를 또 호출하는 건 순수한 낭비다 (9/14 사용자 지적).
 *
 * 그래서 여기선 **결과를 저장하는 게 아니라, "카드 목록이 그대로면 재계산하지
 * 않는다"는 최적화만** 한다 — 캐시 키에 카드 id 목록(정렬)을 같이 저장해두고,
 * 다음 호출 시점의 카드 id 목록과 다르면 캐시를 버리고 다시 계산한다. 그룹을
 * 사용자가 보거나 고치는 기능은 전혀 없으므로 관리 UI가 필요해지지 않는다 — 3장
 * 원칙은 그대로 지켜진다.
 *
 * `localStorage`에 둬서 새로고침·탭 재방문에도 살아남게 한다. 카드 한 장이라도
 * 추가/삭제되면 id 목록이 달라져 자동으로 무효화된다(수동 무효화 로직 불필요).
 * 태그만 수정하는 경우엔 카드 id가 안 바뀌므로 캐시가 유지되는데, `source_dates`/
 * `source_card_ids`는 태그가 아니라 문장 내용에서 나오므로 문제 없다(태그는 애초에
 * 수정 후 재생성해도 결과가 똑같을 항목).
 */
import { Card, StarItem, buildResume, listCards } from "./api";

const CACHE_PREFIX = "career-log:resume-cache:";

interface CachedResume {
  cardIds: number[]; // 정렬된 카드 id — 캐시 유효성 판단 기준
  items: StarItem[];
}

function cacheKey(projectId: number, jdText?: string): string {
  return `${CACHE_PREFIX}${projectId}:${jdText?.trim() ?? ""}`;
}

function sortedIds(cards: Card[]): number[] {
  return cards.map((c) => c.id).sort((a, b) => a - b);
}

function idsEqual(a: number[], b: number[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

function readCache(key: string): CachedResume | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as CachedResume) : null;
  } catch {
    // localStorage 접근 불가(프라이빗 모드 등)나 손상된 값 — 캐시는 최적화일 뿐이니
    // 조용히 무시하고 재계산 경로로 넘어간다.
    return null;
  }
}

function writeCache(key: string, data: CachedResume): void {
  try {
    localStorage.setItem(key, JSON.stringify(data));
  } catch {
    // 용량 초과 등으로 저장 실패해도 기능엔 지장 없다(다음에 또 계산할 뿐).
  }
}

/**
 * `buildResume()`을 카드 목록이 마지막 호출 때와 동일하면 재호출하지 않고 캐시에서
 * 반환한다. `cards`를 이미 들고 있으면(`/stack`처럼) 넘겨서 중복 조회를 피하고,
 * 없으면(`/resume`처럼) 내부에서 `listCards()`로 가져온다 — 이건 LLM 호출이 아니라
 * 가벼운 조회라 비용 걱정 없이 매번 해도 된다.
 */
export async function buildResumeCached(
  projectId: number,
  opts?: { jdText?: string; cards?: Card[] },
): Promise<StarItem[]> {
  const cards = opts?.cards ?? (await listCards(projectId));
  const cardIds = sortedIds(cards);
  const key = cacheKey(projectId, opts?.jdText);

  const cached = readCache(key);
  if (cached && idsEqual(cached.cardIds, cardIds)) {
    return cached.items;
  }

  const items = await buildResume(projectId, opts?.jdText);
  writeCache(key, { cardIds, items });
  return items;
}

/**
 * 네트워크 호출 없이(카드 목록 조회조차 안 함) 캐시에 저장된 마지막 결과만 즉시
 * 반환한다. 없으면 `null`.
 *
 * **왜 필요한가 (9/14)**: `/resume`에서 "경력기술서 만들기"로 생성한 뒤 새로고침하면
 * 화면이 빈 입력 폼으로 돌아가던 문제(사용자 지적) — React state(`items`)가 그냥
 * 메모리에만 있어서 새로고침하면 날아가는 게 당연한데, 카드가 안 바뀌었으면 다시
 * 눌러도 캐시 덕분에 결과 자체는 똑같이 나오니 "생성한 걸 잃어버린 느낌"만 주는
 * 불필요한 마찰이었다. 마운트 시점에 이 함수로 캐시를 먼저 들여다보고 있으면 그걸로
 * 화면을 즉시 채운다 — 카드 구성이 실제로 바뀌었는지 검증까진 안 하므로(그러려면
 * `listCards()` 호출이 필요), 낡은 결과를 잠깐 보여줄 수는 있지만 "다시 만들기"를
 * 누르면 그 시점에 `buildResumeCached()`가 정상적으로 최신 여부를 검증한다.
 */
export function peekCachedResume(projectId: number, jdText?: string): StarItem[] | null {
  const cached = readCache(cacheKey(projectId, jdText));
  return cached?.items ?? null;
}

/**
 * "숫자 되묻기" 인라인 입력(9/15 신규)으로 사용자가 항목 하나를 직접 고쳤을 때,
 * 새로고침해도 그 값이 남아있도록 캐시만 갱신한다 — `cardIds`(유효성 판단 기준)는
 * 그대로 두고 `items`만 바꾼다. 캐시가 아예 없으면(비정상 상태) 조용히 넘어간다 —
 * 화면 자체는 이미 React state로 반영돼 있어 지장 없다.
 */
export function updateCachedResumeItems(projectId: number, items: StarItem[], jdText?: string): void {
  const key = cacheKey(projectId, jdText);
  const cached = readCache(key);
  if (!cached) return;
  writeCache(key, { cardIds: cached.cardIds, items });
}
