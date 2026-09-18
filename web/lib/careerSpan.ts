import { Company } from "./api";

/**
 * 총 경력 계산 — 온보딩 3/4 화면이 타이핑 중에 즉시 보여주는 "6년 3개월"용 (9/18 신규).
 *
 * **서버의 `src/career_span.py`와 같은 규칙이어야 한다.** 화면에 보이는 숫자와
 * 저장되는 연차 구간이 갈라지면 유저가 "내가 본 값과 다르게 저장됐다"를 겪는다.
 * 저장되는 값의 근거는 언제나 서버 계산이고, 여기는 그걸 미리 보여줄 뿐이다.
 * 규칙이 바뀌면 **양쪽을 같이** 고칠 것.
 *
 * 핵심 규칙 두 개:
 *   - 겹치는 기간은 한 번만 센다. 그냥 더하면 실제보다 긴 경력이 나오는데,
 *     경력기술서는 면접에서 검증당하는 문서라 부풀려진 숫자가 나가면 안 된다(2.2).
 *   - 시작월과 종료월을 둘 다 포함해서 센다("2024.03 ~ 2024.03"은 1개월).
 */

/** "2024-03" / "2024.03" -> 절대 월 번호. 형식이 아니면 null. */
function toMonthIndex(yearMonth: string): number | null {
  const parts = yearMonth.trim().replace(/\./g, "-").split("-");
  if (parts.length < 2) return null;
  const year = Number(parts[0]);
  const month = Number(parts[1]);
  if (!Number.isInteger(year) || !Number.isInteger(month)) return null;
  if (month < 1 || month > 12 || year < 1900 || year > 2999) return null;
  return year * 12 + (month - 1);
}

export function totalMonths(companies: Company[]): number {
  const now = new Date();
  const current = now.getFullYear() * 12 + now.getMonth();

  const spans: [number, number][] = [];
  for (const company of companies) {
    const start = toMonthIndex(company.started_at);
    if (start === null) continue;
    const end = company.ended_at ? toMonthIndex(company.ended_at) : current;
    if (end === null || end < start) continue;
    spans.push([start, end]);
  }
  if (spans.length === 0) return 0;

  spans.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [spans[0]];
  for (const [start, end] of spans.slice(1)) {
    const last = merged[merged.length - 1];
    // 3월 퇴사 → 4월 입사는 공백 없이 이어진 경력으로 본다.
    if (start <= last[1] + 1) last[1] = Math.max(last[1], end);
    else merged.push([start, end]);
  }

  return merged.reduce((sum, [start, end]) => sum + (end - start + 1), 0);
}

/** "6년 3개월" (Figma 268:5769). */
export function formatSpan(months: number): string {
  if (months <= 0) return "0개월";
  const years = Math.floor(months / 12);
  const rest = months % 12;
  if (years === 0) return `${rest}개월`;
  if (rest === 0) return `${years}년`;
  return `${years}년 ${rest}개월`;
}
