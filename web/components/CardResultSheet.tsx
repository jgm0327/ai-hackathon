"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { resultTheme as t } from "@/components/resultTheme";
import { ApiError, Card, CardTranslation, addMetricAnswer, translateCard } from "@/lib/api";

interface CardResultSheetProps {
  card: Card;
  /** POST 응답에만 실려 오는 "오늘 기록은 ~~ 케이스입니다" 문구 (`Card.case_summary`). */
  caseSummary: string;
  /** 프로필의 현재 직무 — "퍼포먼스 마케터 관점" 라벨에 쓴다. 없으면 라벨을 안 띄운다. */
  currentJob: string | null;
  /** 온보딩 2/4에서 고른 목표 직무들. 비어 있으면 관점 전환 자체가 안 뜬다. */
  targetJobs: string[];
  onClose: () => void;
  onEditSentence: () => void;
  onCopy: (sentence: string) => void;
  onRegenerate: () => Promise<void> | void;
  copied: boolean;
  regenerating: boolean;
  /** "다시 만들기"가 실패했을 때의 문구. 시트를 닫지 않고 그 자리에 보여준다. */
  error?: string | null;
  /** 변환 전 추가 질문(3.1-q)에서 **건너뛴** 질문. 3.1-n 안내 문구를 구체적으로
   * 적는 데 쓴다. 없으면 일반 문구로 간다 — 묻지도 않은 질문을 지어내지 않는다. */
  skippedMetricQuestion?: string | null;
  /** 수치를 채워 카드가 갱신됐을 때. 호출부가 목록/헤드라인을 다시 그린다. */
  onMetricFilled?: (card: Card) => void;
}

/**
 * 문장에 숫자가 하나라도 있는지 (Figma 3.1-n "수치 없음" 판정).
 *
 * LLM이 아니라 정규식으로 본다 — 결과 시트는 이미 변환을 마친 자리라 여기서 호출을
 * 하나 더 얹을 이유가 없고, "숫자가 있나"는 애초에 판단이 필요한 문제가 아니다.
 * 한글 수사("세 배")는 못 잡지만, 못 잡으면 안내가 한 번 더 뜰 뿐이라 손해가 작다.
 */
function hasNumber(sentence: string): boolean {
  return /\d/.test(sentence);
}

/**
 * "3.1 결과 출력 모달" + "3.1-b 직무 전환 번역 결과" + "3.1-c 직무 접점 없음"
 * (Figma "02 · 변환 결과" `286:7130` / `286:7232` / `286:7256`, 9/18 신규).
 *
 * 세 화면은 **같은 시트의 세 상태**다 — 맨 위 관점 라벨을 눌러 "현재 직무 관점"과
 * "목표 직무 관점"을 오간다. 목표 직무로 읽었는데 접점이 없으면 억지로 갖다 붙이지
 * 않고 3.1-c 상태가 된다(서버가 `related: false`로 답한다).
 *
 * **관점 전환을 라벨에 붙인 이유**: 매일 쓰는 경로에는 선택지를 더하지 않는다는 원칙
 * (CLAUDE.md 2.1) 때문이다. 기본값은 항상 현재 직무 관점이고, 목표 직무를 등록한
 * 사람에게만 라벨 옆에 작은 `›`가 붙는다 — 누르지 않으면 예전과 똑같은 화면이다.
 *
 * 번역 결과는 저장하지 않는다(`lib/api.ts` translateCard 주석 참고). 그래서 시트를
 * 닫았다 다시 열면 현재 직무 관점에서 시작한다.
 */
