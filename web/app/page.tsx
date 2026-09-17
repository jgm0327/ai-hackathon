"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BottomSheet } from "@/components/BottomSheet";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { CardResultSkeleton } from "@/components/Skeleton";
import { VoiceInput } from "@/components/VoiceInput";
import {
  ApiError,
  Card,
  SkillSummary,
  createCard,
  getSkillSummary,
  listCards,
  refineCard,
} from "@/lib/api";
import { useProjects } from "@/lib/useProjects";

const DRAFT_KEY = "career-log:draft-raw-text";

// 버블 색상(Figma 100:692 "흔적 버블 클러스터") — 순서대로 4개 카테고리, "미분류"는
// 항상 마지막 어두운 톤. 카테고리 이름을 색에 매핑하지 않고 순위(등장 순서)로만
// 매핑한다 — 태그 이름을 지어내지 않는 것과 같은 이유로, 색도 실제 데이터 순서를
// 그대로 따를 뿐 의미를 부여하지 않는다.
const BUBBLE_COLORS = [
  "rgba(255,162,89,0.88)",
  "rgba(255,203,86,0.88)",
  "rgba(233,131,111,0.88)",
  "rgba(224,124,124,0.88)",
];
const UNCATEGORIZED_COLOR = "rgba(58,53,46,0.88)";

/** "YYYY-MM-DD" 오늘 날짜 문자열 (로컬 기준) — `card.created_at`과 같은 포맷이라
 * 문자열 비교로 오늘 카드만 골라낼 수 있다. */
