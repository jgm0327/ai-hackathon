"use client";

import Image from "next/image";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { SkeletonLine } from "@/components/Skeleton";
import { Toast, useToast } from "@/components/Toast";
import { stackTheme as t } from "@/components/stackTheme";
import {
  ApiError,
  Card,
  Profile,
  StarItem,
  buildResume,
  getProfile,
  listCards,
  photoUrl,
  currentProjectScope,
} from "@/lib/api";
import { COMPETENCY_EXAMPLES } from "@/lib/coreCompetencies";
import { getCached, navKey, setCached } from "@/lib/navCache";
import { useProjects } from "@/lib/useProjects";

/** 서버의 `get_skill_category_counts()`가 태그 없는 카드에 붙이는 이름과 같아야 한다. */
const UNCATEGORIZED = "미분류";

function formatCardDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
}

/**
 * 대표 태그가 이 역량인 카드만 고른다.
 *
 * **대표 태그(`skill_tags[0]`) 하나로만 판정한다** — 서버의 역량 집계
 * (`get_skill_category_counts`)와 규칙이 같아야, 목록에 "8"이라고 적힌 역량을
 * 눌렀을 때 여기 기록이 8개 나온다. 태그 배열 전체를 훑으면 카드 한 장이 여러
 * 역량에 중복으로 잡혀서 숫자가 안 맞는다. (서버 `cards_with_skill_tag()`와 동일)
 */
function cardsWithTag(cards: Card[], tag: string): Card[] {
  if (tag === UNCATEGORIZED) return cards.filter((c) => c.skill_tags.length === 0);
  return cards.filter((c) => c.skill_tags[0] === tag);
}

/**
 * "4.1-j 역량 상세" + "4.1-k 역량 상세 · 기록 없음"
 * (Figma "03 · 커리어 스택" `301:15249` / `301:15299`, 9/18 신규).
 *
 * `/stack`의 역량 리스트에서 `›`로 들어온다. 기록이 있으면 4.1-j(문장 + 쌓인 기록 +
 * "이 역량으로 문장 만들기"), 없으면 4.1-k(왜 비어 있는지 + 예시 + "이 역량으로
 * 기록하기")다. 역량 공백 경고에서 들어오면 보통 후자다.
 *
 * **"이 역량으로 쓸 수 있는 문장"은 저장하지 않는다.** 누를 때마다 `build_resume()`이
 * 다시 묶는다(CLAUDE.md 3장 — AI가 만든 묶음은 DB에 넣지 않는다). 서버는 **프로젝트별로
 * 나눠서** 부르므로 같은 역량이라도 A은행과 B카드가 섞이지 않는다.
 */
