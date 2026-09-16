"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { BottomSheet } from "@/components/BottomSheet";
import { StarItem } from "@/lib/api";
import { StarField } from "@/lib/resumeFieldOverrides";

export function formatStarItemForClipboard(item: StarItem): string {
  const lines = [
    `${item.title} (${item.period})`,
    `- 상황: ${item.situation}`,
    `- 과제: ${item.task}`,
    `- 행동: ${item.action}`,
  ];
  // result가 빈 문자열이면 줄 자체를 넣지 않는다 — "결과 없음"을 복사물에도 남기지 않는다.
  if (item.result) lines.push(`- 결과: ${item.result}`);
  return lines.join("\n");
}

/**
 * STAR 항목 한 건 (`/resume`). Figma "4.2 경력기술서 빌더"는 항목별 카드가 아니라
 * 하나의 연속된 문서(제목+기간 헤더 → 상황/과제/행동/결과 라벨 행)로 렌더링한다 —
 * 항목 사이 구분은 부모(`app/resume/page.tsx`)가 얇은 구분선으로 넣는다.
 *
 * `result`가 빈 문자열일 수 있다 — 기록에 숫자가 없으면 AI가 지어내지 않고
 * 비워서 반환하기 때문 (CLAUDE.md 2.2). "결과 없음"을 렌더링하지 않고,
 * 대신 되묻기 칩을 보여준다.
 *
 * **구현 노트 (9/14 → 9/15, 인라인 입력으로 변경)**: 원래는 되묻기 칩을 누르면
 * 매일 쓰는 입력 화면(`/`)으로 보내서 새 메모로 남기게 했다("이 화면에 폼을 새로
 * 만들면 2.1 위반"이라는 판단이었는데, `/resume`는 이미 JD 텍스트박스·초안 편집
 * textarea 같은 폼을 갖고 있는 화면이라 그 전제가 약했다). Figma "4.2-2 Before·After
 * 대조" 컨셉을 반영해 그 자리에서 바로 숫자를 채워 넣는 인라인 입력으로 바꿨다.
 * `/`로 새로 기록하는 기존 경로는 보조 링크로 축소해서 남겨뒀다.
 */
