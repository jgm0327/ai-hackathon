"use client";

import { CSSProperties, useEffect, useState } from "react";

/**
 * 웰컴 스크린의 "흔적" 도형 밭 (Figma `268:5984` "1.0 웰컴 스크린 · 흔적 격자 (다크)").
 *
 * 9/18 이전엔 이 자리에 작은 점 365개 격자가 있었다(예전 캔버스 100:692 버전).
 * 새 Figma는 크고 불규칙한 조각들이 흩어진 화면이라 형태가 완전히 다르다.
 *
 * **왜 SVG `<image>`로 배치하는가**: 조각 모양은 손으로 그릴 수 없는 벡터라 Figma에서
 * 내보낸 파일(`public/welcome/*.svg`, 13종)을 그대로 쓴다. 그걸 `viewBox`가 있는 SVG
 * 안에 Figma 좌표 그대로 놓으면, 컨테이너 폭이 얼마든(360px 폰이든 448px 데스크톱이든)
 * 전체가 한 덩어리로 정확히 비율을 지키며 늘었다 줄었다 한다 — div를 절대 위치로
 * 깔면 회전한 조각의 바운딩 박스까지 일일이 스케일해야 해서 틀어지기 쉽다.
 *
 * 좌표는 390×844 목업 기준이고, 도형이 차지하는 구간(y 127~540)만 잘라서 쓴다.
 *
 * Figma의 transform에는 회전과 함께 아주 작은 skew(최대 6도)가 섞여 있는데, 이건
 * Figma가 변환을 분해하면서 생긴 값이고 추상적인 조각 모양이라 눈에 띄지 않아서
 * 회전과 뒤집기만 재현한다.
 *
 * **모션 (9/18 사용자 요청)**: 조각이 한꺼번에 나타나지 않고 **무작위 순서로 3개씩**
 * 드러나고, 나온 뒤에는 **구름처럼 계속 둥실거린다.**
 *   - 드러나는 순서만 무작위이고 **그리는 순서(DOM 순서)는 고정**이다 — 겹침 순서가
 *     매번 바뀌면 화면이 달라 보인다. 순서는 `--in-delay`로만 조절한다.
 *   - 무작위 값은 마운트 후에 만든다. 렌더 중에 `Math.random()`을 쓰면 서버가 그린
 *     HTML과 클라이언트가 그린 것이 달라져 하이드레이션이 깨진다. 그래서 값이 준비되기
 *     전에는 아무것도 그리지 않는다 — 어차피 조각은 처음에 투명한 상태로 시작하므로
 *     화면에 보이는 차이가 없고, 이 밭은 장식(`aria-hidden`)이라 SSR에 없어도 무해하다.
 *   - 모션을 줄이는 설정에서는 `globals.css`가 두 애니메이션을 모두 끈다. 그러면 조각이
 *     처음부터 제자리에 선명하게 놓여서 9/18 이전과 똑같이 보인다.
 */

interface Shape {
  /** public/welcome 아래 파일명. 빈 문자열이면 단색 막대(`<rect>`)다. */
  src: string;
  /** 회전 전 중심 좌표 (목업 기준) */
  cx: number;
  cy: number;
  /** 회전 전 크기 */
  w: number;
  h: number;
  rotate: number;
  /** 세로 뒤집기 */
  flipY?: boolean;
}

/** Figma 프레임의 각 조각: 바깥 상자 중심 = 회전 전 사각형의 중심. */
function shape(
  src: string,
  boxLeft: number,
  boxTop: number,
  boxW: number,
  boxH: number,
  w: number,
  h: number,
  rotate: number,
  flipY = false,
): Shape {
  return { src, cx: boxLeft + boxW / 2, cy: boxTop + boxH / 2, w, h, rotate, flipY };
}

/** 회색 막대 조각들 — 단색 사각형이라 에셋 없이 `<rect>`로 그린다 (Figma `#717171`). */
const SLAB_COLOR = "#717171";

/** 그리는 순서 = 겹침 순서. 막대가 먼저(뒤에), 조각 에셋이 나중(앞에) 온다. */
const FIELD: Shape[] = [
  shape("", 21, 463, 64.313, 55.499, 71.028, 14.779, 142.87, true),
  shape("", 154.75, 128.34, 64.313, 55.499, 71.028, 14.779, 37.13),
  shape("", 154.75, 385.79, 64.313, 55.499, 71.028, 14.779, 37.13),
  shape("", 161.66, 298.49, 50.497, 71.258, 73.825, 14.221, 57.84),
  shape("", 18.73, 223.12, 64.313, 55.499, 71.028, 14.779, 142.87, true),
  shape("shard-a.svg", 307.02, 441, 73.912, 91.83, 74.729, 47.045, 62.63),
  shape("shard-b.svg", 14.14, 136.41, 69.742, 52.677, 68.718, 50.933, -1.46),
  shape("shard-c.svg", 86.5, 457.53, 82.36, 82.543, 70.796, 49.66, 32.95),
  shape("shard-d.svg", 14.14, 393.86, 69.742, 52.677, 68.718, 50.933, -1.46),
  shape("shard-e.svg", 292.09, 127, 79.22, 71.5, 69.457, 50.488, 19.24),
  shape("shard-f.svg", 292.09, 384.45, 79.22, 71.5, 69.457, 50.488, 19.24),
  shape("blob-a.svg", 227.77, 454.09, 83.577, 86.661, 79.734, 41.318, -41.75),
  shape("shard-g.svg", 216.93, 298.41, 82.773, 80.479, 69.457, 50.488, 30.84),
  shape("shard-a.svg", 307.02, 193.38, 73.912, 91.83, 74.729, 47.045, 62.63),
  shape("shard-c.svg", 86.5, 209.91, 82.36, 82.543, 70.796, 49.66, 32.95),
  shape("blob-b.svg", 87.54, 149.05, 81.339, 55.916, 76.425, 42.889, -10.15),
  shape("blob-b.svg", 87.54, 406.5, 81.339, 55.916, 76.425, 42.889, -10.15),
  shape("blob-a.svg", 227.77, 206.47, 83.577, 86.661, 79.734, 41.318, -41.75),
  shape("blob-c.svg", 9.55, 292.28, 83.577, 86.661, 79.734, 41.318, -138.25, true),
  shape("shard-h.svg", 169.19, 465.62, 64.649, 60.694, 60.549, 54.837, 174.28, true),
  shape("shard-i.svg", 216.95, 128.34, 64.649, 60.694, 60.549, 54.837, 5.72),
  shape("shard-j.svg", 219.06, 385.79, 64.649, 60.694, 60.549, 54.837, 5.72),
  shape("shard-j.svg", 311.1, 304.76, 64.649, 60.694, 60.549, 54.837, 5.72),
  shape("shard-h.svg", 169.19, 218, 64.649, 60.694, 60.549, 54.837, 174.28, true),
  shape("shard-j.svg", 86.5, 305.09, 64.649, 60.694, 60.549, 54.837, 5.72),
];

