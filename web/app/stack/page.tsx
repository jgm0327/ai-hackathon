"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { SkeletonLine } from "@/components/Skeleton";
import { ApiError, Card, StarItem, buildResume, deleteCard, listCards, updateCardTags } from "@/lib/api";
import { useProjects } from "@/lib/useProjects";

function formatCardDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const mm = `${d.getMonth() + 1}`.padStart(2, "0");
  const dd = `${d.getDate()}`.padStart(2, "0");
  return `${mm}.${dd}`;
}

interface CardGroup {
  title: string;
  parent: Card;
  children: Card[];
}

/**
 * STAR 항목의 `source_dates`를 카드의 날짜(MM.DD)와 매칭해서 "인과관계로 묶인 카드
 * 그룹"을 계산한다 (9/14 신규 — DB에 저장하지 않고 매번 다시 계산, CLAUDE.md 3장).
 *
 * `source_dates`가 1개뿐인 항목은 독립 카드이므로 그룹으로 취급하지 않는다. 날짜가
 * MM.DD 단위(연도 없음)라 같은 날짜에 카드가 여러 장 있으면 전부 한 그룹으로 묶일 수
 * 있다 — build_resume()/source_dates의 기존 한계를 그대로 물려받는 것이지 여기서
 * 새로 생기는 문제는 아니다.
 */
function groupCardsByStarItems(
  cards: Card[],
  starItems: StarItem[],
): { groups: CardGroup[]; ungrouped: Card[] } {
  const usedCardIds = new Set<number>();
  const groups: CardGroup[] = [];

  for (const item of starItems) {
    if (item.source_dates.length < 2) continue;
    const matched = cards.filter((c) => item.source_dates.includes(formatCardDate(c.created_at)));
    if (matched.length < 2) continue;
    const sorted = [...matched].sort((a, b) => a.created_at.localeCompare(b.created_at));
    const [parent, ...children] = sorted;
    groups.push({ title: item.title, parent, children });
    matched.forEach((c) => usedCardIds.add(c.id));
  }

  const ungrouped = cards.filter((c) => !usedCardIds.has(c.id));
  return { groups, ungrouped };
}

/**
 * 커리어 스택 (`/stack`) — 카드 목록 + 태그 필터.
 *
 * **구현 노트 (9/14, 프로젝트 매핑 버그 수정)**: 원래 `listCards()`를 인자 없이 호출해
 * 프로젝트 구분 없이 전체 카드를 섞어서 보여주고 있었다 — CLAUDE.md 3장의 핵심 설계
 * ("A은행 결제 API 개선"과 "B카드 결제 API 개선"을 별개로 구분)가 이 화면에서만
 * 무너져 있던 셈. 기본은 현재 프로젝트로 필터링하고(`/`와 동일한 `<ProjectSwitcher />`
 * 재사용), "전체 프로젝트 보기" 토글로 전 프로젝트를 한 번에 볼 때만 카드마다
 * 프로젝트명 라벨을 붙인다.
 */
