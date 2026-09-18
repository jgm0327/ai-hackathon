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
 */

interface Shape {
  /** public/welcome 아래 파일명 */
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

const SHAPES: Shape[] = [
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

const SLABS: Shape[] = [
  shape("", 21, 463, 64.313, 55.499, 71.028, 14.779, 142.87, true),
  shape("", 154.75, 128.34, 64.313, 55.499, 71.028, 14.779, 37.13),
  shape("", 154.75, 385.79, 64.313, 55.499, 71.028, 14.779, 37.13),
  shape("", 161.66, 298.49, 50.497, 71.258, 73.825, 14.221, 57.84),
  shape("", 18.73, 223.12, 64.313, 55.499, 71.028, 14.779, 142.87, true),
];

function transformOf({ cx, cy, rotate, flipY }: Shape): string {
  const flip = flipY ? ` scale(1 -1)` : "";
  // 회전/뒤집기는 조각의 제자리(중심)를 기준으로 한다.
  return `translate(${cx} ${cy}) rotate(${rotate})${flip} translate(${-cx} ${-cy})`;
}

export function WelcomeShapeField({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 120 390 430"
      className={className}
      aria-hidden
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      {SLABS.map((s, i) => (
        <rect
          key={`slab-${i}`}
          x={s.cx - s.w / 2}
          y={s.cy - s.h / 2}
          width={s.w}
          height={s.h}
          fill={SLAB_COLOR}
          transform={transformOf(s)}
        />
      ))}
      {SHAPES.map((s, i) => (
        <image
          key={`shape-${i}`}
          href={`/welcome/${s.src}`}
          x={s.cx - s.w / 2}
          y={s.cy - s.h / 2}
          width={s.w}
          height={s.h}
          transform={transformOf(s)}
        />
      ))}
    </svg>
  );
}
