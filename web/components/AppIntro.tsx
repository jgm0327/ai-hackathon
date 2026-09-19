"use client";

import { usePathname } from "next/navigation";
import { preload } from "react-dom";
import { useEffect, useLayoutEffect, useState } from "react";
import {
  CopyStage,
  INTRO_SHARD_ASSETS,
  LOGO_ASSET,
  LogoStage,
} from "@/components/WelcomeIntro";

/** 각 장이 머무는 시간(ms) — 로그인 화면의 인트로와 같은 값이다. */
const STAGE_DURATIONS = [1400, 3200];

/** 이번 세션에 인트로를 이미 봤는지. `sessionStorage`라 탭/앱을 닫으면 사라진다.
 *  로그인 화면도 같은 장면을 재생하므로 같은 키를 쓴다(아래 `markIntroSeen`). */
export const INTRO_SEEN_KEY = "career-log:intro-seen";

/** 로그인 화면이 자기 인트로를 재생했을 때 호출한다 — 로그인 직후 홈으로 넘어가서
 *  같은 인트로를 한 번 더 보는 일을 막는다. */
export function markIntroSeen(): void {
  try {
    sessionStorage.setItem(INTRO_SEEN_KEY, "1");
  } catch {
    // 접근 불가 — 인트로를 한 번 더 보게 될 뿐이라 무시한다.
  }
}

/**
 * SSR에서는 `useLayoutEffect`가 경고를 내므로 브라우저에서만 쓴다.
 * 이 컴포넌트는 **그릴지 말지를 첫 페인트 전에** 정해야 해서(그 뒤에 정하면 새로고침
 * 때 인트로가 한 프레임 번쩍인다) 일반 effect로는 부족하다.
 */
const useIsomorphicLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

/**
 * 앱 스플래시 — 앱을 **열 때** 웰컴 인트로 1·2번 장을 한 번 재생한다 (9/19 신규).
 *
 * **왜 루트에 있나**: 인트로는 원래 `/login`에만 있어서 로그인한 사람은 앱을 열어도
 * 볼 일이 없었다(바로 홈으로 간다). 사용자가 "실행할 때마다 보이게" 해달라고 해서,
 * 진입 주소와 무관하게 도는 오버레이로 올렸다.
 *
 * **"실행"의 기준은 브라우저 세션 1회다** (9/19 조정). 처음엔 문서 로드마다 돌렸는데
 * 그러면 **새로고침할 때마다** 4.6초짜리 인트로를 다시 본다 — 개발/데모 중에는 물론이고
 * 평소에도 성가시다. `sessionStorage`에 표시해서 같은 탭(설치형 PWA라면 같은 실행)
 * 안에서는 한 번만 보여준다:
 *
 *   - 앱을 닫았다 다시 열기 / 새 탭 → 새 세션 → **인트로 재생**
 *   - 새로고침, 탭 이동, 화면 이동 → 같은 세션 → **재생 안 함**
 *
 * **`/login`에서는 뜨지 않는다** — 그 화면이 같은 1·2번 장을 직접 재생하고 이어서
 * 로그인 버튼(3번)까지 보여준다. 둘 다 돌면 인트로를 두 번 보게 된다.
 *
 * 아무 데나 누르면 즉시 건너뛴다 — 자동 재생만 있으면 급한 사람이 4.6초를 기다려야
 * 한다(WCAG 2.2.1 "시간 제한"). 모션을 줄이는 설정이면 globals.css가 애니메이션을
 * 끄고 장면만 넘어간다.
 */
export function AppIntro() {
  const pathname = usePathname();
  // 로그인 화면은 자기 인트로가 있다.
  const skip = pathname === "/login";

  // "pending"은 아직 정하지 않은 상태다. 서버와 첫 클라이언트 렌더가 이 값으로
  // 일치해야 하이드레이션이 깨지지 않는다.
  const [phase, setPhase] = useState<"pending" | "playing" | "done">("pending");
  const [stage, setStage] = useState(0);

  // 2번 장의 조각 6개를 1번 장이 떠 있는 동안 미리 받아둔다(로그인 화면과 같은 이유 —
  // 장이 바뀌는 프레임에 다운로드가 겹치면 조각이 뒤늦게 채워져 전환이 끊겨 보인다).
  [LOGO_ASSET, ...INTRO_SHARD_ASSETS].forEach((href) => preload(href, { as: "image" }));

  useIsomorphicLayoutEffect(() => {
    if (phase !== "pending") return;
    if (skip) {
      setPhase("done");
      return;
    }
    let seen = false;
    try {
      seen = sessionStorage.getItem(INTRO_SEEN_KEY) === "1";
      if (!seen) sessionStorage.setItem(INTRO_SEEN_KEY, "1");
    } catch {
      // 접근 불가(프라이빗 모드 등) — 그냥 재생한다. 인트로는 못 봐도 그만이지만
      // 여기서 막히면 화면이 아예 안 뜨는 쪽이 훨씬 나쁘다.
    }
    setPhase(seen ? "done" : "playing");
  }, [phase, skip]);

  useEffect(() => {
    if (phase !== "playing") return;
    const timer = setTimeout(() => {
      if (stage >= STAGE_DURATIONS.length - 1) setPhase("done");
      else setStage((s) => s + 1);
    }, STAGE_DURATIONS[stage]);
    return () => clearTimeout(timer);
  }, [phase, stage]);

  if (phase !== "playing") return null;

  return (
    <div
      // 스플래시는 화면 전체를 덮는다 — 레이아웃(`max-w-md`) 밖으로 나가야 데스크톱
      // 폭에서도 꽉 찬다.
      onClick={() => setPhase("done")}
      role="presentation"
      className="fixed inset-0 z-[100] flex flex-col bg-[#1a1917] text-[#fafafa]"
    >
      {/* key로 장이 바뀔 때마다 페이드가 다시 돈다(로그인 화면과 동일). */}
      <div key={stage} className="welcome-fade flex flex-1 flex-col">
        {stage === 0 ? <LogoStage /> : <CopyStage />}
      </div>
    </div>
  );
}
