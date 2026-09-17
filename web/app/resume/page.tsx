"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ResumeCompareCarousel } from "@/components/ResumeCompareCarousel";
import { StarItemSection, formatStarItemForClipboard } from "@/components/StarItemCard";
import { StarItemSkeleton } from "@/components/Skeleton";
import { StarQuestionWizard } from "@/components/StarQuestionWizard";
import {
  ApiError,
  EnhancedItem,
  JdRequirementsResult,
  Profile,
  StarItem,
  enhanceResume,
  exportResumeDocx,
  getJdRequirements,
  getResumeDraft,
  getProfile,
  getStarQuestions,
  listCards,
  saveResumeDraft,
} from "@/lib/api";
import {
  buildResumeCached,
  peekCachedResume,
  peekCachedResumeGeneratedAt,
  updateCachedResumeItems,
} from "@/lib/resumeCache";
import { applyFieldOverrides, clearFieldOverride, setFieldOverride, StarField } from "@/lib/resumeFieldOverrides";
import { useProjects } from "@/lib/useProjects";

/** 프로필/프로젝트에서 실제로 있는 값만으로 문서 제목을 만든다 — 없는 정보를
 * 지어내 요약 문단을 만들지 않는다(CLAUDE.md 2.2). `build_resume()`은 제목/요약을
 * 생성하지 않으므로 여기서 조합 가능한 값만 쓴다. */
function buildResumeHeading(profile: Profile | null, projectName: string | null): string | null {
  if (profile?.job_field) {
    const parts = [profile.job_detail ?? profile.job_field];
    if (profile.years_segment) {
      parts.push(profile.years_segment === "10+" ? "10년 이상" : `${profile.years_segment}년차`);
    }
    return parts.join(" · ");
  }
  return projectName;
}

/** STAR 항목 한 건을 마크다운 섹션으로. 클립보드 복사 포맷과 동일한 본문을 재사용해
 * 두 곳에서 STAR→텍스트 변환 로직이 갈라지지 않게 한다. */
function toMarkdownSection(item: StarItem): string {
  const [header, ...rest] = formatStarItemForClipboard(item).split("\n");
  return [`## ${header}`, ...rest].join("\n");
}

function buildResumeMarkdown(heading: string | null, items: StarItem[]): string {
  const parts: string[] = [];
  if (heading) parts.push(`# ${heading}`);
  parts.push(...items.map(toMarkdownSection));
  return parts.join("\n\n");
}

/** 생성 시각(ISO)을 "생성 9/14" 형태로 (Figma 41:236 "생성 2/18 · 3,420자"). */
function formatGeneratedAt(iso: string): string | null {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `생성 ${d.getMonth() + 1}/${d.getDate()}`;
}

/** 저장 시각(ISO)을 "9월 14일 21:05" 형태로. 유효하지 않으면 원본 문자열 그대로. */
function formatSavedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

/**
 * 경력기술서 빌더 (`/resume`) — 이직 준비 경로. 무거운 호출이라 로딩 표시가 중요하다
 * (`docs/02-architecture.md` §2.2 — 입력 200토큰/150토큰짜리 매일 경로와 달리
 * 여기는 2,500/2,000토큰짜리 호출).
 *
 * Figma "4.2 경력기술서 빌더"는 STAR 항목들을 카드로 나열하지 않고 제목+요약 →
 * 항목별 라벨 행(상황/과제/행동/결과)이 이어지는 하나의 문서로 보여준다. 문서
 * 요약 문단은 `build_resume()`이 만들지 않는 데이터라 생성하지 않는다.
 *
 * **구현 노트 (9/14, 직접 편집+저장 추가)**: 사용자 요청 — "AI 초안을 계속 직접
 * 수정하면서 개선하는 게 낫지 않아?" 이건 AI가 만든 StarItem *구조*를 저장하는
 * 것과 다른 문제라고 판단해서 진행함(CLAUDE.md 3장이 막는 건 "AI 그룹핑을 정식
 * 데이터로 저장"이지, "유저가 그 결과를 가져다 직접 고친 자유 텍스트를 저장"이
 * 아니다 — 한 번 유저가 고치기 시작하면 카드 구조와 더 이상 엮여 있을 필요가
 * 없어서 재검증/재동기화 문제 자체가 안 생긴다). 간단한 버전으로 구현 — 항목별
 * 구조화 편집이 아니라 마크다운 텍스트 전체를 한 덩어리로 편집/저장한다.
 * `mode`가 "ai"(AI가 만든 구조화된 뷰 + 재생성)와 "edit"(자유 텍스트 편집 + 저장)를
 * 오간다. 저장된 초안이 있으면 마운트 시점에 서버에서 우선 불러와 "edit" 모드로
 * 바로 진입한다(AI 로컬 캐시 복원보다 우선 — 유저가 명시적으로 저장한 게 더
 * 신뢰할 수 있는 최신 버전이라서).
 */
