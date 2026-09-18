/**
 * Figma "03 · 커리어 스택 · Tab B" 섹션(`294:9924`)의 색 토큰 (9/18 신규).
 *
 * 값은 "02 · 변환 결과" 섹션(`components/resultTheme.ts`)과 같은 따뜻한 팔레트다 —
 * 두 섹션이 같은 디자인 언어로 다시 그려졌기 때문. 다만 이 섹션에만 있는 색이
 * 두 개 있어서(강조 숫자 `accentText`, 비중 스트립 단계색) 파일을 따로 뒀다.
 *
 * `resultTheme`과 합치지 않은 이유: 두 섹션이 앞으로 따로 움직일 수 있고, 한쪽
 * 색을 고치려다 다른 화면이 같이 바뀌는 게 이 프로젝트에서 실제로 겪은 문제다
 * (globals.css의 body 규칙 건). 값이 겹치는 건 지금 우연이 아니라 의도지만,
 * 묶어 두면 그 의도가 강제가 된다.
 */
export const stackTheme = {
  /** 화면 배경 */
  screenBg: "#1a1917",
  /** 카드 · 리스트 항목 · 입력창 */
  cardBg: "#2a2724",
  /** 바텀시트 배경 (`bg/sheet`) — 화면 배경보다 아주 약간 밝다. 디자인 시스템
   * 섹션(`299:12554`)이 시트만 이 값으로 따로 정의한다. */
  sheetBg: "#1b1b1b",
  /** 본문 글자 */
  text: "#ede9e2",
  /** 한 단계 낮춘 글자 */
  textSoft: "#bdb7ae",
  /** 라벨 · 보조 설명 */
  textMuted: "#918c84",
  /** 테두리 · 구분선 */
  border: "#34322e",
  /** 강조 숫자("기록 24개", 1위 역량 개수)와 링크성 텍스트. 버튼 배경(#ff5d00)보다
   * 한 단계 밝아서 어두운 배경 위 글자로 읽기 좋다. */
  accentText: "#ff9a3d",
  /** 홈(3.0)만 쓰는 순검정 배경. 크림색 패널과의 대비를 최대로 가져가려는 선택이라
   * 다른 화면의 `screenBg`(#1a1917)와 다르다 — Figma에서도 이 화면만 `bg/black`이다. */
  homeBg: "#000000",
  /** 홈의 밝은 패널 — 누적 요약(light/1)과 최근 기록(light/2), 그 위 글자(on-light)와
   * 구분선(light/rule). 앱 전체에서 유일한 라이트 영역이다. */
  light1: "#ebebeb",
  light2: "#bdb7ae",
  lightRule: "#a19b92",
  onLight: "#331300",
} as const;

/**
 * "비중 스트립" (Figma `294:10281`) 단계색 — 1위부터 5위까지.
 *
 * 색으로 역량을 구분하는 게 아니라 **순위를 밝기로** 보여준다. 그래서 역량 이름이
 * 아니라 순서로만 매핑한다(홈 화면 버블이 같은 규칙을 쓰는 것과 같은 이유 —
 * 색에 의미를 지어내지 않는다). 6위 이하는 마지막 색을 계속 쓴다.
 */
export const STRIP_COLORS = ["#ff9a3d", "#ede9e2", "#bdb7ae", "#918c84", "#34322e"] as const;

export function stripColor(rank: number): string {
  return STRIP_COLORS[Math.min(rank, STRIP_COLORS.length - 1)];
}
