/**
 * 온보딩 "나중에 설정하기" 스킵 플래그 (Figma 온보딩 화면, 9/16 신규).
 *
 * `AuthGate`는 프로필이 없으면(job_field null) 무조건 `/onboarding`으로 되돌려보낸다
 * (9/14 진입 게이팅). Figma의 스킵 링크를 그냥 `/`로 이동만 시키면 AuthGate가 바로
 * 다시 `/onboarding`으로 튕겨내서 스킵이 무의미해진다 — 그래서 스킵을 누르면 이
 * 플래그를 세션에 남기고, AuthGate가 그 플래그를 보고 이번 세션(탭)에 한해서만
 * 강제 리다이렉트를 건너뛴다. 새로 로그인하거나 탭을 닫고 다시 열면(sessionStorage
 * 특성상) 다시 온보딩을 권유하게 된다 — 완전히 끄는 게 아니라 "이번엔 건너뛰기".
 */
const SKIP_KEY = "career-log:onboarding-skipped";

export function markOnboardingSkipped(): void {
  try {
    sessionStorage.setItem(SKIP_KEY, "1");
  } catch {
    // 세션 스토리지 접근 불가(프라이빗 모드 등) — 이번엔 스킵이 안 먹혀도 치명적이지 않다.
  }
}

export function isOnboardingSkipped(): boolean {
  try {
    return sessionStorage.getItem(SKIP_KEY) === "1";
  } catch {
    return false;
  }
}
