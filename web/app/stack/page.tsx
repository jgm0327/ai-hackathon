"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { SkeletonLine } from "@/components/Skeleton";
import { ApiError, Card, deleteCard, listCards } from "@/lib/api";

function formatCardDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const mm = `${d.getMonth() + 1}`.padStart(2, "0");
  const dd = `${d.getDate()}`.padStart(2, "0");
  return `${mm}.${dd}`;
}

/** 커리어 스택 (`/stack`) — 카드 목록 + 태그 필터. */
export default function StackPage() {
  const [cards, setCards] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const list = await listCards();
        if (!cancelled) setCards(list);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.detail : "카드를 불러오지 못했습니다.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const tags = useMemo(() => {
    const set = new Set<string>();
    cards.forEach((c) => c.skill_tags.forEach((t) => set.add(t)));
    return Array.from(set);
  }, [cards]);

  const visibleCards = activeTag ? cards.filter((c) => c.skill_tags.includes(activeTag)) : cards;

  // ⋯ 메뉴 — 최소 기능: 확인 후 바로 삭제. 별도 액션 시트 없이 인라인으로 처리한다
  // (CLAUDE.md 2.1 정신 — 자주 안 쓰는 동작에 무거운 UI를 얹지 않는다).
  const handleDelete = async (id: number) => {
    setDeletingId(id);
    try {
      await deleteCard(id);
      setCards((prev) => prev.filter((c) => c.id !== id));
    } catch {
      setError("삭제에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setDeletingId(null);
      setConfirmId(null);
    }
  };

  return (
    <div className="flex flex-col gap-3 px-5 pt-[8px]">
      {/* Header */}
      <div className="flex items-center gap-[7px] pb-[8px]">
        <p className="text-[18px] font-bold text-[#18181b]">커리어 스택</p>
        {!loading && <p className="text-[14px] font-medium text-[#a1a1aa]">{cards.length}</p>}
        <div className="flex-1" />
        <Link
          href="/onboarding"
          aria-label="설정"
          className="flex size-[26px] items-center justify-center rounded-full bg-[#f4f4f5] text-xs text-[#6b7280] active:scale-[0.95]"
        >
          ⚙
        </Link>
      </div>

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-[7px]">
          <button
            type="button"
            onClick={() => setActiveTag(null)}
            className={`rounded-full px-3 py-[7px] text-[11px] font-medium ${
              activeTag === null
                ? "border border-black bg-black text-white"
                : "border border-[#e5e7eb] bg-white text-[#6b7280]"
            }`}
          >
            전체
          </button>
          {tags.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => setActiveTag(tag)}
              className={`rounded-full px-3 py-[7px] text-[11px] font-medium ${
                activeTag === tag
                  ? "border border-black bg-black text-white"
                  : "border border-[#e5e7eb] bg-white text-[#6b7280]"
              }`}
            >
              {tag}
            </button>
          ))}
        </div>
      )}

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

      {loading && (
        <div className="flex flex-col gap-[10px]">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="space-y-2 rounded-[12px] border border-[#e5e7eb] bg-white px-[14px] py-[13px]"
            >
              <SkeletonLine className="h-3 w-1/3" />
              <SkeletonLine className="h-4 w-full" />
            </div>
          ))}
        </div>
      )}

      {!loading && !error && visibleCards.length === 0 && (
        <p className="px-1 py-8 text-center text-sm text-zinc-400">아직 남긴 기록이 없습니다.</p>
      )}

      <ul className="flex flex-col gap-[10px]">
        {visibleCards.map((card) => (
          <li
            key={card.id}
            className="flex flex-col gap-2 rounded-[12px] border border-[#e5e7eb] bg-white px-[14px] py-[13px]"
          >
            <p className="text-[13px] font-medium text-[#18181b]">{card.refined_sentence}</p>
            <div className="flex items-center gap-2">
              <p className="text-[11px] text-[#a1a1aa]">{formatCardDate(card.created_at)}</p>
              {card.skill_tags[0] && (
                <p className="text-[11px] text-[#a1a1aa]">#{card.skill_tags[0]}</p>
              )}
              <div className="flex-1" />
              {confirmId === card.id ? (
                <div className="flex items-center gap-2.5">
                  <button
                    type="button"
                    onClick={() => handleDelete(card.id)}
                    disabled={deletingId === card.id}
                    className="text-[11px] font-medium text-red-600 disabled:opacity-50"
                  >
                    {deletingId === card.id ? "삭제 중…" : "삭제"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmId(null)}
                    className="text-[11px] text-[#a1a1aa]"
                  >
                    취소
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirmId(card.id)}
                  aria-label="카드 관리"
                  className="px-1 text-[13px] text-[#a1a1aa]"
                >
                  ⋯
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>

      <div className="pt-2 pb-4">
        <Link
          href="/resume"
          className="flex w-full items-center justify-center rounded-[14px] bg-black py-[17px] text-[15px] font-semibold text-white active:scale-[0.99]"
        >
          마스터 경력기술서 초안 짜기
        </Link>
      </div>
    </div>
  );
}
