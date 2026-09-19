"use client";

import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { BottomSheet } from "@/components/BottomSheet";
import { Toast, useToast } from "@/components/Toast";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { SkeletonLine } from "@/components/Skeleton";
import { stackTheme, stripColor } from "@/components/stackTheme";
import {
  ApiError,
  Card,
  CardCluster,
  Me,
  Profile,
  SkillSummary,
  StarItem,
  bundleCardsIntoProject,
  deleteCard,
  getMe,
  getProfile,
  getResumeDraftCount,
  getSkillSummary,
  getUnclassifiedSuggestions,
  listCards,
  currentProjectScope,
  updateCard,
} from "@/lib/api";
import { missingCoreCompetencies } from "@/lib/coreCompetencies";
import { getCached, navKey, setCached } from "@/lib/navCache";
import { buildResumeCached } from "@/lib/resumeCache";
import { useProjects } from "@/lib/useProjects";

// 카드가 쌓일수록 목록이 한없이 길어지는 걸 막기 위한 페이지네이션 크기.
const PAGE_SIZE = 10;

function formatCardDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const mm = `${d.getMonth() + 1}`.padStart(2, "0");
  const dd = `${d.getDate()}`.padStart(2, "0");
  return `${mm}.${dd}`;
}

/** `card.created_at`과 동일한 "YYYY-MM-DD" 형식으로, 로컬(뷰어) 달력 기준 날짜를
 * 만든다. `Date.toISOString()`은 UTC 기준이라 자정 근처에 하루가 밀리는 문제가
 * 생길 수 있어 로컬 컴포넌트로 직접 조립한다. */
function toDateKey(d: Date): string {
  const y = d.getFullYear();
  const m = `${d.getMonth() + 1}`.padStart(2, "0");
  const day = `${d.getDate()}`.padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * 최근 7일(오늘 포함) 중 카드가 있었던 날 배열(날짜 + 기록 여부) + 오늘부터
 * 거꾸로 센 연속 기록일수를 계산한다 (9/14 신규 — Figma "주간 기록 스트릭").
 *
 * **구현 노트**: 새 API 없이 이미 로드된 `cards`에서 순수 계산한다 — `created_at`이
 * 시간 없는 순수 날짜 문자열이라(`src/storage/db.py` `Card.created_at`) 문자열
 * 동등 비교만으로 충분하다. `showAllProjects` 토글 상태를 그대로 반영한다(그
 * 시점에 로드된 `cards` 자체가 이미 그 필터를 반영하고 있으므로 별도 분기 불필요).
 *
 * **구현 노트 (9/15, 점 클릭으로 그날 기록만 보기 추가)**: 원래 boolean만 반환해서
 * 점이 그냥 장식이었다 — "반응이 없다"는 지적을 받아 각 점에 실제 날짜를 붙여서
 * 클릭 가능하게 만든다.
 */
function computeStreak(cards: Card[]): { days: { date: string; has: boolean }[]; consecutive: number } {
  const dateSet = new Set(cards.map((c) => c.created_at));
  const today = new Date();
  const days: { date: string; has: boolean }[] = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const date = toDateKey(d);
    days.push({ date, has: dateSet.has(date) });
  }
  let consecutive = 0;
  for (let i = days.length - 1; i >= 0; i--) {
    if (!days[i].has) break;
    consecutive++;
  }
  return { days, consecutive };
}

/** 역량 리스트는 개수 제한 없이 사실상 전부 펼친다 — 캐시 키에도 이 값이 들어간다. */
const STACK_TOP_N = 50;

interface CardGroup {
  title: string;
  parent: Card;
  children: Card[];
}

/**
 * STAR 항목의 `source_card_ids`를 카드의 `id`와 매칭해서 "인과관계로 묶인 카드
 * 그룹"을 계산한다 (9/14 신규 — DB에 저장하지 않고 매번 다시 계산, CLAUDE.md 3장).
 *
 * **구현 노트 (9/14, 날짜 매칭 → ID 매칭 전환)**: 원래 `source_dates`(MM.DD 문자열)로
 * 매칭했는데, 같은 날짜에 카드가 여러 장 있으면 무관한 카드까지 같이 묶이는 버그가
 * 실측으로 발견됐다(B은행 계정계 프로젝트, docs/05-api-contract.md §3 참고). 카드
 * `id`는 절대 겹치지 않으므로 `source_card_ids`로 매칭하면 이 문제가 구조적으로
 * 사라진다.
 *
 * `source_card_ids`가 1개뿐인 항목은 독립 카드이므로 그룹으로 취급하지 않는다.
 */
