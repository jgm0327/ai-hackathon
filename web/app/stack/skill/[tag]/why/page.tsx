"use client";

import Image from "next/image";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { SkeletonLine } from "@/components/Skeleton";
import { stackTheme as t } from "@/components/stackTheme";
import { Card, Profile, getProfile, listCards } from "@/lib/api";
import { CORE_COMPETENCIES } from "@/lib/coreCompetencies";
import { getCached, navKey, setCached } from "@/lib/navCache";
import { useProjects } from "@/lib/useProjects";

/** 서버의 `get_skill_category_counts()`가 태그 없는 카드에 붙이는 이름과 같아야 한다. */
const UNCATEGORIZED = "미분류";

/** 처음에 펼쳐 보여줄 근거 개수 (Figma는 3개 + "N개 더 보기"). */
const INITIAL_EVIDENCE = 3;

function shortDate(isoDate: string): string {
  const parts = isoDate.split("-");
  return parts.length === 3 ? `${parts[1]}.${parts[2]}` : isoDate;
}

/**
 * 대표 태그가 이 역량인 카드만. `/stack/skill/[tag]`·서버 `cards_with_skill_tag()`와
 * 같은 규칙이어야 개수가 어긋나지 않는다.
 */
function cardsWithTag(cards: Card[], tag: string): Card[] {
  if (tag === UNCATEGORIZED) return cards.filter((c) => c.skill_tags.length === 0);
  return cards.filter((c) => c.skill_tags[0] === tag);
}

/**
 * "4.1-l 역량 선정 근거" (Figma `303:16485`, 9/18 신규).
 *
 * 역량 상세(4.1-j)의 "왜 이 역량인가요 ›"로 들어온다. **AI가 왜 이 기록들을 이
 * 역량으로 묶었는지 사용자가 직접 확인하는 화면**이다 — 분류가 틀렸을 때 고칠 수
 * 있게(맨 아래 "분류 고치기") 하는 게 목적이다.
 *
 * **여기 나오는 것은 전부 실제 데이터다** (CLAUDE.md 2.2):
 * - 헤드라인의 기록 수 = 대표 태그가 이 역량인 카드 수
 * - 근거 목록 = 그 카드들의 실제 문장과 날짜
 * - 키워드 칩 = `parse_note()`가 그 기록에서 실제로 뽑은 `skill_tags`다. 4.1-h가
 *   "쓰신 기록의 키워드를 읽고 AI가 먼저 나눠뒀어요"라고 말하는 그 키워드가 이것이고,
 *   분류의 근거도 바로 이 값이다. 별도로 "매칭 단어"를 새로 계산하지 않는다 —
 *   계산해서 만들면 실제 분류 근거가 아닌 걸 근거라고 보여주는 셈이 된다.
 *
 * **"직군 기준" 카드에서 출처 문구는 뺐다.** 목업은 "원티드 직군별 채용 데이터 기준 ·
 * 9월 갱신"이라고 적지만 우리에겐 그 데이터가 없다 — 없는 출처를 적는 건 2.2 위반이고,
 * 사용자가 9/18에 "출처 문구는 빼고" 구현하도록 확정했다. 칩 목록은
 * `lib/coreCompetencies.ts`(우리가 구성한 목록)에서 온다.
 */
