"use client";

import { preload } from "react-dom";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { markIntroSeen } from "@/components/AppIntro";
import { CopyStage, INTRO_SHARD_ASSETS, LogoStage } from "@/components/WelcomeIntro";
import { FIELD_ASSETS, WelcomeShapeField } from "@/components/WelcomeShapeField";
import { getMe, kakaoLoginUrl } from "@/lib/api";

/**
 * 웰컴 스크린 (`/login`) — Figma "00 · 온보딩"의 웰컴 3화면을 순서대로 보여준다.
 *
 *   1. `268:5950` 로고         — HEUN JEOG 마크
 *   2. `268:5968` 카피         — "치열했던 오늘 하루, 어떤 흔적을 남기셨나요?"
 *   3. `268:5984` 흔적 격자     — 조각 밭 + 4/365 + 로그인 버튼
 *
 * **9/18 — 1·2번이 빠져 있었다.** 그전엔 3번만 구현돼 있어서 앱을 열면 곧바로 로그인
 * 화면이 떴다. 사용자가 "1, 2번째가 너무 빨리 지나가서 못 본다"고 해서 확인했더니
 * 지나간 게 아니라 아예 없었던 것이다. 세 장을 자동으로 넘기는 인트로로 만들었다.
 *
 * **넘김 규칙**: 로고 1.4초 → 카피 3.2초 → 마지막 장에서 멈춘다(여기에만 버튼이 있다).
 * 카피는 두 줄짜리 헤드라인 + 두 줄 부연이라 읽을 시간이 필요해서 더 길다.
 * **아무 데나 누르면 즉시 다음 장으로** 넘어간다 — 자동 넘김만 있으면 급한 사람이
 * 기다려야 하고(WCAG 2.2.1 "시간 제한" 문제), 반대로 넘김이 없으면 이번 지적처럼
 * 못 보고 지나간다. 마지막 장에서는 탭을 먹지 않는다 — 로그인 버튼을 가로채면 안 된다.
 *
 * **9/19 — 인트로는 로그인 여부와 무관하게 돈다.** 그전엔 로그인돼 있으면 1·2번이
 * 통째로 안 보이고 빈 배경만 지나갔다(`<AuthGate />`가 `/`로 돌려보내는 동안 인트로를
 * 안 그렸다). 앱의 스플래시처럼 누구에게나 보여야 하는 화면이라, 이제 두 장을 다
 * 재생하고 **마지막 장 직전에** 갈림길이 생긴다 — 로그아웃이면 3번(로그인 버튼),
 * 로그인 상태면 곧장 `/`로 보낸다. 로그인한 사람에게 로그인 버튼을 보여줄 이유는 없다.
 *
 * 그래서 `<AuthGate />`의 "로그인 상태로 /login에 오면 /로" 규칙도 뺐다 — 인트로가
 * 도는 도중에 화면을 낚아채면 안 되고, 나가는 판단은 이 화면이 직접 한다.
 *
 * 카카오 로그인 시작은 반드시 실제 `<a>` 네비게이션이어야 한다(fetch가 아니라) —
 * 브라우저가 카카오 로그인/동의 화면으로 이어지는 리다이렉트 체인을 직접 타야 하기 때문.
 */


const WELCOME_ASSETS = ["/welcome/logo-mark.svg", ...INTRO_SHARD_ASSETS, ...FIELD_ASSETS];

/** 각 장이 머무는 시간(ms). 마지막 장은 넘어가지 않는다. */
const STAGE_DURATIONS = [1400, 3200];
const LAST_STAGE = 2;