export function StarItemSection({
  item,
  onApplyResult,
  onEditField,
  onRevertField,
}: {
  item: StarItem;
  /** 인라인 입력에서 "적용"을 누르면 호출된다 — 부모가 items 배열의 이 항목만
   * 갱신한다. 서버에는 저장하지 않는다(StarItem은 원래도 비영속 값, CLAUDE.md 3장). */
  onApplyResult?: (value: string) => void;
  /** "문장 수정" 바텀시트(Figma 89:419)에서 저장을 누르면 호출된다. 부모가
   * `lib/resumeFieldOverrides.ts`에 저장해서 재생성해도 유지되게 한다. */
  onEditField?: (field: StarField, value: string) => void;
  /** "AI 문장으로 되돌리기" — 해당 필드의 override를 지운다. */
  onRevertField?: (field: StarField) => void;
}) {
  const router = useRouter();
  const [showSources, setShowSources] = useState(false);
  const [showResultInput, setShowResultInput] = useState(false);
  const [resultInput, setResultInput] = useState("");
  const [editingField, setEditingField] = useState<StarField | null>(null);
  const [editValue, setEditValue] = useState("");

  const handleApplyResult = () => {
    const trimmed = resultInput.trim();
    if (!trimmed) return;
    onApplyResult?.(trimmed);
    setShowResultInput(false);
    setResultInput("");
  };

  const openEditSheet = (field: StarField, currentValue: string) => {
    setEditingField(field);
    setEditValue(currentValue);
  };

  const handleSaveEdit = () => {
    if (!editingField) return;
    const trimmed = editValue.trim();
    if (trimmed) onEditField?.(editingField, trimmed);
    setEditingField(null);
  };

  const handleRevertEdit = () => {
    if (!editingField) return;
    onRevertField?.(editingField);
    setEditingField(null);
  };

  const rows: Array<{ label: string; field: StarField; value: string }> = [
    { label: "상황", field: "situation", value: item.situation },
    { label: "과제", field: "task", value: item.task },
    { label: "행동", field: "action", value: item.action },
  ];

  return (
    <div className="flex flex-col gap-2.5 py-4">
      <div className="flex items-center gap-2">
        <p className="text-[14px] font-bold text-[#18181b]">{item.title}</p>
        <div className="flex-1" />
        <p className="text-right text-[10px] text-[#a1a1aa]">{item.period}</p>
      </div>

      <div className="flex flex-col gap-2">
        {rows.map((row) => (
          <div key={row.label} className="flex gap-[10px]">
            <div className="flex w-[30px] shrink-0 items-start gap-1">
              <p className="text-[11px] font-semibold text-black">{row.label}</p>
            </div>
            <p className="flex-1 text-[12px] leading-relaxed text-[#18181b]">{row.value}</p>
            <button
              type="button"
              onClick={() => openEditSheet(row.field, row.value)}
              aria-label={`${row.label} 문장 수정`}
              className="shrink-0 text-[11px] text-[#a1a1aa] hover:text-zinc-600"
            >
              ✎
            </button>
          </div>
        ))}

        <div className="flex gap-[10px]">
          <div className="w-[30px] shrink-0">
            <p className="text-[11px] font-semibold text-black">결과</p>
          </div>
          <div className="flex flex-1 flex-col gap-1.5">
            {item.result ? (
              <div className="flex gap-[10px]">
                <p className="flex-1 text-[12px] leading-relaxed text-[#18181b]">{item.result}</p>
                <button
                  type="button"
                  onClick={() => openEditSheet("result", item.result)}
                  aria-label="결과 문장 수정"
                  className="shrink-0 text-[11px] text-[#a1a1aa] hover:text-zinc-600"
                >
                  ✎
                </button>
              </div>
            ) : showResultInput ? (
              <div className="flex flex-col gap-1.5">
                <input
                  type="text"
                  value={resultInput}
                  onChange={(e) => setResultInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleApplyResult();
                    }
                  }}
                  placeholder="예: 오류율 0.8%→0.3%, 처리 속도 10배"
                  autoFocus
                  className="w-full rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs text-[#18181b] placeholder:text-amber-400 focus:border-amber-400 focus:outline-none"
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleApplyResult}
                    disabled={!resultInput.trim()}
                    className="rounded-full bg-black px-2.5 py-1 text-xs font-medium text-white disabled:opacity-40"
                  >
                    적용
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowResultInput(false);
                      setResultInput("");
                    }}
                    className="rounded-full border border-zinc-200 px-2.5 py-1 text-xs text-zinc-500"
                  >
                    취소
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-start gap-1">
                <button
                  type="button"
                  title="기록에 숫자가 없어 비워두었습니다. 기억나신다면 여기 바로 적어보세요."
                  onClick={() => setShowResultInput(true)}
                  className="w-fit rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-700 transition-colors hover:bg-amber-100"
                >
                  숫자를 기억하시나요? (건너뛰기)
                </button>
                <button
                  type="button"
                  onClick={() => router.push("/")}
                  className="text-[11px] text-[#a1a1aa] underline underline-offset-2"
                >
                  또는 입력 화면에서 새 기록으로 남기기
                </button>
              </div>
            )}

            {item.source_dates.length > 0 && (
              <div>
                <button
                  type="button"
                  onClick={() => setShowSources((v) => !v)}
                  className="text-[11px] font-medium text-[#a1a1aa] underline underline-offset-2"
                >
                  이 문장의 근거 {showSources ? "숨기기" : "보기"}
                </button>
                {showSources && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {item.source_dates.map((date, i) => {
                      // source_dates와 source_card_ids는 백엔드가 같은 검증된
                      // 카드 목록에서 같이 계산해서 인덱스가 항상 맞물린다
                      // (docs/05-api-contract.md §3 참고) — 날짜 칩을 누르면
                      // 같은 인덱스의 카드 id로 /stack에서 그 카드를 찾아간다.
                      const cardId = item.source_card_ids[i];
                      return (
                        <button
                          key={cardId ?? `${date}-${i}`}
                          type="button"
                          disabled={cardId == null}
                          onClick={() => cardId != null && router.push(`/stack?cardId=${cardId}`)}
                          className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500 transition-colors hover:bg-zinc-200 disabled:cursor-default disabled:hover:bg-zinc-100"
                        >
                          {date}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* "문장 수정" (Figma 89:419) — 개별 필드를 구조 유지한 채 고친다. 저장하면
          부모가 lib/resumeFieldOverrides.ts에 담아 재생성해도 유지되게 한다. */}
      <BottomSheet
        open={editingField !== null}
        onClose={() => setEditingField(null)}
        hideHandle
        panelClassName="relative w-full max-w-md rounded-tl-[24px] rounded-tr-[24px] bg-white px-5 pt-4 pb-[30px] shadow-xl"
      >
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setEditingField(null)}
              className="text-[13px] text-[#a1a1aa]"
            >
              취소
            </button>
            <p className="text-[14px] font-semibold text-[#18181b]">문장 수정</p>
            <button
              type="button"
              onClick={handleSaveEdit}
              disabled={!editValue.trim()}
              className="text-[13px] font-semibold text-[#18181b] disabled:opacity-40"
            >
              저장
            </button>
          </div>
          <textarea
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            autoFocus
            rows={4}
            className="w-full resize-none rounded-[12px] border border-[#e5e7eb] bg-white p-3 text-[13px] leading-relaxed text-[#18181b] focus:border-zinc-400 focus:outline-none"
          />
          <div className="flex items-center justify-between">
            <p className="text-[11px] text-[#a1a1aa]">직접 고친 문장은 다시 변환해도 유지돼요</p>
            <p className="shrink-0 text-[11px] text-[#a1a1aa]">{editValue.length}자</p>
          </div>
          <button
            type="button"
            onClick={handleRevertEdit}
            className="w-fit rounded-full bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-600 transition-colors hover:bg-zinc-200"
          >
            AI 문장으로 되돌리기
          </button>
        </div>
      </BottomSheet>
    </div>
  );
}
