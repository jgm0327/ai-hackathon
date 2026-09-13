"use client";

import { useEffect, useMemo, useState } from "react";
import { SkeletonLine } from "@/components/Skeleton";
import { ApiError, Card, listCards } from "@/lib/api";

/** 커리어 스택 (`/stack`) — 카드 목록 + 태그 필터. */
export default function StackPage() {
  const [cards, setCards] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTag, setActiveTag] = useState<string | null>(null);

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

  return (
    <div className="flex flex-col gap-4 px-4 pt-4">
      <h1 className="text-lg font-semibold">커리어 스택</h1>

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setActiveTag(null)}
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              activeTag === null ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-600"
            }`}
          >
            전체
          </button>
          {tags.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => setActiveTag(tag)}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                activeTag === tag ? "bg-zinc-900 text-white" : "bg-zinc-100 text-zinc-600"
              }`}
            >
              {tag}
            </button>
          ))}
        </div>
      )}

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

      {loading && (
        <div className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="space-y-2 rounded-xl border border-zinc-200 bg-white p-4">
              <SkeletonLine className="h-3 w-1/3" />
              <SkeletonLine className="h-4 w-full" />
            </div>
          ))}
        </div>
      )}

      {!loading && !error && visibleCards.length === 0 && (
        <p className="px-1 py-8 text-center text-sm text-zinc-400">아직 남긴 기록이 없습니다.</p>
      )}

      <ul className="flex flex-col gap-3">
        {visibleCards.map((card) => (
          <li key={card.id} className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
            <p className="text-xs text-zinc-400">
              {new Date(card.created_at).toLocaleDateString("ko-KR")}
            </p>
            <p className="mt-1 text-sm leading-relaxed text-zinc-900">{card.refined_sentence}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {card.skill_tags.map((tag) => (
                <span key={tag} className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
                  {tag}
                </span>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
