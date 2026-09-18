"use client";

import Image from "next/image";
import { preload } from "react-dom";
import { CSSProperties, useEffect, useState } from "react";
import { FIELD_ASSETS, WelcomeShapeField } from "@/components/WelcomeShapeField";
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

/**
 * 인트로가 쓰는 파일 전부 (19개). 1번 화면이 떠 있는 동안 미리 받아둔다.
 *
 * **왜**: 그러지 않으면 장이 바뀌는 순간에 그 장의 파일이 처음 요청된다 — 2번은
 * 조각 6개, 3번은 13개가 한꺼번에. 애니메이션이 시작되는 바로 그 프레임에 다운로드가
 * 겹쳐서 조각이 뒤늦게 채워지고, 전환이 끊겨 보인다(9/18 실측으로 확인).
 * 1번 화면은 1.4초 동안 로고만 보여주므로 그 시간에 다 받아둘 수 있다.
 */
const INTRO_SHARD_ASSETS = [
  "/welcome/intro-top-1.svg",
  "/welcome/intro-top-2.svg",
  "/welcome/intro-top-3.svg",
  "/welcome/intro-bottom-1.svg",
  "/welcome/intro-bottom-2.svg",
  "/welcome/intro-bottom-3.svg",
];

const WELCOME_ASSETS = ["/welcome/logo-mark.svg", ...INTRO_SHARD_ASSETS, ...FIELD_ASSETS];

/** 각 장이 머무는 시간(ms). 마지막 장은 넘어가지 않는다. */
const STAGE_DURATIONS = [1400, 3200];
const LAST_STAGE = 2;

export default function LoginPage() {
  // 렌더 중에 부르는 게 React가 문서화한 사용법이다 — <link rel="preload">로 끌어올려진다.
  WELCOME_ASSETS.forEach((href) => preload(href, { as: "image" }));

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

/**
 * 조각 하나가 "로고가 있던 자리"에서 출발해 제자리로 날아오는 값.
 *
 * 조각 파일(`intro-top-1..3`, `intro-bottom-1..3`)은 Figma가 내보낸 그룹 SVG
 * (`268:5972` / `268:5979`)를 요소별로 쪼갠 것이다 — 경로 데이터는 손대지 않았고
 * viewBox도 원본과 같아서, 여섯 장을 같은 자리에 겹쳐 놓으면 원본 그룹과 동일하다.
 * 각 레이어는 자기 조각 자리에만 그림이 있으므로 레이어를 옮기면 그 조각만 움직인다. 그래서 레이어를 통째로 옮기면
 * 그 조각만 움직인다. `dx/dy`는 **로고 중심 방향**, 즉 위쪽 조각은 아래에서,
 * 아래쪽 조각은 위에서 올라오도록 잡았다. 좌우 값은 조각이 놓인 쪽의 반대다.
 */
const TOP_SHARDS = [
  { src: "/welcome/intro-top-1.svg", dx: "86px", dy: "132px", r: "-34deg", d: "0ms" },
  { src: "/welcome/intro-top-2.svg", dx: "-96px", dy: "124px", r: "28deg", d: "70ms" },
  { src: "/welcome/intro-top-3.svg", dx: "-6px", dy: "140px", r: "46deg", d: "40ms" },
];

const BOTTOM_SHARDS = [
  { src: "/welcome/intro-bottom-1.svg", dx: "58px", dy: "-128px", r: "38deg", d: "100ms" },
  { src: "/welcome/intro-bottom-2.svg", dx: "-52px", dy: "-136px", r: "-30deg", d: "60ms" },
  { src: "/welcome/intro-bottom-3.svg", dx: "2px", dy: "-142px", r: "-44deg", d: "130ms" },
];

function ShardLayers({ shards }: { shards: typeof TOP_SHARDS }) {
  return (
    <>
      {shards.map((shard) => (
        <div
          key={shard.src}
          className="welcome-shard absolute inset-0"
          style={
            { "--dx": shard.dx, "--dy": shard.dy, "--r": shard.r, "--d": shard.d } as CSSProperties
          }
        >
          {/* lazy면 이 장이 뜨는 순간 요청이 나가서 비행 중에 뒤늦게 채워진다. */}
          <Image src={shard.src} alt="" fill priority className="object-contain" />
        </div>
      ))}
    </>
  );
}

/**
 * 2. 카피 (Figma 268:5968) — 위아래 조각 사이에 문장.
 *
 * 1번에서 넘어올 때 **로고가 깨지며 이 조각들로 흩어지는** 전환을 탄다(9/18 사용자 요청).
 * 로고 마크는 단일 path라 실제로 쪼갤 수는 없어서, 조각 6개가 로고 자리에서 튀어나오는
 * 동시에 로고가 커지며 사라지게 했다 — 겹쳐 보면 파편이 날아가는 것으로 읽힌다.
 *
 * 2번은 1번에서만 올 수 있어서(뒤로 가는 길이 없다) 전환 분기가 따로 필요 없다.
 * 모션을 줄이는 설정에서는 globals.css가 애니메이션을 끄는데, 그러면 조각이 처음부터
 * 제자리에 놓여서 원본 그룹과 똑같이 보인다 — 별도 처리가 필요 없다.
 */
function CopyStage() {
  const [logoGone, setLogoGone] = useState(false);

  return (
    <div className="relative flex flex-1 flex-col items-center justify-center gap-5 px-5 text-center">
      <div className="relative aspect-[324.038/112.743] w-full max-w-[324px]">
        <ShardLayers shards={TOP_SHARDS} />
      </div>

      <div className="welcome-copy-in flex w-full flex-col gap-[22px]">
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
        <ShardLayers shards={BOTTOM_SHARDS} />
      </div>

      {/* 부서지는 로고 — 애니메이션이 끝나면 DOM에서 뺀다. 1번 화면과 같은 자리
          (화면 정중앙)에 겹쳐 놓아야 "그 로고가 부서진 것"으로 보인다. */}
      {!logoGone && (
        <div
          aria-hidden
          onAnimationEnd={() => setLogoGone(true)}
          className="welcome-logo-burst pointer-events-none absolute left-1/2 top-1/2 size-[239px] -translate-x-1/2 -translate-y-1/2"
        >
          <Image src="/welcome/logo-mark.svg" alt="" fill priority className="object-contain" />
        </div>
      )}
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
