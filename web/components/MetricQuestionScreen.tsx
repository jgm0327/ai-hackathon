"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { resultTheme as t } from "@/components/resultTheme";

interface MetricQuestionScreenProps {
  /** 유저가 방금 쓴 메모 원문 — "적어주신 기록" 카드에 그대로 보여준다. */
  rawText: string;
  question: string;
  placeholder: string;
  /** 뒤로 — 입력 화면으로 돌아간다. 메모는 아직 저장되지 않았다. */
  onBack: () => void;
  /** 답을 실어 변환한다. 빈 문자열이면 "숫자 없이"와 같다. */
  onSubmit: (answer: string) => void;
  submitting: boolean;
}

/**
 * "3.1-q 변환 전 추가 질문" (Figma "02 · 변환 결과" `286:7306`, 9/18 신규).
 *
 * CLAUDE.md 2.2가 정한 두 갈래 중 **되묻는 쪽**이다 — "숫자가 없으면 결과 항목을
 * 비우거나, 유저에게 되묻는다(건너뛰기 가능)". 화면에 "지어내지 않아요. 답해주신 값만
 * 문장에 들어가요."라고 적어서 그 약속을 사용자에게도 보여준다.
 *
 * **2.1("평소 입력 비용 0")과 충돌하지 않는 이유**: 이 화면은 항상 뜨는 게 아니다.
 * 서버(`POST /api/cards/metric-question`)가 "수치가 정말로 빠졌다"고 판단한 기록에만
 * 질문이 오고, 그 외에는 빈 문자열이 와서 호출부가 곧장 변환으로 넘어간다. 질문이
 * 떠도 "숫자 없이"가 왼쪽에 항상 있어서 한 번 더 누르면 끝난다.
 *
 * 시트가 아니라 전체 화면인 건 목업 그대로다 — 모바일 키보드가 올라온 상태에서
 * 바텀시트 안에 입력창을 두면 질문과 입력창이 같이 안 보인다.
 */
export function MetricQuestionScreen({
  rawText,
  question,
  placeholder,
  onBack,
  onSubmit,
  submitting,
}: MetricQuestionScreenProps) {
  const [answer, setAnswer] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onBack();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onBack]);

  return (
    // `fixed inset-0`이라 `app/layout.tsx`의 `max-w-md` 컨테이너 밖으로 나간다 —
    // 데스크톱 폭에서 화면이 통째로 늘어나 버리므로, 바텀시트들과 같은 방식으로
    // 여기서 다시 가운데 정렬 + 폭 제한을 건다.
    <div
      role="dialog"
      aria-modal="true"
      aria-label="변환 전 추가 질문"
      style={{ backgroundColor: t.screenBg }}
      className="fixed inset-0 z-50 mx-auto flex w-full max-w-md flex-col overflow-y-auto"
    >
      {/* Header (Figma 286:7308) */}
      <div className="flex items-center px-[20px] pt-[2px] pb-[16px]">
        <button
          type="button"
          onClick={onBack}
          aria-label="뒤로"
          className="flex size-[20px] items-center justify-center transition-opacity active:opacity-60"
        >
          <Image src="/icons/chevron-left.svg" alt="" width={20} height={20} aria-hidden />
        </button>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!submitting) onSubmit(answer.trim());
        }}
        className="flex flex-1 flex-col px-[22px] pt-[24px] pb-[22px]"
      >
        <p
          style={{ color: t.textMuted }}
          className="text-[12px] font-medium leading-[20px]"
        >
          한 가지만 더
        </p>
        <p
          style={{ color: t.text }}
          className="mt-[12px] text-[28px] font-bold leading-[36px]"
        >
          숫자가 있으면
          <br />
          문장이 훨씬 세집니다
        </p>
        <p style={{ color: t.textMuted }} className="mt-[20px] text-[14px] leading-[24px]">
          지어내지 않아요. 답해주신 값만 문장에 들어가요.
        </p>

        {/* 원문 카드 (Figma 286:7318) */}
        <div
          style={{ backgroundColor: t.cardBg }}
          className="mt-[36px] flex flex-col gap-[10px] rounded-[12px] p-[16px]"
        >
          <p style={{ color: t.textMuted }} className="text-[12px] font-medium leading-[20px]">
            적어주신 기록
          </p>
          <p
            style={{ color: t.textSoft }}
            className="whitespace-pre-wrap text-[14px] leading-[24px]"
          >
            {rawText}
          </p>
        </div>

        <label
          htmlFor="metric-answer"
          style={{ color: t.text }}
          className="mt-[28px] text-[20px] font-bold leading-[28px]"
        >
          {question}
        </label>
        <div
          style={{ backgroundColor: t.cardBg }}
          className="mt-[12px] rounded-[12px] px-[16px] py-[18px]"
        >
          {/* maxLength는 서버(schemas.py MAX_ANSWER)와 같은 값 — 여기서 먼저 끊어야
              길게 쓴 뒤에야 422를 보는 일이 없다. */}
          <input
            id="metric-answer"
            ref={inputRef}
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder={placeholder || "예: 3.2%p, 12% → 15.2%"}
            maxLength={1000}
            style={{ color: t.text }}
            className="w-full border-0 bg-transparent p-0 text-[14px] leading-[24px] placeholder:text-[#918c84] focus:outline-none"
          />
        </div>
        <p style={{ color: t.textMuted }} className="mt-[12px] text-[12px] leading-[20px]">
          모르면 비워두셔도 돼요. 나중에 이 기록에서 바로 채울 수 있어요.
        </p>

        <div className="flex-1 min-h-[48px]" />

        {/* 액션 (Figma 286:7329) */}
        <div className="flex items-center gap-[10px]">
          <button
            type="button"
            onClick={() => onSubmit("")}
            disabled={submitting}
            style={{ borderColor: t.border, color: t.text }}
            className="flex h-[56px] flex-1 items-center justify-center rounded-[8px] border text-[14px] font-medium tracking-[-0.14px] transition-opacity active:opacity-70 disabled:opacity-40"
          >
            숫자 없이
          </button>
          <button
            type="submit"
            disabled={submitting}
            style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
            className="flex h-[56px] flex-1 items-center justify-center rounded-[8px] text-[14px] font-bold tracking-[-0.28px] transition-opacity active:opacity-80 disabled:opacity-40"
          >
            {submitting ? "만드는 중…" : "답하고 만들기"}
          </button>
        </div>
      </form>
    </div>
  );
}