/**
 * 이 밭이 쓰는 파일 목록(중복 제거). 웰컴 1번 화면에서 미리 받아두는 데 쓴다 —
 * 그러지 않으면 3번 화면이 뜨는 순간 13개가 동시에 네트워크로 들어와서, 조각이
 * 뒤늦게 뚝뚝 채워진다(9/18 실측: 마운트 시점에 13건 동시 시작).
 */
export const FIELD_ASSETS: string[] = [
  ...new Set(FIELD.filter((s) => s.src).map((s) => `/welcome/${s.src}`)),
];

/** 한 번에 드러나는 조각 수 (사용자 요청: "3개씩"). */
const REVEAL_BATCH = 3;
/** 배치 사이 간격(ms) 범위 — 일정하지 않게 해서 기계적으로 안 보이게 한다. */
const GAP_MIN = 170;
const GAP_MAX = 400;

interface Motion {
  /** 드러나기 시작하는 시각 */
  inDelay: number;
  /** 둥실거림 — 목적지(viewBox 단위), 한 주기 길이, 시작 위상 */
  driftX: number;
  driftY: number;
  driftDuration: number;
  driftDelay: number;
}

function buildMotions(count: number): Motion[] {
  const rand = (min: number, max: number) => min + Math.random() * (max - min);

  // 드러나는 순서만 섞는다(피셔-예이츠). 그리는 순서는 그대로 둔다.
  const order = Array.from({ length: count }, (_, i) => i);
  for (let i = order.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }

  // 배치별 시작 시각을 누적해서 만든다.
  const batchStarts: number[] = [];
  let t = 0;
  for (let b = 0; b * REVEAL_BATCH < count; b++) {
    batchStarts.push(t);
    t += rand(GAP_MIN, GAP_MAX);
  }

  const motions: Motion[] = new Array(count);
  order.forEach((shapeIndex, position) => {
    motions[shapeIndex] = {
      inDelay: batchStarts[Math.floor(position / REVEAL_BATCH)],
      // 구름처럼 — 아주 느리고 폭이 작다. 세로로 더 많이 움직인다.
      driftX: rand(-4, 4),
      driftY: rand(-9, -3),
      driftDuration: rand(4200, 7600),
      // 위상을 흩어야 전체가 같이 오르내리지 않는다.
      driftDelay: -rand(0, 7600),
    };
  });
  return motions;
}

export function WelcomeShapeField({ className }: { className?: string }) {
  const [motions, setMotions] = useState<Motion[] | null>(null);

  useEffect(() => {
    // 마운트 후에 무작위 값을 만든다 — 렌더 중에 만들면 하이드레이션이 깨진다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMotions(buildMotions(FIELD.length));
  }, []);

  return (
    <svg
      viewBox="0 120 390 430"
      className={className}
      aria-hidden
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      {motions &&
        FIELD.map((s, i) => {
          const m = motions[i];
          const style = {
            "--in-delay": `${Math.round(m.inDelay)}ms`,
            "--drift-x": `${m.driftX.toFixed(2)}px`,
            "--drift-y": `${m.driftY.toFixed(2)}px`,
            "--drift-duration": `${Math.round(m.driftDuration)}ms`,
            "--drift-delay": `${Math.round(m.driftDelay)}ms`,
          } as CSSProperties;

          return (
            // 겉의 <g>는 CSS로 움직이고, 안쪽 도형은 Figma 회전을 transform 속성으로
            // 그대로 유지한다 — 한 요소에 둘을 같이 걸면 CSS가 속성을 덮어써서 회전이
            // 날아간다.
            <g key={i} className="welcome-cloud" style={style}>
              {s.src ? (
                <image
                  href={`/welcome/${s.src}`}
                  x={s.cx - s.w / 2}
                  y={s.cy - s.h / 2}
                  width={s.w}
                  height={s.h}
                  transform={transformOf(s)}
                />
              ) : (
                <rect
                  x={s.cx - s.w / 2}
                  y={s.cy - s.h / 2}
                  width={s.w}
                  height={s.h}
                  fill={SLAB_COLOR}
                  transform={transformOf(s)}
                />
              )}
            </g>
          );
        })}
    </svg>
  );
}

function transformOf({ cx, cy, rotate, flipY }: Shape): string {
  const flip = flipY ? ` scale(1 -1)` : "";
  // 회전/뒤집기는 조각의 제자리(중심)를 기준으로 한다.
  return `translate(${cx} ${cy}) rotate(${rotate})${flip} translate(${-cx} ${-cy})`;
}
