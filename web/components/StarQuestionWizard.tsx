"use client";

import Image from "next/image";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, StarItem, applyStarAnswers } from "@/lib/api";

/**
 * "AI 역질문" (9/16 신규, Figma 100:692 "4.2-3 초안 점검"/"4.2-2 Before·After 모드 B").
 *
 * 이미 생성된 STAR 항목 하나를 대상으로, 미리 조회해둔 질문들을 한 번에 하나씩
 * 보여주고(진행률 "N / 총개수") 사용자가 답하거나 건너뛴다. 마지막 질문까지 끝나면
 * `POST /resume/star-apply-answers`를 한 번 호출해 답변을 반영한 Before/After를
 * 보여주고, "적용"을 누르면 부모가 items 배열의 이 항목만 교체한다.
 *
 * 질문 자체는 부모가 `getStarQuestions()`로 미리 조회해서 넘겨준다 — 질문이 하나도
 * 없으면(이미 근거가 충분한 항목) 이 컴포넌트를 아예 렌더링하지 않는 게 부모의 몫이다.
 */
export function StarQuestionWizard({
  item,
  questions,
  onCancel,
  onApply,
}: {
  item: StarItem;
  questions: string[];
  onCancel: () => void;
  onApply: (updated: StarItem) => void;
}) {
  const router = useRouter();
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<string[]>(() => questions.map(() => ""));
  const [currentAnswer, setCurrentAnswer] = useState("");
  const [phase, setPhase] = useState<"asking" | "applying" | "result" | "error">("asking");
  const [result, setResult] = useState<{ item: StarItem; changedField: "action" | "result" } | null>(
    null,
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isLast = index === questions.length - 1;
  const preview = [item.action, item.result].filter(Boolean).join(" ");

  const finish = async (finalAnswers: string[]) => {
    setPhase("applying");
    try {
      const qaPairs = questions
        .map((q, i) => ({ question: q, answer: finalAnswers[i] ?? "" }))
        .filter((qa) => qa.answer.trim());
      const res = await applyStarAnswers(item, qaPairs);
      setResult({ item: res.updated_item, changedField: res.changed_field });
      setPhase("result");
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.detail : "반영에 실패했습니다.");
      setPhase("error");
    }
  };

  const advanceWith = (answerForThisQuestion: string) => {
    const next = [...answers];
    next[index] = answerForThisQuestion;
    setAnswers(next);
    setCurrentAnswer("");
    if (isLast) {
      finish(next);
    } else {
      setIndex((i) => i + 1);
    }
  };

  const handleSkip = () => advanceWith("");
  const handleAnswerNext = () => {
    if (!currentAnswer.trim()) return;
    advanceWith(currentAnswer.trim());
  };

  const answeredCount = answers.filter((a) => a.trim()).length;
  const originalField = result ? item[result.changedField] : "";

  if (phase === "result" && result) {
    return (
      <div className="flex flex-col gap-4 rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e] p-4">
        <div className="flex items-center justify-between">
          <button type="button" onClick={onCancel} aria-label="뒤로" className="text-[17px] text-[#f2f2f2]">
            ←
          </button>
          <p className="text-sm font-semibold text-[#f2f2f2]">역질문 반영 결과</p>
          <p className="text-xs text-[#828282]">{answeredCount}문항 반영</p>
        </div>

        <p className="text-[14px] font-bold text-[#f2f2f2]">{item.title}</p>

        <div className="flex flex-col gap-2 rounded-xl bg-[#181818] p-3">
          <p className="text-[11px] font-medium text-[#828282]">기존</p>
          <p className="text-[13px] leading-relaxed text-[#a0a0a0]">{originalField}</p>
        </div>

        <p className="text-center text-xs text-[#828282]">↓ 내 답변 {answeredCount}개 반영</p>

        <div className="flex flex-col gap-2 rounded-xl border border-[#f2f2f2] bg-[#141414] p-3">
          <p className="text-[11px] font-medium text-[#f2f2f2]">반영</p>
          <p className="text-[13px] leading-relaxed text-[#f2f2f2]">{result.item[result.changedField]}</p>
        </div>

        <div className="flex gap-2 rounded-xl bg-[#181818] p-3">
          <span aria-hidden className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#f2f2f2]" />
          <p className="flex-1 text-[12px] leading-relaxed text-[#a0a0a0]">
            답해주신 이유가 문장에 들어갔습니다. 면접에서 그대로 쓸 수 있어요.
          </p>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 rounded-[11px] border-[1.5px] border-[#2e2e2e] bg-[#1c1c1c] py-[13px] text-[12px] font-semibold text-[#f2f2f2] transition-colors hover:bg-[#242424]"
          >
            그대로 두기
          </button>
          <button
            type="button"
            onClick={() => onApply(result.item)}
            className="flex-1 rounded-[11px] bg-accent py-[13px] text-[12px] font-semibold text-accent-foreground transition-colors hover:bg-[#ff7a2e]"
          >
            적용
          </button>
        </div>
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className="flex flex-col items-center gap-3 rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e] p-6">
        <p className="text-sm text-[#f0645c]">{errorMessage}</p>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-full border border-[#2e2e2e] bg-[#1c1c1c] px-4 py-2 text-xs font-medium text-[#f2f2f2]"
        >
          닫기
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e] p-4">
      <div className="flex items-center justify-between">
        {/* 뒤로는 ← 문자가 아니라 `icon/chevron-left`, 제목은 20px/32다(307:18696). */}
        <button
          type="button"
          onClick={onCancel}
          aria-label="뒤로"
          className="flex size-[22px] items-center justify-center transition-opacity active:opacity-60"
        >
          <Image src="/icons/chevron-left.svg" alt="" width={20} height={20} aria-hidden />
        </button>
        <p className="text-[20px] font-bold leading-[32px] text-[#ede9e2]">초안 점검</p>
        <p className="text-[12px] leading-[20px] text-[#918c84]">
          {index + 1} / {questions.length}
        </p>
      </div>

      <div className="flex flex-col gap-1">
        <p className="text-[11px] font-medium tracking-wide text-[#828282]">점검할 문장</p>
        <div className="flex gap-[11px] rounded-xl bg-[#141414] p-3">
          <span aria-hidden className="w-[2px] shrink-0 rounded-full bg-[#f2f2f2]" />
          <p className="flex-1 text-[13px] leading-relaxed text-[#f2f2f2]">{preview}</p>
        </div>
      </div>

      <div className="flex flex-col gap-2 rounded-xl bg-[#181818] p-3">
        <div className="flex items-center gap-[6px]">
          {/* ✨ 이모지 대신 Figma의 `icon/sparkles` */}
          <Image src="/icons/sparkles.svg" alt="" width={15} height={15} aria-hidden />
          <p className="text-[12px] font-medium leading-[20px] text-[#918c84]">AI가 물어요</p>
        </div>
        <p className="text-[15px] font-bold leading-snug text-[#f2f2f2]">{questions[index]}</p>
      </div>

      <textarea
        value={currentAnswer}
        onChange={(e) => setCurrentAnswer(e.target.value)}
        placeholder="한 줄이면 충분해요."
        rows={3}
        className="w-full resize-none rounded-xl border border-[#2e2e2e] bg-[#141414] p-3 text-sm text-[#f2f2f2] placeholder:text-[#5e5e5e] focus:border-[#5e5e5e] focus:outline-none"
      />
      <p className="text-[11px] text-[#828282]">답해주시면 이 문장에 이유 한 줄이 붙어요.</p>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleSkip}
          disabled={phase === "applying"}
          className="flex h-[50px] flex-1 items-center justify-center rounded-[8px] border border-[#34322e] text-[14px] font-medium text-[#ede9e2] transition-opacity active:opacity-70 disabled:opacity-40"
        >
          건너뛰기
        </button>
        <button
          type="button"
          onClick={handleAnswerNext}
          disabled={!currentAnswer.trim() || phase === "applying"}
          className="flex h-[50px] flex-1 items-center justify-center rounded-[8px] bg-accent text-[14px] font-bold text-accent-foreground transition-colors hover:bg-[#ff7a2e] disabled:opacity-40"
        >
          {phase === "applying" ? "반영하는 중…" : isLast ? "답하고 완료" : "답하고 다음"}
        </button>
      </div>

      <button
        type="button"
        onClick={() => router.push("/")}
        className="text-center text-[11px] text-[#5e5e5e] underline underline-offset-2"
      >
        또는 입력 화면에서 새 기록으로 남기기
      </button>
    </div>
  );
}