function groupCardsByStarItems(
  cards: Card[],
  starItems: StarItem[],
): { groups: CardGroup[]; ungrouped: Card[] } {
  const usedCardIds = new Set<number>();
  const groups: CardGroup[] = [];
  const cardsById = new Map(cards.map((c) => [c.id, c]));

  for (const item of starItems) {
    if (item.source_card_ids.length < 2) continue;
    const matched = item.source_card_ids
      .map((id) => cardsById.get(id))
      .filter((c): c is Card => c !== undefined);
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
 *
 * **구현 노트 (9/14, /resume "이 문장의 근거"에서 카드로 이동)**: `/resume`의 STAR
 * 항목 근거 날짜 칩을 누르면 `/stack?cardId=<id>`로 온다. `useSearchParams()`를
 * 쓰기 때문에 Next.js가 정적 렌더링에서 제외시키려면 `<Suspense>` 경계가 필요해서,
 * 실제 페이지 컴포넌트를 `StackPageContent`로 분리하고 기본 export에서 감쌌다.
 */
function StackPageContent() {
  // ProjectSwitcher에도 그대로 넘겨서 훅 인스턴스를 하나로 공유한다 — 그래야 스위처에서
  // 프로젝트를 바꾸는 즉시 이 페이지의 currentProject도 같이 바뀐다(구현 노트: 9/14
  // ProjectSwitcher.tsx 참고 — 예전엔 각자 useProjects()를 불러서 전환해도 새로고침
  // 전까진 카드 목록이 안 바뀌는 버그가 있었다).
  const projectsState = useProjects();
  const { projects, currentProject, loading: projectsLoading } = projectsState;
  // 9/18 — 탭을 옮겨 다시 들어올 때 빈 목록부터 다시 그리지 않도록 캐시에서 시작한다
  // (`lib/navCache.ts`). 첫 방문엔 캐시가 비어 있어 예전과 동일하게 로딩부터 간다.
  const cachedCards = getCached<Card[]>(navKey.cards(currentProject?.id));
  const [cards, setCards] = useState<Card[]>(cachedCards ?? []);
  const [loading, setLoading] = useState(cachedCards === undefined);
  const [error, setError] = useState<string | null>(null);
  const [activeTag, setActiveTag] = useState<string | null>(null);
  // "역량 리스트"(Figma 100:692 "4.1-h") — 홈 화면 버블과 같은 집계 엔드포인트를
  // top_n만 크게 줘서 재사용한다. 개수 제한 없이 사실상 전부 받는다.
  // 9/18 — 캐시에서 시작한다. 이 블록도 목록 위에 삽입돼서 뒤늦게 나타나면 아래를
  // 밀어낸다(홈의 타깃 트랙 칩과 같은 문제).
  const [skillSummary, setSkillSummary] = useState<SkillSummary | null>(
    () => getCached<SkillSummary>(navKey.skillSummary(currentProject?.id, STACK_TOP_N)) ?? null,
  );
  // 주간 기록 스트릭 점 클릭 필터 (9/15 신규) — 태그 필터와 동시에 걸면 "그날 +
  // 그 태그"처럼 조건이 겹쳐 헷갈리므로, 점을 누르면 태그 필터는 끄고 그 반대도
  // 마찬가지로 동작한다(아래 핸들러 참고).
  const [activeStreakDate, setActiveStreakDate] = useState<string | null>(null);
  const [showAllProjects, setShowAllProjects] = useState(false);
  // 카드 목록 페이지네이션 (9/15 신규) — 카드가 쌓일수록 한 화면에 다 그리지 않도록
  // 클라이언트 쪽에서만 나눠 보여준다. 그룹 뷰(인과관계로 묶어보기)는 항목 수가
  // 훨씬 적어서 페이지 나누기 대상에서 뺀다.
  const [page, setPage] = useState(1);
  // 카드 액션시트 (9/14, BottomSheet 고도화) — 예전엔 "⋯" 탭 시 같은 줄에서
  // 태그수정/삭제/취소를 인라인으로 보여줬는데, Figma "4.1-a 카드 액션 시트"에
  // 맞춰 진짜 바텀시트로 교체했다. 삭제는 한 번 더 확인하는 별도 시트를 거친다
  // (Figma "4.1-c 삭제 확인 다이얼로그").
  const [actionSheetCard, setActionSheetCard] = useState<Card | null>(null);
  const [deleteConfirmCard, setDeleteConfirmCard] = useState<Card | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  // 4.1-h 재설계에 딸려온 것들 (9/18).
  // - profile: "마케팅 · 광고 직군 키워드 기준" 문구와 역량 공백 경고에 쓴다.
  //   직군을 모르면 둘 다 안 띄운다 — 없는 직군을 임의로 고르지 않는다.
  // - draftCount: "내 경력기술서  3개". 실제 저장된 초안 수를 서버에서 받아온다
  //   (숫자를 짐작해서 적지 않는다 — CLAUDE.md 2.2).
  // - addTagOpen: "+ 역량 추가" 시트.
  const [profile, setProfile] = useState<Profile | null>(
    () => getCached<Profile>(navKey.profile()) ?? null,
  );
  const [draftCount, setDraftCount] = useState<number | null>(null);
  // 빈 상태 문구에 이름을 부르기 위한 것 뿐이다(318:23250) — 없으면 문구만 짧아진다.
  const [me, setMe] = useState<Me | null>(null);
  const [addTagOpen, setAddTagOpen] = useState(false);
  const [newTagName, setNewTagName] = useState("");
  const [newTagCardIds, setNewTagCardIds] = useState<Set<number>>(new Set());
  const [addTagError, setAddTagError] = useState<string | null>(null);
  const [addingTag, setAddingTag] = useState(false);
  // 태그를 바꾼 뒤 카드 목록/역량 집계를 다시 부르기 위한 트리거. 값 자체엔 의미가
  // 없고, 아래 두 effect의 의존성으로만 쓰인다.
  const [reloadToken, setReloadToken] = useState(0);
  const [toast, showToast] = useToast();

  useEffect(() => {
    let cancelled = false;
    getProfile()
      .then((p) => {
        setCached(navKey.profile(), p);
        if (!cancelled) setProfile(p);
      })
      .catch(() => {});
    getResumeDraftCount()
      .then((n) => {
        if (!cancelled) setDraftCount(n);
      })
      .catch(() => {}); // 실패하면 숫자만 안 뜬다 — 진입 자체는 그대로 동작한다
    // 빈 상태 문구의 "{이름}님의 하루는 ~"에만 쓴다(318:23250). 실패하거나 닉네임이
    // 없으면 이름 없는 문구로 간다.
    getMe()
      .then((m) => {
        if (!cancelled) setMe(m);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // "4.1.1 AI 프로젝트 자동 제안" (9/14 신규) — project_id가 없는 카드끼리만 비교해서
  // 비슷한 것들을 묶어 후보로 제시한다. 이미 프로젝트가 배정된 카드는 서버가 애초에
  // 조회 대상으로도 삼지 않는다(CLAUDE.md 3장 안전장치, resilient-waddling-simon.md
  // 참고). 한 번에 클러스터 1개(가장 먼저 온 것)만 검토하게 해서 화면을 단순하게
  // 유지 — 처리 후 남은 제안이 있으면 다시 배너가 뜬다.
  const [suggestions, setSuggestions] = useState<CardCluster[]>(
    () => getCached<CardCluster[]>(navKey.suggestions()) ?? [],
  );
  const [suggestionsSheetOpen, setSuggestionsSheetOpen] = useState(false);
  const [selectedCardIds, setSelectedCardIds] = useState<Set<number>>(new Set());
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectStartedAt, setNewProjectStartedAt] = useState("");
  const [bundling, setBundling] = useState(false);
  const [bundleError, setBundleError] = useState<string | null>(null);

  const refreshSuggestions = () => {
    getUnclassifiedSuggestions()
      .then((list) => {
        setCached(navKey.suggestions(), list);
        setSuggestions(list);
      })
      .catch(() => {}); // 실패해도 배너가 안 뜰 뿐 — 화면 전체를 막을 정도는 아니다
  };

  useEffect(() => {
    refreshSuggestions();
  }, []);

  const openSuggestions = () => {
    const first = suggestions[0];
    if (!first) return;
    setSelectedCardIds(new Set(first.card_ids));
    setNewProjectName("");
    setNewProjectStartedAt("");
    setBundleError(null);
    setSuggestionsSheetOpen(true);
  };

  const toggleSelectedCard = (id: number) => {
    setSelectedCardIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleBundle = async () => {
    if (selectedCardIds.size === 0 || !newProjectName.trim() || !newProjectStartedAt) {
      setBundleError("이름과 시작일을 입력하고, 최소 1개 이상 선택해 주세요.");
      return;
    }
    setBundling(true);
    setBundleError(null);
    try {
      await bundleCardsIntoProject(
        Array.from(selectedCardIds),
        newProjectName.trim(),
        newProjectStartedAt,
      );
      setSuggestionsSheetOpen(false);
      // 새 프로젝트가 자동으로 현재 프로젝트가 된다(create_project()의 기존 동작) —
      // projectsState.refresh()가 currentProject.id를 바꾸면 카드 목록을 불러오는
      // 기존 effect가 알아서 다시 실행돼 방금 옮긴 카드들을 보여준다.
      await projectsState.refresh();
      refreshSuggestions();
    } catch (err) {
      setBundleError(err instanceof ApiError ? err.detail : "묶기에 실패했습니다.");
    } finally {
      setBundling(false);
    }
  };

  /**
   * "+ 역량 추가" 적용 — 고른 기록들의 **대표 태그**를 새 이름으로 바꾼다 (9/18).
   *
   * 대표 태그(`skill_tags[0]`)만 바꾸는 게 핵심이다. 역량 목록과 역량 상세가 둘 다
   * 대표 태그로 집계하므로(`get_skill_category_counts`), 뒤쪽 태그에 끼워 넣으면
   * 새 역량이 목록에 나타나지 않는다. 기존 태그는 뒤로 밀어 보존한다 — 사람이
   * 분류를 바꾼 것이지 원래 태그가 틀렸다는 뜻은 아니다.
   */
  const handleAddTag = async () => {
    const name = newTagName.trim();
    if (!name) {
      setAddTagError("역량 이름을 입력해 주세요.");
      return;
    }
    if (newTagCardIds.size === 0) {
      setAddTagError("이 역량으로 볼 기록을 한 개 이상 골라 주세요.");
      return;
    }
    setAddingTag(true);
    setAddTagError(null);
    try {
      await Promise.all(
        cards
          .filter((c) => newTagCardIds.has(c.id))
          .map((c) =>
            updateCard(c.id, { skillTags: [name, ...c.skill_tags.filter((t) => t !== name)] }),
          ),
      );
      setAddTagOpen(false);
      setNewTagName("");
      setNewTagCardIds(new Set());
      // 목록과 역량 집계를 다시 불러온다 — 아래 effect들이 `reloadToken`을 보고 돈다.
      setReloadToken((n) => n + 1);
    } catch (err) {
      setAddTagError(err instanceof ApiError ? err.detail : "역량을 만들지 못했어요.");
    } finally {
      setAddingTag(false);
    }
  };

  // 인과관계 그룹(부모-자식) 보기 (9/14 신규) — 기본은 꺼짐. 켜면 그 순간에만
  // build_resume()을 호출해 "조치→결과" 시간차 묶음을 계산한다. DB에 저장하지 않고
  // 세션 동안만 캐시(starGroups)해서, 껐다 켜도 재호출 안 한다. 프로젝트 단위로만
  // 의미가 있어서 "전체 프로젝트 보기"와 동시에 켤 수 없다(CLAUDE.md 3장: AI가 만든
  // 묶음은 DB에 저장하지 않는다 — 이 뷰도 매번 다시 계산만 하고 저장/관리 UI는 없다).
  //
  // **구현 노트 (9/14, LLM 호출 캐싱 추가)**: 위 세션 캐시는 새로고침하면 날아가서,
  // 카드가 하나도 안 바뀌었어도 새로고침할 때마다 유료 LLM API를 다시 태우는 낭비가
  // 있었다(사용자 지적). `buildResumeCached()`가 카드 id 목록을 키로 localStorage에
  // 결과를 저장해두고, 카드 구성이 그대로면 재호출 없이 반환한다 — "그룹을 정식
  // 데이터로 저장"하는 게 아니라 "동일 입력 재계산 방지"용 캐시라 3장 원칙(관리 UI
  // 없이)은 그대로 유지된다. web/lib/resumeCache.ts 참고.
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

  // 프로젝트를 바꾸거나 "전체 프로젝트 보기"를 토글하면 이전 목록 기준 페이지 번호는
  // 더 이상 의미가 없다 — 1페이지로 되돌린다. (태그 필터/그룹 뷰 토글은 각 버튼의
  // onClick에서 직접 setPage(1)을 호출한다 — 아래 딥링크 점프 effect가 계산해서
  // 넣어주는 페이지 번호와 이 effect가 서로 덮어쓰지 않도록 의존성을 분리해뒀다.)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPage(1);
    setActiveStreakDate(null);
  }, [currentProject?.id, showAllProjects]);

  // /resume의 "이 문장의 근거" 날짜 칩에서 /stack?cardId=<id>로 넘어온 경우, 카드
  // 목록이 뜨면 그 카드로 스크롤 + 잠깐 하이라이트한다 (9/14 신규).
  const searchParams = useSearchParams();
  const targetCardId = searchParams.get("cardId");
  const [highlightedCardId, setHighlightedCardId] = useState<number | null>(null);
  const highlightedOnceRef = useRef(false);
  const pendingScrollCardIdRef = useRef<number | null>(null);

  // 1단계: 목표 카드가 태그 필터나 그룹 뷰에 가려져 있거나, 페이지네이션상 다른
  // 페이지에 있으면 그 카드가 실제로 보이는 상태로 만든다 (9/15, 페이지네이션 추가
  // 이후 신규 — 예전엔 카드가 항상 한 페이지에 다 있어서 이 계산이 필요 없었다).
  useEffect(() => {
    if (loading || !targetCardId || highlightedOnceRef.current) return;
    const id = Number(targetCardId);
    const idx = cards.findIndex((c) => c.id === id);
    if (idx < 0) return; // 아직 이 프로젝트에 없거나 다른 프로젝트 카드
    highlightedOnceRef.current = true;
    pendingScrollCardIdRef.current = id;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setActiveTag(null);
    setActiveStreakDate(null);
    setGroupedView(false);
    setPage(Math.floor(idx / PAGE_SIZE) + 1);
  }, [loading, targetCardId, cards]);

  // 2단계: 1단계가 정한 페이지가 실제로 렌더링된 뒤(다음 커밋) 그 카드 엘리먼트가
  // DOM에 생기면 스크롤 + 하이라이트한다. 아직 없으면(아직 렌더 전) 조용히 넘어가고
  // 다음 렌더에서 이 effect가 다시 실행돼 재시도한다.
  useEffect(() => {
    const id = pendingScrollCardIdRef.current;
    if (id === null) return;
    const el = document.getElementById(`card-${id}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlightedCardId(id);
    pendingScrollCardIdRef.current = null;
    const timer = setTimeout(() => setHighlightedCardId(null), 2500);
    return () => clearTimeout(timer);
  }, [page, cards, groupedView, loading]);

  const toggleGroupedView = async () => {
    setPage(1); // 그룹 뷰는 페이지네이션 대상이 아니라, 껐다 켜면 항상 1페이지부터
    if (groupedView) {
      setGroupedView(false);
      return;
    }
    setActiveTag(null); // 그룹 뷰에서는 태그/날짜 필터를 끈다 — 그룹이 쪼개지는 걸 방지
    setActiveStreakDate(null);
    setGroupedView(true);
    if (starGroups) return; // 이미 계산해둔 게 있으면 재호출하지 않는다
    setGroupsLoading(true);
    setGroupsError(null);
    try {
      // 프로젝트가 없으면 미분류 기록 범위로 묶는다 — 예전엔 위에서 return해서
      // 그룹 보기가 켜지지도 않았다(9/18 수정).
      const items = await buildResumeCached(currentProjectScope(currentProject?.id), { cards });
      setStarGroups(items);
    } catch (err) {
      setGroupsError(err instanceof ApiError ? err.detail : "인과관계 분석에 실패했습니다.");
      setGroupedView(false);
    } finally {
      setGroupsLoading(false);
    }
  };

  // 문장·카테고리(스킬 태그) 직접 수정 (9/14 태그, 9/15 문장 추가) — 저장 시점엔
  // AI가 자동으로 채우고, 이건 그 뒤에 가끔(연 몇 회) 손으로 고치는 별도 경로다
  // (CLAUDE.md 2.1).
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editSentence, setEditSentence] = useState("");
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
      const projectId = showAllProjects ? undefined : (currentProject?.id ?? undefined);
      // 이미 보여줄 값이 있으면 로딩 상태로 되돌리지 않는다 — 갱신 중에 목록이
      // 비어버리면 그게 곧 깜박임이다.
      const hasShown = projectId !== undefined && getCached(navKey.cards(projectId)) !== undefined;
      if (!hasShown) setLoading(true);
      setError(null);
      try {
        const list = await listCards(projectId);
        if (projectId !== undefined) setCached(navKey.cards(projectId), list);
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
  }, [projectsLoading, currentProject?.id, showAllProjects, reloadToken]);

  // 역량 리스트(Figma 100:692 "4.1-h")는 프로젝트 하나를 볼 때만 의미가 있다
  // (CLAUDE.md 3장 — 프로젝트가 다르면 같은 이름 작업이라도 안 섞여야 한다) —
  // "전체 프로젝트 보기" 중엔 집계하지 않고 아래에서 그 블록 자체를 숨긴다.
  //
  // **프로젝트가 아예 없는 계정은 예외다** (9/18). 그 경우 카드가 전부 미분류라서
  // 전부 집계해도 프로젝트끼리 섞일 게 없다 — 예전엔 여기서도 return해서 기록이
  // 쌓여 있는데 역량 리스트가 통째로 안 보였다. 반대로 "프로젝트는 있는데 현재
  // 프로젝트가 없는" 상태에서는 섞일 수 있으니 집계하지 않는다.
  useEffect(() => {
    const aggregateAll = !currentProject && projects.length === 0;
    if (showAllProjects || (!currentProject && !aggregateAll)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSkillSummary(null);
      return;
    }
    let cancelled = false;
    const projectId = currentProject?.id;
    getSkillSummary(projectId, STACK_TOP_N)
      .then((summary) => {
        setCached(navKey.skillSummary(projectId, STACK_TOP_N), summary);
        if (!cancelled) setSkillSummary(summary);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [currentProject, projects.length, showAllProjects, cards.length, reloadToken]);

  // 역량 공백 경고 (Figma 4.1-h `294:10323`, 9/18) — 이 직군에서 자주 묻는 역량 중
  // 아직 한 건도 기록하지 않은 것들. 목록은 우리가 구성한 것이고 원티드 공식 자료가
  // 아니다(`lib/coreCompetencies.ts` 주석 참고). 직군을 모르면 빈 배열이라 안 뜬다.
  const missingCore = useMemo(
    () =>
      missingCoreCompetencies(
        profile?.job_field,
        skillSummary?.categories.map((c) => c.tag) ?? [],
      ),
    [profile, skillSummary],
  );

  // "쓸 수 있는 문장" (Figma 100:692 "4.1-h") — 경력기술서에 그대로 쓸 만큼 구체적인
  // 기록의 수. `confidence`가 낮으면(parse_note()가 "특정 업무 내용을 확인할 수
  // 없음" 같은 모호한 문장으로 정리했다는 뜻) 빼고 센다 — 0.5 기준은 백엔드가
  // "모호함" 판정에 이미 쓰는 것과 동일하다(src/parsing/prompt_templates.py).
  const usableSentenceCount = useMemo(
    () => cards.filter((c) => c.confidence > 0.5).length,
    [cards],
  );

  const projectNameById = useMemo(() => {
    const map = new Map<number, string>();
    projects.forEach((p) => map.set(p.id, p.name));
    return map;
  }, [projects]);

  const visibleCards = activeStreakDate
    ? cards.filter((c) => c.created_at === activeStreakDate)
    : activeTag
      ? cards.filter((c) => c.skill_tags.includes(activeTag))
      : cards;

  const streak = useMemo(() => computeStreak(cards), [cards]);

  // 스트릭 점 클릭 (9/15 신규) — 기록 있는 날만 클릭 가능. 같은 점을 다시 누르면
  // 해제, 다른 날을 누르면 그 날로 전환. 태그 필터와는 배타적으로 동작한다.
  const toggleStreakDate = (date: string) => {
    setActiveStreakDate((prev) => (prev === date ? null : date));
    setActiveTag(null);
    setPage(1);
  };

  const { groups, ungrouped } = useMemo(() => {
    if (!groupedView || !starGroups) return { groups: [] as CardGroup[], ungrouped: visibleCards };
    return groupCardsByStarItems(visibleCards, starGroups);
  }, [groupedView, starGroups, visibleCards]);

  /**
   * "4.1-d 빈 상태" 조건 (9/18 — 한 곳으로 모음).
   *
   * 예전엔 빈 상태 블록 하나만 이 조건을 썼는데, 목업의 빈 상태에는 프로젝트 스위처
   * 줄과 [경력기술서 초안 만들기]가 **없다**. 같은 조건을 세 군데가 쓰게 되면서
   * 식을 여기로 뺐다 — 한쪽만 고쳐져서 빈 화면에 버튼이 남는 일을 막는다.
   */
  const isEmptyStack =
    !loading && !groupsLoading && !error && groups.length === 0 && ungrouped.length === 0;

  // 페이지네이션 (9/15 신규) — 그룹 뷰는 항목이 적어 대상에서 뺀다(원래 ungrouped
  // 그대로 전부 보여준다). 일반 목록만 PAGE_SIZE씩 잘라서 보여준다.
  const totalPages = groupedView ? 1 : Math.max(1, Math.ceil(ungrouped.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedUngrouped = groupedView
    ? ungrouped
    : ungrouped.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  /** 4.1-a 액션 시트의 [복사하기] — 그 기록의 문장을 클립보드로 (9/19 신규). */
  const handleCopyCard = async (card: Card) => {
    try {
      await navigator.clipboard.writeText(card.refined_sentence);
      showToast("클립보드에 복사했어요");
    } catch {
      // 클립보드 접근 실패(권한/비보안 컨텍스트) — 조용히 무시한다.
    }
  };

  const handleDelete = async (id: number) => {
    setDeletingId(id);
    try {
      await deleteCard(id);
      setCards((prev) => prev.filter((c) => c.id !== id));
    } catch {
      setError("삭제에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setDeletingId(null);
      setDeleteConfirmCard(null);
    }
  };

  const startEditingTags = (card: Card) => {
    setEditingId(card.id);
    setEditSentence(card.refined_sentence);
    setEditTags([...card.skill_tags]);
    setNewTagInput("");
    setTagError(null);
  };

  const cancelEditingTags = () => {
    setEditingId(null);
    setEditSentence("");
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
    const trimmedSentence = editSentence.trim();
    if (!trimmedSentence) {
      setTagError("문장을 비워둘 수 없습니다.");
      return;
    }
    setSavingTags(true);
    setTagError(null);
    try {
      const updated = await updateCard(editingId, {
        skillTags: editTags,
        refinedSentence: trimmedSentence,
      });
      setCards((prev) => prev.map((c) => (c.id === editingId ? updated : c)));
      cancelEditingTags();
    } catch {
      setTagError("저장에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setSavingTags(false);
    }
  };

  // 카드 한 장의 본문(문장+메타 행+⋯메뉴+태그 편집 폼). 평범한 카드든, 그룹의
  // 부모/자식이든 똑같은 내용을 그리므로 함수로 뽑아서 재사용한다 — 그룹 뷰에서
  // 부모/자식은 바깥 래퍼(들여쓰기, 연결선)만 다르고 카드 자체 내용은 동일하다.
  const renderCardBody = (card: Card) => (
    <>
      {/* 문장을 누르면 "4.1-b 기록 상세"로 (Figma 89:479, 9/18 신규) — 같은 주제에
          쌓인 기록을 시간순으로 보고 거기에 바로 이어 쓸 수 있는 화면. 인라인 편집
          중일 때는 링크를 빼서, 고치는 중에 실수로 화면을 벗어나지 않게 한다. */}
      {editingId === card.id ? (
        <p className="text-[13px] font-medium text-[#f2f2f2]">{card.refined_sentence}</p>
      ) : (
        <Link
          href={`/stack/${card.id}`}
          className="text-[13px] font-medium text-[#f2f2f2] transition-colors hover:text-white"
        >
          {card.refined_sentence}
        </Link>
      )}
      <div className="flex items-center gap-2">
        {showAllProjects && (
          <p className="rounded-full bg-[#262626] px-2 py-0.5 text-[11px] font-medium text-[#a0a0a0]">
            {card.project_id != null
              ? (projectNameById.get(card.project_id) ?? "알 수 없는 프로젝트")
              : "프로젝트 없음"}
          </p>
        )}
        <p className="text-[11px] text-[#5e5e5e]">{formatCardDate(card.created_at)}</p>
        {card.skill_tags[0] && (
          <p className="text-[11px] text-[#5e5e5e]">#{card.skill_tags[0]}</p>
        )}
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => setActionSheetCard(card)}
          aria-label="카드 관리"
          className="px-1 text-[13px] text-[#5e5e5e]"
        >
          ⋯
        </button>
      </div>

      {editingId === card.id && (
        <div className="flex flex-col gap-2 border-t border-[#2a2a2a] pt-2">
          <textarea
            value={editSentence}
            onChange={(e) => setEditSentence(e.target.value)}
            rows={3}
            placeholder="문장을 입력하세요"
            className="w-full resize-none rounded-md border border-[#333] bg-[#141414] p-2 text-[12px] leading-relaxed text-[#f2f2f2] placeholder:text-[#5e5e5e] focus:border-[#5e5e5e] focus:outline-none"
          />
          <div className="flex flex-wrap gap-1.5">
            {editTags.length === 0 && (
              <p className="text-[11px] text-[#5e5e5e]">태그 없음</p>
            )}
            {editTags.map((tag) => (
              <span
                key={tag}
                className="flex items-center gap-1 rounded-full bg-[#262626] px-2 py-1 text-[11px] text-[#a0a0a0]"
              >
                {tag}
                <button
                  type="button"
                  onClick={() => removeEditTag(tag)}
                  aria-label={`${tag} 삭제`}
                  className="text-[#5e5e5e] transition-colors hover:text-[#c8c8c8]"
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
              className="min-w-0 flex-1 rounded-md border border-[#333] bg-[#141414] px-2 py-1 text-[11px] text-[#f2f2f2] placeholder:text-[#5e5e5e] focus:border-[#5e5e5e] focus:outline-none"
            />
            <button
              type="button"
              onClick={addTagFromInput}
              className="rounded-md border border-[#333] px-2 py-1 text-[11px] text-[#a0a0a0] transition-colors hover:bg-[#262626]"
            >
              추가
            </button>
          </div>
          {tagError && <p className="text-[11px] text-[#f0645c]">{tagError}</p>}
          <div className="flex justify-end gap-3 pt-0.5">
            <button
              type="button"
              onClick={cancelEditingTags}
              className="text-[11px] text-[#828282]"
            >
              취소
            </button>
            <button
              type="button"
              onClick={saveEditingTags}
              disabled={savingTags}
              className="text-[11px] font-semibold text-[#f2f2f2] disabled:opacity-50"
            >
              {savingTags ? "저장 중…" : "저장"}
            </button>
          </div>
        </div>
      )}
    </>
  );

  return (
    <div className="flex flex-col gap-3 px-5 pt-[8px] text-[#f2f2f2]">
      {/* Header (318:23080 / 318:23226, 9/18 개정) — 제목 20px, 개수 12px, 그리고
          설정은 ⚙ 이모지가 아니라 Figma 아이콘이다(이모지는 기기마다 모양이 다르다).
          목업엔 제목 왼쪽에 `‹`도 있는데 여기는 탭 루트라 돌아갈 곳이 없어서 넣지
          않았다 — 눌러도 아무 일도 안 하는 버튼이 되는 쪽이 더 나쁘다. */}
      <div className="flex items-center gap-[10px] pb-[8px]">
        <p style={{ color: stackTheme.text }} className="text-[20px] font-bold leading-[32px]">
          커리어 스택
        </p>
        {!loading && (
          <p
            style={{ color: stackTheme.textMuted }}
            className="text-[12px] font-medium leading-[20px]"
          >
            {cards.length}
          </p>
        )}
        <div className="flex-1" />
        <Link
          href="/settings"
          aria-label="설정"
          className="flex size-[22px] items-center justify-center transition-opacity active:opacity-60"
        >
          <Image src="/icons/settings.svg" alt="" width={20} height={20} aria-hidden />
        </Link>
      </div>

      {/* 스택 헤드 + 역량 리스트 (Figma "03 · 커리어 스택" 4.1-h `294:10275`, 9/18 재설계).
          "전체 프로젝트 보기" 중엔 역량 집계가 의미가 없어서 숨긴다(위 effect가 그때
          skillSummary를 null로 비운다). */}
      {!showAllProjects && skillSummary && skillSummary.categories.length > 0 && (
        <div className="flex flex-col">
          {/* 스택 헤드 (294:10276) */}
          <p
            style={{ color: stackTheme.text }}
            className="text-[20px] font-bold leading-[32px] tracking-[-0.8px]"
          >
            기록 <span style={{ color: stackTheme.accentText }}>{skillSummary.total_cards}</span>개를
            역량 <span style={{ color: stackTheme.accentText }}>{skillSummary.categories.length}</span>
            개로 나눴어요
          </p>
          <p
            style={{ color: stackTheme.textMuted }}
            className="mt-[6px] text-[12px] leading-[20px]"
          >
            지금 쓸 수 있는 문장 {usableSentenceCount}개
          </p>

          {/* 비중 스트립 (294:10281) — 역량별 개수를 그대로 비율로 쓴다. 색은 이름이
              아니라 **순위**에 매핑한다(홈 버블과 같은 규칙). */}
          <div className="mt-[28px] flex gap-[3px]">
            {skillSummary.categories.map((cat, i) => (
              <div
                key={cat.tag}
                title={`${cat.tag} ${cat.count}`}
                style={{ flex: `${cat.count} 0 0`, backgroundColor: stripColor(i), minWidth: 1 }}
                className="h-[5px]"
              />
            ))}
          </div>

          {/* 분류 헤더 (294:10288) — "AI가 먼저 나눠뒀어요" + 기준 + [수정].
              [수정]은 4.1-i 분류 수정 화면으로 간다. */}
          <div className="mt-[36px] flex flex-col gap-[10px]">
            <div className="flex items-start gap-2">
              <Image
                src="/icons/sparkles.svg"
                alt=""
                width={15}
                height={15}
                aria-hidden
                className="mt-[3px] shrink-0"
              />
              <p style={{ color: stackTheme.textSoft }} className="flex-1 text-[12px] leading-[20px]">
                쓰신 기록의 키워드를 읽고 AI가 먼저 나눠뒀어요
              </p>
            </div>
            <div className="flex items-center gap-2">
              <p
                style={{ color: stackTheme.textMuted }}
                className="flex-1 text-[12px] leading-[20px] tracking-[0.4px]"
              >
                {profile?.job_field ? `${profile.job_field} 직군 키워드 기준` : "기록 키워드 기준"}
              </p>
              <Link
                href="/stack/classify"
                style={{ borderColor: stackTheme.border, color: stackTheme.textSoft }}
                className="shrink-0 rounded-[4px] border px-[11px] py-[5px] text-[14px] font-medium leading-[24px] transition-opacity active:opacity-70"
              >
                수정
              </Link>
            </div>
          </div>
          <div style={{ backgroundColor: stackTheme.border }} className="mt-[10px] h-px w-full" />

          {/* 역량 리스트 (294:10298) — 누르면 역량 상세(4.1-j)로 간다. */}
          <div className="mt-[12px] flex flex-col gap-[10px]">
            {skillSummary.categories.map((cat, i) => (
              <Link
                key={cat.tag}
                href={`/stack/skill/${encodeURIComponent(cat.tag)}`}
                style={{ backgroundColor: stackTheme.cardBg }}
                className="flex items-center gap-[14px] rounded-[12px] px-[16px] py-[18px] transition-opacity active:opacity-80"
              >
                <span
                  style={{ color: stackTheme.textSoft }}
                  className="text-[12px] leading-[20px] tracking-[0.72px]"
                >
                  {`${i + 1}`.padStart(2, "0")}
                </span>
                <span
                  style={{ color: stackTheme.text }}
                  className="flex-1 truncate text-[16px] font-medium leading-[28px] tracking-[-0.32px]"
                >
                  {cat.tag}
                </span>
                <span
                  style={{ color: stripColor(i) === stackTheme.border ? stackTheme.textMuted : stripColor(i) }}
                  className="text-[20px] font-bold leading-[28px]"
                >
                  {cat.count}
                </span>
                <Image
                  src="/icons/chevron-right.svg"
                  alt=""
                  width={16}
                  height={16}
                  aria-hidden
                  className="shrink-0"
                />
              </Link>
            ))}
            <button
              type="button"
              onClick={() => setAddTagOpen(true)}
              style={{ borderColor: stackTheme.border, color: stackTheme.textSoft }}
              className="rounded-[12px] border px-[16px] py-[18px] text-[14px] font-medium leading-[24px] transition-opacity active:opacity-70"
            >
              +&nbsp;&nbsp;역량 추가
            </button>
          </div>

          {/* 역량 공백 경고 (Figma 4.1-h `301:15331`) — 직군을 알 때만, 그리고 실제로
              비어 있을 때만. 각 역량은 4.1-k(역량 상세 · 기록 없음)로 이어진다 —
              거기서 "이런 일을 하셨을 때 쌓여요" 예시를 보고 바로 기록할 수 있다. */}
          {missingCore.length > 0 && (
            <div className="mt-[12px] flex flex-col gap-2 px-[16px] py-[14px]">
              <p style={{ color: stackTheme.textMuted }} className="text-[12px] leading-[20px]">
                {profile?.job_field?.split("·")[0]} 면접에서 자주 묻는 역량인데, 아직 기록이
                없어요
              </p>
              <div className="flex flex-wrap gap-[6px]">
                {missingCore.slice(0, 3).map((name) => (
                  <Link
                    key={name}
                    href={`/stack/skill/${encodeURIComponent(name)}`}
                    style={{ borderColor: stackTheme.border, color: stackTheme.textSoft }}
                    className="rounded-full border px-[14px] py-[8px] text-[12px] font-medium leading-[20px] transition-opacity active:opacity-70"
                  >
                    {name}
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* 내 경력기술서 진입 (294:10326) */}
          <Link
            href="/resume/saved"
            style={{ backgroundColor: stackTheme.cardBg }}
            className="mt-[28px] flex items-center gap-2 rounded-[12px] p-[16px] transition-opacity active:opacity-80"
          >
            <span
              style={{ color: stackTheme.text }}
              className="text-[16px] font-medium leading-[28px]"
            >
              내 경력기술서
            </span>
            <span className="flex-1" />
            {draftCount !== null && (
              <span
                style={{ color: stackTheme.textSoft }}
                className="text-[12px] font-medium leading-[20px]"
              >
                {draftCount}개
              </span>
            )}
            <Image src="/icons/chevron-right.svg" alt="" width={16} height={16} aria-hidden />
          </Link>
        </div>
      )}

      {/* 주간 기록 스트릭 (9/14 신규) — 카드가 하나도 없으면 의미가 없어서 숨긴다.
          **구현 노트 (9/15)**: "점이 반응이 없다"는 피드백 반영 — 기록이 있는 날의
          점만 눌러서 그날 카드만 볼 수 있게 했다. 기록 없는 날은 누를 게 없으니
          그대로 비활성 점으로 둔다. */}
      {!loading && cards.length > 0 && (
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {streak.days.map((day) =>
              day.has ? (
                <button
                  key={day.date}
                  type="button"
                  onClick={() => toggleStreakDate(day.date)}
                  aria-label={`${formatCardDate(day.date)} 기록만 보기`}
                  aria-pressed={activeStreakDate === day.date}
                  className="flex -m-1 items-center justify-center p-1"
                >
                  <span
                    className={`block size-2 rounded-full transition-transform ${
                      activeStreakDate === day.date ? "scale-125 bg-amber-500" : "bg-[#f2f2f2]"
                    }`}
                  />
                </button>
              ) : (
                <span key={day.date} className="size-2 rounded-full bg-[#333]" />
              ),
            )}
          </div>
          {activeStreakDate ? (
            <button
              type="button"
              onClick={() => toggleStreakDate(activeStreakDate)}
              className="text-[11px] font-medium text-amber-600 underline underline-offset-2"
            >
              {formatCardDate(activeStreakDate)}만 보는 중 · 전체 보기
            </button>
          ) : (
            streak.consecutive > 0 && (
              <p className="text-[11px] font-medium text-[#828282]">연속 {streak.consecutive}일</p>
            )
          )}
        </div>
      )}

      {/* 프로젝트 스위처 + 전체보기 토글 — CLAUDE.md 3장: 프로젝트별로 카드가 구분돼야 한다.
          기록이 0장이면 숨긴다 (9/18) — 4.1-d 빈 상태 목업에는 이 줄이 없고, 나눌
          카드가 없는데 "인과관계로 묶어보기"를 권하는 건 빈 약속이다. */}
      <div className={`flex flex-wrap items-center gap-x-2 gap-y-1 ${isEmptyStack ? "hidden" : ""}`}>
        <ProjectSwitcher projectsState={projectsState} />
        {projects.length > 1 && (
          <button
            type="button"
            onClick={() => {
              setShowAllProjects((v) => !v);
              setGroupedView(false);
            }}
            className="shrink-0 whitespace-nowrap text-[12px] font-medium text-[#828282] underline underline-offset-2"
          >
            {showAllProjects ? "현재 프로젝트만" : "전체 프로젝트 보기"}
          </button>
        )}
        {/* 인과관계 그룹 보기 (9/14 신규) — 프로젝트 하나를 볼 때만 의미가 있어서
            "전체 프로젝트 보기" 중엔 숨긴다. 프로젝트가 아예 없는 계정(카드가 전부
            미분류)에서도 보여준다 — 섞일 프로젝트가 없으니 같은 이유가 적용되지
            않는다(9/18, 위 역량 집계와 같은 판단). */}
        {(currentProject || projects.length === 0) && !showAllProjects && (
          <button
            type="button"
            onClick={toggleGroupedView}
            disabled={groupsLoading}
            className={`shrink-0 whitespace-nowrap text-[12px] font-medium underline underline-offset-2 disabled:opacity-50 ${
              groupedView ? "text-[#f2f2f2]" : "text-[#828282]"
            }`}
          >
            {groupsLoading ? "분석 중…" : groupedView ? "묶어보기 끄기" : "인과관계로 묶어보기"}
          </button>
        )}
      </div>

      {groupsError && <p className="text-[12px] text-[#f0645c]">{groupsError}</p>}

      {/* "4.1.1 AI 프로젝트 자동 제안" 배너 (9/14 신규) — 미분류 카드가 서로 비슷해
          보일 때만 뜬다. 평소엔 안 보이는 화면이라 2.1 원칙(매일 경로 마찰 금지)에
          영향 없음 */}
      {suggestions.length > 0 && (
        <button
          type="button"
          onClick={openSuggestions}
          className="rounded-[12px] bg-indigo-950 px-3 py-2.5 text-left text-[12px] text-indigo-300"
        >
          미분류 기록 {suggestions[0].card_ids.length}개가 비슷해 보여요 — 프로젝트로 묶어볼까요?
        </button>
      )}


      {error && <p className="rounded-lg bg-[#2a1414] px-3 py-2 text-sm text-red-400">{error}</p>}

      {loading && (
        <div className="flex flex-col gap-[10px]">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="space-y-2 rounded-[12px] border border-[#2a2a2a] bg-[#1e1e1e] px-[14px] py-[13px]"
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
              className="space-y-2 rounded-[12px] border border-[#2a2a2a] bg-[#1e1e1e] px-[14px] py-[13px]"
            >
              <SkeletonLine className="h-3 w-1/3" />
              <SkeletonLine className="h-4 w-full" />
            </div>
          ))}
        </div>
      )}

      {/* "4.1-d 빈 상태 (카드 0장)" (Figma `294:10142`, 9/18 재설계). 예전엔 점선
          placeholder 박스였는데, 새 목업이 그 자리에 **앱 로고**를 넣고 문구도
          사람 이름을 부르는 쪽으로 바뀌었다. 백업 불러오기 진입도 같이 들어왔다 —
          기기를 옮겨 온 사람이 여기서 막히지 않게 하는 게 목적이라 설정까지
          찾아 들어가지 않아도 되게 링크를 둔다. */}
      {isEmptyStack && (
        <div className="flex min-h-[60svh] flex-col">
          {/* 로고 + 문구는 남는 공간 가운데에 놓고, 아래 두 버튼은 바닥에 붙인다
              (318:23233 "Zero State"가 flex-1 + 중앙정렬이다). */}
          <div className="flex flex-1 flex-col items-center justify-center py-[24px]">
            <Image
              /* 4.1-d의 로고는 로고마크 안에 워드마크가 들어간 72px 판이다
                 (318:23235). 웰컴 화면이 쓰는 `/welcome/logo-mark.svg`는 글자가 없는
                 도형만이라 다른 파일로 둔다. */
              src="/icons/logo-mark-72.svg"
              alt=""
              width={72}
              height={72}
              aria-hidden
            />
            <p
              style={{ color: stackTheme.text }}
              className="mt-[36px] text-center text-[20px] font-bold leading-[32px]"
            >
              아직은 비어 있어요
            </p>
            {/* 목업의 "00님"은 로그인한 사람의 이름 자리다(318:23250). 카카오 닉네임을
                모르면 이름 없이 "하루는 ~"으로 자연스럽게 이어지게 문구를 나눈다 —
                "님"만 덩그러니 남거나 없는 이름을 지어내지 않는다. */}
            <p
              style={{ color: stackTheme.textSoft }}
              className="mt-[20px] text-center text-[14px] leading-[24px]"
            >
              {me?.nickname ? `${me.nickname}님의 ` : ""}하루는 분명 가득했을 거예요.
              <br />한 줄만 남겨두면 여기부터 쌓이기 시작해요.
            </p>
          </div>

          <Link
            href="/settings"
            style={{ backgroundColor: stackTheme.cardBg }}
            className="mt-[12px] flex items-center gap-2 rounded-[12px] p-[16px] transition-opacity active:opacity-80"
          >
            <span className="flex flex-1 flex-col">
              <span
                style={{ color: stackTheme.text }}
                className="text-[16px] font-medium leading-[28px]"
              >
                백업 불러오기
              </span>
              <span
                style={{ color: stackTheme.textMuted }}
                className="text-[12px] leading-[20px]"
              >
                기기를 옮겨 오셨다면 백업 파일로 되살릴 수 있어요
              </span>
            </span>
            <Image src="/icons/chevron-right.svg" alt="" width={16} height={16} aria-hidden />
          </Link>

          {/* 318:23257 — 문구가 "기록하러 가기" → "첫 줄 남기러 가기"로 바뀌었고,
              가는 곳도 홈(대시보드)이 아니라 실제로 쓰는 화면이어야 맞다. 홈으로
              보내면 한 번 더 눌러야 입력창이 열린다. */}
          <Link
            href="/record"
            style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
            className="mt-[28px] flex h-[50px] items-center justify-center rounded-[8px] text-[14px] font-bold transition-opacity active:opacity-80"
          >
            첫 줄 남기러 가기
          </Link>
        </div>
      )}

      {!loading && !groupsLoading && (
        <ul className="flex flex-col gap-[10px]">
          {groups.map((group) => (
            <li
              key={`group-${group.parent.id}`}
              className="flex flex-col gap-2.5 rounded-[12px] border border-[#2a2a2a] bg-[#1e1e1e] px-[14px] py-[13px]"
            >
              <p className="text-[11px] font-semibold text-[#5e5e5e]">🔗 {group.title}</p>
              <div
                id={`card-${group.parent.id}`}
                className={`flex flex-col gap-2 rounded-lg transition-shadow ${highlightedCardId === group.parent.id ? "ring-2 ring-amber-400" : ""}`}
              >
                {renderCardBody(group.parent)}
              </div>
              {group.children.map((child) => (
                <div
                  key={child.id}
                  id={`card-${child.id}`}
                  className={`ml-3 flex flex-col gap-2 rounded-lg border-l-2 border-[#333] pl-3 transition-shadow ${highlightedCardId === child.id ? "ring-2 ring-amber-400" : ""}`}
                >
                  {renderCardBody(child)}
                </div>
              ))}
            </li>
          ))}
          {pagedUngrouped.map((card) => (
            <li
              key={card.id}
              id={`card-${card.id}`}
              className={`flex flex-col gap-2 rounded-[12px] border border-[#2a2a2a] bg-[#1e1e1e] px-[14px] py-[13px] transition-shadow ${highlightedCardId === card.id ? "ring-2 ring-amber-400" : ""}`}
            >
              {renderCardBody(card)}
            </li>
          ))}
        </ul>
      )}

      {/* 페이지네이션 (9/15 신규) — 목록이 1페이지뿐이면 숨긴다 */}
      {!groupedView && !loading && totalPages > 1 && (
        <div className="flex items-center justify-center gap-4 pt-1">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1}
            className="rounded-full border border-[#2a2a2a] bg-[#1e1e1e] px-3 py-[6px] text-[12px] font-medium text-[#828282] transition-colors disabled:opacity-40"
          >
            이전
          </button>
          <p className="text-[12px] font-medium text-[#5e5e5e]">
            {currentPage} / {totalPages}
          </p>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage >= totalPages}
            className="rounded-full border border-[#2a2a2a] bg-[#1e1e1e] px-3 py-[6px] text-[12px] font-medium text-[#828282] transition-colors disabled:opacity-40"
          >
            다음
          </button>
        </div>
      )}

      {/* 주 액션 (318:23142) — 9/18 개정에서 문구가 "마스터 경력기술서 초안 짜기" →
          "경력기술서 초안 만들기"로 짧아졌다. 범위 선택은 `/resume`에서 하므로
          "마스터"라는 말이 버튼에 없어도 뜻이 달라지지 않는다.
          기록이 0장이면 숨긴다 — 4.1-d 빈 상태의 주 액션은 [첫 줄 남기러 가기]
          하나뿐이고(목업), 묶을 기록이 없는데 초안을 만들 수도 없다. */}
      <div className={`pt-2 pb-4 ${isEmptyStack ? "hidden" : ""}`}>
        <Link
          href="/resume"
          className="flex h-[50px] w-full items-center justify-center rounded-[8px] bg-accent text-[14px] font-bold text-accent-foreground transition-colors hover:bg-[#ff7a2e] active:scale-[0.99]"
        >
          경력기술서 초안 만들기
        </Link>
      </div>

      {/* "+ 역량 추가" (Figma 4.1-h `294:10320`, 9/18 신규).
          역량은 카드의 태그에서 나오는 값이라, 이름만 만들어 두면 어디에도 안 붙는
          유령 역량이 된다(CLAUDE.md 3장이 AI 그룹핑을 저장하지 않는 것과 같은 이유 —
          붙일 데가 없는 분류는 관리 대상만 늘린다). 그래서 이름과 함께 **그 역량으로
          옮길 기록**을 같이 고르게 한다. */}
      <BottomSheet
        open={addTagOpen}
        onClose={() => setAddTagOpen(false)}
        title="역량 추가"
      >
        <div className="flex flex-col gap-3">
          <p className="text-[12px] text-[#a0a0a0]">
            역량 이름을 짓고, 이 역량으로 볼 기록을 고르세요. 고른 기록의 대표 역량이 이 이름으로
            바뀝니다.
          </p>
          <input
            value={newTagName}
            onChange={(e) => setNewTagName(e.target.value)}
            placeholder="예: 캠페인 운영"
            maxLength={40}
            className="rounded-[10px] bg-[#262626] px-3 py-2.5 text-sm text-[#f2f2f2] placeholder:text-[#5e5e5e] focus:outline-none"
          />
          <div className="flex max-h-[240px] flex-col gap-1 overflow-y-auto">
            {cards.map((card) => (
              <label
                key={card.id}
                className="flex cursor-pointer items-start gap-2 rounded-[10px] px-2 py-2 hover:bg-[#1e1e1e]"
              >
                <input
                  type="checkbox"
                  checked={newTagCardIds.has(card.id)}
                  onChange={() =>
                    setNewTagCardIds((prev) => {
                      const next = new Set(prev);
                      if (next.has(card.id)) next.delete(card.id);
                      else next.add(card.id);
                      return next;
                    })
                  }
                  className="mt-1 size-4 shrink-0 accent-[#ff5d00]"
                />
                <span className="flex-1 text-[13px] leading-[18px] text-[#f2f2f2]">
                  {card.refined_sentence}
                </span>
              </label>
            ))}
          </div>
          {addTagError && <p className="text-[12px] text-red-400">{addTagError}</p>}
          <button
            type="button"
            disabled={addingTag}
            onClick={handleAddTag}
            className="flex h-[50px] items-center justify-center rounded-[8px] bg-accent text-[14px] font-bold text-accent-foreground transition-opacity active:opacity-80 disabled:opacity-40"
          >
            {addingTag ? "적용하는 중…" : "이 역량으로 묶기"}
          </button>
        </div>
      </BottomSheet>

      {/* 카드 액션 시트 (Figma "4.1-a") */}
      {/* 4.1-a 카드 액션 시트 (Figma `307:19531`, 9/19 구조 반영).
          목업은 **어떤 기록에 대한 메뉴인지** 문장을 맨 위에 한 줄 보여주고, 메뉴는
          문장 고치기 / 복사하기 / 삭제 세 개를 56px 행 + 구분선으로 둔다. [취소]는
          메뉴 안이 아니라 아래 별도 버튼(50px)이다. 복사하기는 아예 없던 항목이다. */}
      <BottomSheet open={actionSheetCard !== null} onClose={() => setActionSheetCard(null)}>
        {actionSheetCard && (
          <div className="flex flex-col">
            <p
              style={{ color: stackTheme.textSoft }}
              className="line-clamp-1 text-[14px] leading-[24px]"
            >
              {actionSheetCard.refined_sentence}
            </p>
            <div className="mt-[20px] flex flex-col">
              <button
                type="button"
                onClick={() => {
                  const card = actionSheetCard;
                  setActionSheetCard(null);
                  if (card) startEditingTags(card);
                }}
                style={{ color: stackTheme.text }}
                className="flex h-[56px] items-center text-left text-[14px] leading-[24px] transition-opacity active:opacity-70"
              >
                문장 고치기
              </button>
              <div style={{ backgroundColor: stackTheme.border }} className="h-px w-full" />
              <button
                type="button"
                onClick={() => {
                  const card = actionSheetCard;
                  setActionSheetCard(null);
                  if (card) void handleCopyCard(card);
                }}
                style={{ color: stackTheme.text }}
                className="flex h-[56px] items-center text-left text-[14px] leading-[24px] transition-opacity active:opacity-70"
              >
                복사하기
              </button>
              <div style={{ backgroundColor: stackTheme.border }} className="h-px w-full" />
              <button
                type="button"
                onClick={() => {
                  const card = actionSheetCard;
                  setActionSheetCard(null);
                  setDeleteConfirmCard(card);
                }}
                className="flex h-[56px] items-center text-left text-[14px] leading-[24px] text-[#e8736c] transition-opacity active:opacity-70"
              >
                삭제
              </button>
            </div>
            <button
              type="button"
              onClick={() => setActionSheetCard(null)}
              style={{ borderColor: stackTheme.border, color: stackTheme.text }}
              className="mt-[12px] flex h-[50px] items-center justify-center rounded-[8px] border text-[14px] font-medium transition-opacity active:opacity-70"
            >
              취소
            </button>
          </div>
        )}
      </BottomSheet>

      {/* 4.1-c 삭제 확인 (Figma `307:19628`, 9/19 구조 반영).
          바텀시트로 올라왔는데 목업은 **화면 중앙 다이얼로그**(312 폭)다 — 되돌릴 수
          없는 동작이라 화면 가운데서 한 번 막아 세우는 쪽이 맞다.

          목업 둘째 줄은 "묶여 있는 기록 3개도 함께 사라져요"인데, 우리 삭제는 카드
          한 장만 지운다(묶음은 저장되는 게 아니라 그때그때 계산된다 — CLAUDE.md 3장).
          없는 동작을 경고하지 않도록 그 문장 대신 지울 기록을 그대로 보여준다. */}
      {deleteConfirmCard && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center px-[39px]">
          <button
            type="button"
            aria-label="닫기"
            className="absolute inset-0 bg-black/60"
            onClick={() => setDeleteConfirmCard(null)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="삭제 확인"
            style={{ backgroundColor: stackTheme.cardBg }}
            className="relative flex w-full max-w-[312px] flex-col rounded-[16px] px-[22px] py-[24px]"
          >
            <p style={{ color: stackTheme.text }} className="text-[20px] font-bold leading-[32px]">
              이 기록을 지울까요?
            </p>
            <p
              style={{ color: stackTheme.textSoft }}
              className="mt-[20px] line-clamp-2 text-[14px] leading-[24px]"
            >
              {deleteConfirmCard.refined_sentence}
            </p>
            <p
              style={{ color: stackTheme.textSoft }}
              className="mt-[4px] text-[14px] leading-[24px]"
            >
              되돌릴 수 없어요.
            </p>
            <div className="mt-[36px] flex gap-[8px]">
              <button
                type="button"
                onClick={() => setDeleteConfirmCard(null)}
                style={{ borderColor: stackTheme.border, color: stackTheme.text }}
                className="flex h-[50px] flex-1 items-center justify-center rounded-[8px] border text-[14px] font-medium transition-opacity active:opacity-70"
              >
                취소
              </button>
              <button
                type="button"
                onClick={() => handleDelete(deleteConfirmCard.id)}
                disabled={deletingId === deleteConfirmCard.id}
                className="flex h-[50px] flex-1 items-center justify-center rounded-[8px] bg-[#e8736c] text-[14px] font-bold text-black transition-opacity active:opacity-80 disabled:opacity-50"
              >
                {deletingId === deleteConfirmCard.id ? "삭제 중…" : "삭제"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 미분류 기록 묶기 검토 (Figma "4.2.1 범위 선택" 참고 — 다만 이름은 AI가
          안 짓고 사용자가 직접 입력한다) */}
      <BottomSheet
        open={suggestionsSheetOpen}
        onClose={() => setSuggestionsSheetOpen(false)}
        title="비슷한 기록을 프로젝트로 묶기"
      >
        {suggestions[0] && (
          <div className="flex flex-col gap-3">
            <p className="text-xs text-[#828282]">
              체크된 기록만 새 프로젝트에 포함됩니다. 관련 없는 기록은 체크를 해제해 주세요.
            </p>
            <ul className="flex max-h-48 flex-col gap-1.5 overflow-y-auto">
              {suggestions[0].cards.map((card) => (
                <li key={card.id}>
                  <label className="flex items-start gap-2 rounded-lg px-2 py-2 text-sm hover:bg-[#262626]">
                    <input
                      type="checkbox"
                      checked={selectedCardIds.has(card.id)}
                      onChange={() => toggleSelectedCard(card.id)}
                      className="mt-0.5"
                    />
                    <span className="text-[#f2f2f2]">{card.refined_sentence}</span>
                  </label>
                </li>
              ))}
            </ul>
            <input
              type="text"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              placeholder="프로젝트 이름 (예: A은행 차세대)"
              className="w-full rounded-md border border-[#3a3a3a] bg-[#141414] px-3 py-2 text-sm text-[#f2f2f2] placeholder:text-[#5e5e5e] focus:border-[#5e5e5e] focus:outline-none"
            />
            <input
              type="date"
              value={newProjectStartedAt}
              onChange={(e) => setNewProjectStartedAt(e.target.value)}
              className="w-full rounded-md border border-[#3a3a3a] bg-[#141414] px-3 py-2 text-sm text-[#f2f2f2] [color-scheme:dark] focus:border-[#5e5e5e] focus:outline-none"
            />
            {bundleError && <p className="text-xs text-[#f0645c]">{bundleError}</p>}
            <button
              type="button"
              onClick={handleBundle}
              disabled={bundling || selectedCardIds.size === 0}
              className="w-full rounded-xl bg-accent py-2.5 text-sm font-semibold text-accent-foreground transition-colors hover:bg-[#ff7a2e] disabled:opacity-40"
            >
              {bundling ? "묶는 중…" : `선택한 ${selectedCardIds.size}개를 프로젝트로 묶기`}
            </button>
            <button
              type="button"
              onClick={() => setSuggestionsSheetOpen(false)}
              className="text-center text-xs text-[#5e5e5e]"
            >
              나중에
            </button>
          </div>
        )}
      </BottomSheet>
      <Toast toast={toast} />
    </div>
  );
}

export default function StackPage() {
  return (
    <Suspense fallback={null}>
      <StackPageContent />
    </Suspense>
  );
}
