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
 * STAR 항목 카드 (`/resume`).
 *
 * `result`가 빈 문자열일 수 있다 — 기록에 숫자가 없으면 AI가 지어내지 않고
 * 비워서 반환하기 때문 (CLAUDE.md 2.2). "결과 없음"을 렌더링하지 않고,
 * 대신 되묻기 칩을 보여준다 (`tasks/track-c-frontend.md` §3.2, §6).
 */
export function StarItemCard({ item }: { item: StarItem }) {
  const [showSources, setShowSources] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(formatStarItemForClipboard(item));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // 클립보드 접근 실패 — 조용히 무시 (수동 선택 복사로 대체 가능)
    }
  };

  return (
    <div className="space-y-2.5 rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-zinc-900">{item.title}</h3>
          <p className="text-xs text-zinc-400">{item.period}</p>
        </div>
        <button
          type="button"
          onClick={handleCopy}
          className="shrink-0 rounded-full border border-zinc-200 px-2.5 py-1 text-xs text-zinc-600"
        >
          {copied ? "복사됨" : "복사"}
        </button>
      </div>

      <dl className="space-y-1.5 text-sm text-zinc-700">
        <div>
          <dt className="text-xs font-medium text-zinc-400">상황</dt>
          <dd>{item.situation}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-zinc-400">과제</dt>
          <dd>{item.task}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-zinc-400">행동</dt>
          <dd>{item.action}</dd>
        </div>
        {item.result ? (
          <div>
            <dt className="text-xs font-medium text-zinc-400">결과</dt>
            <dd>{item.result}</dd>
          </div>
        ) : (
          <button
            type="button"
            title="기록에 숫자가 없어 비워두었습니다. 기억나신다면 입력 화면에서 새 메모로 남겨보세요."
            className="mt-1 w-fit rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-700"
          >
            숫자를 기억하시나요? (건너뛰기)
          </button>
        )}
      </dl>

      {item.source_dates.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setShowSources((v) => !v)}
            className="text-xs font-medium text-zinc-400 underline underline-offset-2"
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
  );
}
