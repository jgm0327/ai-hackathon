"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BottomSheet } from "@/components/BottomSheet";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { CardResultSkeleton } from "@/components/Skeleton";
import { VoiceInput } from "@/components/VoiceInput";
import { ApiError, Card, Profile, createCard, getProfile, syncNotion } from "@/lib/api";
import { useProjects } from "@/lib/useProjects";

/** `job_field`/`job_detail`/`years_segment` 중 있는 값만으로 합성한다 — 없는 값을
 * 지어내 "시니어" 같은 라벨을 붙이지 않는다 (CLAUDE.md 2.2 정신 — 프로필도 사실만). */
function formatTrackLabel(profile: Profile | null): string | null {
  if (!profile || !profile.job_field) return null;
  const parts = [profile.job_detail ?? profile.job_field];
  if (profile.years_segment) {
    parts.push(profile.years_segment === "10+" ? "10년 이상" : `${profile.years_segment}년차`);
  }
  return parts.join(" · ");
}

/**
 * 입력 화면 (`/`) — 제품에서 매일 쓰는 유일한 경로.
 *
 * "3초 만에 끝내고 모니터 끄기"가 슬로건이다 (CLAUDE.md 2.1). 텍스트 한 줄 →
 * 제출 버튼 외에는 아무 선택지도 없다. 프로젝트 스위처는 화면 상단에 있지만
 * 연 1~3회만 여는 바텀시트라 평소 입력 경로에 끼어들지 않는다.
 */
