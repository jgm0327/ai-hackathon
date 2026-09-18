/**
 * STAR 항목 개별 필드(상황/과제/행동/결과) 직접 수정 — Figma `89:419` "문장 수정".
 *
 * `build_resume()`은 매번 카드로부터 새로 계산되는 비영속 값이라(CLAUDE.md 3장,
 * `resumeCache.ts` 참고), 유저가 특정 항목의 특정 필드를 손으로 고쳐도 그냥
 * `items` 배열을 직접 바꿔버리면 재생성(JD를 바꿔 다시 만들기 등) 시 사라진다.
 * Figma는 "직접 고친 문장은 다시 변환해도 유지돼요"라고 명시하므로, AI가 만든
 * 원본 값과 사람이 고친 값을 **분리해서** 보관해야 한다 — 재생성돼도 override만
 * 다시 덮어씌우면 되고, "AI 문장으로 되돌리기"도 원본을 잃지 않고 그대로 가능하다.
 *
 * 항목 자체엔 안정적인 id가 없다(매 생성마다 LLM이 새로 그룹핑). 대신
 * `source_card_ids`(정렬된 카드 id 조합)를 항목의 식별자로 쓴다 — 같은 카드
 * 조합이 같은 항목으로 다시 묶이는 한 override가 계속 적용된다. 카드 구성/그룹핑이
 * 바뀌면(카드 추가/삭제, LLM이 다르게 묶음) 조용히 매칭이 끊기고 override는 그냥
 * 안 쓰이게 된다 — 에러 없이 자연스럽게 무효화되는 편이 낫다고 판단함.
 *
 * 이 override는 **사람이 직접 쓴 값**이라 CLAUDE.md 3장이 막는 "AI 그룹핑 저장"과는
 * 무관하다(`resume/draft` 자유 텍스트 저장과 같은 성격) — 다만 여기선 프로젝트당
 * 여러 초안을 오갈 수 있으므로 서버 저장 대신 로컬 캐시로 충분하다고 판단해 `PUT
 * /resume/draft`까지는 확장하지 않았다.
 */
import { StarItem } from "./api";

export type StarField = "situation" | "task" | "action" | "result";

type FieldMap = Partial<Record<StarField, string>>;
type ScopeOverrides = Record<string, FieldMap>; // itemKey -> field -> 사용자가 쓴 값

const PREFIX = "career-log:resume-field-overrides:";

/**
 * 9/18부터 프로젝트 id가 아니라 "범위 키"(`lib/api.ts`의 `resumeScopeKey`)로 칸을
 * 나눈다 — 마스터 경력기술서(여러 프로젝트를 한 문서로)는 프로젝트 하나에 귀속되지
 * 않기 때문. 프로젝트 하나짜리 범위의 키는 `"12"`처럼 예전과 같은 모양이라 이전에
 * 저장된 수정값이 그대로 이어진다.
 */
function storageKey(scopeKey: string): string {
  return `${PREFIX}${scopeKey}`;
}

function itemKey(sourceCardIds: number[]): string {
  return [...sourceCardIds].sort((a, b) => a - b).join(",");
}

function readAll(scopeKey: string): ScopeOverrides {
  try {
    const raw = localStorage.getItem(storageKey(scopeKey));
    return raw ? (JSON.parse(raw) as ScopeOverrides) : {};
  } catch {
    return {};
  }
}

function writeAll(scopeKey: string, data: ScopeOverrides): void {
  try {
    localStorage.setItem(storageKey(scopeKey), JSON.stringify(data));
  } catch {
    // 용량 초과 등 — 이번 수정만 반영이 안 될 뿐 치명적이지 않다.
  }
}

export function getFieldOverrides(scopeKey: string, sourceCardIds: number[]): FieldMap {
  if (sourceCardIds.length === 0) return {};
  return readAll(scopeKey)[itemKey(sourceCardIds)] ?? {};
}

export function setFieldOverride(
  scopeKey: string,
  sourceCardIds: number[],
  field: StarField,
  value: string,
): void {
  if (sourceCardIds.length === 0) return; // 근거 카드가 없는 항목은 재식별이 안 되므로 무시
  const all = readAll(scopeKey);
  const key = itemKey(sourceCardIds);
  all[key] = { ...all[key], [field]: value };
  writeAll(scopeKey, all);
}

export function clearFieldOverride(
  scopeKey: string,
  sourceCardIds: number[],
  field: StarField,
): void {
  const all = readAll(scopeKey);
  const key = itemKey(sourceCardIds);
  if (!all[key]) return;
  const rest: FieldMap = { ...all[key] };
  delete rest[field];
  if (Object.keys(rest).length === 0) {
    delete all[key];
  } else {
    all[key] = rest;
  }
  writeAll(scopeKey, all);
}

/** `items`에 저장된 override를 덮어씌운 표시용 배열을 만든다. 원본 `items`는 그대로
 * 두고 렌더링용으로만 파생시켜서, "되돌리기"가 항상 진짜 AI 원본으로 돌아갈 수
 * 있게 한다. */
export function applyFieldOverrides(items: StarItem[], scopeKey: string): StarItem[] {
  return items.map((item) => {
    const overrides = getFieldOverrides(scopeKey, item.source_card_ids);
    if (Object.keys(overrides).length === 0) return item;
    return { ...item, ...overrides };
  });
}
