"use client";

import Image from "next/image";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { PhotoStrip } from "@/components/PhotoStrip";
import { SkeletonLine } from "@/components/Skeleton";
import { Toast, useToast } from "@/components/Toast";
import { ApiError, Card, Project, listCards, listProjects, updateCard } from "@/lib/api";

/**
 * "4.1-b 기록 상세 (이어 쓰기)" (Figma `89:479`, 9/18 신규).
 *
 * `/stack`의 카드를 누르면 오는 화면. 카드 한 장을 크게 보여주는 게 아니라,
 * **그 카드가 속한 "주제"를 통째로** 보여주는 게 핵심이다 — 같은 주제의 기록이
 * 시간 순으로 쌓여 있는 걸 눈으로 확인하고, 거기에 바로 이어 쓸 수 있다.
 * 제품의 결정적 순간("2월에 쓴 조치"와 "3월에 쓴 결과"가 한 문장으로 합쳐지는 것,
 * CLAUDE.md 1장)이 실제로 준비되고 있다는 걸 유저가 볼 수 있는 유일한 화면이다.
 *
 * **주제를 어떻게 정하는가**: 카드의 대표 태그(`skill_tags[0]`)가 같고 같은
 * 프로젝트에 있는 카드들을 한 주제로 본다. 이 묶음은 **저장하지 않는다** — 화면을
 * 열 때마다 카드에서 다시 계산한다(CLAUDE.md 3장: AI 작업 묶음을 DB에 저장하면
 * 관리 UI가 필요해지고 그 순간 2.1이 깨진다). 그래서 LLM도 부르지 않는다.
 *
 * **Figma와 다른 점 하나**: Figma는 이 화면 맨 위에 여러 기록이 합쳐진 "통합 경력
 * 문장"을 보여준다. 우리 데이터 모델에서 문장은 카드 한 장에 하나씩 붙어 있고
 * (`cards.refined_sentence`), 여러 장을 인과로 묶는 건 초안 생성 시점에 LLM이
 * 그때그때 하는 일이다. 없는 "통합 문장"을 여기서 새로 만들어 보여주면 (1) 화면을
 * 열 때마다 LLM을 부르게 되고 (2) 그 문장이 실제 경력기술서에 들어가는 문장과
 * 다를 수 있다. 그래서 이 카드의 실제 문장을 그대로 보여주고, 합쳐지는 건 초안
 * 생성 때 일어난다고 안내한다.
 */

/** "2023-02-24" -> "02.24" (Figma 89:510). */
function shortDate(isoDate: string): string {
  const parts = isoDate.split("-");
  return parts.length === 3 ? `${parts[1]}.${parts[2]}` : isoDate;
}