export default function StackPage() {
  // ProjectSwitcher에도 그대로 넘겨서 훅 인스턴스를 하나로 공유한다 — 그래야 스위처에서
  // 프로젝트를 바꾸는 즉시 이 페이지의 currentProject도 같이 바뀐다(구현 노트: 9/14
  // ProjectSwitcher.tsx 참고 — 예전엔 각자 useProjects()를 불러서 전환해도 새로고침
  // 전까진 카드 목록이 안 바뀌는 버그가 있었다).
  const projectsState = useProjects();
  const { projects, currentProject, loading: projectsLoading } = projectsState;
  const [cards, setCards] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [showAllProjects, setShowAllProjects] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  // 인과관계 그룹(부모-자식) 보기 (9/14 신규) — 기본은 꺼짐. 켜면 그 순간에만
  // build_resume()을 호출해 "조치→결과" 시간차 묶음을 계산한다. DB에 저장하지 않고
  // 세션 동안만 캐시(starGroups)해서, 껐다 켜도 재호출 안 한다. 프로젝트 단위로만
  // 의미가 있어서 "전체 프로젝트 보기"와 동시에 켤 수 없다(CLAUDE.md 3장: AI가 만든
  // 묶음은 DB에 저장하지 않는다 — 이 뷰도 매번 다시 계산만 하고 저장/관리 UI는 없다).
  const [groupedView, setGroupedView] = useState(false);
  const [starGroups, setStarGroups] = useState<StarItem[] | null>(null);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [groupsError, setGroupsError] = useState<string | null>(null);

  // 프로젝트가 바뀌면 이전 프로젝트 기준으로 캐시된 그룹은 더 이상 유효하지 않다 —
  // currentProject.id가 바뀔 때 파생 상태(캐시)를 리셋하는 표준 패턴이라 억제한다
  // (VoiceInput.tsx의 지원 여부 체크, PushSetup.tsx의 localStorage 복원과 동일한 이유).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setStarGroups(null);
    setGroupedView(false);
    setGroupsError(null);
  }, [currentProject?.id]);

  const toggleGroupedView = async () => {
    if (groupedView) {
      setGroupedView(false);
      return;
    }
    if (!currentProject) return;
    setActiveTag(null); // 그룹 뷰에서는 태그 필터를 끈다 — 그룹이 태그로 쪼개지는 걸 방지
    setGroupedView(true);
    if (starGroups) return; // 이미 계산해둔 게 있으면 재호출하지 않는다
    setGroupsLoading(true);
    setGroupsError(null);
    try {
      const items = await buildResume(currentProject.id);
      setStarGroups(items);
    } catch (err) {
      setGroupsError(err instanceof ApiError ? err.detail : "인과관계 분석에 실패했습니다.");
      setGroupedView(false);
    } finally {
      setGroupsLoading(false);
    }
  };

  // 카테고리(스킬 태그) 직접 수정 (9/14 신규) — 저장 시점엔 AI가 자동으로 뽑고,
  // 이건 그 뒤에 가끔(연 몇 회) 손으로 고치는 별도 경로다 (CLAUDE.md 2.1).
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTags, setEditTags] = useState<string[]>([]);
  const [newTagInput, setNewTagInput] = useState("");
  const [savingTags, setSavingTags] = useState(false);
  const [tagError, setTagError] = useState<string | null>(null);

  // 프로젝트 목록 로딩이 끝나기 전엔 아직 currentProject를 모르므로 대기한다 —
  // 그 전에 필터 없이 먼저 불러오면 "현재 프로젝트만" 모드에서도 잠깐 전체가
  // 보였다가 바뀌는 깜빡임이 생긴다.
  useEffect(() => {
    if (projectsLoading) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const projectId = showAllProjects ? undefined : (currentProject?.id ?? undefined);
        const list = await listCards(projectId);
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
  }, [projectsLoading, currentProject?.id, showAllProjects]);

  const projectNameById = useMemo(() => {
    const map = new Map<number, string>();
    projects.forEach((p) => map.set(p.id, p.name));
    return map;
  }, [projects]);

  const tags = useMemo(() => {
    const set = new Set<string>();
    cards.forEach((c) => c.skill_tags.forEach((t) => set.add(t)));
    return Array.from(set);
  }, [cards]);

  const visibleCards = activeTag ? cards.filter((c) => c.skill_tags.includes(activeTag)) : cards;

  const { groups, ungrouped } = useMemo(() => {
    if (!groupedView || !starGroups) return { groups: [] as CardGroup[], ungrouped: visibleCards };
    return groupCardsByStarItems(visibleCards, starGroups);
  }, [groupedView, starGroups, visibleCards]);

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

  const startEditingTags = (card: Card) => {
    setEditingId(card.id);
    setEditTags([...card.skill_tags]);
    setNewTagInput("");
    setTagError(null);
    setConfirmId(null);
  };

  const cancelEditingTags = () => {
    setEditingId(null);
    setEditTags([]);
    setNewTagInput("");
    setTagError(null);
  };

  const addTagFromInput = () => {
    const trimmed = newTagInput.trim();
    setNewTagInput("");
    if (!trimmed || editTags.includes(trimmed)) return;
    setEditTags((prev) => [...prev, trimmed]);
  };

  const removeEditTag = (tag: string) => {
    setEditTags((prev) => prev.filter((t) => t !== tag));
  };

  const saveEditingTags = async () => {
    if (editingId == null) return;
    setSavingTags(true);
    setTagError(null);
    try {
      const updated = await updateCardTags(editingId, editTags);
      setCards((prev) => prev.map((c) => (c.id === editingId ? updated : c)));
      cancelEditingTags();
    } catch {
      setTagError("태그 저장에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setSavingTags(false);
    }
  };

  // 카드 한 장의 본문(문장+메타 행+⋯메뉴+태그 편집 폼). 평범한 카드든, 그룹의
  // 부모/자식이든 똑같은 내용을 그리므로 함수로 뽑아서 재사용한다 — 그룹 뷰에서
  // 부모/자식은 바깥 래퍼(들여쓰기, 연결선)만 다르고 카드 자체 내용은 동일하다.
  const renderCardBody = (card: Card) => (
    <>
      <p className="text-[13px] font-medium text-[#18181b]">{card.refined_sentence}</p>
      <div className="flex items-center gap-2">
        {showAllProjects && (
          <p className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-600">
            {card.project_id != null
              ? (projectNameById.get(card.project_id) ?? "알 수 없는 프로젝트")
              : "프로젝트 없음"}
          </p>
        )}
        <p className="text-[11px] text-[#a1a1aa]">{formatCardDate(card.created_at)}</p>
        {card.skill_tags[0] && (
          <p className="text-[11px] text-[#a1a1aa]">#{card.skill_tags[0]}</p>
        )}
        <div className="flex-1" />
        {confirmId === card.id ? (
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => startEditingTags(card)}
              className="text-[11px] font-medium text-zinc-600 underline underline-offset-2"
            >
              태그 수정
            </button>
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

      {editingId === card.id && (
        <div className="flex flex-col gap-2 border-t border-[#e5e7eb] pt-2">
          <div className="flex flex-wrap gap-1.5">
            {editTags.length === 0 && (
              <p className="text-[11px] text-zinc-400">태그 없음</p>
            )}
            {editTags.map((tag) => (
              <span
                key={tag}
                className="flex items-center gap-1 rounded-full bg-zinc-100 px-2 py-1 text-[11px] text-zinc-600"
              >
                {tag}
                <button
                  type="button"
                  onClick={() => removeEditTag(tag)}
                  aria-label={`${tag} 삭제`}
                  className="text-zinc-400 transition-colors hover:text-zinc-700"
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-1.5">
            <input
              type="text"
              value={newTagInput}
              onChange={(e) => setNewTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addTagFromInput();
                }
              }}
              placeholder="새 태그"
              className="min-w-0 flex-1 rounded-md border border-zinc-200 px-2 py-1 text-[11px] focus:border-zinc-400 focus:outline-none"
            />
            <button
              type="button"
              onClick={addTagFromInput}
              className="rounded-md border border-zinc-200 px-2 py-1 text-[11px] text-zinc-600 transition-colors hover:bg-zinc-50"
            >
              추가
            </button>
          </div>
          {tagError && <p className="text-[11px] text-red-600">{tagError}</p>}
          <div className="flex justify-end gap-3 pt-0.5">
            <button
              type="button"
              onClick={cancelEditingTags}
              className="text-[11px] text-zinc-500"
            >
              취소
            </button>
            <button
              type="button"
              onClick={saveEditingTags}
              disabled={savingTags}
              className="text-[11px] font-semibold text-black disabled:opacity-50"
            >
              {savingTags ? "저장 중…" : "저장"}
            </button>
          </div>
        </div>
      )}
    </>
  );

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
          className="flex size-[26px] items-center justify-center rounded-full bg-[#f4f4f5] text-xs text-[#6b7280] transition-colors hover:bg-[#e4e4e7] active:scale-[0.95]"
        >
          ⚙
        </Link>
      </div>

      {/* 프로젝트 스위처 + 전체보기 토글 — CLAUDE.md 3장: 프로젝트별로 카드가 구분돼야 한다 */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <ProjectSwitcher projectsState={projectsState} />
        {projects.length > 1 && (
          <button
            type="button"
            onClick={() => {
              setShowAllProjects((v) => !v);
              setGroupedView(false);
            }}
            className="shrink-0 whitespace-nowrap text-[12px] font-medium text-zinc-500 underline underline-offset-2"
          >
            {showAllProjects ? "현재 프로젝트만" : "전체 프로젝트 보기"}
          </button>
        )}
        {/* 인과관계 그룹 보기 (9/14 신규) — 프로젝트 하나를 볼 때만 의미가 있어서
            "전체 프로젝트 보기" 중엔 숨긴다 */}
        {currentProject && !showAllProjects && (
          <button
            type="button"
            onClick={toggleGroupedView}
            disabled={groupsLoading}
            className={`shrink-0 whitespace-nowrap text-[12px] font-medium underline underline-offset-2 disabled:opacity-50 ${
              groupedView ? "text-zinc-900" : "text-zinc-500"
            }`}
          >
            {groupsLoading ? "분석 중…" : groupedView ? "묶어보기 끄기" : "인과관계로 묶어보기"}
          </button>
        )}
      </div>

      {groupsError && <p className="text-[12px] text-red-600">{groupsError}</p>}

      {!groupedView && tags.length > 0 && (
        <div className="flex flex-wrap gap-[7px]">
          <button
            type="button"
            onClick={() => setActiveTag(null)}
            className={`rounded-full px-3 py-[7px] text-[11px] font-medium transition-colors ${
              activeTag === null
                ? "border border-black bg-black text-white hover:bg-zinc-800"
                : "border border-[#e5e7eb] bg-white text-[#6b7280] hover:bg-zinc-50"
            }`}
          >
            전체
          </button>
          {tags.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => setActiveTag(tag)}
              className={`rounded-full px-3 py-[7px] text-[11px] font-medium transition-colors ${
                activeTag === tag
                  ? "border border-black bg-black text-white hover:bg-zinc-800"
                  : "border border-[#e5e7eb] bg-white text-[#6b7280] hover:bg-zinc-50"
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

      {groupsLoading && (
        <div className="flex flex-col gap-[10px]">
          {[0, 1].map((i) => (
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

      {!loading && !groupsLoading && !error && groups.length === 0 && ungrouped.length === 0 && (
        <p className="px-1 py-8 text-center text-sm text-zinc-400">아직 남긴 기록이 없습니다.</p>
      )}

      {!loading && !groupsLoading && (
        <ul className="flex flex-col gap-[10px]">
          {groups.map((group) => (
            <li
              key={`group-${group.parent.id}`}
              className="flex flex-col gap-2.5 rounded-[12px] border border-[#e5e7eb] bg-white px-[14px] py-[13px]"
            >
              <p className="text-[11px] font-semibold text-zinc-400">🔗 {group.title}</p>
              <div className="flex flex-col gap-2">{renderCardBody(group.parent)}</div>
              {group.children.map((child) => (
                <div
                  key={child.id}
                  className="ml-3 flex flex-col gap-2 border-l-2 border-zinc-100 pl-3"
                >
                  {renderCardBody(child)}
                </div>
              ))}
            </li>
          ))}
          {ungrouped.map((card) => (
            <li
              key={card.id}
              className="flex flex-col gap-2 rounded-[12px] border border-[#e5e7eb] bg-white px-[14px] py-[13px]"
            >
              {renderCardBody(card)}
            </li>
          ))}
        </ul>
      )}

      <div className="pt-2 pb-4">
        <Link
          href="/resume"
          className="flex w-full items-center justify-center rounded-[14px] bg-black py-[17px] text-[15px] font-semibold text-white transition-colors hover:bg-zinc-800 active:scale-[0.99]"
        >
          마스터 경력기술서 초안 짜기
        </Link>
      </div>
    </div>
  );
}
