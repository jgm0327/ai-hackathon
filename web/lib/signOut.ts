import { logout } from "@/lib/api";

/**
 * 로그아웃 — 서버 세션을 지우고 **브라우저에 남은 그 사람 데이터까지** 비운 뒤
 * 로그인 화면으로 나간다 (9/21 신규).
 *
 * **왜 함수로 뺐나 (그리고 왜 통째로 새로고침하나)**: 예전엔 설정 화면이
 * `await logout()` 뒤에 `router.replace("/login")`만 했다. 그런데 그건 **클라이언트
 * 라우팅**이라 문서가 그대로 살아 있고, 그 안의 메모리 캐시도 같이 살아남는다 —
 * `lib/navCache.ts`는 모듈 수준 `Map`에 이전 사용자의 카드·프로젝트·프로필을 들고
 * 있다. 그래서 로그아웃 뒤 다른 계정으로 들어와도 첫 화면에 **앞사람 기록이 잠깐
 * 그대로 보인다**(각 화면이 캐시에서 먼저 그리고 나중에 갱신하는 구조라서).
 * 로그아웃은 그 상태를 남겨서는 안 되는 동작이므로 `location.replace`로 문서를
 * 통째로 새로 띄운다 — 메모리 캐시가 한 번에 사라진다.
 *
 * `localStorage`에 남는 것들도 기기 공유(데모에서 한 폰으로 여러 명이 로그인)를
 * 생각하면 같이 지워야 한다. 다만 **우리 키만** 지운다 — 같은 도메인의 다른 값을
 * 건드리지 않도록 접두사로 고른다.
 */
const CLEAR_PREFIXES = [
  "career-log:", // 입력 중이던 메모 초안, 인트로 표시 등
  "careerlog:", // 퇴근 알림 시각 등 (초기 코드가 쓰던 접두사)
];

function clearLocalData(storage: Storage): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i);
      if (key && CLEAR_PREFIXES.some((p) => key.startsWith(p))) keys.push(key);
    }
    keys.forEach((key) => storage.removeItem(key));
  } catch {
    // 접근 불가(프라이빗 모드 등) — 로그아웃 자체는 계속 진행한다.
  }
}

export async function signOut(): Promise<void> {
  try {
    await logout();
  } catch {
    // 세션이 이미 만료됐어도 서버는 204(멱등)를 준다. 네트워크 실패로 여기 와도
    // 로컬 정리와 화면 이동은 그대로 진행한다 — 쿠키가 유효하지 않으면 다음
    // 요청에서 401로 걸러진다.
  }
  clearLocalData(window.localStorage);
  clearLocalData(window.sessionStorage);
  // `router.replace`가 아니라 문서 교체다(위 주석 참고).
  window.location.replace("/login");
}