export default function HomePage() {
  const [rawText, setRawText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Card | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiedResult, setCopiedResult] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [profile, setProfile] = useState<Profile | null>(null);
  // ProjectSwitcher에 그대로 넘긴다 — 훅 인스턴스를 이 화면과 공유해야 전환이 즉시
  // 반영된다(구현 노트: components/ProjectSwitcher.tsx 9/14 참고).
  const projectsState = useProjects();

  // Figma "타깃 트랙" 행 — 연 1~3회 바꾸는 온보딩 프로필을 조회만 한다(2.1). 실패해도
  // 치명적이지 않으므로(행이 안 보일 뿐) 조용히 무시한다.
  useEffect(() => {
    let cancelled = false;
    getProfile()
      .then((p) => {
        if (!cancelled) setProfile(p);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // 텍스트 입력과 음성 입력이 공유하는 단일 제출 경로 — 어느 쪽에서 오든 동일한
  // 스켈레톤/결과 모달 UX를 탄다 (docs/06-migration.md §2.1: 별도 흐름을 만들지 않는다).
  const submitText = async (text: string) => {
    if (!text || submitting) return;

    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      // 응답이 3~10초 걸린다 (docs/05-api-contract.md §1) — 스켈레톤으로 대기 표시.
      const card = await createCard(text);
      setResult(card);
      setRawText("");
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

  const trackLabel = formatTrackLabel(profile);

  return (
    <div className="flex flex-col gap-3 px-5 pt-[6px]">
      {/* Header */}
      <div className="flex items-center gap-1 pb-[10px] pt-[8px]">
        <p className="text-[18px] font-bold text-[#18181b]">오늘의 기록</p>
        <div className="flex-1" />
        {/* Figma "⚙ 설정 → 5.0" 대응 — 연 1~3회만 건드리는 설정은 /onboarding으로 분리 (2.1) */}
        <Link
          href="/onboarding"
          aria-label="설정"
          className="flex size-[26px] items-center justify-center rounded-full bg-[#f4f4f5] text-xs text-[#6b7280] transition-colors hover:bg-[#e4e4e7] active:scale-[0.95]"
        >
          ⚙
        </Link>
      </div>

      {/* 타깃 트랙 (신규) — 온보딩 프로필 요약, 탭하면 /onboarding으로 수정하러 이동 */}
      <Link href="/onboarding" className="-mt-1 flex w-fit items-center gap-1 text-[13px]">
        {trackLabel ? (
          <span className="font-semibold text-[#6b7280]">{trackLabel}</span>
        ) : (
          <span className="font-medium text-[#a1a1aa]">직군 설정하기</span>
        )}
        <span className="text-[#a1a1aa]">›</span>
      </Link>

      <ProjectSwitcher projectsState={projectsState} />

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <div className="flex flex-col rounded-[14px] border-[1.5px] border-[#e5e7eb] bg-white px-[14px] pt-[14px] pb-[12px]">
          <textarea
            ref={textareaRef}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder="오늘 한 일을 한 줄로 남겨보세요"
            rows={4}
            className="w-full resize-none border-0 p-0 text-[13px] text-[#18181b] focus:outline-none"
          />
          <div className="flex items-end justify-end pt-2">
            <VoiceInput variant="icon" onTranscript={submitText} disabled={submitting} />
          </div>
        </div>

        <NotionImportButton />

        <button
          type="submit"
          disabled={submitting || !rawText.trim()}
          className="w-full rounded-[14px] bg-black py-[18px] text-[16px] font-semibold text-white transition-colors hover:bg-zinc-800 active:scale-[0.98] disabled:opacity-40 disabled:hover:bg-black"
        >
          {submitting ? "정리하는 중…" : "경력 변환하기"}
        </button>
      </form>

      {submitting && <CardResultSkeleton />}

      {error && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
      )}

      {/* 결과 출력 바텀시트 (Figma "3.1 결과 출력 모달") */}
      <BottomSheet
        open={!!result}
        onClose={handleCloseResult}
        hideHandle
        panelClassName="relative w-full max-w-md rounded-tl-[24px] rounded-tr-[24px] bg-white px-5 pt-3 pb-[30px] shadow-xl"
      >
        {result && (
          <div className="flex flex-col gap-3.5">
            <div className="flex items-center justify-end">
              <button
                type="button"
                onClick={handleCloseResult}
                aria-label="닫기"
                className="flex size-[38px] items-center justify-center rounded-full bg-[#f4f4f5] text-sm text-[#6b7280] transition-colors hover:bg-[#e4e4e7] active:scale-[0.95]"
              >
                ✕
              </button>
            </div>

            <p className="text-[12px] text-[#6b7280]">오늘 기록을 이렇게 정리했어요.</p>

            <div className="flex gap-3 rounded-[14px] bg-[#f4f4f5] px-4 py-[18px]">
              <div className="w-[3px] shrink-0 self-stretch rounded-full bg-black" />
              <p className="flex-1 text-[14px] font-medium text-[#18181b]">
                {result.refined_sentence}
              </p>
            </div>

            {result.skill_tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {result.skill_tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full bg-zinc-100 px-2.5 py-1 text-xs text-zinc-600"
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
                className="flex flex-1 items-center justify-center rounded-[12px] bg-black py-4 text-[14px] font-semibold text-white transition-colors hover:bg-zinc-800 active:scale-[0.98]"
              >
                {copiedResult ? "복사됨" : "복사"}
              </button>
              <button
                type="button"
                onClick={handleRetry}
                className="flex flex-1 items-center justify-center rounded-[12px] border-[1.5px] border-[#e5e7eb] bg-white py-4 text-[14px] font-semibold text-[#18181b] transition-colors hover:bg-zinc-50 active:scale-[0.98]"
              >
                다시 변환
              </button>
            </div>
          </div>
        )}
      </BottomSheet>
    </div>
  );
}

/**
 * "노션에서 가져오기" — 백엔드는 이미 지원하지만(`POST /api/notion/sync`) 프론트가
 * 없었던 기능 갭. 토큰 입력 + 동기화만 있는 최소 버전 (CLAUDE.md 2.4 — OAuth/페이지
 * 선택 UI는 만들지 않는다).
 */
function NotionImportButton() {
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const closeSheet = () => {
    setOpen(false);
    setToken("");
    setError(null);
    setSuccessMessage(null);
  };

  const handleSync = async () => {
    const trimmed = token.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    setError(null);
    setSuccessMessage(null);
    try {
      // 임포트되는 페이지 전부를 그때그때 파싱해서 느릴 수 있다 (docs/05-api-contract.md §5).
      const res = await syncNotion(trimmed);
      setSuccessMessage(`${res.imported}개 페이지를 가져왔어요.`);
      setToken("");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "노션 동기화에 실패했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center justify-center rounded-[10px] border border-[#e5e7eb] bg-white px-3 py-[10px] transition-colors hover:bg-zinc-50 active:scale-[0.98]"
      >
        <p className="text-[12px] font-medium text-[#6b7280]">노션에서 가져오기</p>
      </button>

      <BottomSheet open={open} onClose={closeSheet} title="노션에서 가져오기">
        <div className="flex flex-col gap-3">
          <p className="text-xs text-zinc-500">
            노션 통합(integration) 토큰을 입력하면 접근 가능한 페이지를 가져와 카드로
            저장해요. 페이지가 많으면 다소 걸릴 수 있어요.
          </p>
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="secret_..."
            autoComplete="off"
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
          />
          {error && <p className="text-xs text-red-600">{error}</p>}
          {successMessage && <p className="text-xs text-emerald-600">{successMessage}</p>}
          <button
            type="button"
            onClick={handleSync}
            disabled={submitting || !token.trim()}
            className="w-full rounded-xl bg-zinc-900 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-zinc-800 active:scale-[0.98] disabled:opacity-40 disabled:hover:bg-zinc-900"
          >
            {submitting ? "가져오는 중…" : "동기화"}
          </button>
        </div>
      </BottomSheet>
    </>
  );
}
