"use client";

import Image from "next/image";
import { CSSProperties, useState } from "react";

/**
 * 웰컴 인트로의 1·2번 장 (Figma "00 · 온보딩" `268:5950` / `268:5968`).
 *
 * **왜 별도 파일인가 (9/19)**: 이 두 장은 두 곳에서 쓴다 —
 *   - `app/login/page.tsx`: 로그인 화면의 1·2번 장(그 뒤 3번 로그인 버튼으로 이어진다)
 *   - `components/AppIntro.tsx`: **앱을 열 때마다** 뜨는 스플래시
 * 한쪽만 고쳐져서 두 인트로가 달라지는 걸 막으려고 마크업을 여기로 모았다.
 */

/**
 * 인트로가 쓰는 파일 전부 (19개). 1번 화면이 떠 있는 동안 미리 받아둔다.
 *
 * **왜**: 그러지 않으면 장이 바뀌는 순간에 그 장의 파일이 처음 요청된다 — 2번은
 * 조각 6개, 3번은 13개가 한꺼번에. 애니메이션이 시작되는 바로 그 프레임에 다운로드가
 * 겹쳐서 조각이 뒤늦게 채워지고, 전환이 끊겨 보인다(9/18 실측으로 확인).
 * 1번 화면은 1.4초 동안 로고만 보여주므로 그 시간에 다 받아둘 수 있다.
 */
/** 로고 마크 — 1번 장과 2번 장의 "부서지는 로고"가 같이 쓴다. */
export const LOGO_ASSET = "/welcome/logo-mark.svg";

export const INTRO_SHARD_ASSETS = [
  "/welcome/intro-top-1.svg",
  "/welcome/intro-top-2.svg",
  "/welcome/intro-top-3.svg",
  "/welcome/intro-bottom-1.svg",
  "/welcome/intro-bottom-2.svg",
  "/welcome/intro-bottom-3.svg",
];

/** 1. 로고 (Figma 268:5950) — 화면 정중앙. */
export function LogoStage() {
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
export function CopyStage() {
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
