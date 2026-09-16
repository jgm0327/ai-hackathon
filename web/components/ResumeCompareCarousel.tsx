"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { EnhancedItem } from "@/lib/api";

/**
 * "기존 경력기술서 붙여넣기 → Before·After 대조" (9/15 신규, Figma `90:640`).
 *
 * 유저가 이미 써둔 문장을 하나씩 캐러셀로 보여주고 "그대로 두기"/"적용"을 고르게
 * 한다. 관련 기록이 없는 항목은 대조할 게 없으므로 안내만 보여주고 "적용"은
 * 비활성화한다 — 근거 없이 보강된 것처럼 보이는 문장을 적용시키지 않는다
 * (CLAUDE.md 2.2). 마지막 항목까지 끝나면 각 항목의 최종 텍스트(적용 시 enhanced,
 * 그대로 두기 시 original)를 `onFinish`로 부모에 전달한다 — 여기서 서버에 저장하지
 * 않는다(CLAUDE.md 3장). `/resume/page.tsx`가 그 결과를 자유 텍스트 초안에 합친다.
 */
export function ResumeCompareCarousel({
  items,
  onFinish,
  onCancel,
}: {
  items: EnhancedItem[];
  onFinish: (finalTexts: string[]) => void;
  onCancel: () => void;
}) {
  const router = useRouter();
  const [index, setIndex] = useState(0);
  const [chosen, setChosen] = useState<string[]>([]);

  const item = items[index];
  const isLast = index === items.length - 1;
  const hasEvidence = item.source_card_ids.length > 0;

  const advance = (finalText: string) => {
    const next = [...chosen, finalText];
    if (isLast) {
      onFinish(next);
    } else {
      setChosen(next);
      setIndex((i) => i + 1);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e] p-4">
      <div className="flex items-center justify-between">
        <button type="button" onClick={onCancel} aria-label="뒤로" className="text-[17px] text-[#f2f2f2]">
          ←
        </button>
        <p className="text-sm font-semibold text-[#f2f2f2]">보강 결과</p>
        {items.length > 1 ? (
          <p className="w-[40px] text-right text-xs text-[#828282]">
            {index + 1} / {items.length}
          </p>
        ) : (
          <div className="w-[17px]" />
        )}
      </div>

      <div className="flex flex-col gap-1.5 rounded-xl bg-[#181818] p-3">
        <p className="text-[11px] font-medium text-[#a0a0a0]">기존</p>
        <p className="text-[13px] leading-relaxed text-[#a0a0a0]">{item.original}</p>
      </div>

      {hasEvidence ? (
        <>
          <p className="text-center text-xs text-[#828282]">
            ↓ 기록 {item.source_card_ids.length}건으로 보강
          </p>

          <div className="flex flex-col gap-1.5 rounded-xl border border-[#f2f2f2] bg-[#141414] p-3">
            <p className="text-[11px] font-medium text-[#a0a0a0]">보강</p>
            <p className="text-[13px] leading-relaxed text-[#f2f2f2]">{item.enhanced}</p>
            <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
              <span className="text-[11px] font-medium text-[#828282]">근거</span>
              {item.source_dates.map((date, i) => {
                // source_dates/source_card_ids는 백엔드가 같은 검증된 카드에서 같이
                // 계산해서 인덱스가 항상 맞물린다(StarItemCard.tsx와 동일한 패턴).
                const cardId = item.source_card_ids[i];
                return (
                  <button
                    key={cardId ?? `${date}-${i}`}
                    type="button"
                    disabled={cardId == null}
                    onClick={() => cardId != null && router.push(`/stack?cardId=${cardId}`)}
                    className="rounded-full bg-[#242424] px-2 py-0.5 text-xs text-[#a0a0a0] transition-colors hover:bg-[#2e2e2e] disabled:cursor-default"
                  >
                    {date}
                  </button>
                );
              })}
            </div>
          </div>

          {item.gap_comment && (
            <div className="flex gap-2 rounded-xl bg-[#181818] p-3">
              <span aria-hidden className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#f2f2f2]" />
              <p className="flex-1 text-[12px] leading-relaxed text-[#a0a0a0]">{item.gap_comment}</p>
            </div>
          )}
        </>
      ) : (
        <p className="px-1 py-2 text-center text-xs text-[#828282]">
          아직 관련된 기록을 찾지 못했어요. 원문 그대로 둘게요.
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => advance(item.original)}
          className="flex-1 rounded-[11px] border-[1.5px] border-[#2e2e2e] bg-[#1c1c1c] py-[13px] text-[12px] font-semibold text-[#f2f2f2] transition-colors hover:bg-[#242424]"
        >
          그대로 두기
        </button>
        <button
          type="button"
          onClick={() => advance(item.enhanced)}
          disabled={!hasEvidence}
          className="flex-1 rounded-[11px] bg-[#f2f2f2] py-[13px] text-[12px] font-semibold text-[#171717] transition-colors hover:bg-white disabled:opacity-40"
        >
          적용
        </button>
      </div>

      {items.length > 1 && (
        <div className="flex justify-center gap-1.5">
          {items.map((_, i) => (
            <span
              key={i}
              className={`h-1.5 w-1.5 rounded-full ${i === index ? "bg-[#f2f2f2]" : "bg-[#3a3a3a]"}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}