function todayDateString(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function formatTodayLabel(): string {
  const d = new Date();
  return `${d.getMonth() + 1}월 ${d.getDate()}일 · 오늘`;
}

/**
 * 홈 화면 (`/`) — 제품에서 매일 쓰는 유일한 경로 (Figma 100:692 "01·기록·Tab A",
 * "3.0-버 홈·흔적 버블").
 *
 * "3초 만에 끝내고 모니터 끄기"가 슬로건이다 (CLAUDE.md 2.1). 기존 "큰 입력창
 * 하나"만 있던 화면을, 오늘까지 쌓인 것을 먼저 보여주는 대시보드형으로 바꿨다 —
 * "무엇이 쌓였나요"(역량별 버블) + "오늘 남긴 것"(오늘 기록 리스트) + 입력창을
 * 한 화면에 둔다. 다크 테마는 디자인 시스템 문서(라이트, 다크는 "웰컴 전용"으로
 * 표기)와 실제 이 화면 코드가 서로 달랐는데, 사용자가 "화면 코드가 맞다"고
 * 확인해줘서 다크로 구현했다(9/16).
 */
export default function HomePage() {
  const [rawText, setRawText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Card | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiedResult, setCopiedResult] = useState(false);
  // 변환 실패 폴백 (9/15 신규) — result.refinement_failed가 true면 "다시 정리하기"로
  // 재시도할 수 있다. 카드는 이미 원문 그대로 저장돼 있으므로(CLAUDE.md P0) 재시도가
  // 또 실패해도 데이터 유실은 없다.
  const [refining, setRefining] = useState(false);
  const [refineError, setRefineError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // ProjectSwitcher에 그대로 넘긴다 — 훅 인스턴스를 이 화면과 공유해야 전환이 즉시
  // 반영된다(구현 노트: components/ProjectSwitcher.tsx 9/14 참고).
  const projectsState = useProjects();
  const { currentProject } = projectsState;

  // "무엇이 쌓였나요" 버블 + "오늘 남긴 것" 목록 (9/16 신규) — 둘 다 카드 목록에서
  // 나오는 값이라 하나로 묶어 조회한다(중복 호출 방지).
  const [skillSummary, setSkillSummary] = useState<SkillSummary | null>(null);
  const [todayCards, setTodayCards] = useState<Card[]>([]);

  // 오프라인 배너 (Figma 41:762) — 자차 이동 중 신호가 끊긴 상태(CLAUDE.md 1장
  // 사용 맥락 2)에서도 방금 입력한 원문이 사라진 게 아니라는 걸 알려준다. 실제로
  // 텍스트박스 내용은 submitting에 실패해도 지우지 않으므로(아래 submitText),
  // 오프라인이면 애초에 제출 자체를 막아 원문이 화면에 그대로 남게 한다.
  const [isOffline, setIsOffline] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsOffline(!navigator.onLine);
    const goOffline = () => setIsOffline(true);
    const goOnline = () => setIsOffline(false);
    window.addEventListener("offline", goOffline);
    window.addEventListener("online", goOnline);
    return () => {
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("online", goOnline);
    };
  }, []);

  // 위 오프라인 배너의 "원문은 저장됐어요"가 실제로 참이 되게 한다 — 텍스트박스
  // 내용을 매번 로컬에 남겨서, 오프라인 상태로 화면을 벗어나거나 새로고침해도
  // 방금 쓰던 원문을 잃지 않는다. 제출에 성공하면(rawText가 빈 문자열이 됨)
  // 자동으로 지워진다.
  useEffect(() => {
    try {
      const saved = localStorage.getItem(DRAFT_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (saved) setRawText(saved);
    } catch {
      // 접근 불가(프라이빗 모드 등) — 평소처럼 빈 입력으로 시작할 뿐 치명적이지 않다.
    }
  }, []);

  useEffect(() => {
    try {
      if (rawText) localStorage.setItem(DRAFT_KEY, rawText);
      else localStorage.removeItem(DRAFT_KEY);
    } catch {
      // 저장 실패해도 화면상 입력 자체는 지장 없다.
    }
  }, [rawText]);

  const refreshHomeData = () => {
    if (!currentProject) return;
    getSkillSummary(currentProject.id)
      .then(setSkillSummary)
      .catch(() => {});
    listCards(currentProject.id)
      .then((list) => {
        const today = todayDateString();
        setTodayCards(list.filter((c) => c.created_at === today));
      })
      .catch(() => {});
  };

  useEffect(refreshHomeData, [currentProject]);

  // 텍스트 입력과 음성 입력이 공유하는 단일 제출 경로 — 어느 쪽에서 오든 동일한
  // 스켈레톤/결과 모달 UX를 탄다 (docs/06-migration.md §2.1: 별도 흐름을 만들지 않는다).
  const submitText = async (text: string) => {
    if (!text || submitting || isOffline) return;

    setSubmitting(true);
    setError(null);
    setResult(null);
    setRefineError(null);
    try {
      // 응답이 3~10초 걸린다 (docs/05-api-contract.md §1) — 스켈레톤으로 대기 표시.
      const card = await createCard(text);
      setResult(card);
      setRawText("");
      refreshHomeData(); // 방금 쌓인 카드를 버블/오늘 목록에 바로 반영
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "저장에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    submitText(rawText.trim());
  };

  const handleCloseResult = () => {
    setResult(null);
  };

  const handleRetry = () => {
    setResult(null);
    textareaRef.current?.focus();
  };

  const handleCopyResult = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.refined_sentence);
      setCopiedResult(true);
      setTimeout(() => setCopiedResult(false), 1500);
    } catch {
      // 클립보드 접근 실패 — 조용히 무시
    }
  };

  const handleRefine = async () => {
    if (!result) return;
    setRefining(true);
    setRefineError(null);
    try {
      const updated = await refineCard(result.id);
      setResult(updated);
    } catch {
      setRefineError("다시 정리하는 데 실패했어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setRefining(false);
    }
  };

  const totalCards = skillSummary?.total_cards ?? 0;
  const categoryCount = skillSummary?.categories.length ?? 0;
  const maxCount = Math.max(1, ...(skillSummary?.categories.map((c) => c.count) ?? [1]));

  return (
    <div className="flex flex-col gap-5 px-5 pt-[8px] pb-4 text-[#f2f2f2]">
      {/* Header */}
      <div className="flex items-center gap-2">
        <p className="text-[19px] font-bold tracking-[-0.5px]">오늘의 흔적</p>
        <div className="flex-1" />
        <ProjectSwitcher projectsState={projectsState} />
        <Link
          href="/settings"
          aria-label="설정"
          className="flex size-[26px] items-center justify-center rounded-full bg-[#1e1e1e] text-xs text-[#a0a0a0] transition-colors hover:bg-[#2a2a2a] active:scale-[0.95]"
        >
          ⚙
        </Link>
      </div>

      {isOffline && (
        <div className="flex items-center gap-2 rounded-[12px] bg-[#1e1e1e] px-3 py-2.5">
          <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#a0a0a0]" />
          <p className="text-[12px] text-[#a0a0a0]">
            오프라인 · 원문은 저장됐어요. 연결되면 자동으로 변환할게요
          </p>
        </div>
      )}

      {/* 무엇이 쌓였나요 */}
      <div className="flex flex-col items-center gap-1">
        <p className="text-[27px] font-bold leading-[36px] tracking-[-0.9px]">무엇이 쌓였나요</p>
        <p className="text-[12.5px] text-[#828282]">
          {totalCards > 0
            ? `기록 ${totalCards}개가 역량 ${categoryCount}개로 모였습니다`
            : "기록이 쌓이면 여기 역량별로 모아 보여드려요"}
        </p>
      </div>

      {skillSummary && skillSummary.categories.length > 0 && (
        <div className="flex flex-wrap items-center justify-center gap-3 py-2">
          {skillSummary.categories.map((cat, i) => {
            const size = Math.round(66 + (cat.count / maxCount) * 74);
            const isUncategorized = cat.tag === "미분류";
            const color = isUncategorized ? UNCATEGORIZED_COLOR : BUBBLE_COLORS[i % BUBBLE_COLORS.length];
            // "미분류" 버블은 배경이 어두워서(UNCATEGORIZED_COLOR) 다른 버블과 같은
            // 어두운 글자색(#2a2018)을 쓰면 대비가 너무 낮다 — 밝은 글자로 바꾼다.
            const textColor = isUncategorized ? "#d8d3c8" : "#2a2018";
            return (
              <div
                key={cat.tag}
                style={{ width: size, height: size, backgroundColor: color }}
                className="flex flex-col items-center justify-center gap-0.5 rounded-full px-2 text-center"
              >
                <p
                  className="line-clamp-2 text-[11px] font-medium leading-[14px]"
                  style={{ color: textColor }}
                >
                  {cat.tag}
                </p>
                <p className="text-[16px] font-bold leading-[20px]" style={{ color: textColor }}>
                  {cat.count}
                </p>
              </div>
            );
          })}
        </div>
      )}

      {/* 오늘 남긴 것 */}
      {todayCards.length > 0 && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-1.5">
            <p className="text-[11px] font-medium text-[#f2f2f2]">오늘 남긴 것</p>
            <div className="flex-1" />
            <p className="text-[11px] font-medium text-[#828282]">{todayCards.length}</p>
          </div>
          <div className="flex flex-col gap-3">
            {todayCards.map((card) => (
              <div key={card.id} className="flex gap-2.5 rounded-lg py-1">
                <p className="w-[38px] shrink-0 text-[11px] tracking-[0.4px] text-[#828282]">
                  {card.created_time ?? "--:--"}
                </p>
                <p className="flex-1 text-[13px] leading-[18px] text-[#f2f2f2]">
                  {card.refined_sentence}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 오늘 입력 */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <div className="flex items-center gap-1.5">
          <p className="text-[11px] font-medium text-[#a0a0a0]">{formatTodayLabel()}</p>
          <div className="flex-1" />
          <p className="text-[11px] font-medium text-[#828282]">기록 {todayCards.length}</p>
        </div>
        <div className="flex flex-col gap-2 rounded-[14px] bg-[#1e1e1e] px-[15px] py-[11px]">
          {/* maxLength는 서버(schemas.py MAX_RAW_TEXT)와 같은 값으로 맞춘다 — 여기서
              먼저 끊어야 유저가 길게 쓴 뒤에야 422를 보는 일이 없다. */}
          <textarea
            ref={textareaRef}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder={"오늘 뭐 하셨어요?"}
            rows={2}
            maxLength={2000}
            className="w-full resize-none border-0 bg-transparent p-0 text-[14px] text-[#f2f2f2] placeholder:text-[#828282] focus:outline-none"
          />
          <div className="flex items-center justify-end gap-2">
            {rawText.trim() ? (
              <button
                type="submit"
                disabled={submitting || isOffline}
                aria-label={isOffline ? "연결을 기다리는 중" : "경력 변환하기"}
                className="flex size-[36px] items-center justify-center rounded-full bg-[#f2f2f2] text-sm font-semibold text-[#141210] transition-colors disabled:opacity-40"
              >
                {submitting ? "…" : "↑"}
              </button>
            ) : (
              <VoiceInput variant="icon" onTranscript={submitText} disabled={submitting || isOffline} />
            )}
          </div>
        </div>
      </form>

      {submitting && <CardResultSkeleton />}

      {error && <p className="rounded-lg bg-[#1e1e1e] px-3 py-2 text-sm text-red-400">{error}</p>}

      {/* 결과 출력 바텀시트 (Figma "3.1 결과 출력 모달") */}
      <BottomSheet
        open={!!result}
        onClose={handleCloseResult}
        hideHandle
        panelClassName="relative w-full max-w-md rounded-tl-[24px] rounded-tr-[24px] bg-[#1a1a1a] px-5 pt-3 pb-[30px] shadow-xl"
      >
        {result && (
          <div className="flex flex-col gap-3.5">
            <div className="flex items-center justify-end">
              <button
                type="button"
                onClick={handleCloseResult}
                aria-label="닫기"
                className="flex size-[38px] items-center justify-center rounded-full bg-[#2a2a2a] text-sm text-[#a0a0a0] transition-colors hover:bg-[#333] active:scale-[0.95]"
              >
                ✕
              </button>
            </div>

            {result.refinement_failed ? (
              <>
                <div className="flex items-center gap-2">
                  <span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-red-500" />
                  <p className="text-[14px] font-semibold text-[#f2f2f2]">변환에 실패했어요</p>
                </div>
                <p className="text-[12px] text-amber-400">
                  메모는 그대로 있습니다. 다시 시도하거나 원문만 저장할 수 있어요.
                </p>

                <div className="flex gap-3 rounded-[14px] bg-[#2a2320] px-4 py-[18px]">
                  <div className="w-[3px] shrink-0 self-stretch rounded-full bg-amber-500" />
                  <p className="flex-1 text-[14px] font-medium text-[#f2f2f2]">{result.raw_text}</p>
                </div>

                {refineError && <p className="text-[12px] text-red-400">{refineError}</p>}

                <div className="flex gap-2.5">
                  <button
                    type="button"
                    onClick={handleRefine}
                    disabled={refining}
                    className="flex flex-1 items-center justify-center rounded-[12px] bg-[#f2f2f2] py-4 text-[14px] font-semibold text-[#141210] transition-colors active:scale-[0.98] disabled:opacity-40"
                  >
                    {refining ? "정리하는 중…" : "다시 시도"}
                  </button>
                  <button
                    type="button"
                    onClick={handleCloseResult}
                    className="flex flex-1 items-center justify-center rounded-[12px] border-[1.5px] border-[#333] bg-transparent py-4 text-[14px] font-semibold text-[#f2f2f2] transition-colors hover:bg-[#2a2a2a] active:scale-[0.98]"
                  >
                    그냥 저장하기
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="text-[17px] font-bold leading-[24px] text-[#f2f2f2]">
                  {result.case_summary || "오늘 기록을 이렇게 정리했어요."}
                </p>

                <div className="flex gap-3 rounded-[14px] bg-[#242424] px-4 py-[18px]">
                  <p className="flex-1 text-[14px] leading-relaxed text-[#f2f2f2]">
                    {result.refined_sentence}
                  </p>
                </div>

                {result.skill_tags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {result.skill_tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-full bg-[#2a2a2a] px-2.5 py-1 text-xs text-[#c8c8c8]"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                <div className="flex gap-2.5">
                  <button
                    type="button"
                    onClick={handleCopyResult}
                    className="flex flex-1 items-center justify-center rounded-[12px] bg-[#f2f2f2] py-4 text-[14px] font-semibold text-[#141210] transition-colors active:scale-[0.98]"
                  >
                    {copiedResult ? "복사됨" : "복사하기"}
                  </button>
                  <button
                    type="button"
                    onClick={handleRetry}
                    className="flex flex-1 items-center justify-center rounded-[12px] border-[1.5px] border-[#333] bg-transparent py-4 text-[14px] font-semibold text-[#f2f2f2] transition-colors hover:bg-[#2a2a2a] active:scale-[0.98]"
                  >
                    다시 변환
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </BottomSheet>
    </div>
  );
}

