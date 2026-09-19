"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BottomSheet } from "@/components/BottomSheet";
import { SkeletonLine } from "@/components/Skeleton";
import { stackTheme as t } from "@/components/stackTheme";
import { ApiError, CardTagSuggestion, getTagSuggestions, updateCard } from "@/lib/api";
import { useProjects } from "@/lib/useProjects";

function formatCardDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const mm = `${d.getMonth() + 1}`.padStart(2, "0");
  const dd = `${d.getDate()}`.padStart(2, "0");
  return `${mm}.${dd}`;
}

/**
 * "4.1-i 분류 수정 (반자동 · 미분류 처리)" (Figma `301:15000`, 9/18 신규).
 *
 * `/stack`의 분류 헤더 [수정]에서 들어온다. 역량 태그가 없는 기록마다 AI가 가까운
 * 역량 2개를 칩으로 제시하고, 사용자가 맞는 것을 누르거나 다른 역량에서 고른다.
 *
 * **추천은 임베딩이고 확정은 사람이 한다** — CLAUDE.md 2.3이 말하는 임베딩의 자리
 * ("새 카드를 기존 작업 그룹에 배정, 보조적, 틀려도 손해 작음")이고, AI가 고른 걸
 * 그대로 저장하면 사용자가 검증하지 않은 분류가 조용히 굳는다. 그래서 고르기 전엔
 * 아무것도 저장되지 않고, [이대로 확정하기]를 눌러야 한 번에 반영된다.
 *
 * **없는 역량을 지어내지 않는다** — 후보는 이 유저가 이미 가진 역량 이름뿐이다
 * (서버 `suggest_tags_for_cards()`). 역량이 하나도 없으면 추천이 비고 "직접 추가"만
 * 남는다.
 */
