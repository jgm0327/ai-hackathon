"use client";

import Image from "next/image";
import { useMemo, useState } from "react";
import {
  JOB_CATEGORIES,
  JobCategory,
  buildJobSections,
  categoryOfJob,
  jobWithCategoryLabel,
} from "@/lib/jobTaxonomy";

/**
 * 직군 · 직무 칩 클라우드 (Figma "00 · 온보딩" `268:5827` 1/4 단일 / `268:5888` 2/4 다중).
 *
 * 두 화면이 헤더 라벨("단일 선택"/"다중 선택")과 선택 개수만 다르고 나머지는 완전히
 * 같아서 한 컴포넌트로 만들고 `multiple`로 가른다.
 *
 * 화면 구성: 검색창 → 직군 가로 스크롤 세그먼트 → 직군별 칩 클라우드 → 하단 고정
 * 선택 요약 바(선택 칩 + "선택 완료"). 목록이 길어서 바닥이 잘리는 걸 알려주려고
 * Figma엔 아래쪽 페이드(`268:5880`)가 있고 여기서도 같은 그라데이션을 얹는다.
 */
interface Props {
  multiple: boolean;
  selected: string[];
  onChange: (next: string[]) => void;
  /** 하단 "선택 완료" 버튼. 아무것도 안 골랐으면 비활성. */
  onConfirm: () => void;
  confirmLabel?: string;
  /** "선택 완료" 아래에 붙는 보조 동작(예: 2/4의 "지금 하는 일을 계속할게요").
   * 하단 바 **안**에 둬야 한다 — 바깥에 두면 sticky 바에 가려 안 보인다. */
  footer?: React.ReactNode;
}

export function JobPicker({ multiple, selected, onChange, onConfirm, confirmLabel, footer }: Props) {
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<JobCategory | null>(null);

  const sections = useMemo(() => buildJobSections(query, activeCategory), [query, activeCategory]);

  const toggle = (job: string) => {
    if (!multiple) {
      // 단일 선택은 같은 걸 다시 눌러도 해제하지 않는다 — 그러면 "선택 완료"가
      // 비활성으로 돌아가서 뒤로 가는 것처럼 보인다.
      onChange([job]);
      return;
    }
    onChange(selected.includes(job) ? selected.filter((j) => j !== job) : [...selected, job]);
  };

  return (
    <div className="flex flex-1 flex-col">
      {/* 목록은 페이지와 함께 스크롤한다 — 내부에 별도 스크롤 영역을 만들면 모바일에서
          주소창이 접혔다 펴질 때 높이가 튄다. 하단 바는 sticky로 따라붙는다. */}
      <div className="pb-6">
        {/* 검색 (Figma 2.2-a `299:11545`) — 직군 필터와 무관하게 전체에서 찾는다.
            9/19: 목업의 `icon/search` 18px가 빠져 있었다(입력창만 있었다). */}
        <div className="relative">
          <Image
            src="/icons/search.svg"
            alt=""
            width={18}
            height={18}
            aria-hidden
            className="pointer-events-none absolute left-[16px] top-1/2 -translate-y-1/2"
          />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="직무 검색"
          className="w-full rounded-[12px] border border-[#34322e] bg-[#2a2724] py-3 pl-[42px] pr-4 text-[14px] text-[#ede9e2] placeholder:text-[#918c84] focus:border-[#918c84] focus:outline-none"
        />
        </div>

        {/* 직군 세그먼트 (Figma 268:5847) — 가로 스크롤. 검색 중엔 전체를 훑으므로 숨긴다. */}
        {!query.trim() && (
          <div className="no-scrollbar -mx-5 mt-3 flex gap-2 overflow-x-auto px-5 pb-1">
            {JOB_CATEGORIES.map((category) => {
              const active = activeCategory === category;
              return (
                <button
                  key={category}
                  type="button"
                  onClick={() => setActiveCategory(active ? null : category)}
                  className={`shrink-0 rounded-[10px] px-3.5 py-2 text-[13px] transition-colors ${
                    active
                      ? "bg-accent font-semibold text-accent-foreground"
                      : "bg-[#1c1c1c] text-[#a0a0a0] hover:bg-[#242424]"
                  }`}
                >
                  {category}
                </button>
              );
            })}
          </div>
        )}

        <div className="mt-4 flex flex-col gap-5">
          {sections.map((section) => (
            <div key={section.category} className="flex flex-col gap-3">
              <p className="text-[13px] text-[#828282]">
                {section.category} <span className="text-[#5e5e5e]">{section.jobs.length}</span>
              </p>
              <div className="flex flex-wrap gap-2">
                {section.jobs.map((job) => {
                  const active = selected.includes(job);
                  return (
                    <button
                      key={job}
                      type="button"
                      onClick={() => toggle(job)}
                      aria-pressed={active}
                      className={`rounded-[12px] px-4 py-3 text-[13px] transition-colors ${
                        active
                          ? "bg-accent font-semibold text-accent-foreground"
                          : "bg-[#1c1c1c] text-[#d4d4d4] hover:bg-[#242424]"
                      }`}
                    >
                      {job}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}

          {sections.length === 0 && (
            <p className="py-8 text-center text-[13px] text-[#828282]">
              찾는 직무가 없어요. 다른 말로 검색해 보세요.
            </p>
          )}
        </div>
      </div>

      {/* 하단 선택 바 (Figma 268:5881) */}
      <div className="sticky bottom-0 -mx-5 mt-auto border-t border-[#242424] bg-[#141210] px-5 pb-3 pt-3">
        {/* 페이드 (Figma 268:5880) — 위 목록이 이 바 밑으로 잘린다는 걸 알린다. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 -top-12 h-12 bg-gradient-to-b from-transparent to-[#141210]"
        />
        <div className="flex min-h-[34px] flex-wrap gap-2">
          {selected.length === 0 ? (
            <p className="py-1.5 text-[12px] text-[#5e5e5e]">
              {multiple ? "여러 개 골라도 됩니다" : "하나만 골라주세요"}
            </p>
          ) : (
            selected.map((job) => (
              <span
                key={job}
                className="flex items-center gap-1.5 rounded-[10px] bg-[#2a2a2a] px-2.5 py-1.5 text-[12px] text-[#f2f2f2]"
              >
                {multiple ? job : jobWithCategoryLabel(job)}
                <button
                  type="button"
                  onClick={() => onChange(selected.filter((j) => j !== job))}
                  aria-label={`${job} 선택 해제`}
                  className="text-[#828282] transition-colors hover:text-[#f2f2f2]"
                >
                  ✕
                </button>
              </span>
            ))
          )}
        </div>
        <button
          type="button"
          onClick={onConfirm}
          disabled={selected.length === 0}
          className="mt-3 w-full rounded-[12px] bg-accent py-4 text-[15px] font-semibold text-accent-foreground transition-colors hover:bg-[#ff7a2e] disabled:opacity-40 disabled:hover:bg-accent"
        >
          {confirmLabel ?? "선택 완료"}
        </button>
        {footer}
      </div>
    </div>
  );
}

/** 저장된 직무 이름이 지금 분류표에 없으면(표를 갈아끼운 경우) 화면에서 조용히 뺀다.
 * 없는 칩을 선택된 것처럼 보여주면 해제할 방법이 없어진다. */
export function keepKnownJobs(jobs: string[]): string[] {
  return jobs.filter((job) => categoryOfJob(job) !== null);
}
