"use client";

import { useState } from "react";
import { StarItem } from "@/lib/api";

export function formatStarItemForClipboard(item: StarItem): string {
  const lines = [
    `${item.title} (${item.period})`,
    `- 상황: ${item.situation}`,
    `- 과제: ${item.task}`,
    `- 행동: ${item.action}`,
  ];
  // result가 빈 문자열이면 줄 자체를 넣지 않는다 — "결과 없음"을 복사물에도 남기지 않는다.
  if (item.result) lines.push(`- 결과: ${item.result}`);
  return lines.join("\n");
}

/**
 * STAR 항목 한 건 (`/resume`). Figma "4.2 경력기술서 빌더"는 항목별 카드가 아니라
 * 하나의 연속된 문서(제목+기간 헤더 → 상황/과제/행동/결과 라벨 행)로 렌더링한다 —
 * 항목 사이 구분은 부모(`app/resume/page.tsx`)가 얇은 구분선으로 넣는다.
 *
 * `result`가 빈 문자열일 수 있다 — 기록에 숫자가 없으면 AI가 지어내지 않고
 * 비워서 반환하기 때문 (CLAUDE.md 2.2). "결과 없음"을 렌더링하지 않고,
 * 대신 되묻기 칩을 보여준다.
 */
export function StarItemSection({ item }: { item: StarItem }) {
  const [showSources, setShowSources] = useState(false);

  const rows: Array<{ label: string; value: string }> = [
    { label: "상황", value: item.situation },
    { label: "과제", value: item.task },
    { label: "행동", value: item.action },
  ];

  return (
    <div className="flex flex-col gap-2.5 py-4">
      <div className="flex items-center gap-2">
        <p className="text-[14px] font-bold text-[#18181b]">{item.title}</p>
        <div className="flex-1" />
        <p className="text-right text-[10px] text-[#a1a1aa]">{item.period}</p>
      </div>

      <div className="flex flex-col gap-2">
        {rows.map((row) => (
          <div key={row.label} className="flex gap-[10px]">
            <div className="w-[30px] shrink-0">
              <p className="text-[11px] font-semibold text-black">{row.label}</p>
            </div>
            <p className="flex-1 text-[12px] leading-relaxed text-[#18181b]">{row.value}</p>
          </div>
        ))}

        <div className="flex gap-[10px]">
          <div className="w-[30px] shrink-0">
            <p className="text-[11px] font-semibold text-black">결과</p>
          </div>
          <div className="flex flex-1 flex-col gap-1.5">
            {item.result ? (
              <p className="text-[12px] leading-relaxed text-[#18181b]">{item.result}</p>
            ) : (
              <button
                type="button"
                title="기록에 숫자가 없어 비워두었습니다. 기억나신다면 입력 화면에서 새 메모로 남겨보세요."
                className="w-fit rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-700"
              >
                숫자를 기억하시나요? (건너뛰기)
              </button>
            )}

            {item.source_dates.length > 0 && (
              <div>
                <button
                  type="button"
                  onClick={() => setShowSources((v) => !v)}
                  className="text-[11px] font-medium text-[#a1a1aa] underline underline-offset-2"
                >
                  이 문장의 근거 {showSources ? "숨기기" : "보기"}
                </button>
                {showSources && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {item.source_dates.map((date) => (
                      <span
                        key={date}
                        className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500"
                      >
                        {date}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