export default function ClassifyPage() {
  const router = useRouter();
  const { currentProject, loading: projectsLoading } = useProjects();

  const [suggestions, setSuggestions] = useState<CardTagSuggestion[] | null>(null);
  const [knownTags, setKnownTags] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  /** 카드 id → 사용자가 고른 역량. 여기 있는 것만 확정 시 저장된다. */
  const [chosen, setChosen] = useState<Record<number, string>>({});
  /** "다른 역량에서 고르기" 시트를 연 카드. */
  const [pickerCardId, setPickerCardId] = useState<number | null>(null);
  /** "+ 역량 직접 추가" 시트. */
  const [customOpen, setCustomOpen] = useState(false);
  const [customName, setCustomName] = useState("");

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (projectsLoading) return;
    let cancelled = false;
    getTagSuggestions(currentProject?.id)
      .then((res) => {
        if (cancelled) return;
        setSuggestions(res.suggestions);
        setKnownTags(res.known_tags);
      })
      .catch((err) => {
        if (cancelled) return;
        setSuggestions([]);
        setLoadError(
          err instanceof ApiError ? err.detail : "역량을 추천해 드리지 못했어요.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [projectsLoading, currentProject?.id]);

  const choose = (cardId: number, tag: string) => {
    setChosen((prev) => (prev[cardId] === tag ? omit(prev, cardId) : { ...prev, [cardId]: tag }));
    setPickerCardId(null);
  };

  const handleConfirm = async () => {
    const entries = Object.entries(chosen);
    if (entries.length === 0) {
      router.back();
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      // 대표 태그(`skill_tags[0]`)로 넣어야 역량 목록/역량 상세 집계에 잡힌다.
      // 이 카드들은 원래 태그가 없던 것들이라 덮어쓸 기존 태그도 없다.
      await Promise.all(entries.map(([cardId, tag]) => updateCard(Number(cardId), { skillTags: [tag] })));
      router.push("/stack");
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.detail : "저장하지 못했어요.");
    } finally {
      setSaving(false);
    }
  };

  const loading = suggestions === null;
  const pickerCard = suggestions?.find((s) => s.card_id === pickerCardId) ?? null;

  return (
    <div
      style={{ backgroundColor: t.screenBg, color: t.text }}
      className="flex flex-1 flex-col px-[22px] pt-[6px] pb-6"
    >
      {/* Header (301:15002) */}
      <div className="flex items-center gap-[10px] pb-[16px]">
        <button
          type="button"
          onClick={() => router.back()}
          aria-label="뒤로"
          className="flex size-[22px] items-center justify-center transition-opacity active:opacity-60"
        >
          <Image src="/icons/chevron-left.svg" alt="" width={20} height={20} aria-hidden />
        </button>
        <h1 className="text-[20px] font-bold leading-[32px]">분류 수정</h1>
      </div>

      <div className="flex flex-1 flex-col gap-[12px] pt-[24px]">
        <p style={{ color: t.textSoft }} className="text-[14px] leading-[24px]">
          AI가 먼저 나눠뒀어요. 애매한 것만 골라주시면 돼요.
        </p>

        {loading && (
          <div className="flex flex-col gap-3 pt-3">
            <SkeletonLine />
            <SkeletonLine />
          </div>
        )}

        {loadError && <p className="text-[12px] text-red-400">{loadError}</p>}

        {!loading && (
          <>
            <div
              style={{ color: t.textMuted }}
              className="mt-[12px] flex items-center gap-2 text-[12px] font-medium leading-[20px]"
            >
              <p className="flex-1">미분류 기록</p>
              <p>{suggestions.length}</p>
            </div>

            {suggestions.length === 0 && (
              <p style={{ color: t.textMuted }} className="py-6 text-[14px] leading-[24px]">
                분류할 기록이 없어요. 모든 기록에 역량이 붙어 있습니다.
              </p>
            )}

            {suggestions.map((s) => (
              <div
                key={s.card_id}
                style={{ backgroundColor: t.cardBg }}
                className="flex flex-col gap-[9px] rounded-[12px] px-[16px] py-[18px]"
              >
                <p style={{ color: t.textSoft }} className="text-[12px] leading-[20px]">
                  {formatCardDate(s.card.created_at)}
                </p>
                <p className="text-[14px] leading-[24px]">{s.card.refined_sentence}</p>
                <p style={{ color: t.textSoft }} className="text-[12px] leading-[20px]">
                  {s.suggested_tags.length > 0
                    ? "AI가 추천했어요. 맞으면 눌러주세요."
                    : "아직 비교할 역량이 없어요. 직접 골라주세요."}
                </p>

                <div className="flex flex-wrap gap-[6px]">
                  {/* 고른 역량이 추천 칩에 없을 수도 있다(다른 역량에서 고르기 /
                      직접 추가) — 그때도 선택 상태가 보이도록 목록에 끼워 넣는다. */}
                  {dedupe([
                    ...s.suggested_tags,
                    ...(chosen[s.card_id] ? [chosen[s.card_id]] : []),
                  ]).map((tag) => {
                    const active = chosen[s.card_id] === tag;
                    return (
                      <button
                        key={tag}
                        type="button"
                        onClick={() => choose(s.card_id, tag)}
                        aria-pressed={active}
                        style={{
                          borderColor: active ? "var(--accent)" : t.border,
                          color: active ? "var(--accent)" : t.textSoft,
                        }}
                        className="rounded-full border px-[14px] py-[8px] text-[12px] font-medium leading-[20px] transition-opacity active:opacity-70"
                      >
                        {tag}
                      </button>
                    );
                  })}
                </div>

                <button
                  type="button"
                  onClick={() => setPickerCardId(s.card_id)}
                  style={{ color: t.accentText }}
                  className="self-start py-[12px] text-[12px] font-medium leading-[20px]"
                >
                  다른 역량에서 고르기&nbsp;&nbsp;›
                </button>
              </div>
            ))}

            <button
              type="button"
              onClick={() => setCustomOpen(true)}
              style={{ borderColor: t.border, color: t.text }}
              className="mt-[20px] flex h-[50px] items-center justify-center rounded-[8px] border text-[14px] font-medium transition-opacity active:opacity-70"
            >
              + 역량 직접 추가
            </button>
          </>
        )}

        <div className="min-h-[40px] flex-1" />

        {saveError && <p className="text-[12px] text-red-400">{saveError}</p>}

        <button
          type="button"
          onClick={handleConfirm}
          disabled={saving}
          style={{ backgroundColor: "var(--accent)", color: "var(--accent-foreground)" }}
          className="flex h-[50px] items-center justify-center rounded-[8px] text-[14px] font-bold transition-opacity active:opacity-80 disabled:opacity-40"
        >
          {saving ? "저장하는 중…" : "이대로 확정하기"}
        </button>
      </div>

      {/* 다른 역량에서 고르기 */}
      <BottomSheet
        open={pickerCard !== null}
        onClose={() => setPickerCardId(null)}
        title="역량 고르기"
      >
        {knownTags.length === 0 ? (
          <p className="py-4 text-[13px] text-[#a0a0a0]">
            아직 만들어진 역량이 없어요. [+ 역량 직접 추가]로 먼저 만들어 주세요.
          </p>
        ) : (
          <div className="flex max-h-[320px] flex-wrap gap-2 overflow-y-auto">
            {knownTags.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => pickerCard && choose(pickerCard.card_id, tag)}
                className="rounded-full border border-[#333] px-3 py-2 text-[12px] text-[#c8c8c8] transition-colors hover:bg-[#262626]"
              >
                {tag}
              </button>
            ))}
          </div>
        )}
      </BottomSheet>

      {/* + 역량 직접 추가 — 이름만 만들고, 어느 기록에 붙일지는 위 칩에서 고른다. */}
      <BottomSheet open={customOpen} onClose={() => setCustomOpen(false)} title="역량 직접 추가">
        <div className="flex flex-col gap-3">
          <p className="text-[12px] text-[#a0a0a0]">
            새 역량 이름을 만들면 위 기록들의 칩 목록에 함께 나타납니다. 붙일 기록을 골라
            [이대로 확정하기]를 눌러 주세요.
          </p>
          <input
            value={customName}
            onChange={(e) => setCustomName(e.target.value)}
            placeholder="예: 그로스 해킹"
            maxLength={40}
            className="rounded-[10px] bg-[#262626] px-3 py-2.5 text-sm text-[#f2f2f2] placeholder:text-[#5e5e5e] focus:outline-none"
          />
          <button
            type="button"
            onClick={() => {
              const name = customName.trim();
              if (!name) return;
              setKnownTags((prev) => dedupe([name, ...prev]));
              setCustomName("");
              setCustomOpen(false);
            }}
            className="flex h-[50px] items-center justify-center rounded-[8px] bg-accent text-[14px] font-bold text-accent-foreground transition-opacity active:opacity-80"
          >
            만들기
          </button>
        </div>
      </BottomSheet>
    </div>
  );
}

function omit(map: Record<number, string>, key: number): Record<number, string> {
  const next = { ...map };
  delete next[key];
  return next;
}

function dedupe(values: string[]): string[] {
  return Array.from(new Set(values));
}
