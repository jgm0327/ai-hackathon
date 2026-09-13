"use client";

import { FormEvent, useState } from "react";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { PushSetup } from "@/components/PushSetup";
import { CardResultSkeleton } from "@/components/Skeleton";
import { VoiceInput } from "@/components/VoiceInput";
import { ApiError, Card, createCard } from "@/lib/api";

/**
 * 입력 화면 (`/`) — 제품에서 매일 쓰는 유일한 경로.
 *
 * "3초 만에 끝내고 모니터 끄기"가 슬로건이다 (CLAUDE.md 2.1). 텍스트 한 줄 →
 * 제출 버튼 외에는 아무 선택지도 없다. 프로젝트 스위처는 화면 상단에 있지만
 * 연 1~3회만 여는 바텀시트라 평소 경로에 끼어들지 않는다.
 */
export default function HomePage() {
  const [rawText, setRawText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Card | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 텍스트 입력과 음성 입력이 공유하는 단일 제출 경로 — 어느 쪽에서 오든 동일한
  // 스켈레톤/결과 카드 UX를 탄다 (docs/06-migration.md §2.1: 별도 흐름을 만들지 않는다).
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

  return (
    <div className="flex flex-col gap-4 px-4 pt-4">
      <ProjectSwitcher />
      <PushSetup />

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <textarea
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
          placeholder="오늘 한 일을 한 줄로 남겨보세요. 예) 결제 API 느려서 레디스 캐시 붙임"
          rows={4}
          className="w-full resize-none rounded-xl border border-zinc-200 bg-white p-3 text-base shadow-sm focus:border-zinc-400 focus:outline-none"
        />
        <button
          type="submit"
          disabled={submitting || !rawText.trim()}
          className="w-full rounded-xl bg-zinc-900 py-3 text-base font-semibold text-white disabled:opacity-40"
        >
          {submitting ? "정리하는 중…" : "3초 만에 정리하기"}
        </button>
      </form>

      <VoiceInput onTranscript={submitText} disabled={submitting} />

      {submitting && <CardResultSkeleton />}

      {error && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
      )}

      {result && !submitting && (
        <div className="space-y-2 rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
          <p className="text-xs text-zinc-400">방금 남긴 기록</p>
          <p className="text-base leading-relaxed text-zinc-900">{result.refined_sentence}</p>
          <div className="flex flex-wrap gap-1.5 pt-1">
            {result.skill_tags.map((tag) => (
              <span key={tag} className="rounded-full bg-zinc-100 px-2.5 py-1 text-xs text-zinc-600">
                {tag}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