export default function SkillDetailPage() {
  const params = useParams<{ tag: string }>();
  const router = useRouter();
  const tag = decodeURIComponent(params.tag);

  const projectsState = useProjects();
  const { currentProject, loading: projectsLoading } = projectsState;

  const cachedPid = currentProject?.id;
  const [cards, setCards] = useState<Card[] | null>(
    () => getCached<Card[]>(navKey.cards(cachedPid)) ?? null,
  );
  const [profile, setProfile] = useState<Profile | null>(
    () => getCached<Profile>(navKey.profile()) ?? null,
  );

  // "이 역량으로 문장 만들기" — 누르기 전엔 만들지 않는다(무거운 LLM 호출).
  const [items, setItems] = useState<StarItem[] | null>(null);
  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);

  const [toast, showToast] = useToast();

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

  const handleBuild = async () => {
    setBuilding(true);
    setBuildError(null);
    try {
      // 프로젝트가 없으면 미분류 기록 범위로 만든다 — 예전엔 여기서 return해서
      // 버튼이 아무 반응 없이 끝났다(9/18 수정).
      setItems(await buildResume(currentProjectScope(currentProject?.id), undefined, tag));
    } catch (err) {
      setBuildError(err instanceof ApiError ? err.detail : "문장을 만들지 못했어요.");
    } finally {
      setBuilding(false);
    }
  };

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      showToast("클립보드에 복사했어요");
    } catch {
      // 클립보드 접근 실패 — 조용히 무시
    }
  };

  const loading = cards === null;
  const isEmpty = !loading && matched.length === 0;
  const examples = COMPETENCY_EXAMPLES[tag] ?? [];

  return (
    <div
      style={{ backgroundColor: t.screenBg, color: t.text }}
      className="flex flex-1 flex-col px-[22px] pt-[6px] pb-6"
    >
      {/* Header (301:15251) */}
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

      {loading && (
        <div className="flex flex-col gap-3 pt-4">
          <SkeletonLine />
          <SkeletonLine />
          <SkeletonLine />
        </div>
      )}

      {/* 4.1-k 기록 없음 (301:15306) */}
      {isEmpty && (
        <div className="flex flex-1 flex-col pt-[24px]">
          <p className="text-[20px] font-bold leading-[32px]">아직 비어 있어요</p>
          <p style={{ color: t.textSoft }} className="mt-[12px] text-[14px] leading-[24px]">
            {profile?.job_field
              ? `${profile.job_field.split("·")[0]} 면접에서 자주 묻는 역량인데, `
              : ""}
            이 역량으로 남긴 기록이 아직 없어요.
          </p>

          {examples.length > 0 && (
            <>
              <p
                style={{ color: t.textMuted }}
                className="mt-[36px] text-[12px] font-medium leading-[20px]"
              >
                이런 일을 하셨을 때 쌓여요
              </p>
              <div className="mt-[12px] flex flex-col gap-[10px]">
                {examples.map((example) => (
                  <p
                    key={example}
                    style={{ backgroundColor: t.cardBg }}
                    className="rounded-[12px] px-[16px] py-[18px] text-[14px] leading-[24px]"
                  >
                    {example}
                  </p>
                ))}
              </div>
            </>
          )}

          <div className="min-h-[36px] flex-1" />
          {/* 홈으로 보내면서 이 역량을 "이어 쓰는 주제"로 넘긴다 — 저장할 때 태그가
              확실히 붙어서, 돌아오면 이 화면이 4.1-j로 바뀐다. */}
          <Link
            href={`/?topic=${encodeURIComponent(tag)}`}
            style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
            className="mt-6 flex h-[50px] items-center justify-center rounded-[8px] text-[14px] font-bold transition-opacity active:opacity-80"
          >
            이 역량으로 기록하기
          </Link>
        </div>
      )}

      {/* 4.1-j 기록 있음 (301:15256) */}
      {!loading && matched.length > 0 && (
        <div className="flex flex-col pt-[24px]">
          <p style={{ color: t.textMuted }} className="text-[12px] font-medium leading-[20px]">
            이 역량으로 쓸 수 있는 문장
          </p>

          {items === null ? (
            <p style={{ color: t.textMuted }} className="mt-[12px] text-[14px] leading-[24px]">
              아래 [이 역량으로 문장 만들기]를 누르면 기록 {matched.length}개를 묶어 문장을
              만들어요.
            </p>
          ) : items.length === 0 ? (
            <p style={{ color: t.textMuted }} className="mt-[12px] text-[14px] leading-[24px]">
              아직 묶을 만한 인과관계를 찾지 못했어요. 기록이 더 쌓이면 다시 시도해 보세요.
            </p>
          ) : (
            <div className="mt-[12px] flex flex-col gap-3">
              {items.map((item, i) => (
                <div key={`${item.title}-${i}`} className="flex flex-col gap-2">
                  <p className="text-[14px] leading-[24px]">
                    {[item.situation, item.task, item.action, item.result]
                      .filter(Boolean)
                      .join(" ")}
                  </p>
                  <button
                    type="button"
                    onClick={() =>
                      handleCopy(
                        [item.situation, item.task, item.action, item.result]
                          .filter(Boolean)
                          .join(" "),
                      )
                    }
                    style={{ color: t.textSoft }}
                    className="self-end text-[12px] font-medium leading-[20px]"
                  >
                    복사
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* 이 안내는 문장이 실제로 만들어진 뒤에만 의미가 있다 — 만들기 전에 띄우면
              위의 "누르면 만들어요"와 같은 자리에서 서로 모순되게 읽힌다. */}
          {items !== null && items.length > 0 && (
            <p style={{ color: t.textMuted }} className="mt-[12px] text-[12px] leading-[20px]">
              기록 {matched.length}개를 묶어 만든 문장이에요. 기록이 늘면 다시 다듬어져요.
            </p>
          )}

          {/* "왜 이 역량인가요 ›" (Figma `303:16338`, 9/18 신규) — AI가 이 기록들을 왜
              이 역량으로 묶었는지 보여주는 4.1-l로 간다. 분류가 틀렸을 때 거기서 바로
              고칠 수 있다. */}
          <Link
            href={`/stack/skill/${encodeURIComponent(tag)}/why`}
            style={{ color: t.accentText }}
            className="mt-[8px] self-start py-[12px] text-[12px] font-medium leading-[20px]"
          >
            왜 이 역량인가요&nbsp;›
          </Link>

          {buildError && <p className="mt-2 text-[12px] text-red-400">{buildError}</p>}

          {/* 쌓인 기록 (301:15263) */}
          <div
            style={{ color: t.textMuted }}
            className="mt-[12px] flex items-center gap-2 text-[12px] font-medium leading-[20px]"
          >
            <p className="flex-1">쌓인 기록</p>
            <p>{matched.length}</p>
          </div>

          <div className="mt-[12px] flex flex-col gap-[10px]">
            {matched
              .slice()
              .sort((a, b) => b.created_at.localeCompare(a.created_at))
              .map((card) => (
                <Link
                  key={card.id}
                  href={`/stack/${card.id}`}
                  style={{ backgroundColor: t.cardBg }}
                  className="flex items-center gap-[14px] rounded-[12px] px-[16px] py-[18px] transition-opacity active:opacity-80"
                >
                  <span className="flex flex-1 flex-col gap-[7px]">
                    <span
                      style={{ color: t.textSoft }}
                      className="text-[12px] leading-[20px]"
                    >
                      {formatCardDate(card.created_at)}
                    </span>
                    <span className="text-[14px] leading-[24px]">{card.refined_sentence}</span>
                  </span>
                  {/* 사진이 붙은 기록만 썸네일을 보여준다. 첫 장을 대표로 쓴다 —
                      목록에서 몇 장인지까지 셀 필요는 없다(상세에 들어가면 다 보인다). */}
                  {(card.photo_count ?? 0) > 0 && (
                    <PhotoThumb cardId={card.id} />
                  )}
                </Link>
              ))}
          </div>

          <button
            type="button"
            onClick={handleBuild}
            disabled={building}
            style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
            className="mt-[12px] flex h-[50px] items-center justify-center rounded-[8px] text-[14px] font-bold transition-opacity active:opacity-80 disabled:opacity-40"
          >
            {building ? "묶는 중…" : "이 역량으로 문장 만들기"}
          </button>

          <Link
            href={`/?topic=${encodeURIComponent(tag)}`}
            style={{ color: t.accentText }}
            className="mt-[12px] text-center text-[12px] font-medium leading-[20px]"
          >
            이 역량으로 더 기록하기&nbsp;&nbsp;›
          </Link>
        </div>
      )}

      <Toast toast={toast} />
    </div>
  );
}

/**
 * 목록의 44px 썸네일 (Figma `301:15271`).
 *
 * 카드 목록 응답엔 장수(`photo_count`)만 있고 사진 id는 없어서, 첫 장을 알려면
 * 그 카드의 사진 목록을 한 번 조회해야 한다. 사진이 **있는 카드만** 이 컴포넌트를
 * 그리므로(호출부에서 걸러짐) 헛되이 요청이 나가지는 않는다.
 */
function PhotoThumb({ cardId }: { cardId: number }) {
  const [id, setId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    import("@/lib/api").then(({ listCardPhotos }) =>
      listCardPhotos(cardId)
        .then((photos) => {
          if (!cancelled && photos[0]) setId(photos[0].id);
        })
        .catch(() => {}),
    );
    return () => {
      cancelled = true;
    };
  }, [cardId]);

  return (
    <span
      style={{ borderColor: t.border, backgroundColor: t.cardBg }}
      className="size-[44px] shrink-0 overflow-hidden rounded-[2px] border"
    >
      {id !== null && (
        // next/image가 아니라 <img>인 이유: 세션 쿠키가 필요한 우리 백엔드 경로라
        // Next 이미지 최적화 서버가 대신 받아올 수 없다.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={photoUrl(id)} alt="" className="size-full object-cover" />
      )}
    </span>
  );
}