export function CardResultSheet({
  card,
  caseSummary,
  currentJob,
  targetJobs,
  onClose,
  onEditSentence,
  onCopy,
  onRegenerate,
  copied,
  regenerating,
  error,
  skippedMetricQuestion,
  onMetricFilled,
}: CardResultSheetProps) {
  // null이면 현재 직무 관점(3.1), 값이 있으면 그 목표 직무 관점(3.1-b/3.1-c).
  const [targetIndex, setTargetIndex] = useState<number | null>(null);
  const [translation, setTranslation] = useState<CardTranslation | null>(null);
  const [translating, setTranslating] = useState(false);
  const [translateError, setTranslateError] = useState<string | null>(null);

  // 3.1-n "수치 없음" — [지금 채우기]를 누르면 그 자리에서 입력창이 열린다. 화면을
  // 따로 띄우지 않는 건, 결과를 보다가 숫자 하나 더하는 동작이라 맥락을 끊으면
  // 오히려 번거롭기 때문이다(3.1-q는 변환 전이라 전체 화면이 맞다).
  const [fillingMetric, setFillingMetric] = useState(false);
  const [metricDraft, setMetricDraft] = useState("");
  const [savingMetric, setSavingMetric] = useState(false);
  const [metricError, setMetricError] = useState<string | null>(null);

  const activeTarget = targetIndex === null ? null : targetJobs[targetIndex];

  // 카드가 바뀌면(다시 만들기 등) 번역 결과는 더 이상 그 문장의 번역이 아니다 —
  // 버리고 현재 직무 관점으로 되돌린다. 오래된 번역을 그대로 두면 화면의 문장과
  // 원문이 어긋난 채로 남는다.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTargetIndex(null);
    setTranslation(null);
    setTranslateError(null);
  }, [card.id, card.refined_sentence]);

  // 예전 결과 시트는 `<BottomSheet>` 프리미티브를 써서 Esc로 닫혔다 — 이 시트는
  // 레이아웃이 달라 프리미티브를 쓰지 않으므로 여기서 같은 동작을 유지한다.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const runTranslate = async (job: string) => {
    setTranslating(true);
    setTranslateError(null);
    setTranslation(null);
    try {
      setTranslation(await translateCard(card.id, job));
    } catch {
      setTranslateError("지금은 다른 직무 관점으로 읽어드리기 어려워요.");
    } finally {
      setTranslating(false);
    }
  };

  /** 현재 직무 → 목표 직무 1 → … → 다시 현재 직무. */
  const cyclePerspective = () => {
    const next = targetIndex === null ? 0 : targetIndex + 1;
    if (next >= targetJobs.length) {
      setTargetIndex(null);
      setTranslation(null);
      setTranslateError(null);
      return;
    }
    setTargetIndex(next);
    runTranslate(targetJobs[next]);
  };

  const handleFillMetric = async () => {
    const answer = metricDraft.trim();
    if (!answer) return;
    setSavingMetric(true);
    setMetricError(null);
    try {
      const updated = await addMetricAnswer(card.id, answer);
      onMetricFilled?.(updated);
      setFillingMetric(false);
      setMetricDraft("");
    } catch (err) {
      setMetricError(err instanceof ApiError ? err.detail : "채우지 못했어요.");
    } finally {
      setSavingMetric(false);
    }
  };

  // 접점 없음(3.1-c)은 "번역이 왔고 related가 false"일 때만이다. 번역 실패는 다른
  // 상태라 — 접점이 없다고 단정하면 안 된다(모르는 것과 아닌 것은 다르다).
  const unrelated = !!translation && !translation.related;
  const sentence =
    translation && translation.related ? translation.translated_sentence : card.refined_sentence;

  const perspectiveLabel = (() => {
    if (activeTarget && unrelated) return `${activeTarget}와는 조금 멀어요`;
    if (activeTarget) return `${currentJob ?? "현재 직무"} → ${activeTarget}`;
    return currentJob ? `${currentJob} 관점` : null;
  })();

  const headline = (() => {
    if (translating) return "다른 직무 관점으로 읽는 중…";
    if (translation?.headline) return translation.headline;
    return caseSummary || "오늘 기록을 이렇게 정리했어요.";
  })();

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <button
        type="button"
        aria-label="닫기"
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        style={{ backgroundColor: t.sheetBg }}
        className="relative flex w-full max-w-md flex-col rounded-t-[24px] px-[22px] pt-[14px] pb-[26px] shadow-xl"
      >
        <div className="flex items-center justify-center pt-[2px] pb-[20px]">
          <div
            aria-hidden
            style={{ backgroundColor: t.handle }}
            className="h-[4px] w-[36px] rounded-full"
          />
        </div>

        {/* 관점 라벨 (Figma 286:7133 / 286:7235 / 286:7259). 목표 직무가 있으면
            눌러서 관점을 바꾼다 — 그때만 `›`가 붙어 누를 수 있다는 걸 알린다. */}
        {perspectiveLabel &&
          (targetJobs.length > 0 ? (
            <button
              type="button"
              onClick={cyclePerspective}
              disabled={translating}
              style={{ color: t.textMuted }}
              className="flex items-center gap-1 self-start text-[12px] font-medium leading-[20px] tracking-[0.4px] transition-opacity active:opacity-60 disabled:opacity-50"
            >
              {perspectiveLabel}
              <span aria-hidden>›</span>
            </button>
          ) : (
            <p
              style={{ color: t.textMuted }}
              className="text-[12px] font-medium leading-[20px] tracking-[0.4px]"
            >
              {perspectiveLabel}
            </p>
          ))}

        <p
          style={{ color: t.text }}
          className="mt-[20px] text-[20px] font-bold leading-[28px] tracking-[-0.4px]"
        >
          {headline}
        </p>

        {/* 문장 카드 (Figma 286:7138). 접점 없음(3.1-c)일 땐 목업이 패딩을 16으로
            줄인다 — 문장이 짧게 유지되는 상태라서. */}
        <div
          style={{ backgroundColor: t.cardBg }}
          className={`mt-[36px] flex rounded-[12px] ${unrelated ? "p-[16px]" : "p-[18px]"}`}
        >
          <p
            style={{ color: t.text }}
            className="flex-1 text-[14px] leading-[24px] tracking-[-0.5px]"
          >
            {sentence}
          </p>
        </div>

        {/* 직접 수정 진입 (Figma 286:7140) — 현재 직무 관점에서만. 번역 문장은
            저장된 값이 아니라서 "고치기"의 대상이 아니다. */}
        {!activeTarget && (
          <button
            type="button"
            onClick={onEditSentence}
            className="mt-[8px] flex items-center justify-end gap-[6px]"
          >
            <Image src="/icons/pencil.svg" alt="" width={16} height={16} aria-hidden />
            <span
              style={{ color: t.textSoft }}
              className="text-[12px] font-medium leading-[20px] tracking-[0.4px]"
            >
              문장 고치기
            </span>
          </button>
        )}

        {/* "3.1-n 결과 · 수치 없음" (Figma `299:12512`, 9/18 신규).
            현재 직무 관점에서, 문장에 숫자가 하나도 없을 때만. 번역 문장은 저장되는
            값이 아니라서 여기에 수치를 채울 대상이 아니다. */}
        {!activeTarget && !hasNumber(sentence) && (
          <div
            style={{ borderColor: t.action }}
            className="mt-[20px] flex flex-col gap-[10px] rounded-[8px] border px-[16px] py-[14px]"
          >
            <div className="flex items-center gap-2">
              <span
                style={{ color: t.action }}
                className="text-[12px] font-medium leading-[20px]"
              >
                수치 없음
              </span>
              <span className="flex-1" />
              {!fillingMetric && (
                <button
                  type="button"
                  onClick={() => setFillingMetric(true)}
                  style={{ color: t.action }}
                  className="text-[12px] font-medium leading-[20px] transition-opacity active:opacity-60"
                >
                  지금 채우기 ›
                </button>
              )}
            </div>

            {fillingMetric ? (
              <div className="flex flex-col gap-2">
                <label
                  htmlFor="metric-fill"
                  style={{ color: t.textSoft }}
                  className="text-[12px] leading-[20px]"
                >
                  {skippedMetricQuestion || "얼마나 달라졌는지 숫자로 적어 주세요"}
                </label>
                <input
                  id="metric-fill"
                  value={metricDraft}
                  onChange={(e) => setMetricDraft(e.target.value)}
                  placeholder="예: 3.2%p, 12% → 15.2%"
                  maxLength={1000}
                  autoFocus
                  style={{ backgroundColor: t.cardBg, color: t.text }}
                  className="rounded-[8px] px-3 py-2.5 text-[14px] leading-[24px] placeholder:text-[#918c84] focus:outline-none"
                />
                {metricError && <p className="text-[12px] text-red-400">{metricError}</p>}
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleFillMetric}
                    disabled={savingMetric || !metricDraft.trim()}
                    style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
                    className="flex-1 rounded-[8px] py-2.5 text-[12px] font-bold transition-opacity active:opacity-80 disabled:opacity-40"
                  >
                    {savingMetric ? "채우는 중…" : "채우고 다시 만들기"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setFillingMetric(false);
                      setMetricError(null);
                    }}
                    style={{ borderColor: t.border, color: t.text }}
                    className="flex-1 rounded-[8px] border py-2.5 text-[12px] font-medium transition-opacity active:opacity-70"
                  >
                    나중에
                  </button>
                </div>
              </div>
            ) : (
              <p style={{ color: t.textSoft }} className="text-[12px] leading-[20px]">
                {skippedMetricQuestion
                  ? `${skippedMetricQuestion} 답을 더하면 면접에서 쓸 수 있는 문장이 돼요.`
                  : "숫자를 더하면 면접에서 쓸 수 있는 문장이 돼요."}
              </p>
            )}
          </div>
        )}

        {/* 원문 보기 (Figma 286:7242) — 번역 문장이 원래 무엇에서 나왔는지 바로
            대조할 수 있어야 "없는 말을 지어낸 건 아닌지" 유저가 직접 확인한다
            (CLAUDE.md 2.2를 화면에서 검증 가능하게 하는 장치). */}
        {activeTarget && translation?.related && (
          <details className="mt-[36px]">
            <summary
              style={{ color: t.textMuted }}
              className="flex cursor-pointer list-none items-center gap-2 text-[12px] leading-[20px] tracking-[0.4px] [&::-webkit-details-marker]:hidden"
            >
              <span className="flex-1 truncate">원문 · {card.raw_text}</span>
              <Image
                src="/icons/chevron-right.svg"
                alt=""
                width={16}
                height={16}
                aria-hidden
                className="shrink-0"
              />
            </summary>
            <p
              style={{ color: t.textSoft }}
              className="mt-2 whitespace-pre-wrap text-[13px] leading-[20px]"
            >
              {card.raw_text}
            </p>
          </details>
        )}

        {/* 다음 기록 제안 (Figma 286:7266) — 3.1-c 전용. */}
        {unrelated && translation.suggestion && (
          <div
            style={{ backgroundColor: t.cardBg }}
            className="mt-[44px] flex items-start gap-[10px] rounded-[12px] px-[16px] py-[14px]"
          >
            <Image
              src="/icons/sparkles.svg"
              alt=""
              width={15}
              height={15}
              aria-hidden
              className="mt-[5px] shrink-0"
            />
            <p style={{ color: t.textSoft }} className="flex-1 text-[14px] leading-[24px]">
              {translation.suggestion}
            </p>
          </div>
        )}

        {(translateError || error) && (
          <p className="mt-4 text-[12px] text-red-400">{translateError ?? error}</p>
        )}

        {/* 액션 (Figma 286:7144 / 286:7270) */}
        <div className="mt-[36px] flex items-center gap-[10px]">
          <button
            type="button"
            // 3.1-c의 왼쪽 버튼은 "기록 고치기"다 — 접점이 없다는 말을 듣고 나서
            // 할 수 있는 건 다시 만들기가 아니라 문장을 직접 손보는 것이라서,
            // "문장 고치기"와 같은 수정 시트로 보낸다.
            onClick={unrelated ? onEditSentence : onRegenerate}
            disabled={regenerating || translating}
            style={{ borderColor: t.border, color: t.text }}
            className="flex h-[56px] flex-1 items-center justify-center rounded-[8px] border text-[14px] font-medium transition-opacity active:opacity-70 disabled:opacity-40"
          >
            {unrelated ? "기록 고치기" : regenerating ? "만드는 중…" : "다시 만들기"}
          </button>
          <button
            type="button"
            // 3.1-c의 오른쪽은 "그대로 저장" — 카드는 이미 저장돼 있으므로 시트를
            // 닫기만 하면 된다(저장을 또 하지 않는다).
            onClick={unrelated ? onClose : () => onCopy(sentence)}
            disabled={translating}
            style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
            className="flex h-[56px] flex-1 items-center justify-center rounded-[8px] text-[14px] font-bold transition-opacity active:opacity-80 disabled:opacity-40"
          >
            {unrelated ? "그대로 저장" : copied ? "복사됨" : "복사하기"}
          </button>
        </div>
      </div>
    </div>
  );
}
