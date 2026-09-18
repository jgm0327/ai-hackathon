/**
 * 노션 통합 토큰 보관 — 세션 동안만 (9/18 신규).
 *
 * **왜 서버에 저장하지 않는가**: 노션 통합 토큰은 그 워크스페이스를 읽을 수 있는
 * 서드파티 자격증명이다. 우리 SQLite에 평문으로 눕히면, DB 파일 하나가 새는 순간
 * 사용자의 노션까지 같이 샌다. 우리가 굳이 보관할 이유도 없다 — 노션을 읽는 시점은
 * 사용자가 화면에서 "가져오기"를 누른 그 순간뿐이다.
 *
 * **왜 localStorage가 아니라 sessionStorage인가**: localStorage는 탭을 닫아도 남는다.
 * 공용 PC에서 로그아웃해도 토큰이 남아 있는 상태를 만들고 싶지 않았다. sessionStorage는
 * 탭을 닫으면 사라진다 — Figma의 "처음 한 번만 연결하면 돼요"보다는 짧지만,
 * 자격증명을 오래 들고 있지 않는 쪽을 택했다.
 *
 * 접근이 막힌 환경(프라이빗 모드 등)에서는 조용히 "없음"으로 동작한다. 그때는
 * 사용자가 가져오기를 누를 때마다 토큰을 다시 입력하면 될 뿐, 기능이 깨지지는 않는다.
 */
const KEY = "career-log:notion-token";

export function getNotionToken(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setNotionToken(token: string): void {
  try {
    sessionStorage.setItem(KEY, token);
  } catch {
    // 저장 못 해도 이번 요청은 그대로 진행된다 — 다음에 다시 물어볼 뿐이다.
  }
}

export function clearNotionToken(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // 이미 없거나 접근 불가 — 어느 쪽이든 결과는 같다.
  }
}
