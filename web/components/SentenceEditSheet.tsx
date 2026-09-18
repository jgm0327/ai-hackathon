"use client";

import { useEffect, useRef, useState } from "react";
import { resultTheme as t } from "@/components/resultTheme";

interface SentenceEditSheetProps {
  open: boolean;
  /** 지금 화면에 보이는 문장 (사람이 고쳤으면 고친 것) */
  sentence: string;
  /** 가장 최근 AI 문장. 없거나 현재 문장과 같으면 "되돌리기"를 띄우지 않는다. */
  aiSentence?: string | null;
  onCancel: () => void;
  onSave: (sentence: string) => Promise<void> | void;
  onRevertToAi: () => Promise<void> | void;
}

/**
 * "3.1-d 결과 문장 직접 수정" (Figma `286:7148` / 시트 `286:7153`, 9/18 신규).
 *
 * 결과 시트에서 "문장 고치기"를 누르면 올라오는 수정 시트다. 화면이 두 가지를 동시에
 * 약속한다 — **"직접 고친 문장은 다시 변환해도 유지돼요"**와 **"AI 문장으로 되돌리기"**.
 * 둘 다 지키려면 AI가 만든 문장과 사람이 고친 문장을 따로 들고 있어야 해서, 서버가
 * 카드에 `ai_sentence`/`sentence_edited`를 별도로 보관한다(`src/storage/db.py` 참고).
 * 여기서는 그 값을 받아 버튼을 띄울지만 판단한다.
 *
 * 저장은 `PATCH /api/cards/{id}`라 실패할 수 있다. 실패하면 시트를 닫지 않고 그대로
 * 둔다 — 시트가 닫히면 방금 고쳐 쓴 문장이 통째로 날아간다.
 */
export function SentenceEditSheet({
  open,
  sentence,
  aiSentence,
  onCancel,
  onSave,
  onRevertToAi,
}: SentenceEditSheetProps) {
  const [draft, setDraft] = useState(sentence);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 시트가 열릴 때마다 지금 문장에서 다시 시작한다. 닫힌 동안(다시 만들기 등으로)
  // 문장이 바뀌었을 수 있어서, 마운트 시점 한 번이 아니라 open 전환마다 맞춘다.
  useEffect(() => {
    if (!open) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraft(sentence);
     
    setError(null);
    textareaRef.current?.focus();
  }, [open, sentence]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  const trimmed = draft.trim();
  // 빈 문장으로 저장하면 결과 카드가 통째로 비어버린다 — 저장 자체를 막는다.
  const canSave = trimmed.length > 0 && trimmed !== sentence && !saving;
  // 이미 AI 문장과 같다면 되돌릴 게 없다. 마이그레이션 이전 카드는 ai_sentence가
  // 아예 없어서 자연스럽게 안 뜬다.
  const canRevert = !!aiSentence && aiSentence !== sentence && !saving;

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(trimmed);
    } catch {
      setError("저장하지 못했어요. 다시 시도해 주세요.");
    } finally {
      setSaving(false);
    }
  };

  const handleRevert = async () => {
    if (!canRevert) return;
    setSaving(true);
    setError(null);
    try {
      await onRevertToAi();
    } catch {
      setError("되돌리지 못했어요. 다시 시도해 주세요.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center">
      <button
        type="button"
        aria-label="닫기"
        className="absolute inset-0 bg-black/40"
        onClick={onCancel}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="문장 수정"
        style={{ backgroundColor: t.sheetBg }}
        className="relative flex w-full max-w-md flex-col gap-[18px] rounded-t-[24px] px-[22px] pt-[14px] pb-[26px] shadow-xl"
      >
        <div className="flex items-center justify-center pt-[2px] pb-[18px]">
          <div
            aria-hidden
            style={{ backgroundColor: t.handle }}
            className="h-[4px] w-[36px] rounded-full"
          />
        </div>

        {/* 헤더 — 취소 / 제목 / 저장 (Figma `299:12374`).
            9/18 대조: 세 라벨 모두 14px/24다(16px/28로 크게 잡혀 있었다). */}
        <div className="flex items-center gap-[10px]">
          <button
            type="button"
            onClick={onCancel}
            style={{ color: t.textSoft }}
            className="text-[14px] font-medium leading-[24px] transition-opacity active:opacity-60"
          >
            취소
          </button>
          <p
            style={{ color: t.text }}
            className="flex-1 text-center text-[14px] font-medium leading-[24px]"
          >
            문장 수정
          </p>
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave}
            style={{ color: t.action }}
            className="text-[14px] font-medium leading-[24px] transition-opacity active:opacity-60 disabled:opacity-35"
          >
            저장
          </button>
        </div>

        {/* 편집 가능 텍스트 영역 (Figma 286:7162) — 목업엔 테두리·배경이 없다.
            maxLength는 서버(schemas.py MAX_SENTENCE)와 같은 값. */}
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          maxLength={2000}
          aria-label="변환된 문장"
          style={{ color: t.text }}
          className="w-full resize-none border-0 bg-transparent px-[13px] py-[12px] text-[14px] leading-[24px] focus:outline-none"
        />

        {/* 편집 메타 (Figma 286:7164) */}
        <div
          style={{ color: t.textMuted }}
          className="flex items-center gap-2 text-[12px] leading-[20px] tracking-[0.4px]"
        >
          <p className="flex-1">직접 고친 문장은 다시 변환해도 유지돼요</p>
          <p className="shrink-0 text-right">{draft.length}자</p>
        </div>

        {error && <p className="text-[12px] text-red-400">{error}</p>}

        {canRevert && (
          <button
            type="button"
            onClick={handleRevert}
            style={{ backgroundColor: t.cardBg, color: t.textSoft }}
            className="self-start rounded-[8px] px-[16px] py-[14px] text-[12px] font-medium leading-[20px] tracking-[0.4px] transition-opacity active:opacity-70"
          >
            AI 문장으로 되돌리기
          </button>
        )}
      </div>
    </div>
  );
}
