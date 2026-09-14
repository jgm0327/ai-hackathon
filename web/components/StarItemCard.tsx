"use client";

import { useRouter } from "next/navigation";
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
 *
 * **구현 노트 (9/14)**: 되묻기 칩을 누르면 숫자를 직접 입력할 자리가 없으므로(여기서
 * 새 폼을 만들면 CLAUDE.md 2.1 정신에 어긋남 — 이 화면은 어쩌다 한 번 오는 이직 준비
 * 경로), 매일 쓰는 입력 화면(`/`)으로 보내서 새 메모로 남기게 한다. 원래는 onClick
 * 없이 title 툴팁 안내만 있었는데, `<button>`인데 눌러도 반응이 없어 혼란을 줄 수
 * 있다는 지적을 받아 실제 이동 동작을 붙였다.
 */
export function StarItemSection({ item }: { item: StarItem }) {
  const router = useRouter();
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
                onClick={() => router.push("/")}
                className="w-fit rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-700 transition-colors hover:bg-amber-100"
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
                    {item.source_dates.map((date, i) => {
                      // source_dates와 source_card_ids는 백엔드가 같은 검증된
                      // 카드 목록에서 같이 계산해서 인덱스가 항상 맞물린다
                      // (docs/05-api-contract.md §3 참고) — 날짜 칩을 누르면
                      // 같은 인덱스의 카드 id로 /stack에서 그 카드를 찾아간다.
                      const cardId = item.source_card_ids[i];
                      return (
                        <button
                          key={cardId ?? `${date}-${i}`}
                          type="button"
                          disabled={cardId == null}
                          onClick={() => cardId != null && router.push(`/stack?cardId=${cardId}`)}
                          className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500 transition-colors hover:bg-zinc-200 disabled:cursor-default disabled:hover:bg-zinc-100"
                        >
                          {date}
                        </button>
                      );
                    })}
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