export default function ResumePage() {
  const { currentProject, loading: projectsLoading } = useProjects();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [jdText, setJdText] = useState("");
  const [items, setItems] = useState<StarItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Figma 41:737 "초안 생성 실패" 전용 화면 — "저장된 카드 N장은 그대로 있습니다"
  // 문구에 쓸 개수. 실패했을 때만 조회하면 되므로 평소 렌더링 경로엔 영향 없다.
  const [errorCardCount, setErrorCardCount] = useState<number | null>(null);
  // Figma 41:714 "초안 생성 중" — "카드 N장을 조합하고 있어요" 문구용. handleBuild가
  // 카드 목록을 조회하는 김에 같이 채운다(별도 네트워크 호출 추가 없음).
  const [loadingCardCount, setLoadingCardCount] = useState<number | null>(null);
  const [showBuildForm, setShowBuildForm] = useState(true);
  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  // "숫자 되묻기" 인라인 입력(9/15 신규)이 캐시를 정확한 키로 갱신하려면, 지금
  // 보고 있는 items가 어떤 jdText로 생성됐는지 알아야 한다(캐시 키 = projectId+jdText).
  const [builtJdText, setBuiltJdText] = useState<string | undefined>(undefined);
  // Figma 41:236 "생성 2/18 · 3,420자" 메타 표시용 (9/16 신규).
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);

  const [mode, setMode] = useState<"ai" | "edit">("ai");
  const [draftContent, setDraftContent] = useState("");
  const [draftUpdatedAt, setDraftUpdatedAt] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"saved" | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);

  // "기존 경력기술서 붙여넣기 → Before/After 대조" (9/15 신규, Figma 90:612/90:640).
  // 완전히 선택 사항이라 기본은 접혀있다 — JD 폼처럼 매번 노출되면 2.1 위반.
  const [showPasteSection, setShowPasteSection] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [enhancing, setEnhancing] = useState(false);
  const [enhanceError, setEnhanceError] = useState<string | null>(null);
  const [compareItems, setCompareItems] = useState<EnhancedItem[] | null>(null);
  // "문장 수정"(Figma 89:419) override는 localStorage에 있어 리액트 state가 아니다 —
  // 이 카운터를 올려서 displayItems 메모를 강제로 다시 계산시킨다.
  const [overridesVersion, setOverridesVersion] = useState(0);

  // "공고 요구사항 매칭" (9/16 신규, Figma 100:692 "4.2-j2") — JD를 붙여넣고 분석하면
  // 실제 초안 생성 전에 먼저 보여준다. build_resume()보다 가벼운 별도 호출이라 로딩
  // 상태를 분리해서 관리한다.
  const [jdRequirements, setJdRequirements] = useState<JdRequirementsResult | null>(null);
  const [loadingRequirements, setLoadingRequirements] = useState(false);
  const [requirementsError, setRequirementsError] = useState<string | null>(null);

  // "AI 역질문" (9/16 신규, Figma 100:692 "4.2-3"/"4.2-2 모드 B") — items 배열의 몇 번째
  // 항목을 점검 중인지와 그 질문 목록. 질문이 하나도 없으면(이미 근거 충분) 위저드를
  // 아예 열지 않고 짧은 안내만 보여준다.
  const [wizardData, setWizardData] = useState<{ index: number; questions: string[] } | null>(null);
  const [questionsLoadingIndex, setQuestionsLoadingIndex] = useState<number | null>(null);
  const [questionsMessage, setQuestionsMessage] = useState<{ index: number; text: string } | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    getProfile()
      .then((p) => {
        if (!cancelled) setProfile(p);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // 프로젝트를 바꾸면 이전 프로젝트 기준으로 보던 내용은 더 이상 유효하지 않다 —
  // /stack의 프로젝트 전환 리셋과 동일한 이유(9/14).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setItems(null);
    setShowBuildForm(true);
    setMode("ai");
    setDraftContent("");
    setDraftUpdatedAt(null);
    setError(null);
    setDraftError(null);
    setShowPasteSection(false);
    setPasteText("");
    setEnhanceError(null);
    setCompareItems(null);
    setGeneratedAt(null);
    setJdRequirements(null);
    setRequirementsError(null);
    setWizardData(null);
    setQuestionsMessage(null);
  }, [currentProject?.id]);

  // 새로고침해도 방금 만든 경력기술서가 사라진 것처럼 보이지 않게, 마운트 시점에
  // 캐시(네트워크 호출 없음)를 먼저 들여다보고 있으면 즉시 복원한다 (9/14, 사용자
  // 지적 — web/lib/resumeCache.ts의 peekCachedResume() 참고). 카드 구성이 그 사이
  // 바뀌었을 수도 있는 낡은 값일 수 있는데, "다시 만들기"를 누르면 그때 정상
  // 검증된다.
  useEffect(() => {
    if (!currentProject) return;
    const cached = peekCachedResume(currentProject.id);
    if (cached) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setItems(cached);
      setShowBuildForm(false);
      setBuiltJdText(undefined); // 이 캐시 조회 자체가 jdText 없이 한 것과 같은 키
      setGeneratedAt(peekCachedResumeGeneratedAt(currentProject.id));
    }
  }, [currentProject]);

  // 서버에 저장된 초안이 있으면 위 AI 캐시 복원보다 우선해서 편집 모드로 바로
  // 들어간다 — 유저가 명시적으로 저장한 버전이 가장 신뢰할 수 있는 최신본이므로.
  useEffect(() => {
    if (!currentProject) return;
    let cancelled = false;
    getResumeDraft(currentProject.id)
      .then((draft) => {
        if (cancelled || !draft.content) return;
        setDraftContent(draft.content);
        setDraftUpdatedAt(draft.updated_at);
        setMode("edit");
        setShowBuildForm(false);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [currentProject]);

  const handleBuild = async () => {
    if (!currentProject) return;
    setLoading(true);
    setError(null);
    setErrorCardCount(null);
    setLoadingCardCount(null);
    try {
      // 카드 구성이 지난 생성 때와 같으면 재호출 없이 캐시에서 반환한다 (9/14, LLM
      // 호출 비용 절감 — web/lib/resumeCache.ts 참고). 카드는 여기서 한 번만
      // 조회해서 개수는 "초안 생성 중" 문구(41:714)에 바로 쓰고, buildResumeCached에도
      // 그대로 넘겨 내부에서 다시 조회하지 않게 한다.
      const usedJdText = jdText.trim() || undefined;
      const cards = await listCards(currentProject.id);
      setLoadingCardCount(cards.length);
      const result = await buildResumeCached(currentProject.id, { jdText: usedJdText, cards });
      setItems(result);
      setBuiltJdText(usedJdText);
      setGeneratedAt(peekCachedResumeGeneratedAt(currentProject.id, usedJdText));
      setShowBuildForm(false);
      setMode("ai");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "경력기술서 생성에 실패했습니다.");
      // 카드는 이미 안전하게 저장돼 있다 — 실패해도 몇 장이 남아있는지 보여줘서
      // 안심시킨다(Figma 41:737). 이 조회 자체가 실패해도 실패 화면은 그대로 보여준다.
      try {
        const cards = await listCards(currentProject.id);
        setErrorCardCount(cards.length);
      } catch {
        // 무시 — 개수 없이도 실패 화면은 뜬다.
      }
    } finally {
      setLoading(false);
    }
  };

  // JD를 붙여넣고 "공고 분석하기"를 누르면 실제 초안 생성 전에 요구사항 매칭부터
  // 보여준다(Figma "4.2-j2"). JD가 비어있으면 분석할 게 없으니 바로 handleBuild로.
  const handleAnalyzeJd = async () => {
    const trimmed = jdText.trim();
    if (!trimmed) {
      handleBuild();
      return;
    }
    if (!currentProject) return;
    setLoadingRequirements(true);
    setRequirementsError(null);
    try {
      const result = await getJdRequirements(currentProject.id, trimmed);
      setJdRequirements(result);
    } catch (err) {
      setRequirementsError(err instanceof ApiError ? err.detail : "공고 분석에 실패했습니다.");
    } finally {
      setLoadingRequirements(false);
    }
  };

  const heading = buildResumeHeading(profile, currentProject?.name ?? null);

  const handleEnhance = async () => {
    if (!currentProject) return;
    const existingItems = pasteText
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(0, 10);
    if (existingItems.length === 0) return;
    setEnhancing(true);
    setEnhanceError(null);
    try {
      const result = await enhanceResume(currentProject.id, existingItems);
      setCompareItems(result);
    } catch (err) {
      setEnhanceError(err instanceof ApiError ? err.detail : "보강에 실패했습니다.");
    } finally {
      setEnhancing(false);
    }
  };

  // 캐러셀을 다 돌면(적용/그대로 두기 선택 완료) 최종 텍스트를 자유 텍스트 초안에
  // 합쳐 곧바로 저장한다 — 새 저장 구조 없이 기존 PUT /resume/draft를 재사용한다
  // (CLAUDE.md 3장, AI가 만든 보강 결과 자체는 저장하지 않는다).
  const handleFinishCompare = async (finalTexts: string[]) => {
    const bulletLines = finalTexts.map((text) => `- ${text}`).join("\n");
    const markdown = heading ? `# ${heading}\n\n${bulletLines}` : bulletLines;

    setCompareItems(null);
    setShowPasteSection(false);
    setPasteText("");
    setDraftContent(markdown);
    setMode("edit");
    setShowBuildForm(false);

    if (!currentProject) return;
    try {
      const saved = await saveResumeDraft(currentProject.id, markdown);
      setDraftUpdatedAt(saved.updated_at);
    } catch (err) {
      setDraftError(err instanceof ApiError ? err.detail : "저장에 실패했습니다.");
    }
  };

  // "마크다운"/"노션 복사" 두 버튼으로 나뉘어 있었는데 실제로는 완전히 같은 텍스트를
  // 복사했다 — 노션은 붙여넣기 시 마크다운 문법을 자동으로 블록으로 변환해주므로
  // 별도 포맷이 필요 없다. 버튼 하나로 통합(9/16).
  const currentText = () =>
    mode === "edit" ? draftContent : displayItems ? buildResumeMarkdown(heading, displayItems) : "";

  const handleCopy = async () => {
    const text = currentText();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // 클립보드 접근 실패 — 조용히 무시
    }
  };

  const handleExportDocx = async () => {
    const text = currentText();
    if (!text) return;
    setExporting(true);
    setExportError(null);
    try {
      await exportResumeDocx(text);
    } catch (err) {
      setExportError(err instanceof ApiError ? err.detail : "내보내기에 실패했습니다.");
    } finally {
      setExporting(false);
    }
  };

  // "숫자 되묻기" 인라인 입력 적용 (9/15 신규) — 서버에 저장하지 않는다(StarItem은
  // 원래도 비영속 값, CLAUDE.md 3장). 화면 state와 로컬 캐시만 갱신해서 새로고침해도
  // 남아있게 한다.
  const handleApplyResult = (index: number, value: string) => {
    setItems((prev) => {
      if (!prev) return prev;
      const next = prev.map((it, i) => (i === index ? { ...it, result: value } : it));
      if (currentProject) updateCachedResumeItems(currentProject.id, next, builtJdText);
      return next;
    });
  };

  // "AI로 초안 점검하기" (9/16 신규) — 질문을 먼저 조회해서, 이미 근거가 충분해
  // 질문이 없는 항목이면 위저드를 아예 열지 않고 짧은 안내만 보여준다.
  const handleStartQuestions = async (index: number) => {
    const item = items?.[index];
    if (!item) return;
    setQuestionsLoadingIndex(index);
    setQuestionsMessage(null);
    try {
      const questions = await getStarQuestions(item);
      if (questions.length === 0) {
        setQuestionsMessage({ index, text: "이미 근거가 충분해서 점검할 게 없어요." });
      } else {
        setWizardData({ index, questions });
      }
    } catch (err) {
      setQuestionsMessage({
        index,
        text: err instanceof ApiError ? err.detail : "점검에 실패했습니다.",
      });
    } finally {
      setQuestionsLoadingIndex(null);
    }
  };

  // 역질문 반영 결과를 "적용"하면 items 배열의 그 항목만 교체한다 — "숫자 되묻기"
  // 인라인 입력(handleApplyResult)과 동일하게 서버에는 저장하지 않는다(3장).
  const handleApplyWizardResult = (updated: StarItem) => {
    if (!wizardData) return;
    const idx = wizardData.index;
    setItems((prev) => {
      if (!prev) return prev;
      const next = prev.map((it, i) => (i === idx ? updated : it));
      if (currentProject) updateCachedResumeItems(currentProject.id, next, builtJdText);
      return next;
    });
    setWizardData(null);
  };

  // 재생성해도 유지되는 표시용 배열 — items(순수 AI 원본)는 그대로 두고 override만
  // 덧씌워서, "AI 문장으로 되돌리기"가 항상 진짜 원본으로 돌아갈 수 있게 한다.
  const displayItems = useMemo(
    () => (items && currentProject ? applyFieldOverrides(items, currentProject.id) : items),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items, currentProject, overridesVersion],
  );

  const handleEditField = (index: number, field: StarField, value: string) => {
    if (!currentProject || !items) return;
    setFieldOverride(currentProject.id, items[index].source_card_ids, field, value);
    setOverridesVersion((v) => v + 1);
  };

  const handleRevertField = (index: number, field: StarField) => {
    if (!currentProject || !items) return;
    clearFieldOverride(currentProject.id, items[index].source_card_ids, field);
    setOverridesVersion((v) => v + 1);
  };

  const startEditing = () => {
    if (displayItems) setDraftContent(buildResumeMarkdown(heading, displayItems));
    setMode("edit");
  };

  const handleSaveDraft = async () => {
    if (!currentProject) return;
    setSaving(true);
    setDraftError(null);
    try {
      const saved = await saveResumeDraft(currentProject.id, draftContent);
      setDraftUpdatedAt(saved.updated_at);
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus(null), 1500);
    } catch (err) {
      setDraftError(err instanceof ApiError ? err.detail : "저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex min-h-full flex-col gap-4 bg-[#121212] px-5 pb-8">
      <div className="flex items-center gap-[10px] pb-[6px] pt-[8px]">
        <Link href="/stack" aria-label="뒤로" className="text-[17px] text-[#f2f2f2]">
          ←
        </Link>
      </div>

      <p className="text-sm text-[#a0a0a0]">
        {projectsLoading
          ? "프로젝트를 불러오는 중…"
          : currentProject
            ? `현재 프로젝트: ${currentProject.name}`
            : "먼저 입력 화면에서 프로젝트를 선택해 주세요."}
      </p>

      {mode === "edit" ? (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-[#a0a0a0]">
              직접 수정 중 — 저장하면 다음에 열 때도 그대로 보입니다.
              {draftUpdatedAt && (
                <span className="block text-[11px] text-[#828282]">
                  마지막 저장: {formatSavedAt(draftUpdatedAt)}
                </span>
              )}
            </p>
            <button
              type="button"
              onClick={() => setMode("ai")}
              className="shrink-0 text-xs font-medium text-[#a0a0a0] underline underline-offset-2"
            >
              AI 초안으로 돌아가기
            </button>
          </div>
          <textarea
            value={draftContent}
            onChange={(e) => setDraftContent(e.target.value)}
            rows={16}
            className="w-full resize-y rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e] p-4 text-[13px] leading-relaxed text-[#f2f2f2] focus:border-[#5e5e5e] focus:outline-none"
          />
          {draftError && (
            <p className="rounded-lg bg-[#2a1614] px-3 py-2 text-sm text-[#f0645c]">{draftError}</p>
          )}
          {exportError && (
            <p className="rounded-lg bg-[#2a1614] px-3 py-2 text-sm text-[#f0645c]">{exportError}</p>
          )}
          <div className="flex flex-col gap-[10px] rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e] p-4">
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleSaveDraft}
                disabled={saving}
                className="flex flex-1 items-center justify-center rounded-[11px] bg-[#f2f2f2] py-[13px] text-[12px] font-semibold text-[#171717] transition-colors hover:bg-white disabled:opacity-40"
              >
                {saving ? "저장 중…" : saveStatus === "saved" ? "저장됨" : "저장"}
              </button>
              <button
                type="button"
                onClick={handleExportDocx}
                disabled={exporting}
                className="flex flex-1 items-center justify-center rounded-[11px] border-[1.5px] border-[#2e2e2e] bg-[#1c1c1c] py-[13px] text-[12px] font-semibold text-[#f2f2f2] transition-colors hover:bg-[#242424] disabled:opacity-40"
              >
                {exporting ? "내보내는 중…" : "Word"}
              </button>
              <button
                type="button"
                onClick={handleCopy}
                className="flex flex-1 items-center justify-center rounded-[11px] border-[1.5px] border-[#2e2e2e] bg-[#1c1c1c] py-[13px] text-[12px] font-semibold text-[#f2f2f2] transition-colors hover:bg-[#242424]"
              >
                {copied ? "복사됨" : "복사"}
              </button>
            </div>
            <Link href="/" className="text-center text-[11px] text-[#828282]">
              다시 기록하러 가기 ↩
            </Link>
          </div>
        </div>
      ) : wizardData ? (
        <StarQuestionWizard
          item={items![wizardData.index]}
          questions={wizardData.questions}
          onCancel={() => setWizardData(null)}
          onApply={handleApplyWizardResult}
        />
      ) : compareItems ? (
        <ResumeCompareCarousel
          items={compareItems}
          onCancel={() => setCompareItems(null)}
          onFinish={handleFinishCompare}
        />
      ) : (
        <>
          {error && !items ? (
            <div className="flex flex-col items-center gap-4 px-4 py-16">
              <div className="flex size-12 items-center justify-center rounded-full bg-[#181818]">
                <span className="h-[18px] w-[3px] rounded-full bg-[#f0645c]" />
              </div>
              <div className="flex flex-col items-center gap-1">
                <p className="text-[15px] font-semibold text-[#f2f2f2]">초안 생성에 실패했어요</p>
                <p className="text-center text-[13px] text-[#a0a0a0]">
                  {errorCardCount != null && `저장된 카드 ${errorCardCount}장은 그대로 있습니다.`}
                  {errorCardCount != null && <br />}
                  잠시 후 다시 시도해 주세요.
                </p>
              </div>
              <div className="flex w-full flex-col gap-2.5">
                <button
                  type="button"
                  onClick={handleBuild}
                  className="w-full rounded-[12px] bg-[#f2f2f2] py-4 text-[14px] font-semibold text-[#171717] transition-colors hover:bg-white active:scale-[0.98]"
                >
                  다시 시도
                </button>
                <Link
                  href="/stack"
                  className="flex w-full items-center justify-center rounded-[12px] border-[1.5px] border-[#2e2e2e] bg-[#1c1c1c] py-4 text-[14px] font-semibold text-[#f2f2f2] transition-colors hover:bg-[#242424]"
                >
                  스택으로 돌아가기
                </Link>
              </div>
            </div>
          ) : (
            <>
          {(!items || showBuildForm) && jdRequirements && (
            <div className="flex flex-col gap-3 rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e] p-4">
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => setJdRequirements(null)}
                  aria-label="뒤로"
                  className="text-[17px] text-[#f2f2f2]"
                >
                  ←
                </button>
                <p className="text-sm font-semibold text-[#f2f2f2]">공고 분석 결과</p>
                <button
                  type="button"
                  onClick={() => setJdRequirements(null)}
                  className="text-[11px] font-medium text-[#828282] underline underline-offset-2"
                >
                  다시
                </button>
              </div>

              {(jdRequirements.job_title || jdRequirements.company || jdRequirements.years_label) && (
                <div>
                  <p className="text-[14px] font-bold text-[#f2f2f2]">
                    {jdRequirements.job_title || "채용 공고"}
                  </p>
                  <p className="text-[11px] text-[#828282]">
                    {[jdRequirements.company, jdRequirements.years_label].filter(Boolean).join(" · ")}
                  </p>
                </div>
              )}

              {jdRequirements.requirements.length > 0 ? (
                <>
                  <p className="text-[18px] font-bold leading-snug text-[#f2f2f2]">
                    요구사항 {jdRequirements.requirements.length}개 중{" "}
                    {jdRequirements.requirements.filter((r) => r.source_card_ids.length > 0).length}개에
                    기록이 있어요
                  </p>
                  <p className="text-[11px] text-[#a0a0a0]">기록이 있는 것만 골라서 경력기술서를 써요.</p>

                  <div className="flex flex-col overflow-hidden rounded-[14px] border border-[#2e2e2e]">
                    {jdRequirements.requirements.map((req, i) => {
                      const hasEvidence = req.source_card_ids.length > 0;
                      return (
                        <div
                          key={`${req.requirement}-${i}`}
                          className={`flex flex-col gap-1 px-3 py-3 ${i > 0 ? "border-t border-[#2e2e2e]" : ""} ${hasEvidence ? "" : "opacity-50"}`}
                        >
                          <div className="flex items-center gap-2">
                            <span
                              aria-hidden
                              className={`flex size-[13px] shrink-0 items-center justify-center rounded-full text-[8px] ${hasEvidence ? "bg-[#f2f2f2] text-[#171717]" : "bg-[#333] text-transparent"}`}
                            >
                              ✓
                            </span>
                            <p className="flex-1 text-[13px] text-[#f2f2f2]">{req.requirement}</p>
                            <p className="shrink-0 text-[11px] text-[#a0a0a0]">
                              {hasEvidence ? `기록 ${req.source_card_ids.length}` : "기록 없음"}
                            </p>
                          </div>
                          {req.source_dates.length > 0 && (
                            <p className="pl-[21px] text-[11px] text-[#828282]">
                              {req.source_dates.join(" · ")}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {jdRequirements.requirements.some((r) => r.source_card_ids.length === 0) && (
                    <div className="rounded-[10px] bg-[#181818] px-3 py-2.5">
                      <p className="text-[11px] text-[#a0a0a0]">
                        기록이 없는 요구사항은 초안에서 뒤로 밀려요. 지금 새로 기록하시면 반영돼요.
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-[13px] text-[#a0a0a0]">
                  공고에서 뽑을 만한 요구사항을 찾지 못했어요. 그래도 초안은 만들 수 있어요.
                </p>
              )}

              <button
                type="button"
                onClick={handleBuild}
                disabled={!currentProject || loading}
                className="w-full rounded-[999px] bg-[#f2f2f2] py-3 text-base font-semibold text-[#171717] transition-colors hover:bg-white disabled:opacity-40"
              >
                {loading ? "경력기술서 만드는 중… (최대 10초)" : "이 공고에 맞춰 초안 만들기"}
              </button>
            </div>
          )}

          {(!items || showBuildForm) && !jdRequirements && (
            <div className="flex flex-col gap-3 rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e] p-4">
              <p className="text-[15px] font-bold text-[#f2f2f2]">지원할 공고가 있나요?</p>
              <p className="text-xs leading-relaxed text-[#a0a0a0]">
                공고를 넣으면 그 공고가 요구하는 경험만 골라서 씁니다. 없으면 전체 기록으로 마스터
                버전을 만들어요.
              </p>
              <textarea
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
                placeholder="공고 내용을 붙여넣어 주세요 (선택)"
                rows={4}
                maxLength={20000}
                className="w-full resize-none rounded-[14px] border border-[#2e2e2e] bg-[#141414] p-3 text-sm text-[#f2f2f2] placeholder:text-[#5e5e5e] focus:border-[#5e5e5e] focus:outline-none"
              />
              {requirementsError && (
                <p className="rounded-lg bg-[#2a1614] px-3 py-2 text-sm text-[#f0645c]">
                  {requirementsError}
                </p>
              )}
              <button
                type="button"
                onClick={handleAnalyzeJd}
                disabled={!currentProject || loading || loadingRequirements}
                className="w-full rounded-[999px] bg-[#f2f2f2] py-3 text-base font-semibold text-[#171717] transition-colors hover:bg-white disabled:opacity-40 disabled:hover:bg-[#f2f2f2]"
              >
                {loadingRequirements
                  ? "공고 분석하는 중…"
                  : loading
                    ? "경력기술서 만드는 중… (최대 10초)"
                    : jdText.trim()
                      ? "공고 분석하기"
                      : "공고 없이 마스터 버전 만들기"}
              </button>

              <div className="h-px w-full bg-[#2e2e2e]" />

              {showPasteSection ? (
                <div className="flex flex-col gap-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] font-semibold text-[#f2f2f2]">
                      이미 쓰신 경력기술서가 있나요?
                    </p>
                    <button
                      type="button"
                      onClick={() => setShowPasteSection(false)}
                      className="shrink-0 text-xs font-medium text-[#828282] underline underline-offset-2"
                    >
                      건너뛰기
                    </button>
                  </div>
                  <p className="text-xs text-[#a0a0a0]">
                    한 항목만 붙여넣으면 쌓인 기록으로 얼마나 보강되는지 바로 비교해서 보여드려요.
                  </p>
                  <textarea
                    value={pasteText}
                    onChange={(e) => setPasteText(e.target.value)}
                    placeholder={"결제 API 성능 개선 담당"}
                    rows={3}
                    maxLength={10000}
                    className="w-full resize-none rounded-[14px] border border-[#2e2e2e] bg-[#141414] p-3 text-sm text-[#f2f2f2] placeholder:text-[#5e5e5e] focus:border-[#5e5e5e] focus:outline-none"
                  />
                  <div className="rounded-[14px] bg-[#181818] p-3 text-xs text-[#a0a0a0]">
                    <p className="font-medium text-[#f2f2f2]">이런 식으로 한 줄이면 충분해요</p>
                    <p className="mt-1">결제 API 성능 개선 담당</p>
                    <p>신규 회원 온보딩 플로우 기획</p>
                  </div>
                  {enhanceError && (
                    <p className="rounded-lg bg-[#2a1614] px-3 py-2 text-sm text-[#f0645c]">{enhanceError}</p>
                  )}
                  <button
                    type="button"
                    onClick={handleEnhance}
                    disabled={!pasteText.trim() || !currentProject || enhancing}
                    className="w-full rounded-[999px] bg-[#f2f2f2] py-3 text-sm font-semibold text-[#171717] transition-colors hover:bg-white disabled:opacity-40"
                  >
                    {enhancing ? "보강하는 중…" : "보강해서 비교하기"}
                  </button>
                  <p className="text-center text-[11px] text-[#828282]">
                    없으면 건너뛰세요. 새 경력기술서로 만들어 드려요.
                  </p>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setShowPasteSection(true)}
                  className="text-left text-xs font-medium text-[#a0a0a0] underline underline-offset-2"
                >
                  이미 쓰신 경력기술서가 있나요? (선택)
                </button>
              )}
            </div>
          )}

          {items && !showBuildForm && (
            <div className="flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowBuildForm(true);
                  setJdRequirements(null);
                }}
                className="text-xs font-medium text-[#a0a0a0] underline underline-offset-2"
              >
                JD를 바꿔 다시 만들기
              </button>
              {items.length > 0 && (
                <button
                  type="button"
                  onClick={startEditing}
                  className="text-xs font-medium text-[#f2f2f2] underline underline-offset-2"
                >
                  직접 수정하기 ✎
                </button>
              )}
            </div>
          )}

          {error && items && (
            <p className="rounded-lg bg-[#2a1614] px-3 py-2 text-sm text-[#f0645c]">{error}</p>
          )}

          {loading && (
            <div className="flex flex-col items-center gap-2 rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e] px-4 py-8">
              <span
                aria-hidden
                className="h-5 w-5 animate-spin rounded-full border-2 border-[#3a3a3a] border-t-[#f2f2f2]"
              />
              <p className="text-[13px] font-medium text-[#f2f2f2]">
                {loadingCardCount != null
                  ? `카드 ${loadingCardCount}장을 조합하고 있어요`
                  : "카드를 조합하고 있어요"}
              </p>
              <p className="text-[11px] text-[#a0a0a0]">보통 10~30초 걸립니다</p>
              <div className="flex w-full flex-col gap-3 pt-3">
                <StarItemSkeleton />
                <StarItemSkeleton />
              </div>
            </div>
          )}

          {items && !loading && (
            <>
              {items.length === 0 ? (
                <p className="px-1 py-8 text-center text-sm text-[#828282]">
                  아직 STAR로 묶을 만한 기록이 없습니다.
                </p>
              ) : (
                <div className="flex flex-col rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e] p-5">
                  {(heading || generatedAt) && (
                    <>
                      {heading && <p className="text-[16px] font-bold text-[#f2f2f2]">{heading}</p>}
                      {generatedAt && displayItems && (
                        <p className="mt-1 text-[11px] text-[#828282]">
                          {formatGeneratedAt(generatedAt)} ·{" "}
                          {buildResumeMarkdown(heading, displayItems).length.toLocaleString()}자
                        </p>
                      )}
                      <div className="my-3 h-px w-full bg-[#2e2e2e]" />
                    </>
                  )}
                  {(displayItems ?? items).map((item, i) => (
                    <div key={`${item.title}-${i}`}>
                      <StarItemSection
                        item={item}
                        onApplyResult={(v) => handleApplyResult(i, v)}
                        onEditField={(field, value) => handleEditField(i, field, value)}
                        onRevertField={(field) => handleRevertField(i, field)}
                      />
                      <button
                        type="button"
                        onClick={() => handleStartQuestions(i)}
                        disabled={questionsLoadingIndex === i}
                        className="pb-2 text-left text-[11px] font-medium text-[#828282] underline underline-offset-2 disabled:opacity-50"
                      >
                        {questionsLoadingIndex === i ? "점검 중…" : "✨ AI로 초안 점검하기"}
                      </button>
                      {questionsMessage?.index === i && (
                        <p className="pb-2 text-[11px] text-[#828282]">{questionsMessage.text}</p>
                      )}
                      {i < items.length - 1 && <div className="h-px w-full bg-[#2e2e2e]" />}
                    </div>
                  ))}
                </div>
              )}

              {items.length > 0 && (
                <div className="flex flex-col gap-[10px] rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e] p-4">
                  {exportError && (
                    <p className="rounded-lg bg-[#2a1614] px-3 py-2 text-sm text-[#f0645c]">
                      {exportError}
                    </p>
                  )}
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={handleExportDocx}
                      disabled={exporting}
                      className="flex flex-1 items-center justify-center rounded-[11px] border-[1.5px] border-[#2e2e2e] bg-[#1c1c1c] py-[13px] text-[12px] font-semibold text-[#f2f2f2] transition-colors hover:bg-[#242424] disabled:opacity-40"
                    >
                      {exporting ? "내보내는 중…" : "Word"}
                    </button>
                    <button
                      type="button"
                      onClick={handleCopy}
                      className="flex flex-1 items-center justify-center rounded-[11px] border-[1.5px] border-[#2e2e2e] bg-[#1c1c1c] py-[13px] text-[12px] font-semibold text-[#f2f2f2] transition-colors hover:bg-[#242424]"
                    >
                      {copied ? "복사됨" : "복사"}
                    </button>
                  </div>
                  <Link href="/" className="text-center text-[11px] text-[#828282]">
                    다시 기록하러 가기 ↩
                  </Link>
                </div>
              )}
            </>
          )}
            </>
          )}
        </>
      )}
    </div>
  );
}