export default function SkillWhyPage() {
  const params = useParams<{ tag: string }>();
  const router = useRouter();
  const tag = decodeURIComponent(params.tag);

  const { currentProject, loading: projectsLoading } = useProjects();
  const cachedPid = currentProject?.id;

  const [cards, setCards] = useState<Card[] | null>(
    () => getCached<Card[]>(navKey.cards(cachedPid)) ?? null,
  );
  const [profile, setProfile] = useState<Profile | null>(
    () => getCached<Profile>(navKey.profile()) ?? null,
  );
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (projectsLoading) return;
    // 프로젝트가 없으면 미분류 카드를 포함해 전부 받는다 (9/18 수정 —
    // `app/page.tsx`의 같은 자리 주석 참고).
    const projectId = currentProject?.id;
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

  useEffect(() => {
    getProfile()
      .then((p) => {
        setCached(navKey.profile(), p);
        setProfile(p);
      })
      .catch(() => {});
  }, []);

  const matched = useMemo(() => cardsWithTag(cards ?? [], tag), [cards, tag]);
  const jobField = profile?.job_field ?? null;
  const coreList = jobField ? CORE_COMPETENCIES[jobField] ?? [] : [];

  const visible = expanded ? matched : matched.slice(0, INITIAL_EVIDENCE);
  const remaining = matched.length - visible.length;

  return (
    <div
      style={{ backgroundColor: t.screenBg, color: t.text }}
      className="flex min-h-full flex-col px-[22px] pt-[2px] pb-6"
    >
      {/* Header (303:16487) */}
      <div className="flex items-center gap-[10px] pb-[16px]">
        <button
          type="button"
          onClick={() => router.back()}
          aria-label="뒤로"
          className="flex size-[22px] items-center justify-center transition-opacity active:opacity-60"
        >
          <Image src="/icons/chevron-left.svg" alt="" width={20} height={20} aria-hidden />
        </button>
        <h1 className="truncate text-[20px] font-bold leading-[32px]">{tag}</h1>
      </div>

      <div className="flex flex-col pt-[24px]">
        <p style={{ color: t.textMuted }} className="text-[12px] font-medium leading-[20px]">
          이 역량으로 분류한 이유
        </p>

        {cards === null ? (
          <div className="mt-3 flex flex-col gap-3">
            <SkeletonLine />
            <SkeletonLine />
          </div>
        ) : (
          <>
            {/* 헤드라인 (303:16493) — 직군을 모르면 앞 절을 빼고 사실만 남긴다.
                없는 직군을 지어내지 않는다. */}
            <p className="mt-[12px] text-[20px] font-bold leading-[32px]">
              {jobField ? `${jobField} 직군에서 자주 요구되고,` : "쓰신 기록의 키워드를 읽고,"}
              <br />
              적어주신 기록 {matched.length}개가 여기에 모였어요
            </p>

            {/* 직군 기준 (303:16497) — 직군을 알 때만. 출처 문구는 뺐다(위 주석 참고). */}
            {coreList.length > 0 && (
              <>
                <p
                  style={{ color: t.textMuted }}
                  className="mt-[36px] text-[12px] font-medium leading-[20px]"
                >
                  직군 기준
                </p>
                <div
                  style={{ backgroundColor: t.cardBg }}
                  className="mt-[12px] flex flex-col gap-[12px] rounded-[12px] p-[16px]"
                >
                  <p style={{ color: t.textSoft }} className="text-[14px] leading-[24px]">
                    {jobField} 직군에서 자주 요구되는 역량 {coreList.length}개예요.
                  </p>
                  <div className="no-scrollbar -mx-[16px] flex gap-2 overflow-x-auto px-[16px]">
                    {coreList.map((name) => {
                      const current = name === tag;
                      return (
                        <span
                          key={name}
                          style={
                            current
                              ? { backgroundColor: t.border, color: t.text }
                              : { borderColor: t.border, color: t.textSoft }
                          }
                          className={`shrink-0 rounded-full px-[14px] py-[8px] text-[12px] leading-[20px] ${
                            current ? "font-bold" : "border font-medium"
                          }`}
                        >
                          {name}
                        </span>
                      );
                    })}
                  </div>
                </div>
              </>
            )}

            {/* 내 기록에서 찾은 근거 (303:16510) */}
            <div
              style={{ color: t.textMuted }}
              className="mt-[36px] flex items-center gap-2 text-[12px] font-medium leading-[20px]"
            >
              <p>내 기록에서 찾은 근거</p>
              <div className="flex-1" />
              <p>{matched.length}개</p>
            </div>

            {matched.length === 0 ? (
              <p style={{ color: t.textMuted }} className="mt-[12px] text-[14px] leading-[24px]">
                이 역량으로 묶인 기록이 아직 없어요.
              </p>
            ) : (
              <div className="mt-[12px] flex flex-col gap-[10px]">
                {visible.map((card) => {
                  // 대표 태그는 이 화면의 제목이라 칩으로 또 보여줄 이유가 없다.
                  // 나머지가 없으면 대표 태그 하나라도 보여준다 — 근거 칸이 비면
                  // "왜 이 역량인지"에 답하지 못한다.
                  const rest = card.skill_tags.filter((s) => s !== tag);
                  const keywords = rest.length > 0 ? rest : card.skill_tags;
                  return (
                    <Link
                      key={card.id}
                      href={`/stack/${card.id}`}
                      style={{ backgroundColor: t.cardBg }}
                      className="flex flex-col gap-[10px] rounded-[12px] p-[16px] transition-opacity active:opacity-80"
                    >
                      <span
                        style={{ color: t.textMuted }}
                        className="text-[12px] font-medium leading-[20px]"
                      >
                        {shortDate(card.created_at)}
                      </span>
                      <span className="text-[14px] leading-[24px]">{card.refined_sentence}</span>
                      {keywords.length > 0 && (
                        <span className="flex flex-wrap gap-[6px]">
                          {keywords.map((keyword) => (
                            <span
                              key={keyword}
                              style={{ backgroundColor: t.border, color: t.accentText }}
                              className="rounded-full px-[10px] py-[4px] text-[12px] font-medium leading-[20px]"
                            >
                              {keyword}
                            </span>
                          ))}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </div>
            )}

            {remaining > 0 && (
              <button
                type="button"
                onClick={() => setExpanded(true)}
                style={{ color: t.accentText }}
                className="mt-[12px] self-start text-[12px] font-medium leading-[20px]"
              >
                기록 {remaining}개 더 보기&nbsp;&nbsp;›
              </button>
            )}

            {/* 분류 고치기 진입 (303:16546) */}
            <Link
              href="/stack/classify"
              style={{ backgroundColor: t.cardBg }}
              className="mt-[36px] flex items-center gap-2 rounded-[12px] p-[16px] transition-opacity active:opacity-80"
            >
              <span className="text-[14px] font-medium leading-[24px]">이 분류가 안 맞나요?</span>
              <span className="flex-1" />
              <span
                style={{ color: t.accentText }}
                className="text-[12px] font-medium leading-[20px]"
              >
                분류 고치기&nbsp;&nbsp;›
              </span>
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
