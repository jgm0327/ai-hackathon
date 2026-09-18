"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, useEffect } from "react";
import { SkeletonLine } from "@/components/Skeleton";
import { stackTheme as t } from "@/components/stackTheme";
import { Card, listCards } from "@/lib/api";
import { getCached, navKey, setCached } from "@/lib/navCache";
import { useProjects } from "@/lib/useProjects";

/**
 * 필터 칩 (Figma `299:12049` 3.2 "내 기록").
 *
 * 전부 **이미 카드에 있는 값으로만** 판정한다 — 추가 조회도, LLM도 없다.
 * - 변환 전: 원문 그대로 저장된 것(`refined_sentence === raw_text`). 변환이 실패해
 *   폴백 저장된 카드가 여기 잡힌다(`refinement_failed`는 생성 시점 전용 플래그라
 *   목록 응답엔 안 실린다 — 그래서 문장 비교로 본다).
 * - 미분류: 역량 태그가 하나도 없는 것.
 * - 수치 없음: 문장에 숫자가 하나도 없는 것(3.1-n과 같은 규칙).
 */
type Filter = "all" | "unconverted" | "untagged" | "no-metric";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "unconverted", label: "변환 전" },
  { key: "untagged", label: "미분류" },
  { key: "no-metric", label: "수치 없음" },
];

function matchesFilter(card: Card, filter: Filter): boolean {
  switch (filter) {
    case "unconverted":
      return card.refined_sentence.trim() === card.raw_text.trim();
    case "untagged":
      return card.skill_tags.length === 0;
    case "no-metric":
      return !/\d/.test(card.refined_sentence);
    default:
      return true;
  }
}

function toDateKey(d: Date): string {
  const y = d.getFullYear();
  const m = `${d.getMonth() + 1}`.padStart(2, "0");
  const day = `${d.getDate()}`.padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** "2026-09-15" → "09.15" (+ 오늘이면 " 오늘"). */
function dateLabel(isoDate: string): string {
  const parts = isoDate.split("-");
  const short = parts.length === 3 ? `${parts[1]}.${parts[2]}` : isoDate;
  return isoDate === toDateKey(new Date()) ? `${short} 오늘` : short;
}

/**
 * "3.2 내 기록 (전체 보기)" (Figma `299:12049`, 9/18 신규).
 *
 * 홈(3.0)이 최근 두 줄만 보여주게 되면서, **전부 훑어보는 자리**가 이 화면으로
 * 분리됐다. 홈의 "최근 기록"에서, 그리고 기록 탭에서 들어온다.
 *
 * 필터는 "손봐야 할 것"을 찾는 용도다 — 변환 전(실패해서 원문만 남은 것), 미분류
 * (역량이 안 붙은 것), 수치 없음(숫자가 빠져 면접에서 약한 것). 셋 다 **이미 받아온
 * 카드로만** 판정하므로 칩을 눌러도 서버를 다시 부르지 않는다(CLAUDE.md 2.1).
 */
export default function RecordsPage() {
  const router = useRouter();
  const { currentProject, loading: projectsLoading } = useProjects();

  const cachedPid = currentProject?.id;
  const [cards, setCards] = useState<Card[] | null>(
    () => (cachedPid ? getCached<Card[]>(navKey.cards(cachedPid)) ?? null : null),
  );
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    if (projectsLoading || !currentProject) return;
    const projectId = currentProject.id;
    let cancelled = false;
    listCards(projectId)
      .then((list) => {
        setCached(navKey.cards(projectId), list);
        if (!cancelled) setCards(list);
      })
      .catch(() => {
        if (!cancelled) setCards([]);
      });
    return () => {
      cancelled = true;
    };
  }, [projectsLoading, currentProject]);

  const visible = useMemo(
    () => (cards ?? []).filter((card) => matchesFilter(card, filter)),
    [cards, filter],
  );

  return (
    <div
      style={{ backgroundColor: t.screenBg, color: t.text }}
      className="flex min-h-full flex-col px-[22px] pt-[2px] pb-6"
    >
      {/* Header */}
      <div className="flex items-center gap-[10px] pb-[16px]">
        <button
          type="button"
          onClick={() => router.back()}
          aria-label="뒤로"
          className="flex size-[22px] items-center justify-center transition-opacity active:opacity-60"
        >
          <Image src="/icons/chevron-left.svg" alt="" width={20} height={20} aria-hidden />
        </button>
        <h1 className="text-[20px] font-bold leading-[32px]">내 기록</h1>
        <div className="flex-1" />
        {cards !== null && (
          <p style={{ color: t.textMuted }} className="text-[12px] leading-[20px]">
            {cards.length}
          </p>
        )}
      </div>

      {/* 필터 칩 (299:12053) */}
      <div className="no-scrollbar -mx-[22px] flex gap-2 overflow-x-auto px-[22px] pb-[20px] pt-[8px]">
        {FILTERS.map(({ key, label }) => {
          const active = filter === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              aria-pressed={active}
              style={{
                backgroundColor: active ? t.cardBg : "transparent",
                borderColor: active ? t.cardBg : t.border,
                color: active ? t.text : t.textSoft,
              }}
              className="shrink-0 rounded-full border px-[16px] py-[9px] text-[12px] font-medium leading-[20px] transition-opacity active:opacity-70"
            >
              {label}
            </button>
          );
        })}
      </div>

      {cards === null ? (
        <div className="flex flex-col gap-3">
          <SkeletonLine />
          <SkeletonLine />
          <SkeletonLine />
        </div>
      ) : visible.length === 0 ? (
        <p style={{ color: t.textMuted }} className="py-10 text-center text-[14px] leading-[24px]">
          {filter === "all"
            ? "아직 남긴 기록이 없어요."
            : "이 조건에 해당하는 기록이 없어요."}
        </p>
      ) : (
        <div className="flex flex-col gap-[10px]">
          {visible.map((card) => {
            const unconverted = matchesFilter(card, "unconverted");
            const noMetric = matchesFilter(card, "no-metric");
            return (
              <Link
                key={card.id}
                href={`/stack/${card.id}`}
                style={{ backgroundColor: t.cardBg }}
                className="flex flex-col gap-[10px] rounded-[12px] px-[16px] py-[18px] transition-opacity active:opacity-80"
              >
                <span className="flex items-center gap-2">
                  <span
                    style={{ color: t.textSoft }}
                    className="text-[12px] leading-[20px]"
                  >
                    {dateLabel(card.created_at)}
                  </span>
                  <span className="flex-1" />
                  {/* 상태 배지는 "손봐야 할 것"만 붙인다 — 멀쩡한 기록에 배지를 달면
                      목록이 배지밭이 되어 오히려 눈에 안 들어온다. */}
                  {unconverted && (
                    <span
                      style={{ borderColor: t.border, color: t.textSoft }}
                      className="rounded-full border px-[10px] py-[3px] text-[11px] leading-[18px]"
                    >
                      변환 전
                    </span>
                  )}
                  {noMetric && !unconverted && (
                    <span
                      style={{ borderColor: t.border, color: t.textSoft }}
                      className="rounded-full border px-[10px] py-[3px] text-[11px] leading-[18px]"
                    >
                      수치 없음
                    </span>
                  )}
                  {card.skill_tags[0] && (
                    <span
                      style={{ color: t.accentText }}
                      className="text-[12px] font-medium leading-[20px]"
                    >
                      {card.skill_tags[0]} ›
                    </span>
                  )}
                </span>
                <span className="text-[14px] leading-[24px]">{card.refined_sentence}</span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