export default function CardDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const cardId = Number(params.id);

  const [cards, setCards] = useState<Card[] | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [toast, showToast] = useToast();

  useEffect(() => {
    let cancelled = false;
    Promise.all([listCards(), listProjects()])
      .then(([cardList, projectList]) => {
        if (cancelled) return;
        setCards(cardList);
        setProjects(projectList);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.detail : "기록을 불러오지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const card = cards?.find((c) => c.id === cardId) ?? null;
  const topic = card?.skill_tags[0] ?? null;

  /** 같은 프로젝트 + 같은 대표 태그 = 한 주제. 최신순으로 보여준다(Figma 89:507). */
  const topicCards = useMemo(() => {
    if (!cards || !card) return [];
    if (!topic) return [card]; // 태그가 없으면 주제를 만들 수 없다 — 자기 자신만
    return cards
      .filter((c) => c.project_id === card.project_id && c.skill_tags[0] === topic)
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [cards, card, topic]);

  const projectName = card ? (projects.find((p) => p.id === card.project_id)?.name ?? null) : null;

  const handleCopy = async () => {
    if (!card) return;
    try {
      await navigator.clipboard.writeText(card.refined_sentence);
      showToast("클립보드에 복사했어요");
    } catch {
      // 클립보드 접근 실패 — 조용히 무시
    }
  };

  const handleSave = async () => {
    if (!card) return;
    const next = draft.trim();
    if (!next || next === card.refined_sentence) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      const updated = await updateCard(card.id, { refinedSentence: next });
      setCards((prev) => (prev ? prev.map((c) => (c.id === updated.id ? updated : c)) : prev));
      setEditing(false);
      showToast("수정했어요");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "수정에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-4 px-5 pb-8 pt-[8px] text-[#f2f2f2]">
      <div className="flex items-center gap-[10px]">
        <button
          type="button"
          onClick={() => router.back()}
          aria-label="뒤로"
          className="flex size-[22px] items-center justify-center transition-opacity active:opacity-60"
        >
          <Image src="/icons/chevron-left.svg" alt="" width={20} height={20} aria-hidden />
        </button>
        <p className="text-[15px] font-bold">기록 상세</p>
      </div>

      {error && <p className="rounded-lg bg-[#2a1614] px-3 py-2 text-sm text-[#f0645c]">{error}</p>}

      {!cards ? (
        <div className="flex flex-col gap-2">
          <SkeletonLine />
          <SkeletonLine />
        </div>
      ) : !card ? (
        <div className="flex flex-col items-center gap-3 py-16">
          <p className="text-[14px] text-[#a0a0a0]">이 기록을 찾을 수 없어요.</p>
          <Link
            href="/stack"
            className="rounded-[12px] border-[1.5px] border-[#2e2e2e] bg-[#1c1c1c] px-4 py-2.5 text-[13px] font-semibold"
          >
            스택으로 돌아가기
          </Link>
        </div>
      ) : (
        <>
          {/* 메타 (Figma 89:492) */}
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-[#2a2a2a] px-2.5 py-1 text-[11px] text-[#c8c8c8]">
              {projectName ?? "미분류"}
            </span>
            {topic && (
              <span className="rounded-full bg-[#2a2a2a] px-2.5 py-1 text-[11px] text-[#c8c8c8]">
                #{topic}
              </span>
            )}
            <span className="text-[11px] text-[#828282]">기록 {topicCards.length}개</span>
          </div>

          {/* 경력기술서 문장 (Figma 89:496) */}
          <div className="flex flex-col gap-2.5 rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e] p-4">
            <p className="text-[11px] font-medium text-[#828282]">경력기술서 문장</p>
            {editing ? (
              <>
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={4}
                  maxLength={2000}
                  className="w-full resize-none rounded-[12px] border border-[#2e2e2e] bg-[#141414] p-3 text-[14px] leading-relaxed text-[#f2f2f2] focus:border-[#5e5e5e] focus:outline-none"
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={saving}
                    className="flex-1 rounded-[11px] bg-accent py-2.5 text-[12px] font-semibold text-accent-foreground disabled:opacity-40"
                  >
                    {saving ? "저장 중…" : "저장"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditing(false)}
                    className="flex-1 rounded-[11px] border-[1.5px] border-[#2e2e2e] bg-[#1c1c1c] py-2.5 text-[12px] font-semibold"
                  >
                    취소
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="text-[14px] leading-relaxed">{card.refined_sentence}</p>
                <div className="flex gap-4">
                  <button
                    type="button"
                    onClick={() => {
                      setDraft(card.refined_sentence);
                      setEditing(true);
                    }}
                    className="flex items-center gap-[6px] text-[12px] font-medium text-[#a0a0a0]"
                  >
                    {/* ✎ 문자 대신 Figma의 `icon/pencil` */}
                    <Image src="/icons/pencil.svg" alt="" width={14} height={14} aria-hidden />
                    <span className="underline underline-offset-2">직접 수정</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleCopy}
                    className="text-[12px] font-medium text-[#a0a0a0] underline underline-offset-2"
                  >
                    복사
                  </button>
                </div>
              </>
            )}
            <p className="text-[11px] leading-relaxed text-[#828282]">
              {topicCards.length > 1
                ? "이 주제의 기록들은 경력기술서를 만들 때 한 문장으로 합쳐집니다."
                : "이 주제에 기록이 더 쌓이면 경력기술서에서 하나로 합쳐집니다."}
            </p>
          </div>

          {/* 이 주제에 쌓인 기록 (Figma 89:503) — 원문을 그대로 보여준다. 여기가
              "시간차 누적"이 눈에 보이는 유일한 지점이다. */}
          <div className="flex flex-col gap-2">
            <p className="text-[11px] font-medium text-[#a0a0a0]">이 주제에 쌓인 기록</p>
            <div className="flex flex-col overflow-hidden rounded-[14px] border border-[#2e2e2e]">
              {topicCards.map((entry, i) => (
                <Link
                  key={entry.id}
                  href={`/stack/${entry.id}`}
                  className={`flex flex-col gap-1 px-3.5 py-3 transition-colors hover:bg-[#232323] ${
                    i > 0 ? "border-t border-[#2e2e2e]" : ""
                  } ${entry.id === card.id ? "bg-[#1e1e1e]" : ""}`}
                >
                  <p className="text-[11px] text-[#828282]">
                    {shortDate(entry.created_at)}
                    {i === 0 && " · 최신"}
                    {entry.id === card.id && " · 지금 보는 기록"}
                    {/* Figma 301:15068 "02.24 · 최신 · 사진 2" — 사진이 붙은 기록을
                        타임라인에서 바로 알아볼 수 있게 한다. */}
                    {(entry.photo_count ?? 0) > 0 && ` · 사진 ${entry.photo_count}`}
                  </p>
                  <p className="text-[13px] leading-relaxed text-[#f2f2f2]">{entry.raw_text}</p>
                </Link>
              ))}
            </div>
          </div>

          {/* 첨부한 사진 (Figma "03 · 커리어 스택" 4.1-b `301:15077`, 9/18 신규).
              기록에 근거 자료를 붙여두는 자리다 — 나중에 경력기술서를 쓸 때
              "그때 화면이 어땠더라"를 되살리는 용도라서, LLM을 타지 않고 그냥 저장만
              한다(변환 대기 시간에 영향 없음). */}
          <PhotoStrip cardId={card.id} initialCount={card.photo_count ?? 0} />

          {/* 이 주제에 이어 쓰기 (Figma 89:519) — 홈으로 돌아가되 주제를 들고 간다.
              주제가 없는 카드(태그 0개)는 이어 쓸 대상이 없으므로 일반 기록으로 보낸다. */}
          <Link
            href={topic ? `/?topic=${encodeURIComponent(topic)}` : "/"}
            className="w-full rounded-[12px] bg-accent py-4 text-center text-[14px] font-semibold text-accent-foreground transition-colors hover:bg-[#ff7a2e] active:scale-[0.98]"
          >
            {topic ? "이 주제에 이어 쓰기" : "기록하러 가기"}
          </Link>
        </>
      )}

      <Toast toast={toast} />
    </div>
  );
}
