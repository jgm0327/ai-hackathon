"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { stackTheme as t } from "@/components/stackTheme";
import { Card, SkillSummary, getSkillSummary, listCards } from "@/lib/api";
import { getCached, navKey, setCached } from "@/lib/navCache";
import { useProjects } from "@/lib/useProjects";

/** 역량 집계는 개수 제한 없이 전부 받는다 — 화면엔 "역량 N개"라는 총계만 쓴다. */
const SUMMARY_TOP_N = 50;

/** 최근 기록은 두 줄만 (Figma 303:15880 "최근 기록"). */
const RECENT_COUNT = 2;

function toDateKey(d: Date): string {
  const y = d.getFullYear();
  const m = `${d.getMonth() + 1}`.padStart(2, "0");
  const day = `${d.getDate()}`.padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function formatTodayLabel(): string {
  const d = new Date();
  return `${d.getMonth() + 1}월 ${d.getDate()}일  ·  오늘`;
}

/**
 * 최근 기록 줄의 날짜 라벨 — 오늘/어제는 이름으로, 그 이전은 날짜로.
 * 목업이 "어제"와 "9월 12일"을 나란히 쓴다(Figma 303:15884 / 303:15888).
 */
function relativeDateLabel(isoDate: string): string {
  const today = new Date();
  if (isoDate === toDateKey(today)) return "오늘";
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (isoDate === toDateKey(yesterday)) return "어제";
  const parts = isoDate.split("-");
  return parts.length === 3 ? `${Number(parts[1])}월 ${Number(parts[2])}일` : isoDate;
}

/**
 * 홈 — "3.0 홈 · 오늘 (입력 중심)" (Figma `303:15859`, 9/18 전면 재설계).
 *
 * **무엇이 바뀌었나**: 예전 홈은 입력창과 역량 버블과 오늘 목록을 한 화면에 쌓은
 * 대시보드였다. 새 목업은 그걸 **"오늘 뭘 했는지 묻는 화면"**으로 되돌린다 —
 * 큰 질문 한 줄, 지금까지 쌓인 숫자 셋, 최근 기록 두 줄, 그리고 맨 아래 알약 하나.
 * 실제로 쓰는 자리는 `/record`(3.3)로 분리됐다.
 *
 * **앱에서 유일하게 밝은 영역이 여기 있다**(누적 요약/최근 기록 패널). 검정 배경 위에
 * 크림색 블록을 얹어 "쌓인 것"을 물리적인 종이처럼 보이게 하는 의도로 읽힌다.
 * 색 토큰은 `components/stackTheme.ts`의 `light1`/`light2`/`onLight`/`lightRule`.
 *
 * 설정 진입과 프로젝트 스위처는 이 화면에서 빠졌다 — 둘 다 `/stack`에 있다(4.1-h).
 */
export default function HomePage() {
  const router = useRouter();
  const { currentProject, loading: projectsLoading } = useProjects();

  const cachedPid = currentProject?.id;
  // 탭을 옮겨 다시 들어올 때 빈 화면부터 다시 그리지 않도록 캐시에서 시작한다.
  const [summary, setSummary] = useState<SkillSummary | null>(
    () => (cachedPid ? getCached<SkillSummary>(navKey.skillSummary(cachedPid, SUMMARY_TOP_N)) ?? null : null),
  );
  const [cards, setCards] = useState<Card[] | null>(
    () => (cachedPid ? getCached<Card[]>(navKey.cards(cachedPid)) ?? null : null),
  );

  useEffect(() => {
    if (projectsLoading || !currentProject) return;
    const projectId = currentProject.id;
    let cancelled = false;

    getSkillSummary(projectId, SUMMARY_TOP_N)
      .then((next) => {
        setCached(navKey.skillSummary(projectId, SUMMARY_TOP_N), next);
        if (!cancelled) setSummary(next);
      })
      .catch(() => {});
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

  /**
   * "쓸 수 있는 문장" — 경력기술서에 그대로 쓸 만큼 구체적인 기록의 수.
   *
   * `confidence`가 낮으면(parse_note()가 "특정 업무 내용을 확인할 수 없음" 같은 모호한
   * 문장으로 정리했다는 뜻) 빼고 센다. 0.5 기준은 백엔드가 "모호함" 판정에 이미 쓰는
   * 것과 같다(`src/parsing/prompt_templates.py`). `/stack`의 같은 이름 값과 규칙이
   * 일치해야 두 화면의 숫자가 어긋나지 않는다.
   */
  const usableSentenceCount = useMemo(
    () => (cards ?? []).filter((c) => c.confidence >= 0.5).length,
    [cards],
  );

  // 카드 목록은 최신순으로 온다(서버 계약) — 앞에서 두 개만 쓴다.
  const recent = (cards ?? []).slice(0, RECENT_COUNT);

  return (
    <div
      style={{ backgroundColor: t.homeBg, color: t.text }}
      className="flex min-h-full flex-col"
    >
      {/* Header (303:15861) */}
      <div className="flex items-center px-[22px] pt-[4px] pb-[16px]">
        <p className="text-[16px] font-bold leading-[28px]">HEUNJEOG</p>
      </div>

      {/* 히어로 (303:15863) */}
      <div className="flex flex-col px-[22px] pt-[8px] pb-[28px]">
        <p className="text-[28px] font-bold leading-[40px]">
          오늘은
          <br />
          어떤 일을 하셨나요?
        </p>
        <p style={{ color: t.textMuted }} className="mt-[12px] text-[14px] leading-[24px]">
          한 줄이어도 괜찮아요
        </p>
      </div>

      {/* 오늘 배너 (303:15868) — 폭이 글자에 맞춰 잘리는 블록이라 self-start다. */}
      <div
        style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
        className="self-start pl-[22px] pr-[26px] py-[12px] text-[16px] font-bold leading-[28px]"
      >
        {formatTodayLabel()}
      </div>

      {/* 누적 요약 (303:15870) — 앱에서 유일한 라이트 영역. */}
      <div
        style={{ backgroundColor: t.light1, color: t.onLight }}
        className="flex px-[22px] pt-[16px] pb-[18px] text-center"
      >
        {[
          { label: "기록", value: summary?.total_cards ?? 0 },
          { label: "역량", value: summary?.categories.length ?? 0 },
          { label: "쓸 수 있는 문장", value: usableSentenceCount },
        ].map((stat) => (
          <div key={stat.label} className="flex flex-1 flex-col items-center gap-[2px]">
            <p className="w-full text-[12px] font-medium leading-[20px]">{stat.label}</p>
            <p className="w-full text-[32px] font-extralight leading-[44px]">{stat.value}</p>
          </div>
        ))}
      </div>

      {/* 최근 기록 (303:15880) — 기록이 하나도 없으면 패널 자체를 안 그린다.
          빈 패널은 "아직 없다"는 정보를 주는 게 아니라 그냥 빈 칸으로 읽힌다. */}
      {recent.length > 0 && (
        <div
          style={{ backgroundColor: t.light2, color: t.onLight }}
          className="flex flex-col px-[22px] py-[24px]"
        >
          <div className="flex items-center gap-2">
            <p className="flex-1 text-[12px] font-medium leading-[20px]">최근 기록</p>
            {/* 전체 보기(3.2)로 가는 유일한 진입점이다 — 홈은 두 줄만 보여준다. */}
            <Link href="/records" className="text-[12px] font-medium leading-[20px] underline">
              전체 보기
            </Link>
          </div>
          <div className="mt-[8px] flex flex-col">
            {recent.map((card, i) => (
              <Link
                key={card.id}
                href={`/stack/${card.id}`}
                className={`flex gap-[14px] py-[14px] transition-opacity active:opacity-70 ${
                  i > 0 ? "border-t" : ""
                }`}
                style={i > 0 ? { borderColor: t.lightRule } : undefined}
              >
                <span className="w-[52px] shrink-0 text-[12px] font-medium leading-[20px]">
                  {relativeDateLabel(card.created_at)}
                </span>
                <span className="flex-1 text-[14px] leading-[24px]">{card.refined_sentence}</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* 기록이 하나도 없을 때만 — 숫자 0 셋만 덩그러니 놓이지 않게 한 줄 안내한다. */}
      {cards !== null && cards.length === 0 && (
        <p
          style={{ color: t.textMuted }}
          className="px-[22px] pt-[24px] text-[14px] leading-[24px]"
        >
          아래에 한 줄만 남기면 여기부터 쌓이기 시작해요.
        </p>
      )}

      <div className="min-h-[40px] flex-1" />

      {/* 입력 영역 (303:15891) — 알약을 누르면 실제로 쓰는 화면(3.3)으로 간다.
          마이크는 같은 화면으로 가되 음성으로 바로 시작한다. */}
      <div className="flex flex-col px-[22px] pb-[20px] pt-[12px]">
        <div
          style={{ backgroundColor: t.cardBg }}
          className="flex items-center gap-[10px] rounded-full pl-[20px] pr-[10px] py-[10px]"
        >
          <button
            type="button"
            onClick={() => router.push("/record")}
            style={{ color: t.textSoft }}
            className="flex-1 text-left text-[14px] leading-[24px]"
          >
            오늘 뭐 하셨어요?
          </button>
          <button
            type="button"
            onClick={() => router.push("/record?voice=1")}
            aria-label="음성으로 기록하기"
            style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
            className="flex size-[36px] shrink-0 items-center justify-center rounded-full text-[15px] transition-opacity active:opacity-80"
          >
            🎙
          </button>
        </div>
      </div>
    </div>
  );
}