export default function LoginPage() {
  // 렌더 중에 부르는 게 React가 문서화한 사용법이다 — <link rel="preload">로 끌어올려진다.
  WELCOME_ASSETS.forEach((href) => preload(href, { as: "image" }));

  const router = useRouter();
  const [stage, setStage] = useState(0);
  /**
   * 로그인 여부 (`null`이면 아직 확인 중).
   *
   * 인트로를 그릴지 말지가 아니라 **인트로가 끝난 뒤 어디로 갈지**를 정하는 값이다.
   * 확인이 늦어져도 1·2번은 그대로 돌아간다 — 마지막 장으로 넘어가는 지점에서만
   * 이 값을 기다린다(아래 넘김 effect).
   */
  const [loggedOut, setLoggedOut] = useState<boolean | null>(null);

  // 이 화면이 인트로를 재생했으니 스플래시(`<AppIntro />`)는 이번 세션에 다시 돌
  // 필요가 없다 — 로그인 직후 홈으로 넘어가면서 같은 장면을 또 보게 된다.
  useEffect(() => {
    markIntroSeen();
  }, []);

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((me) => {
        if (!cancelled) setLoggedOut(me === null);
      })
      .catch(() => {
        // 판단이 안 되면 인트로를 보여주는 쪽으로 — 로그인 화면이 기본 상태다.
        if (!cancelled) setLoggedOut(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /** 마지막 장(로그인 버튼) 바로 앞인가 — 여기서 로그인 상태에 따라 길이 갈린다. */
  const atLastIntroStage = stage === LAST_STAGE - 1;

  useEffect(() => {
    if (stage >= LAST_STAGE) return;
    // 마지막 장으로 넘어가려는데 아직 로그인 여부를 모르면 기다린다 — 그 사이 화면은
    // 카피 장에 머문다. 값이 정해지면 이 effect가 다시 돌면서 이어서 넘어간다.
    if (atLastIntroStage && loggedOut === null) return;

    const timer = setTimeout(() => {
      // 이미 로그인한 사람에게 로그인 버튼을 보여줄 이유가 없다 — 인트로만 보여주고
      // 홈으로 보낸다(`replace`라 뒤로가기로 인트로에 다시 갇히지 않는다).
      if (atLastIntroStage && loggedOut === false) {
        router.replace("/");
        return;
      }
      setStage((s) => s + 1);
    }, STAGE_DURATIONS[stage]);
    return () => clearTimeout(timer);
  }, [stage, atLastIntroStage, loggedOut, router]);

  const advance = () => {
    if (stage >= LAST_STAGE) return;
    if (atLastIntroStage && loggedOut === false) {
      router.replace("/");
      return;
    }
    // 아직 확인 중이면 탭을 먹지 않는다 — 로그인한 사람에게 버튼이 번쩍이면 안 된다.
    if (atLastIntroStage && loggedOut === null) return;
    setStage((s) => s + 1);
  };

  return (
    <div
      onClick={advance}
      className="-mb-6 flex min-h-[100svh] flex-col bg-[#1a1917] text-[#fafafa]"
    >
      {/* 높이 두 가지를 같이 고친다 (9/18 — "버튼이 먼저 보이고 밑으로 간다"):
          1. `dvh` → `svh`. dvh는 모바일 주소창이 접히면 값이 커지는 단위라, 그때마다
             이 컨테이너가 늘어나고 아래 `flex-1` 스페이서가 같이 늘어나 버튼이 내려간다.
             svh는 "주소창이 보이는 상태의 높이"로 고정이라 흔들리지 않는다.
          2. `-mb-6`으로 레이아웃(`app/layout.tsx`의 `main`)이 주는 pb-6(24px)을 상쇄.
             그게 남아 있으면 문서가 뷰포트보다 정확히 24px 길어져(실측 755 vs 731)
             스크롤이 생기고, 그 스크롤이 위 1번의 주소창 접힘을 유발한다. */}
      {/* key로 장이 바뀔 때마다 페이드가 다시 돈다. 모션을 줄이는 설정이면
          globals.css가 애니메이션을 끈다. */}
      <div key={stage} className="welcome-fade flex flex-1 flex-col">
        {stage === 0 && <LogoStage />}
        {stage === 1 && <CopyStage />}
        {stage === LAST_STAGE && <SignInStage />}
      </div>
    </div>
  );
}

/**
 * 3. 흔적 격자 + 로그인 (Figma 268:5984).
 *
 * **구현 노트**: Figma 원문 footer는 "작성하신 소중한 기록은 이 기기 안에만 안전하게
 * 보관돼요."인데, 이 서비스는 로컬전용저장이 아니라 카카오 로그인 + 서버(SQLite)
 * 저장이라 사실과 다르다 — 실제 아키텍처에 맞는 문구로 바꿨다(CLAUDE.md 2.2).
 *
 * "4 / 365"의 숫자는 로그인 전이라 실제 유저 데이터가 없다. Figma 목업 값을 그대로
 * 둔다 — 유저의 기록이라고 주장하는 자리가 아니라 "1년 중 기억나는 날이 이만큼밖에
 * 안 된다"를 보여주는 일러스트레이션이다.
 */
function SignInStage() {
  return (
    <>
      {/* 도형 밭 — 아래쪽은 배경색으로 잠기게 덮는다 (Figma 268:6012 페이드). */}
      <div className="relative pt-6">
        <WelcomeShapeField className="w-full" />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-[45%] bg-gradient-to-b from-transparent via-[#1a1917]/85 to-[#1a1917]"
        />
      </div>

      {/* `relative`가 필요하다 — 위 페이드가 absolute라서, 그냥 흐름 요소로 두면
          음수 마진으로 겹친 이 블록이 페이드에 가려진다(실제로 "4"가 잘렸다). */}
      <div className="relative -mt-10 px-5">
        <div className="flex items-baseline gap-2">
          <p className="text-[52px] font-bold leading-none tracking-[-1.5px] text-accent">4</p>
          <p className="text-[28px] font-medium tracking-[-0.5px] text-[#fafafa]">/ 365</p>
        </div>
        <p className="mt-3 text-[14px] text-[rgba(250,250,250,0.7)]">
          우리의 기억은 생각보다 쉽게 흐려져요
        </p>
      </div>

      <div className="flex-1" />

      <div className="px-5 pb-[26px]">
        <a
          href={kakaoLoginUrl()}
          className="flex h-[50px] w-full items-center justify-center rounded-[8px] bg-accent text-[16px] font-bold tracking-[-0.16px] text-accent-foreground transition-colors hover:bg-[#ff7a2e] active:scale-[0.98]"
        >
          오늘부터 기록하기
        </a>
        <p className="mt-3 text-center text-[12px] leading-[20px] text-[rgba(250,250,250,0.8)]">
          카카오 로그인으로 안전하게 보관돼요
        </p>
      </div>
    </>
  );
}
