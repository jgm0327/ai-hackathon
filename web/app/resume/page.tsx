"use client";

import { useState } from "react";
import { StarItemCard, formatStarItemForClipboard } from "@/components/StarItemCard";
import { StarItemSkeleton } from "@/components/Skeleton";
import { ApiError, StarItem, buildResume } from "@/lib/api";
import { useProjects } from "@/lib/useProjects";

/**
 * 경력기술서 빌더 (`/resume`) — 이직 준비 경로. 무거운 호출이라 로딩 표시가 중요하다
 * (`docs/02-architecture.md` §2.2 — 입력 200토큰/150토큰짜리 매일 경로와 달리
 * 여기는 2,500/2,000토큰짜리 호출).
 */
export default function ResumePage() {
  const { currentProject, loading: projectsLoading } = useProjects();
  const [jdText, setJdText] = useState("");
  const [items, setItems] = useState<StarItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedAll, setCopiedAll] = useState(false);

  const handleBuild = async () => {
    if (!currentProject) return;
    setLoading(true);
    setError(null);
    try {
      const result = await buildResume(currentProject.id, jdText.trim() || undefined);
      setItems(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "경력기술서 생성에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const handleCopyAll = async () => {
    if (!items || items.length === 0) return;
    try {
      await navigator.clipboard.writeText(items.map(formatStarItemForClipboard).join("\n\n"));
      setCopiedAll(true);
      setTimeout(() => setCopiedAll(false), 1500);
    } catch {
      // 클립보드 접근 실패 — 조용히 무시
    }
  };

  return (
    <div className="flex flex-col gap-4 px-4 pt-4">
      <h1 className="text-lg font-semibold">경력기술서</h1>

      <p className="text-sm text-zinc-500">
        {projectsLoading
          ? "프로젝트를 불러오는 중…"
          : currentProject
            ? `현재 프로젝트: ${currentProject.name}`
            : "먼저 입력 화면에서 프로젝트를 선택해 주세요."}
      </p>

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
        className="w-full rounded-xl bg-zinc-900 py-3 text-base font-semibold text-white disabled:opacity-40"
      >
        {loading ? "경력기술서 만드는 중… (최대 10초)" : "경력기술서 만들기"}
      </button>

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

      {loading && (
        <div className="flex flex-col gap-3">
          <StarItemSkeleton />
          <StarItemSkeleton />
        </div>
      )}

      {items && !loading && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-zinc-500">{items.length}개 항목</p>
            {items.length > 0 && (
              <button
                type="button"
                onClick={handleCopyAll}
                className="rounded-full border border-zinc-200 px-3 py-1 text-xs text-zinc-600"
              >
                {copiedAll ? "전체 복사됨" : "전체 복사"}
              </button>
            )}
          </div>

          {items.length === 0 ? (
            <p className="px-1 py-8 text-center text-sm text-zinc-400">
              아직 STAR로 묶을 만한 기록이 없습니다.
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              {items.map((item, i) => (
                <StarItemCard key={`${item.title}-${i}`} item={item} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
