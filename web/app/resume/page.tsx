"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StarItemSection, formatStarItemForClipboard } from "@/components/StarItemCard";
import { StarItemSkeleton } from "@/components/Skeleton";
import { ApiError, Profile, StarItem, getResumeDraft, getProfile, saveResumeDraft } from "@/lib/api";
import { buildResumeCached, peekCachedResume } from "@/lib/resumeCache";
import { useProjects } from "@/lib/useProjects";

/** 프로필/프로젝트에서 실제로 있는 값만으로 문서 제목을 만든다 — 없는 정보를
 * 지어내 요약 문단을 만들지 않는다(CLAUDE.md 2.2). `build_resume()`은 제목/요약을
 * 생성하지 않으므로 여기서 조합 가능한 값만 쓴다. */
function buildResumeHeading(profile: Profile | null, projectName: string | null): string | null {
  if (profile?.job_field) {
    const parts = [profile.job_detail ?? profile.job_field];
    if (profile.years_segment) {
      parts.push(profile.years_segment === "10+" ? "10년 이상" : `${profile.years_segment}년차`);
    }
    return parts.join(" · ");
  }
  return projectName;
}

/** STAR 항목 한 건을 마크다운 섹션으로. 클립보드 복사 포맷과 동일한 본문을 재사용해
 * 두 곳에서 STAR→텍스트 변환 로직이 갈라지지 않게 한다. */
function toMarkdownSection(item: StarItem): string {
  const [header, ...rest] = formatStarItemForClipboard(item).split("\n");
  return [`## ${header}`, ...rest].join("\n");
}

function buildResumeMarkdown(heading: string | null, items: StarItem[]): string {
  const parts: string[] = [];
  if (heading) parts.push(`# ${heading}`);
  parts.push(...items.map(toMarkdownSection));
  return parts.join("\n\n");
}

/** 저장 시각(ISO)을 "9월 14일 21:05" 형태로. 유효하지 않으면 원본 문자열 그대로. */
function formatSavedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

/**
 * 경력기술서 빌더 (`/resume`) — 이직 준비 경로. 무거운 호출이라 로딩 표시가 중요하다
 * (`docs/02-architecture.md` §2.2 — 입력 200토큰/150토큰짜리 매일 경로와 달리
 * 여기는 2,500/2,000토큰짜리 호출).
 *
 * Figma "4.2 경력기술서 빌더"는 STAR 항목들을 카드로 나열하지 않고 제목+요약 →
 * 항목별 라벨 행(상황/과제/행동/결과)이 이어지는 하나의 문서로 보여준다. 문서
 * 요약 문단은 `build_resume()`이 만들지 않는 데이터라 생성하지 않는다.
 *
 * **구현 노트 (9/14, 직접 편집+저장 추가)**: 사용자 요청 — "AI 초안을 계속 직접
 * 수정하면서 개선하는 게 낫지 않아?" 이건 AI가 만든 StarItem *구조*를 저장하는
 * 것과 다른 문제라고 판단해서 진행함(CLAUDE.md 3장이 막는 건 "AI 그룹핑을 정식
 * 데이터로 저장"이지, "유저가 그 결과를 가져다 직접 고친 자유 텍스트를 저장"이
 * 아니다 — 한 번 유저가 고치기 시작하면 카드 구조와 더 이상 엮여 있을 필요가
 * 없어서 재검증/재동기화 문제 자체가 안 생긴다). 간단한 버전으로 구현 — 항목별
 * 구조화 편집이 아니라 마크다운 텍스트 전체를 한 덩어리로 편집/저장한다.
 * `mode`가 "ai"(AI가 만든 구조화된 뷰 + 재생성)와 "edit"(자유 텍스트 편집 + 저장)를
 * 오간다. 저장된 초안이 있으면 마운트 시점에 서버에서 우선 불러와 "edit" 모드로
 * 바로 진입한다(AI 로컬 캐시 복원보다 우선 — 유저가 명시적으로 저장한 게 더
 * 신뢰할 수 있는 최신 버전이라서).
 */
