"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { CardResultSheet } from "@/components/CardResultSheet";
import { MetricQuestionScreen } from "@/components/MetricQuestionScreen";
import { NotionPagePicker } from "@/components/NotionPagePicker";
import { SentenceEditSheet } from "@/components/SentenceEditSheet";
import { CardResultSkeleton } from "@/components/Skeleton";
import { stackTheme as t } from "@/components/stackTheme";
import { Toast, useToast } from "@/components/Toast";
import { VoiceInput } from "@/components/VoiceInput";
import {
  ApiError,
  Card,
  Profile,
  createCard,
  getMetricQuestion,
  getProfile,
  listCards,
  refineCard,
  updateCard,
  uploadCardPhoto,
} from "@/lib/api";
import { resizeImageForUpload } from "@/lib/imageResize";
import { getCached, navKey, setCached } from "@/lib/navCache";
import { useProjects } from "@/lib/useProjects";

/** 홈 대시보드와 같은 키 — 어느 쪽에서 쓰다 말았든 이어서 쓸 수 있어야 한다. */
const DRAFT_KEY = "career-log:draft-raw-text";

function formatTodayLabel(): string {
  const d = new Date();
  return `${d.getMonth() + 1}월 ${d.getDate()}일 · 오늘`;
}

/** "YYYY-MM-DD" 오늘 (로컬 기준) — `card.created_at`과 같은 포맷이라 문자열 비교로 쓴다. */
function todayDateString(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/**
 * 이어 쓰기 배너(Figma 3.0-i `299:12194`)가 가리킬 주제 — **오늘 이전** 기록 중 가장
 * 최근 것의 대표 역량.
 *
 * 태그가 없는 카드는 이어 쓸 "주제"가 없으므로 건너뛴다. 카드 목록은 최신순이라
 * 앞에서부터 찾는다. 오늘 이미 그 주제를 건드렸으면 호출부가 배너를 숨긴다 — 방금
 * 쓴 걸 다시 이어 쓰라고 권하면 잔소리가 된다.
 */
function lastTopicOf(cards: Card[]): string | null {
  const today = todayDateString();
  const previous = cards.find((c) => c.created_at < today && c.skill_tags.length > 0);
  return previous ? previous.skill_tags[0] : null;
}

/** 타깃 트랙 라벨 — 프로필에 실제로 있는 값만 쓴다(없는 직무를 지어내지 않는다). */
function jobLabel(profile: Profile | null): string | null {
  if (!profile?.job_field) return null;
  return profile.job_detail ?? profile.job_field;
}

/**
 * "3.3 맥락 지정 입력 (역량 · 공고 · 이어 쓰기)" (Figma `299:12223`, 9/18 신규)
 * + 그 뒤에 이어지는 변환 흐름(3.1-q / 3.1 / 3.1-d) 전체.
 *
 * **왜 홈에서 이리로 옮겼는가**: 3.0 홈이 "대시보드 + 진입점"으로 다시 그려지면서
 * 입력창이 알약 하나로 줄었다. 실제로 쓰는 자리가 이 화면이므로, 변환·되묻기·결과
 * 시트도 여기로 같이 옮겼다 — 두 화면에 나눠두면 한쪽만 고쳐지는 버그가 난다.
 *
 * 맥락 배너는 `?topic=`으로 들어온 역량을 보여주고 [해제]로 뗄 수 있다. 4.1-j "이
 * 역량으로 더 기록하기", 4.1-k "이 역량으로 기록하기", 기록 상세의 "이 주제에 이어
 * 쓰기"가 전부 이 파라미터로 들어온다.
 */
function RecordPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [rawText, setRawText] = useState("");
  const [topic, setTopic] = useState<string | null>(null);
  const [savedDraft, setSavedDraft] = useState(false);
  const [photos, setPhotos] = useState<File[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Card | null>(null);
  const [caseSummary, setCaseSummary] = useState("");
  const [copied, setCopied] = useState(false);
  const [refining, setRefining] = useState(false);
  const [refineError, setRefineError] = useState<string | null>(null);
  const [editingSentence, setEditingSentence] = useState(false);
  const [isOffline, setIsOffline] = useState(false);

  // 3.1-q 변환 전 추가 질문. 값이 있으면 질문 화면이 전체를 덮는다 — 이 시점에 카드는
  // 아직 저장되지 않았다. 건너뛴 질문은 결과 시트의 3.1-n 안내에 다시 쓰인다.
  const [pendingQuestion, setPendingQuestion] = useState<{
    rawText: string;
    question: string;
    placeholder: string;
  } | null>(null);
  const [skippedQuestion, setSkippedQuestion] = useState<string | null>(null);

  // "3.0-i 노션 미인증"의 [노션 연동하기] (Figma `299:12209`) — 누르면 페이지 선택
  // 화면이 뜨고, 고른 페이지 본문이 이 입력창에 들어온다. 대량 가져오기는 없다.
  const [notionOpen, setNotionOpen] = useState(false);

  // 이어 쓰기 배너 (Figma 3.0-i) — "어제 쓰던 [X]에 이어 쓰기". 홈이 대시보드로
  // 바뀌면서 갈 곳을 잃었던 블록이라 여기로 옮겨 왔다(9/18 재검토).
  const { currentProject, loading: projectsLoading } = useProjects();
  const [lastTopic, setLastTopic] = useState<string | null>(null);
  const [todayTopics, setTodayTopics] = useState<string[]>([]);

  const [profile, setProfile] = useState<Profile | null>(
    () => getCached<Profile>(navKey.profile()) ?? null,
  );
  const [toast, showToast] = useToast();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const photoInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTopic(searchParams.get("topic"));
  }, [searchParams]);

  useEffect(() => {
    getProfile()
      .then((p) => {
        setCached(navKey.profile(), p);
        setProfile(p);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (projectsLoading || !currentProject) return;
    const projectId = currentProject.id;
    let cancelled = false;
    listCards(projectId)
      .then((list) => {
        setCached(navKey.cards(projectId), list);
        if (cancelled) return;
        setLastTopic(lastTopicOf(list));
        const today = todayDateString();
        setTodayTopics(list.filter((c) => c.created_at === today).flatMap((c) => c.skill_tags));
      })
      .catch(() => {}); // 실패해도 배너만 안 뜬다 — 입력 자체는 그대로 된다
    return () => {
      cancelled = true;
    };
  }, [projectsLoading, currentProject]);

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

  // 쓰던 원문을 로컬에 남긴다 — "자동 저장됨" 표시가 실제로 참이 되게 하는 장치이고,
  // 오프라인으로 화면을 벗어나도 방금 쓰던 메모를 잃지 않게 한다.
  useEffect(() => {
    try {
      const stored = localStorage.getItem(DRAFT_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (stored) setRawText(stored);
    } catch {
      // 접근 불가(프라이빗 모드 등) — 빈 입력으로 시작할 뿐이다.
    }
    textareaRef.current?.focus();
  }, []);

  /**
   * 입력을 바꾸면서 곧바로 로컬에 남긴다.
   *
   * effect가 아니라 핸들러에서 하는 이유: "자동 저장됨" 표시는 **저장이 실제로
   * 됐는지**를 나타내야 하는데, effect에서 state를 또 건드리면 렌더가 한 번 더 돌고
   * 표시가 한 박자 늦는다. 여기서 쓰고 그 결과를 바로 반영하면 둘이 항상 같이 간다.
   */
  const updateRawText = (text: string) => {
    setRawText(text);
    try {
      if (text) localStorage.setItem(DRAFT_KEY, text);
      else localStorage.removeItem(DRAFT_KEY);
      setSavedDraft(!!text);
    } catch {
      // 접근 불가(프라이빗 모드 등) — 입력은 그대로 되지만 "저장됨"이라고 하지 않는다.
      setSavedDraft(false);
    }
  };

  /**
   * 실제 저장 경로 — 메모(+되묻기 답)를 카드로 만들고, 고른 사진을 이어서 올린다.
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

      // 맥락으로 들어온 역량은 확실히 붙여준다. LLM이 뽑은 태그에 그 역량이 없을 수
      // 있는데(같은 일을 다른 말로 적으면 어휘가 안 겹친다 — 2.3이 말하는 임베딩의
      // 한계와 같은 문제), 여기서는 **유저가 직접 고른 역량**이라 추측이 아니다.
      if (topic && !card.skill_tags.includes(topic)) {
        try {
          card = await updateCard(card.id, { skillTags: [topic, ...card.skill_tags] });
        } catch {
          // 태그 얹기에 실패해도 카드 자체는 이미 저장됐다 — 결과는 그대로 보여준다.
        }
      }

      // 사진은 카드가 생긴 뒤에만 붙일 수 있다. 실패해도 카드와 문장은 이미 저장돼
      // 있으므로 결과는 그대로 보여준다 — 사진 때문에 메모를 잃지 않는다.
      if (photos.length > 0) {
        const files = photos;
        setPhotos([]);
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
      // 헤드라인은 POST 응답에만 실려 온다 — 이후 PATCH/refine으로 카드를 갈아끼워도
      // 사라지지 않게 따로 붙들어 둔다.
      setCaseSummary(card.case_summary ?? "");
      setPendingQuestion(null);
      updateRawText("");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "저장에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setSubmitting(false);
    }
  };

  /**
   * [문장으로 바꾸기] — 저장 앞에 "변환 전 추가 질문"(3.1-q)이 한 단계 붙는다.
   *
   * 다만 **항상 뜨지 않는다**: 서버가 "이 기록엔 수치가 정말로 빠졌다"고 판단할 때만
   * 질문이 오고, 그 외에는 빈 문자열이 와서 곧장 변환으로 넘어간다(CLAUDE.md 2.1).
   * 판정이 실패해도 그냥 질문 없이 진행한다 — 부가 단계라 여기서 막히면 메모 저장
   * 자체가 막힌다(P0).
   */
  const handleConvert = async () => {
    const text = rawText.trim();
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
    setSkippedQuestion(null);
    await createCardFrom(text, "");
  };

  const handleCopy = async (sentence: string) => {
    try {
      await navigator.clipboard.writeText(sentence);
      setCopied(true);
      showToast("클립보드에 복사했어요");
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // 클립보드 접근 실패 — 조용히 무시
    }
  };

  /** "다시 만들기" — 사람이 고친 문장은 서버가 덮어쓰지 않는다(3.1-d). */
  const handleRefine = async () => {
    if (!result) return;
    setRefining(true);
    setRefineError(null);
    try {
      setResult(await refineCard(result.id));
    } catch {
      setRefineError("다시 정리하는 데 실패했어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setRefining(false);
    }
  };

  const handleSaveSentence = async (sentence: string) => {
    if (!result) return;
    setResult(await updateCard(result.id, { refinedSentence: sentence }));
    setEditingSentence(false);
  };

  const handleRevertSentence = async () => {
    if (!result) return;
    setResult(await updateCard(result.id, { revertToAi: true }));
    setEditingSentence(false);
  };

  /** 결과를 닫으면 할 일이 끝난 것이므로 홈으로 돌려보낸다(대시보드가 갱신된다). */
  const handleCloseResult = () => {
    setResult(null);
    setEditingSentence(false);
    router.push("/");
  };

  return (
    <div
      style={{ backgroundColor: t.screenBg, color: t.text }}
      className="flex min-h-full flex-col px-[22px] pt-[2px] pb-3"
    >
      {/* Header (299:12225) */}
      <div className="flex items-center gap-[10px] pb-[16px]">
        <button
          type="button"
          onClick={() => router.push("/")}
          aria-label="뒤로"
          className="flex size-[22px] items-center justify-center transition-opacity active:opacity-60"
        >
          <Image src="/icons/chevron-left.svg" alt="" width={20} height={20} aria-hidden />
        </button>
        <h1 className="text-[20px] font-bold leading-[32px]">기록하기</h1>
        <div className="flex-1" />
        {/* 설정 진입 (Figma 3.1 우상단) — 홈이 대시보드로 바뀌며 ⚙가 사라졌는데,
            목업은 이 화면 헤더에 두고 있다. 기록 탭 쪽의 유일한 설정 입구다. */}
        <Link
          href="/settings"
          aria-label="설정"
          style={{ backgroundColor: t.cardBg, color: t.textSoft }}
          className="flex size-[26px] items-center justify-center rounded-full text-[12px] transition-opacity active:opacity-70"
        >
          ⚙
        </Link>
      </div>

      <div className="flex flex-1 flex-col pt-[24px]">
        {/* 타깃 트랙 (Figma 3.0-i `299:12191`) — 어떤 직무 기준으로 문장이 다듬어지는지.
            프로필이 비어 있으면 아예 안 띄운다(빈 칩은 정보가 아니라 잡음이다). */}
        {jobLabel(profile) && (
          <Link
            href="/settings"
            style={{ color: t.textMuted }}
            className="mb-[12px] flex items-center gap-[6px] self-start text-[12px] font-medium leading-[20px] transition-opacity active:opacity-60"
          >
            {jobLabel(profile)}
            <Image src="/icons/chevron-right.svg" alt="" width={16} height={16} aria-hidden />
          </Link>
        )}

        {/* 이어 쓰기 배너 (Figma 3.0-i `299:12194`) — 오늘 그 주제를 이미 건드렸거나
            이미 맥락이 잡혀 있으면 띄우지 않는다. */}
        {lastTopic && !topic && !todayTopics.includes(lastTopic) && (
          <button
            type="button"
            onClick={() => setTopic(lastTopic)}
            style={{ backgroundColor: t.cardBg }}
            className="mb-[12px] flex items-center gap-[10px] rounded-[12px] px-[16px] py-[14px] text-left transition-opacity active:opacity-80"
          >
            <span className="flex-1 text-[14px] font-medium leading-[24px]">
              어제 쓰던 [{lastTopic}]에 이어 쓰기
            </span>
            <Image src="/icons/chevron-right.svg" alt="" width={16} height={16} aria-hidden />
          </button>
        )}

        {/* 맥락 배너 (299:12230) — 없으면 아예 안 띄운다. 빈 배너는 정보가 아니다. */}
        {topic && (
          <div
            style={{ backgroundColor: t.cardBg }}
            className="flex items-center gap-[10px] rounded-[12px] px-[16px] py-[14px]"
          >
            <p className="flex-1 text-[14px] font-medium leading-[24px]">
              {topic} 역량으로 기록해요
            </p>
            <button
              type="button"
              onClick={() => setTopic(null)}
              style={{ color: t.textSoft }}
              className="text-[12px] font-medium leading-[20px] transition-opacity active:opacity-60"
            >
              해제
            </button>
          </div>
        )}

        {isOffline && (
          <div
            style={{ backgroundColor: t.cardBg, color: t.textMuted }}
            className="mt-3 rounded-[12px] px-[16px] py-[14px] text-[12px] leading-[20px]"
          >
            오프라인 · 원문은 저장됐어요. 연결되면 변환할 수 있어요
          </div>
        )}

        <p
          style={{ color: t.textMuted }}
          className={`${topic || isOffline ? "mt-[20px]" : ""} text-[12px] font-medium leading-[20px]`}
        >
          {formatTodayLabel()}
        </p>

        <p className="mt-[20px] text-[28px] font-bold leading-[40px]">
          오늘은
          <br />
          어떤 일을 하셨나요?
        </p>

        {/* 오늘 입력 (히어로) (299:12238) */}
        <div
          style={{ borderColor: t.border }}
          className="mt-[12px] flex flex-col rounded-[8px] border pt-[26px] pb-[23px] pl-[24px] pr-[20px]"
        >
          {/* maxLength는 서버(schemas.py MAX_RAW_TEXT)와 같은 값 */}
          {/* Enter = 변환, Shift+Enter = 줄바꿈 (9/18 사용자 요청).
              **한글 입력 중(조합 중)에는 무시해야 한다** — 한글은 글자를 확정할 때도
              Enter를 누르는데, 그걸 제출로 받으면 "안녕"을 치다가 "안"에서 변환이
              돌아버린다. `isComposing`이 그 구분을 해준다. */}
          <textarea
            ref={textareaRef}
            value={rawText}
            onChange={(e) => updateRawText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== "Enter" || e.shiftKey) return;
              if (e.nativeEvent.isComposing) return;
              e.preventDefault();
              handleConvert();
            }}
            placeholder="오늘 뭐 하셨어요? (Enter로 변환, Shift+Enter 줄바꿈)"
            rows={4}
            maxLength={2000}
            aria-label="오늘 한 일"
            style={{ color: t.text }}
            className="w-full resize-none border-0 bg-transparent p-0 text-[14px] leading-[24px] placeholder:text-[#918c84] focus:outline-none"
          />

          {photos.length > 0 && (
            <div className="no-scrollbar mt-3 flex gap-2 overflow-x-auto">
              {photos.map((file, i) => (
                <button
                  key={`${file.name}-${file.lastModified}-${i}`}
                  type="button"
                  onClick={() => setPhotos((prev) => prev.filter((_, j) => j !== i))}
                  aria-label={`${file.name} 빼기`}
                  style={{ borderColor: t.border, backgroundColor: t.cardBg, color: t.textMuted }}
                  className="flex size-[44px] shrink-0 items-center justify-center rounded-[8px] border text-[11px]"
                >
                  ✕
                </button>
              ))}
            </div>
          )}

          <div className="mt-[12px] flex items-center gap-[10px]">
            <span className="flex items-center gap-[6px]">
              <span
                aria-hidden
                style={{ backgroundColor: savedDraft ? t.accentText : t.border }}
                className="size-[4px] rounded-full"
              />
              <span style={{ color: t.textSoft }} className="text-[12px] leading-[20px]">
                {savedDraft ? "자동 저장됨" : "자동 저장"}
              </span>
            </span>
            <span className="flex-1" />

            <button
              type="button"
              onClick={() => photoInputRef.current?.click()}
              aria-label="사진 붙이기"
              style={{ color: t.text }}
              className="flex size-[44px] items-center justify-center rounded-full text-[18px] transition-opacity active:opacity-60"
            >
              ⊕
            </button>
            <input
              ref={photoInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              multiple
              onChange={(e) => {
                setPhotos((prev) => [...prev, ...Array.from(e.target.files ?? [])]);
                if (photoInputRef.current) photoInputRef.current.value = "";
              }}
              className="hidden"
            />

            {/* 음성으로 받은 문장은 바로 변환하지 않고 입력창에 넣는다 — 이 화면의
                주 액션은 [문장으로 바꾸기]이고, 말하자마자 변환되면 고칠 틈이 없다. */}
            <VoiceInput
              variant="icon"
              disabled={submitting}
              onTranscript={(text) => updateRawText(rawText ? `${rawText} ${text}` : text)}
            />
          </div>
        </div>

        {error && <p className="mt-3 text-[12px] text-red-400">{error}</p>}
        {submitting && !pendingQuestion && (
          <div className="mt-4">
            <CardResultSkeleton />
          </div>
        )}

        {/* 노션 연동 행 (Figma 3.0-i `299:12208`) — 주 액션 바로 위. */}
        <div className="mt-[12px] flex items-center gap-[9px]">
          <button
            type="button"
            onClick={() => setNotionOpen(true)}
            style={{ backgroundColor: t.cardBg, borderColor: t.border, color: t.text }}
            className="shrink-0 rounded-[8px] border px-[13px] py-[14px] text-[14px] font-medium leading-[24px] transition-opacity active:opacity-70"
          >
            노션에서 가져오기
          </button>
          <p style={{ color: t.textMuted }} className="text-[12px] leading-[20px]">
            페이지 하나를 골라 본문만 가져와요
          </p>
        </div>

        <button
          type="button"
          onClick={handleConvert}
          disabled={!rawText.trim() || submitting || isOffline}
          style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
          className="mt-[28px] flex items-center justify-center rounded-[8px] py-[17px] text-[14px] font-bold transition-opacity active:opacity-80 disabled:opacity-40"
        >
          {submitting ? "만드는 중…" : "문장으로 바꾸기"}
        </button>
      </div>

      {/* 3.1 결과 출력 모달 (+ 3.1-b/3.1-c/3.1-n) */}
      {result && !result.refinement_failed && (
        <CardResultSheet
          card={result}
          caseSummary={caseSummary}
          currentJob={jobLabel(profile)}
          targetJobs={profile?.target_jobs ?? []}
          onClose={handleCloseResult}
          onEditSentence={() => setEditingSentence(true)}
          onCopy={handleCopy}
          onRegenerate={handleRefine}
          copied={copied}
          regenerating={refining}
          error={refineError}
          skippedMetricQuestion={skippedQuestion}
          onMetricFilled={(card) => {
            setResult(card);
            setSkippedQuestion(null);
          }}
        />
      )}

      {/* 변환 실패 폴백 (Figma 41:737) — 메모는 이미 원문 그대로 저장돼 있다. */}
      {result && result.refinement_failed && (
        <div className="fixed inset-0 z-50 flex items-end justify-center">
          <button
            type="button"
            aria-label="닫기"
            className="absolute inset-0 bg-black/40"
            onClick={handleCloseResult}
          />
          <div
            style={{ backgroundColor: t.cardBg }}
            className="relative flex w-full max-w-md flex-col gap-3.5 rounded-t-[24px] px-5 pt-6 pb-[30px]"
          >
            <p className="text-[14px] font-semibold">변환에 실패했어요</p>
            <p className="text-[12px] text-amber-400">
              메모는 그대로 있습니다. 다시 시도하거나 원문만 저장할 수 있어요.
            </p>
            <p className="rounded-[12px] bg-[#2a2320] px-4 py-[18px] text-[14px]">
              {result.raw_text}
            </p>
            {refineError && <p className="text-[12px] text-red-400">{refineError}</p>}
            <div className="flex gap-2.5">
              <button
                type="button"
                onClick={handleRefine}
                disabled={refining}
                style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
                className="flex-1 rounded-[12px] py-4 text-[14px] font-semibold disabled:opacity-40"
              >
                {refining ? "정리하는 중…" : "다시 시도"}
              </button>
              <button
                type="button"
                onClick={handleCloseResult}
                style={{ borderColor: t.border }}
                className="flex-1 rounded-[12px] border-[1.5px] py-4 text-[14px] font-semibold"
              >
                그냥 저장하기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 3.1-d 결과 문장 직접 수정 — 결과 시트 위에 겹친다. */}
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

      {/* 3.1-q 변환 전 추가 질문 — 이 시점에 카드는 아직 저장 전이다. */}
      {pendingQuestion && (
        <MetricQuestionScreen
          rawText={pendingQuestion.rawText}
          question={pendingQuestion.question}
          placeholder={pendingQuestion.placeholder}
          submitting={submitting}
          onBack={() => {
            updateRawText(pendingQuestion.rawText);
            setPendingQuestion(null);
          }}
          onSubmit={(answer) => {
            // 건너뛴 질문은 결과 시트의 3.1-n 안내에 그대로 다시 쓴다 — 묻지도 않은
            // 질문을 지어내지 않기 위해, 실제로 던졌던 질문만 들고 간다.
            setSkippedQuestion(answer ? null : pendingQuestion.question);
            createCardFrom(pendingQuestion.rawText, answer);
          }}
        />
      )}

      {/* 3.0-b 노션 페이지 선택 — 고른 페이지 본문이 입력창에 삽입된다. */}
      <NotionPagePicker
        open={notionOpen}
        onClose={() => setNotionOpen(false)}
        onPicked={(content, title) => {
          // 이미 쓰던 내용이 있으면 지우지 않고 아래에 이어 붙인다 — 실수로 날리면
          // 되돌릴 방법이 없다.
          const incoming = title ? `[${title}]\n${content}` : content;
          updateRawText(rawText.trim() ? `${rawText}\n\n${incoming}` : incoming);
          showToast("노션 본문을 가져왔어요");
        }}
      />

      <Toast toast={toast} />
    </div>
  );
}

/** `useSearchParams()`를 쓰므로 정적 렌더링에서 빼려면 `<Suspense>`가 필요하다. */
export default function RecordPage() {
  return (
    <Suspense fallback={null}>
      <RecordPageInner />
    </Suspense>
  );
}
