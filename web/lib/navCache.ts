/**
 * 탭을 옮길 때 화면이 깜박이지 않게 하는 아주 작은 메모리 캐시 (9/18 신규).
 *
 * **왜 필요한가**: 하단 탭으로 `/`와 `/stack`을 오갈 때마다 화면이 빈 상태에서
 * 다시 시작했다. 실측(로컬 프로덕션 빌드, `/stack` → `/`):
 *
 *   +57ms  "불러오는 중…" 빈 상태 (본문 96자, 높이 731)
 *   +89ms  프로젝트·타깃 트랙 채워짐
 *   +111ms 역량 버블 등장 (높이 740)
 *   +116ms 이어 쓰기 배너 등장 (높이 798)
 *
 * 네 단계로 나뉘어 채워지고 문서 높이가 두 번 뛴다. 로컬은 간격이 20~30ms라 "빠른
 * 번쩍임"이지만, 배포 환경에서는 호출마다 수십~수백 ms라 눈에 확 띈다. 게다가
 * `cards`/`skill-summary`가 `projects` 응답을 기다리는 순차 대기라 더 늘어난다.
 *
 * **무엇을 하는가**: 마지막으로 성공한 응답을 기억해서, 같은 화면에 다시 들어올 때
 * **첫 렌더부터 그 값으로 그린다.** 그 뒤 백그라운드로 다시 받아 갱신한다. 값이
 * 바뀌지 않으면 화면도 그대로다 — 깜박임이 사라진다.
 *
 * **의도적으로 작게 유지한다**:
 *   - 메모리에만 둔다(탭 수명). 새로고침하면 사라지므로 오래된 값이 남지 않는다.
 *   - 만료/무효화 규칙이 없다. 쓰기 동작(카드 추가/삭제 등)은 이미 각 화면이
 *     자기 상태를 직접 갱신하고, 다음 진입 때 어차피 다시 받는다.
 *   - `localStorage`를 쓰지 않는다. 기기에 남을 값이 아니고, 이미 경력기술서 캐시가
 *     그쪽을 쓰고 있어 역할을 섞지 않는다.
 */
const cache = new Map<string, unknown>();

export function getCached<T>(key: string): T | undefined {
  return cache.get(key) as T | undefined;
}

export function setCached<T>(key: string, value: T): void {
  cache.set(key, value);
}

/** 캐시 키 — 오타로 서로 다른 칸을 쓰지 않게 한곳에 모아둔다. */
export const navKey = {
  projects: () => "projects",
  cards: (projectId: number) => `cards:${projectId}`,
  // 홈은 상위 4개, /stack 역량 리스트는 50개를 받는다 — 같은 칸을 쓰면 서로의 값을
  // 덮어써서 버블 개수가 뒤바뀐다. topN을 키에 넣어 분리한다.
  skillSummary: (projectId: number, topN: number) => `skill-summary:${projectId}:${topN}`,
  profile: () => "profile",
  suggestions: () => "unclassified-suggestions",
};