export default function ResumePage() {
  const { currentProject, loading: projectsLoading } = useProjects();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [jdText, setJdText] = useState("");
  const [items, setItems] = useState<StarItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showBuildForm, setShowBuildForm] = useState(true);
  const [copyStatus, setCopyStatus] = useState<"markdown" | "notion" | null>(null);

  const [mode, setMode] = useState<"ai" | "edit">("ai");
  const [draftContent, setDraftContent] = useState("");
  const [draftUpdatedAt, setDraftUpdatedAt] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"saved" | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);

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

  // 프로젝트를 바꾸면 이전 프로젝트 기준으로 보던 내용은 더 이상 유효하지 않다 —
  // /stack의 프로젝트 전환 리셋과 동일한 이유(9/14).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setItems(null);
    setShowBuildForm(true);
    setMode("ai");
    setDraftContent("");
    setDraftUpdatedAt(null);
    setError(null);
    setDraftError(null);
  }, [currentProject?.id]);

  // 새로고침해도 방금 만든 경력기술서가 사라진 것처럼 보이지 않게, 마운트 시점에
  // 캐시(네트워크 호출 없음)를 먼저 들여다보고 있으면 즉시 복원한다 (9/14, 사용자
  // 지적 — web/lib/resumeCache.ts의 peekCachedResume() 참고). 카드 구성이 그 사이
  // 바뀌었을 수도 있는 낡은 값일 수 있는데, "다시 만들기"를 누르면 그때 정상
  // 검증된다.
  useEffect(() => {
    if (!currentProject) return;
    const cached = peekCachedResume(currentProject.id);
    if (cached) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setItems(cached);
      setShowBuildForm(false);
    }
  }, [currentProject]);

  // 서버에 저장된 초안이 있으면 위 AI 캐시 복원보다 우선해서 편집 모드로 바로
  // 들어간다 — 유저가 명시적으로 저장한 버전이 가장 신뢰할 수 있는 최신본이므로.
  useEffect(() => {
    if (!currentProject) return;
    let cancelled = false;
    getResumeDraft(currentProject.id)
      .then((draft) => {
        if (cancelled || !draft.content) return;
        setDraftContent(draft.content);
        setDraftUpdatedAt(draft.updated_at);
        setMode("edit");
        setShowBuildForm(false);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [currentProject]);

  const handleBuild = async () => {
    if (!currentProject) return;
    setLoading(true);
    setError(null);
    try {
      // 카드 구성이 지난 생성 때와 같으면 재호출 없이 캐시에서 반환한다 (9/14, LLM
      // 호출 비용 절감 — web/lib/resumeCache.ts 참고).
      const result = await buildResumeCached(currentProject.id, { jdText: jdText.trim() || undefined });
      setItems(result);
      setShowBuildForm(false);
      setMode("ai");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "경력기술서 생성에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const heading = buildResumeHeading(profile, currentProject?.name ?? null);

  const handleCopy = async (kind: "markdown" | "notion") => {
    const text = mode === "edit" ? draftContent : items ? buildResumeMarkdown(heading, items) : "";
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopyStatus(kind);
      setTimeout(() => setCopyStatus(null), 1500);
    } catch {
      // 클립보드 접근 실패 — 조용히 무시
    }
  };

  const startEditing = () => {
    if (items) setDraftContent(buildResumeMarkdown(heading, items));
    setMode("edit");
  };

  const handleSaveDraft = async () => {
    if (!currentProject) return;
    setSaving(true);
    setDraftError(null);
    try {
      const saved = await saveResumeDraft(currentProject.id, draftContent);
      setDraftUpdatedAt(saved.updated_at);
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus(null), 1500);
    } catch (err) {
      setDraftError(err instanceof ApiError ? err.detail : "저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 px-5 pb-8">
      <div className="flex items-center gap-[10px] pb-[6px] pt-[8px]">
        <Link href="/stack" aria-label="뒤로" className="text-[17px] text-[#18181b]">
          ←
        </Link>
      </div>

      <p className="text-sm text-zinc-500">
        {projectsLoading
          ? "프로젝트를 불러오는 중…"
          : currentProject
            ? `현재 프로젝트: ${currentProject.name}`
            : "먼저 입력 화면에서 프로젝트를 선택해 주세요."}
      </p>

      {mode === "edit" ? (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-zinc-500">
              직접 수정 중 — 저장하면 다음에 열 때도 그대로 보입니다.
              {draftUpdatedAt && (
                <span className="block text-[11px] text-zinc-400">
                  마지막 저장: {formatSavedAt(draftUpdatedAt)}
                </span>
              )}
            </p>
            <button
              type="button"
              onClick={() => setMode("ai")}
              className="shrink-0 text-xs font-medium text-zinc-500 underline underline-offset-2"
            >
              AI 초안으로 돌아가기
            </button>
          </div>
          <textarea
            value={draftContent}
            onChange={(e) => setDraftContent(e.target.value)}
            rows={16}
            className="w-full resize-y rounded-[14px] border border-[#e5e7eb] bg-white p-4 text-[13px] leading-relaxed shadow-sm focus:border-zinc-400 focus:outline-none"
          />
          {draftError && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{draftError}</p>}
          <div className="flex flex-col gap-[10px] rounded-[14px] border border-[#e5e7eb] bg-white p-4">
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleSaveDraft}
                disabled={saving}
                className="flex flex-1 items-center justify-center rounded-[11px] bg-zinc-900 py-[13px] text-[12px] font-semibold text-white transition-colors hover:bg-zinc-800 disabled:opacity-40"
              >
                {saving ? "저장 중…" : saveStatus === "saved" ? "저장됨" : "저장"}
              </button>
              <button
                type="button"
                onClick={() => handleCopy("markdown")}
                className="flex flex-1 items-center justify-center rounded-[11px] border-[1.5px] border-[#e5e7eb] bg-white py-[13px] text-[12px] font-semibold text-[#18181b] transition-colors hover:bg-zinc-50"
              >
                {copyStatus === "markdown" ? "복사됨" : "마크다운"}
              </button>
              <button
                type="button"
                onClick={() => handleCopy("notion")}
                className="flex flex-1 items-center justify-center rounded-[11px] border-[1.5px] border-[#e5e7eb] bg-white py-[13px] text-[12px] font-semibold text-[#18181b] transition-colors hover:bg-zinc-50"
              >
                {copyStatus === "notion" ? "복사됨" : "노션 복사"}
              </button>
            </div>
            <Link href="/" className="text-center text-[11px] text-[#a1a1aa]">
              다시 기록하러 가기 ↩
            </Link>
          </div>
        </div>
      ) : (
        <>
          {(!items || showBuildForm) && (
            <div className="flex flex-col gap-3 rounded-[14px] border border-[#e5e7eb] bg-white p-4">
              <textarea
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
                placeholder="채용공고 본문을 붙여넣으면 맞춰서 재구성해 드려요 (선택)"
                rows={4}
                className="w-full resize-none rounded-xl border border-zinc-200 bg-white p-3 text-sm shadow-sm focus:border-zinc-400 focus:outline-none"
              />
              <button
                type="button"
                onClick={handleBuild}
                disabled={!currentProject || loading}
                className="w-full rounded-xl bg-zinc-900 py-3 text-base font-semibold text-white transition-colors hover:bg-zinc-800 disabled:opacity-40 disabled:hover:bg-zinc-900"
              >
                {loading ? "경력기술서 만드는 중… (최대 10초)" : "경력기술서 만들기"}
              </button>
            </div>
          )}

          {items && !showBuildForm && (
            <div className="flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => setShowBuildForm(true)}
                className="text-xs font-medium text-zinc-500 underline underline-offset-2"
              >
                JD를 바꿔 다시 만들기
              </button>
              {items.length > 0 && (
                <button
                  type="button"
                  onClick={startEditing}
                  className="text-xs font-medium text-zinc-900 underline underline-offset-2"
                >
                  직접 수정하기 ✎
                </button>
              )}
            </div>
          )}

          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

          {loading && (
            <div className="flex flex-col gap-3">
              <StarItemSkeleton />
              <StarItemSkeleton />
            </div>
          )}

          {items && !loading && (
            <>
              {items.length === 0 ? (
                <p className="px-1 py-8 text-center text-sm text-zinc-400">
                  아직 STAR로 묶을 만한 기록이 없습니다.
                </p>
              ) : (
                <div className="flex flex-col rounded-[14px] border border-[#e5e7eb] bg-white p-5">
                  {heading && (
                    <>
                      <p className="text-[16px] font-bold text-[#18181b]">{heading}</p>
                      <div className="my-3 h-px w-full bg-[#e5e7eb]" />
                    </>
                  )}
                  {items.map((item, i) => (
                    <div key={`${item.title}-${i}`}>
                      <StarItemSection item={item} />
                      {i < items.length - 1 && <div className="h-px w-full bg-[#e5e7eb]" />}
                    </div>
                  ))}
                </div>
              )}

              {items.length > 0 && (
                <div className="flex flex-col gap-[10px] rounded-[14px] border border-[#e5e7eb] bg-white p-4">
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled
                      title="Word(.docx) 내보내기는 아직 준비 중이에요"
                      className="flex flex-1 cursor-not-allowed flex-col items-center justify-center gap-0.5 rounded-[11px] bg-zinc-200 py-[13px] text-zinc-400"
                    >
                      <span className="text-[12px] font-semibold">Word</span>
                      <span className="text-[9px]">준비 중</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleCopy("markdown")}
                      className="flex flex-1 items-center justify-center rounded-[11px] border-[1.5px] border-[#e5e7eb] bg-white py-[13px] text-[12px] font-semibold text-[#18181b] transition-colors hover:bg-zinc-50"
                    >
                      {copyStatus === "markdown" ? "복사됨" : "마크다운"}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleCopy("notion")}
                      className="flex flex-1 items-center justify-center rounded-[11px] border-[1.5px] border-[#e5e7eb] bg-white py-[13px] text-[12px] font-semibold text-[#18181b] transition-colors hover:bg-zinc-50"
                    >
                      {copyStatus === "notion" ? "복사됨" : "노션 복사"}
                    </button>
                  </div>
                  <Link href="/" className="text-center text-[11px] text-[#a1a1aa]">
                    다시 기록하러 가기 ↩
                  </Link>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
