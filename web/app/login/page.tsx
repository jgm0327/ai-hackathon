"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { WelcomeShapeField } from "@/components/WelcomeShapeField";
import { kakaoLoginUrl } from "@/lib/api";

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
 * `<AuthGate />`가 로그아웃 상태를 감지하면 이 화면으로 보내고, 로그인된 사용자가
 * 이 주소로 오면 `/`로 돌려보낸다 — **이 화면은 로그아웃 상태에서만 보인다**
 * (시크릿 창으로 확인 가능).
 *
 * 카카오 로그인 시작은 반드시 실제 `<a>` 네비게이션이어야 한다(fetch가 아니라) —
 * 브라우저가 카카오 로그인/동의 화면으로 이어지는 리다이렉트 체인을 직접 타야 하기 때문.
 */

/** 각 장이 머무는 시간(ms). 마지막 장은 넘어가지 않는다. */
const STAGE_DURATIONS = [1400, 3200];
const LAST_STAGE = 2;

export default function LoginPage() {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    if (stage >= LAST_STAGE) return;
    const timer = setTimeout(() => setStage((s) => s + 1), STAGE_DURATIONS[stage]);
    return () => clearTimeout(timer);
  }, [stage]);

  const advance = () => {
    if (stage < LAST_STAGE) setStage((s) => s + 1);
  };

  return (
    <div
      onClick={advance}
      className="flex min-h-[100dvh] flex-col bg-[#1a1917] text-[#fafafa]"
    >
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

/** 1. 로고 (Figma 268:5950) — 화면 정중앙. */
function LogoStage() {
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="relative size-[239px]">
        <Image src="/welcome/logo-mark.svg" alt="" fill priority className="object-contain" />
        {/* 마크 위 글자는 Figma에서도 텍스트다 — 이미지로 굽지 않는다. */}
        <p className="absolute inset-[36.82%_31.38%_29.71%_29.29%] text-[32px] font-bold leading-[40px] tracking-[0.64px] whitespace-nowrap text-[rgba(0,0,0,0.96)]">
          HEUN
          <br />
          JEOG
        </p>
      </div>
      <span className="sr-only">커리어 로그</span>
    </div>
  );
}

/** 2. 카피 (Figma 268:5968) — 위아래 조각 사이에 문장. */
function CopyStage() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-5 px-5 text-center">
      <div className="relative aspect-[324.038/112.743] w-full max-w-[324px]">
        <Image src="/welcome/intro-top.svg" alt="" fill className="object-contain" />
      </div>

      <div className="flex w-full flex-col gap-[22px]">
        <p className="text-[28px] font-bold leading-[36px] tracking-[-0.84px] text-[rgba(226,222,215,0.95)]">
          치열했던 오늘 하루,
          <br />
          어떤 흔적을 남기셨나요?
        </p>
        <p className="text-[12px] font-light leading-[20px] tracking-[-0.12px] text-[rgba(255,255,255,0.64)]">
          거창하지 않아도 괜찮아요. 한 줄의 기록들이 모여
          <br />
          나를 증명하는 가장 확실한 커리어가 됩니다.
        </p>
      </div>

      <div className="relative aspect-[253.962/77.9315] w-full max-w-[254px]">
        <Image src="/welcome/intro-bottom.svg" alt="" fill className="object-contain" />
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
