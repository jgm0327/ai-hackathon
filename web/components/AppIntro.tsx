"use client";

import { usePathname } from "next/navigation";
import { preload } from "react-dom";
import { useEffect, useState } from "react";
import {
  CopyStage,
  INTRO_SHARD_ASSETS,
  LOGO_ASSET,
  LogoStage,
} from "@/components/WelcomeIntro";

/** 각 장이 머무는 시간(ms) — 로그인 화면의 인트로와 같은 값이다. */
const STAGE_DURATIONS = [1400, 3200];

/**
 * 앱 스플래시 — **앱을 열 때마다** 웰컴 인트로 1·2번 장을 한 번 재생한다 (9/19 신규).
 *
 * **왜 루트에 있나**: 인트로는 원래 `/login`에만 있어서 로그인한 사람은 앱을 열어도
 * 볼 일이 없었다(바로 홈으로 간다). 사용자가 "실행할 때마다 보이게" 해달라고 해서,
 * 진입 주소와 무관하게 문서가 새로 뜰 때 한 번 도는 오버레이로 올렸다.
 *
 * **"실행"의 기준은 문서 로드 1회**다. 이 컴포넌트는 루트 레이아웃에 있어서 탭을
 * 옮기거나(`/` ↔ `/stack`) 화면을 이동해도 다시 마운트되지 않는다 — 새로고침하거나
 * 앱을 다시 열 때만 다시 돈다. `sessionStorage` 같은 걸로 한 번만 보여주는 식은
 * 일부러 쓰지 않았다. 그러면 새로고침에는 안 뜨는데, 그건 "실행할 때마다"가 아니다.
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
  // 로그인 화면은 자기 인트로가 있다. 첫 렌더부터 빼야 두 인트로가 겹치지 않는다.
  const skip = pathname === "/login";

  const [stage, setStage] = useState(0);
  const [done, setDone] = useState(skip);

  // 2번 장의 조각 6개를 1번 장이 떠 있는 동안 미리 받아둔다(로그인 화면과 같은 이유 —
  // 장이 바뀌는 프레임에 다운로드가 겹치면 조각이 뒤늦게 채워져 전환이 끊겨 보인다).
  [LOGO_ASSET, ...INTRO_SHARD_ASSETS].forEach((href) => preload(href, { as: "image" }));

  useEffect(() => {
    if (done) return;
    const timer = setTimeout(() => {
      if (stage >= STAGE_DURATIONS.length - 1) setDone(true);
      else setStage((s) => s + 1);
    }, STAGE_DURATIONS[stage]);
    return () => clearTimeout(timer);
  }, [stage, done]);

  if (done) return null;

  return (
    <div
      // 스플래시는 화면 전체를 덮는다 — 아래 화면이 준비되는 동안 잠깐 가려두는 게
      // 목적이라, 레이아웃(`max-w-md`) 밖으로 나가야 데스크톱 폭에서도 꽉 찬다.
      onClick={() => setDone(true)}
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
