"use client";

import { FormEvent, Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { BottomSheet } from "@/components/BottomSheet";
import { CardResultSheet } from "@/components/CardResultSheet";
import { MetricQuestionScreen } from "@/components/MetricQuestionScreen";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { SentenceEditSheet } from "@/components/SentenceEditSheet";
import { CardResultSkeleton } from "@/components/Skeleton";
import { Toast, useToast } from "@/components/Toast";
import { VoiceInput } from "@/components/VoiceInput";
import {
  ApiError,
  Card,
  Profile,
  SkillSummary,
  createCard,
  getMetricQuestion,
  getProfile,
  getSkillSummary,
  listCards,
  refineCard,
  updateCard,
  uploadCardPhoto,
} from "@/lib/api";
import { resizeImageForUpload } from "@/lib/imageResize";
import { getCached, navKey, setCached } from "@/lib/navCache";
import { useProjects } from "@/lib/useProjects";

const DRAFT_KEY = "career-log:draft-raw-text";

/** 홈 버블은 상위 4개 + "미분류"까지 보여준다(서버 기본값과 같은 값을 명시해,
 * 캐시 키가 /stack의 50개짜리 집계와 섞이지 않게 한다). */
const HOME_TOP_N = 4;

/** 타깃 트랙 칩(Figma 41:116 "시니어 백엔드 ›")에 쓸 한 줄 라벨. 프로필에 실제로
 * 있는 값만 이어 붙인다 — 없는 직무/연차를 지어내지 않는다(CLAUDE.md 2.2). */
function targetTrackLabel(profile: Profile | null): string | null {
  if (!profile?.job_field) return null;
  return profile.job_detail ?? profile.job_field;
}

// 버블 색상(Figma 100:692 "흔적 버블 클러스터") — 순서대로 4개 카테고리, "미분류"는
// 항상 마지막 어두운 톤. 카테고리 이름을 색에 매핑하지 않고 순위(등장 순서)로만
// 매핑한다 — 태그 이름을 지어내지 않는 것과 같은 이유로, 색도 실제 데이터 순서를
// 그대로 따를 뿐 의미를 부여하지 않는다.
const BUBBLE_COLORS = [
  "rgba(255,162,89,0.88)",
  "rgba(255,203,86,0.88)",
  "rgba(233,131,111,0.88)",
  "rgba(224,124,124,0.88)",
];
const UNCATEGORIZED_COLOR = "rgba(58,53,46,0.88)";

/** "YYYY-MM-DD" 오늘 날짜 문자열 (로컬 기준) — `card.created_at`과 같은 포맷이라
 * 문자열 비교로 오늘 카드만 골라낼 수 있다. */
function todayDateString(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/**
 * 이어 쓰기 배너(Figma 41:119)가 가리킬 주제 — 오늘 이전 기록 중 가장 최근 것의
 * 대표 태그. 태그가 없는 카드는 이어 쓸 "주제"가 없으므로 건너뛴다. 카드 목록은
 * 오래된 순이라 뒤에서부터 찾는다.
 */
function lastTopicOf(cards: Card[]): string | null {
  const today = todayDateString();
  const previous = [...cards].reverse().find((c) => c.created_at < today && c.skill_tags.length > 0);
  return previous ? previous.skill_tags[0] : null;
}

/** 오늘 날짜 카드만. state 초기화(캐시)와 갱신 양쪽에서 같은 규칙을 쓰기 위한 헬퍼. */
function filterToday(cards: Card[]): Card[] {
  const today = todayDateString();
  return cards.filter((c) => c.created_at === today);
}

function formatTodayLabel(): string {
  const d = new Date();
  return `${d.getMonth() + 1}월 ${d.getDate()}일 · 오늘`;
}

/**
 * 홈 화면 (`/`) — 제품에서 매일 쓰는 유일한 경로 (Figma 100:692 "01·기록·Tab A",
 * "3.0-버 홈·흔적 버블").
 *
 * "3초 만에 끝내고 모니터 끄기"가 슬로건이다 (CLAUDE.md 2.1). 기존 "큰 입력창
 * 하나"만 있던 화면을, 오늘까지 쌓인 것을 먼저 보여주는 대시보드형으로 바꿨다 —
 * "무엇이 쌓였나요"(역량별 버블) + "오늘 남긴 것"(오늘 기록 리스트) + 입력창을
 * 한 화면에 둔다. 다크 테마는 디자인 시스템 문서(라이트, 다크는 "웰컴 전용"으로
 * 표기)와 실제 이 화면 코드가 서로 달랐는데, 사용자가 "화면 코드가 맞다"고
 * 확인해줘서 다크로 구현했다(9/16).
 */
function HomePageInner() {
  const [rawText, setRawText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Card | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiedResult, setCopiedResult] = useState(false);
  // 변환 실패 폴백 (9/15 신규) — result.refinement_failed가 true면 "다시 정리하기"로
  // 재시도할 수 있다. 카드는 이미 원문 그대로 저장돼 있으므로(CLAUDE.md P0) 재시도가
  // 또 실패해도 데이터 유실은 없다.
  const [refining, setRefining] = useState(false);
  const [refineError, setRefineError] = useState<string | null>(null);
  // 결과 시트의 헤드라인("오늘 하신 A/B 테스트는 …"). POST /api/cards 응답에만 실려
  // 오는 값이라(`case_summary`), 이후 PATCH/refine 응답으로 카드를 갈아끼워도
  // 헤드라인이 사라지지 않게 따로 붙들어 둔다.
  const [caseSummary, setCaseSummary] = useState("");
  // "3.1-q 변환 전 추가 질문" (9/18) — 값이 있으면 질문 화면이 전체를 덮는다.
  // 이 시점에 카드는 **아직 저장되지 않았다**. 뒤로 나가면 입력 화면으로 돌아간다.
  const [pendingQuestion, setPendingQuestion] = useState<{
    rawText: string;
    question: string;
    placeholder: string;
  } | null>(null);
  // "3.1-d 결과 문장 직접 수정" (9/18) — 결과 시트 위에 겹쳐 뜨는 수정 시트.
  const [editingSentence, setEditingSentence] = useState(false);
  // 저장 전에 고른 사진들 (9/18). 사진은 카드에 붙는 것이라 카드가 생기기 전엔
  // 올릴 수 없다 — 여기 들고 있다가 `createCard()` 성공 직후에 올린다.
  const [pendingPhotos, setPendingPhotos] = useState<File[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);

  // ProjectSwitcher에 그대로 넘긴다 — 훅 인스턴스를 이 화면과 공유해야 전환이 즉시
  // 반영된다(구현 노트: components/ProjectSwitcher.tsx 9/14 참고).
  const projectsState = useProjects();
  const { currentProject } = projectsState;

  // "무엇이 쌓였나요" 버블 + "오늘 남긴 것" 목록 (9/16 신규) — 둘 다 카드 목록에서
  // 나오는 값이라 하나로 묶어 조회한다(중복 호출 방지).
  //
  // 9/18 — 탭을 옮겨 다시 들어올 때 빈 화면부터 다시 그리지 않도록 캐시에서 시작한다
  // (`lib/navCache.ts`). 이 시점에 `currentProject`는 프로젝트 캐시 덕분에 이미
  // 정해져 있어서, 첫 렌더부터 지난번 내용을 그릴 수 있다.
  const cachedPid = currentProject?.id;
  const [skillSummary, setSkillSummary] = useState<SkillSummary | null>(
    () => (cachedPid ? getCached<SkillSummary>(navKey.skillSummary(cachedPid, HOME_TOP_N)) ?? null : null),
  );
  const [todayCards, setTodayCards] = useState<Card[]>(
    () => (cachedPid ? filterToday(getCached<Card[]>(navKey.cards(cachedPid)) ?? []) : []),
  );

  // 오프라인 배너 (Figma 41:762) — 자차 이동 중 신호가 끊긴 상태(CLAUDE.md 1장
  // 사용 맥락 2)에서도 방금 입력한 원문이 사라진 게 아니라는 걸 알려준다. 실제로
  // 텍스트박스 내용은 submitting에 실패해도 지우지 않으므로(아래 submitText),
  // 오프라인이면 애초에 제출 자체를 막아 원문이 화면에 그대로 남게 한다.
  const [isOffline, setIsOffline] = useState(false);

  // 타깃 트랙 칩 (Figma 41:116) — 지금 어떤 직무 기준으로 문장이 다듬어지는지 보여주고,
  // 누르면 설정으로 간다. 표시 전용이라 실패해도 칩만 안 뜬다.
  //
  // 9/18 — 캐시에서 시작한다. 이 칩은 화면 맨 위에 삽입되는 블록이라, 뒤늦게 나타나면
  // 아래 내용을 통째로 밀어내서 깜박이는 것처럼 보인다(실측: 문서 높이 740 → 798).
  const [profile, setProfile] = useState<Profile | null>(
    () => getCached<Profile>(navKey.profile()) ?? null,
  );

  // "이어 쓰기" (Figma 41:119 배너 / 89:519 "이 주제에 이어 쓰기", 9/18 신규).
  // 지금 쓰는 메모를 어느 주제(대표 태그)에 이어 붙일지. 값이 있으면 저장 직후
  // 그 태그를 카드에 확실히 얹어서, 다음에 같은 주제로 다시 찾아올 수 있게 한다.
  const [continueTag, setContinueTag] = useState<string | null>(null);
  // 배너에 쓸 "어제 하던 [X]" — 오늘 이전에 마지막으로 기록한 카드의 대표 태그.
  // 이 배너도 위쪽에 삽입되는 블록이라 같은 이유로 캐시에서 시작한다
  // (실측: 문서 높이 682 → 740).
  const [lastTopic, setLastTopic] = useState<string | null>(
    () => (cachedPid ? lastTopicOf(getCached<Card[]>(navKey.cards(cachedPid)) ?? []) : null),
  );

  const [toast, showToast] = useToast();
  const searchParams = useSearchParams();

  // 기록 상세(`/stack/<id>`)의 "이 주제에 이어 쓰기"가 `/?topic=...`으로 보낸다.
  useEffect(() => {
    const topic = searchParams.get("topic");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (topic) setContinueTag(topic);
  }, [searchParams]);

  useEffect(() => {
    let cancelled = false;
    getProfile()
      .then((p) => {
        setCached(navKey.profile(), p);
        if (!cancelled) setProfile(p);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsOffline(!navigator.onLine);
    const goOffline = () => setIsOffline(true);
    const goOnline = () => setIsOffline(false);
    window.addEventListener("offline", goOffline);
    window.addEventListener("online", goOnline);
    return () => {
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("online", goOnline);
    };
  }, []);

  // 위 오프라인 배너의 "원문은 저장됐어요"가 실제로 참이 되게 한다 — 텍스트박스
  // 내용을 매번 로컬에 남겨서, 오프라인 상태로 화면을 벗어나거나 새로고침해도
  // 방금 쓰던 원문을 잃지 않는다. 제출에 성공하면(rawText가 빈 문자열이 됨)
  // 자동으로 지워진다.
  useEffect(() => {
    try {
      const saved = localStorage.getItem(DRAFT_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (saved) setRawText(saved);
    } catch {
      // 접근 불가(프라이빗 모드 등) — 평소처럼 빈 입력으로 시작할 뿐 치명적이지 않다.
    }
  }, []);

  useEffect(() => {
    try {
      if (rawText) localStorage.setItem(DRAFT_KEY, rawText);
      else localStorage.removeItem(DRAFT_KEY);
    } catch {
      // 저장 실패해도 화면상 입력 자체는 지장 없다.
    }
  }, [rawText]);

  const refreshHomeData = () => {
    if (!currentProject) return;
    const projectId = currentProject.id;
    getSkillSummary(projectId, HOME_TOP_N)
      .then((summary) => {
        setSkillSummary(summary);
        setCached(navKey.skillSummary(projectId, HOME_TOP_N), summary);
      })
      .catch(() => {});
    listCards(projectId)
      .then((list) => {
        setCached(navKey.cards(projectId), list);
        setTodayCards(filterToday(list));

        setLastTopic(lastTopicOf(list));
      })
      .catch(() => {});
  };

  useEffect(refreshHomeData, [currentProject]);

  // 텍스트 입력과 음성 입력이 공유하는 단일 제출 경로 — 어느 쪽에서 오든 동일한
  // 스켈레톤/결과 모달 UX를 탄다 (docs/06-migration.md §2.1: 별도 흐름을 만들지 않는다).
  /**
   * 실제 저장 경로 — 메모(+되묻기 답)를 카드로 만든다.
   *
   * `metricAnswer`는 3.1-q에서 유저가 **직접 답한** 수치다. 건너뛰면 빈 문자열이고,
   * 그때 동작은 되묻기가 생기기 전과 완전히 같다 (CLAUDE.md 2.2 "건너뛰기 가능").
   */
  const createCardFrom = async (text: string, metricAnswer: string) => {
    setSubmitting(true);
    setError(null);
    setResult(null);
    setRefineError(null);
    try {
      // 응답이 3~10초 걸린다 (docs/05-api-contract.md §1) — 스켈레톤으로 대기 표시.
      let card = await createCard(text, metricAnswer || undefined);

      // "이어 쓰기"로 들어온 메모는 그 주제에 확실히 붙여준다 (9/18). LLM이 뽑은
      // 태그에 그 주제가 없을 수 있는데(같은 일을 다른 말로 적으면 어휘가 안 겹친다
      // — CLAUDE.md 2.3이 말하는 임베딩의 한계와 같은 문제), 여기서는 **유저가
      // 직접 고른 주제**라 추측이 아니다. 문장을 건드리지 않고 태그만 앞에 얹는다.
      if (continueTag && !card.skill_tags.includes(continueTag)) {
        try {
          card = await updateCard(card.id, { skillTags: [continueTag, ...card.skill_tags] });
        } catch {
          // 태그 얹기에 실패해도 카드 자체는 이미 저장됐다 — 결과는 그대로 보여준다.
        }
      }

      // 붙일 사진이 있으면 카드가 생긴 직후에 올린다. 실패해도 카드와 문장은 이미
      // 저장돼 있으므로 결과는 그대로 보여준다 — 사진 때문에 메모를 잃지 않는다.
      if (pendingPhotos.length > 0) {
        const files = pendingPhotos;
        setPendingPhotos([]);
        for (const file of files) {
          try {
            const { blob, filename } = await resizeImageForUpload(file);
            await uploadCardPhoto(card.id, blob, filename);
          } catch {
            // 개별 실패는 조용히 넘어간다(기록 상세에서 다시 붙일 수 있다).
          }
        }
      }

      setResult(card);
      // 3.1의 헤드라인은 POST 응답에만 실려 온다 — PATCH/refine 응답엔 없으므로
      // 여기서 따로 붙들어 둬야 "다시 만들기" 후에도 헤드라인이 안 사라진다.
      setCaseSummary(card.case_summary ?? "");
      setPendingQuestion(null);
      setRawText("");
      setContinueTag(null);
      refreshHomeData(); // 방금 쌓인 카드를 버블/오늘 목록에 바로 반영
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "저장에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * 텍스트 입력과 음성 입력이 공유하는 단일 제출 경로.
   *
   * 9/18 — 저장 앞에 "변환 전 추가 질문"(Figma 3.1-q)이 한 단계 붙었다. 다만
   * **항상 뜨는 게 아니다**: 서버가 "이 기록엔 수치가 정말로 빠졌다"고 판단할 때만
   * 질문이 오고, 그 외에는 빈 문자열이 와서 곧장 변환으로 넘어간다 — 매일 쓰는
   * 경로에 화면을 더하지 않기 위한 조건이다(CLAUDE.md 2.1).
   *
   * 판정 호출이 실패해도 그냥 질문 없이 진행한다. 이건 부가 단계라, 여기서 막히면
   * 메모 저장 자체가 막힌다(P0: 저장이 없으면 제품이 없다).
   */
  const submitText = async (text: string) => {
    if (!text || submitting || isOffline) return;

    setSubmitting(true);
    setError(null);
    try {
      const { question, placeholder } = await getMetricQuestion(text);
      if (question) {
        setPendingQuestion({ rawText: text, question, placeholder });
        setSubmitting(false);
        return;
      }
    } catch {
      // 판정 실패 — 되묻지 않고 그대로 변환한다.
    }
    await createCardFrom(text, "");
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    submitText(rawText.trim());
  };

  const handleCloseResult = () => {
    setResult(null);
    setEditingSentence(false);
  };

  const handleCopyResult = async (sentence: string) => {
    try {
      await navigator.clipboard.writeText(sentence);
      setCopiedResult(true);
      showToast("클립보드에 복사했어요"); // Figma 41:880 / 286:7211
      setTimeout(() => setCopiedResult(false), 1500);
    } catch {
      // 클립보드 접근 실패 — 조용히 무시
    }
  };

  /**
   * "다시 만들기" (Figma 286:7145) / 변환 실패 화면의 "다시 시도".
   *
   * 사람이 직접 고친 문장은 서버가 덮어쓰지 않는다 — 새 문장을 `ai_sentence`에만
   * 넣는다(3.1-d "직접 고친 문장은 다시 변환해도 유지돼요").
   */
  const handleRefine = async () => {
    if (!result) return;
    setRefining(true);
    setRefineError(null);
    try {
      const updated = await refineCard(result.id);
      setResult(updated);
      refreshHomeData(); // 오늘 목록에도 새 문장이 반영돼야 한다
    } catch {
      setRefineError("다시 정리하는 데 실패했어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setRefining(false);
    }
  };

  /** 3.1-d "저장" — 고친 문장을 카드에 반영한다. 실패하면 시트가 열린 채로 남는다. */
  const handleSaveSentence = async (sentence: string) => {
    if (!result) return;
    const updated = await updateCard(result.id, { refinedSentence: sentence });
    setResult(updated);
    setEditingSentence(false);
    refreshHomeData();
  };

  /** 3.1-d "AI 문장으로 되돌리기" — 서버가 보관 중인 ai_sentence로 되돌린다. */
  const handleRevertSentence = async () => {
    if (!result) return;
    const updated = await updateCard(result.id, { revertToAi: true });
    setResult(updated);
    setEditingSentence(false);
    refreshHomeData();
  };

  const totalCards = skillSummary?.total_cards ?? 0;
  const categoryCount = skillSummary?.categories.length ?? 0;
  const maxCount = Math.max(1, ...(skillSummary?.categories.map((c) => c.count) ?? [1]));

  return (
    <div className="flex flex-col gap-5 px-5 pt-[8px] pb-4 text-[#f2f2f2]">
      {/* Header */}
      <div className="flex items-center gap-2">
        <p className="text-[19px] font-bold tracking-[-0.5px]">오늘의 흔적</p>
        <div className="flex-1" />
        <ProjectSwitcher projectsState={projectsState} />
        <Link
          href="/settings"
          aria-label="설정"
          className="flex size-[26px] items-center justify-center rounded-full bg-[#1e1e1e] text-xs text-[#a0a0a0] transition-colors hover:bg-[#2a2a2a] active:scale-[0.95]"
        >
          ⚙
        </Link>
      </div>

      {isOffline && (
        <div className="flex items-center gap-2 rounded-[12px] bg-[#1e1e1e] px-3 py-2.5">
          <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#a0a0a0]" />
          <p className="text-[12px] text-[#a0a0a0]">
            오프라인 · 원문은 저장됐어요. 연결되면 자동으로 변환할게요
          </p>
        </div>
      )}

      {/* 타깃 트랙 (Figma 41:116) — 어떤 직무 기준으로 다듬어지는지. 탭하면 설정으로.
          프로필이 비어 있으면 아예 안 띄운다(빈 칩은 정보가 아니라 잡음이다). */}
      {targetTrackLabel(profile) && (
        <Link
          href="/settings"
          className="flex items-center gap-2 rounded-[12px] bg-[#1e1e1e] px-3 py-2.5 transition-colors hover:bg-[#242424]"
        >
          <span className="text-[11px] text-[#828282]">타깃 트랙</span>
          <span className="flex-1 truncate text-[12px] font-medium text-[#f2f2f2]">
            {targetTrackLabel(profile)}
          </span>
          <span aria-hidden className="text-[12px] text-[#5e5e5e]">
            ›
          </span>
        </Link>
      )}

      {/* 이어 쓰기 배너 (Figma 41:119) — "어제 하던 [X] 이어 쓰기". 이미 이어 쓰는
          중이거나 그 주제를 오늘 이미 건드렸으면 띄우지 않는다. */}
      {lastTopic && !continueTag && !todayCards.some((c) => c.skill_tags.includes(lastTopic)) && (
        <button
          type="button"
          onClick={() => {
            setContinueTag(lastTopic);
            textareaRef.current?.focus();
          }}
          className="flex items-center gap-2 rounded-[12px] bg-[#1e1e1e] px-3 py-2.5 text-left transition-colors hover:bg-[#242424]"
        >
          <span className="flex-1 truncate text-[12px] text-[#f2f2f2]">
            지난번 하던 <span className="font-semibold">[{lastTopic}]</span> 이어 쓰기
          </span>
          <span aria-hidden className="text-[12px] text-[#5e5e5e]">
            ›
          </span>
        </button>
      )}

      {/* 무엇이 쌓였나요 */}
      <div className="flex flex-col items-center gap-1">
        <p className="text-[27px] font-bold leading-[36px] tracking-[-0.9px]">무엇이 쌓였나요</p>
        {/* 아직 모르는 상태(skillSummary === null)에서 "기록이 쌓이면…"을 띄우면,
            잠시 뒤 실제 기록 수로 문구가 뒤집혀서 깜박이는 것처럼 보인다(9/18).
            모를 때는 자리만 잡아둔다. */}
        <p className="min-h-[18px] text-[12.5px] text-[#828282]">
          {skillSummary === null
            ? ""
            : totalCards > 0
              ? `기록 ${totalCards}개가 역량 ${categoryCount}개로 모였습니다`
              : "기록이 쌓이면 여기 역량별로 모아 보여드려요"}
        </p>
      </div>

      {skillSummary && skillSummary.categories.length > 0 && (
        <div className="flex flex-wrap items-center justify-center gap-3 py-2">
          {skillSummary.categories.map((cat, i) => {
            const size = Math.round(66 + (cat.count / maxCount) * 74);
            const isUncategorized = cat.tag === "미분류";
            const color = isUncategorized ? UNCATEGORIZED_COLOR : BUBBLE_COLORS[i % BUBBLE_COLORS.length];
            // "미분류" 버블은 배경이 어두워서(UNCATEGORIZED_COLOR) 다른 버블과 같은
            // 어두운 글자색(#2a2018)을 쓰면 대비가 너무 낮다 — 밝은 글자로 바꾼다.
            const textColor = isUncategorized ? "#d8d3c8" : "#2a2018";
            return (
              <div
                key={cat.tag}
                style={{ width: size, height: size, backgroundColor: color }}
                className="flex flex-col items-center justify-center gap-0.5 rounded-full px-2 text-center"
              >
                <p
                  className="line-clamp-2 text-[11px] font-medium leading-[14px]"
                  style={{ color: textColor }}
                >
                  {cat.tag}
                </p>
                <p className="text-[16px] font-bold leading-[20px]" style={{ color: textColor }}>
                  {cat.count}
                </p>
              </div>
            );
          })}
        </div>
      )}

      {/* 오늘 남긴 것 */}
      {todayCards.length > 0 && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-1.5">
            <p className="text-[11px] font-medium text-[#f2f2f2]">오늘 남긴 것</p>
            <div className="flex-1" />
            <p className="text-[11px] font-medium text-[#828282]">{todayCards.length}</p>
          </div>
          <div className="flex flex-col gap-3">
            {todayCards.map((card) => (
              <div key={card.id} className="flex gap-2.5 rounded-lg py-1">
                <p className="w-[38px] shrink-0 text-[11px] tracking-[0.4px] text-[#828282]">
                  {card.created_time ?? "--:--"}
                </p>
                <p className="flex-1 text-[13px] leading-[18px] text-[#f2f2f2]">
                  {card.refined_sentence}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 오늘 입력 */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <div className="flex items-center gap-1.5">
          <p className="text-[11px] font-medium text-[#a0a0a0]">{formatTodayLabel()}</p>
          <div className="flex-1" />
          <p className="text-[11px] font-medium text-[#828282]">기록 {todayCards.length}</p>
        </div>
        <div className="flex flex-col gap-2 rounded-[14px] bg-[#1e1e1e] px-[15px] py-[11px]">
          {/* 이어 쓰기 중임을 입력창 안에서 계속 보여준다 — 배너를 누르고 나면
              무엇에 이어 쓰는 중인지 알 방법이 없어진다. ✕로 언제든 해제. */}
          {continueTag && (
            <div className="flex items-center gap-1.5">
              <span className="rounded-full bg-[#2a2a2a] px-2.5 py-1 text-[11px] text-[#c8c8c8]">
                이어 쓰는 중 · {continueTag}
              </span>
              <button
                type="button"
                onClick={() => setContinueTag(null)}
                aria-label="이어 쓰기 해제"
                className="text-[11px] text-[#828282] transition-colors hover:text-[#f2f2f2]"
              >
                ✕
              </button>
            </div>
          )}
          {/* maxLength는 서버(schemas.py MAX_RAW_TEXT)와 같은 값으로 맞춘다 — 여기서
              먼저 끊어야 유저가 길게 쓴 뒤에야 422를 보는 일이 없다. */}
          <textarea
            ref={textareaRef}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder={"오늘 뭐 하셨어요?"}
            rows={2}
            maxLength={2000}
            className="w-full resize-none border-0 bg-transparent p-0 text-[14px] text-[#f2f2f2] placeholder:text-[#828282] focus:outline-none"
          />
          {/* 붙일 사진 미리보기 (9/18). 아직 카드가 없어서 업로드는 저장 직후에
              일어난다 — 여기서는 고른 파일만 들고 있는다. */}
          {pendingPhotos.length > 0 && (
            <div className="no-scrollbar flex gap-2 overflow-x-auto">
              {pendingPhotos.map((file, i) => (
                <PendingPhotoThumb
                  key={`${file.name}-${file.lastModified}-${i}`}
                  file={file}
                  onRemove={() => setPendingPhotos((prev) => prev.filter((_, j) => j !== i))}
                />
              ))}
            </div>
          )}

          <div className="flex items-center justify-end gap-2">
            {/* 사진 붙이기 (9/18) — "03 · 커리어 스택" 4.1-b가 기록에 붙은 사진을
                보여주는데, 정작 붙이는 화면이 어느 목업에도 없었다. 사용자가 9/18에
                "사진까지 전부 구현"으로 확정해서 이 버튼만 우리가 넣었다.
                LLM을 타지 않아서 변환 대기 시간에는 영향이 없다. */}
            <button
              type="button"
              onClick={() => photoInputRef.current?.click()}
              disabled={submitting || isOffline}
              aria-label="사진 붙이기"
              className="flex size-[36px] items-center justify-center rounded-full bg-[#2a2a2a] text-[15px] text-[#a0a0a0] transition-colors hover:bg-[#333] disabled:opacity-40"
            >
              ⊕
            </button>
            <input
              ref={photoInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              multiple
              onChange={(e) => {
                setPendingPhotos((prev) => [...prev, ...Array.from(e.target.files ?? [])]);
                // 같은 파일을 연달아 고를 수 있게 비운다.
                if (photoInputRef.current) photoInputRef.current.value = "";
              }}
              className="hidden"
            />
            {rawText.trim() ? (
              <button
                type="submit"
                disabled={submitting || isOffline}
                aria-label={isOffline ? "연결을 기다리는 중" : "경력 변환하기"}
                className="flex size-[36px] items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-foreground transition-colors disabled:opacity-40"
              >
                {submitting ? "…" : "↑"}
              </button>
            ) : (
              <VoiceInput variant="icon" onTranscript={submitText} disabled={submitting || isOffline} />
            )}
          </div>
        </div>
        {/* "노션에서 가져오기" (Figma 41:128) — 실제 연동 화면은 설정에 있다.
            매일 쓰는 경로에 선택지를 늘리지 않으려고 버튼이 아닌 작은 링크로 둔다. */}
        <Link
          href="/settings"
          className="self-end text-[11px] text-[#828282] underline underline-offset-2 transition-colors hover:text-[#a0a0a0]"
        >
          노션에서 가져오기
        </Link>
      </form>

      {submitting && <CardResultSkeleton />}

      {error && <p className="rounded-lg bg-[#1e1e1e] px-3 py-2 text-sm text-red-400">{error}</p>}

      {/* 변환 실패 폴백 (Figma 41:737, 9/15) — 이 경우만 예전 시트를 그대로 쓴다.
          "02 · 변환 결과" 섹션에는 실패 화면이 없어서 새 톤으로 다시 그릴 근거가
          없고, 여기서 중요한 건 "메모는 남아 있다"는 사실이지 색이 아니다. */}
      <BottomSheet
        open={!!result && !!result.refinement_failed}
        onClose={handleCloseResult}
        hideHandle
        panelClassName="relative w-full max-w-md rounded-tl-[24px] rounded-tr-[24px] bg-[#1a1a1a] px-5 pt-3 pb-[30px] shadow-xl"
      >
        {result && (
          <div className="flex flex-col gap-3.5">
            <div className="flex items-center justify-end">
              <button
                type="button"
                onClick={handleCloseResult}
                aria-label="닫기"
                className="flex size-[38px] items-center justify-center rounded-full bg-[#2a2a2a] text-sm text-[#a0a0a0] transition-colors hover:bg-[#333] active:scale-[0.95]"
              >
                ✕
              </button>
            </div>

            <div className="flex items-center gap-2">
              <span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-red-500" />
              <p className="text-[14px] font-semibold text-[#f2f2f2]">변환에 실패했어요</p>
            </div>
            <p className="text-[12px] text-amber-400">
              메모는 그대로 있습니다. 다시 시도하거나 원문만 저장할 수 있어요.
            </p>

            <div className="flex gap-3 rounded-[14px] bg-[#2a2320] px-4 py-[18px]">
              <div className="w-[3px] shrink-0 self-stretch rounded-full bg-amber-500" />
              <p className="flex-1 text-[14px] font-medium text-[#f2f2f2]">{result.raw_text}</p>
            </div>

            {refineError && <p className="text-[12px] text-red-400">{refineError}</p>}

            <div className="flex gap-2.5">
              <button
                type="button"
                onClick={handleRefine}
                disabled={refining}
                className="flex flex-1 items-center justify-center rounded-[12px] bg-accent py-4 text-[14px] font-semibold text-accent-foreground transition-colors active:scale-[0.98] disabled:opacity-40"
              >
                {refining ? "정리하는 중…" : "다시 시도"}
              </button>
              <button
                type="button"
                onClick={handleCloseResult}
                className="flex flex-1 items-center justify-center rounded-[12px] border-[1.5px] border-[#333] bg-transparent py-4 text-[14px] font-semibold text-[#f2f2f2] transition-colors hover:bg-[#2a2a2a] active:scale-[0.98]"
              >
                그냥 저장하기
              </button>
            </div>
          </div>
        )}
      </BottomSheet>

      {/* "3.1 결과 출력 모달" + 3.1-b/3.1-c 직무 전환 번역 (Figma 286:7130 등, 9/18).
          기존 시트에 있던 스킬 태그 칩과 ✕ 버튼은 재설계에서 빠졌다 — 태그는
          `/stack`에서 계속 보이고 고칠 수 있으므로 정보가 사라지진 않는다. */}
      {result && !result.refinement_failed && (
        <CardResultSheet
          card={result}
          caseSummary={caseSummary}
          currentJob={targetTrackLabel(profile)}
          targetJobs={profile?.target_jobs ?? []}
          onClose={handleCloseResult}
          onEditSentence={() => setEditingSentence(true)}
          onCopy={handleCopyResult}
          onRegenerate={handleRefine}
          copied={copiedResult}
          regenerating={refining}
          error={refineError}
        />
      )}

      {/* "3.1-d 결과 문장 직접 수정" (Figma 286:7148) — 결과 시트 위에 겹친다. */}
      {result && (
        <SentenceEditSheet
          open={editingSentence}
          sentence={result.refined_sentence}
          aiSentence={result.ai_sentence}
          onCancel={() => setEditingSentence(false)}
          onSave={handleSaveSentence}
          onRevertToAi={handleRevertSentence}
        />
      )}

      {/* "3.1-q 변환 전 추가 질문" (Figma 286:7306) — 카드는 아직 저장 전이다. */}
      {pendingQuestion && (
        <MetricQuestionScreen
          rawText={pendingQuestion.rawText}
          question={pendingQuestion.question}
          placeholder={pendingQuestion.placeholder}
          submitting={submitting}
          onBack={() => {
            // 되묻기 화면에서 뒤로 나가면 메모를 입력창에 되돌려준다 — 음성 입력으로
            // 들어온 경우 여기서 그냥 버리면 방금 말한 내용이 통째로 사라진다.
            setRawText(pendingQuestion.rawText);
            setPendingQuestion(null);
          }}
          onSubmit={(answer) => createCardFrom(pendingQuestion.rawText, answer)}
        />
      )}

      <Toast toast={toast} />
    </div>
  );
}

/**
 * 저장 전 사진 미리보기 한 장 (9/18). 누르면 목록에서 뺀다.
 *
 * `createObjectURL`로 만든 주소는 **직접 해제해야** 브라우저가 파일 버퍼를 놓는다 —
 * 여러 장을 고르고 지우기를 반복하면 그만큼 메모리가 쌓인다.
 */
function PendingPhotoThumb({ file, onRemove }: { file: File; onRemove: () => void }) {
  // 지연 초기화로 한 번만 만든다 — 이 컴포넌트는 파일 하나당 하나이고(key가 파일
  // 고유값), effect에서 setState를 부르지 않으려는 목적도 있다.
  const [url] = useState(() => URL.createObjectURL(file));

  useEffect(() => () => URL.revokeObjectURL(url), [url]);

  return (
    <button
      type="button"
      onClick={onRemove}
      aria-label={`${file.name} 빼기`}
      className="relative size-[44px] shrink-0 overflow-hidden rounded-[8px] border border-[#3a3a3a] bg-[#2a2a2a]"
    >
      {url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className="size-full object-cover" />
      )}
      <span className="absolute inset-0 flex items-center justify-center bg-black/40 text-[11px] text-white">
        ✕
      </span>
    </button>
  );
}

/**
 * `useSearchParams()`(기록 상세에서 넘어오는 `?topic=`)를 쓰기 때문에 Next.js가
 * 정적 렌더링에서 제외하려면 `<Suspense>` 경계가 필요하다 — `/stack`과 같은 구조다.
 */
export default function HomePage() {
  return (
    <Suspense fallback={null}>
      <HomePageInner />
    </Suspense>
  );
}

