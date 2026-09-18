"use client";

import { Company } from "@/lib/api";
import { formatSpan, totalMonths } from "@/lib/careerSpan";

/**
 * "2.3 경력 입력 (회사 · 기간)" (Figma `268:5732`, 9/18 신규).
 *
 * 연차를 직접 묻지 않고 회사와 기간으로 계산한다 — 화면에도 "연차는 여기서 자동으로
 * 계산해요. 따로 묻지 않을게요"라고 적혀 있다.
 *
 * **CLAUDE.md 2.4와의 관계**: 배제 목록에 "연차 직접 입력 — 세그먼트 4개로 충분"이
 * 있었고 그동안 4개 칩으로 받아왔다. 이 화면은 그걸 대체한다 — 사용자가 이 Figma
 * 재설계를 보고 명시적으로 "전부 구현"을 지시해서 진행했다(2026-09-18). 저장되는
 * 값은 여전히 그 4개 구간이고(서버가 기간에서 계산), 화면만 회사·기간을 받는다.
 *
 * 화면에 보이는 "6년 3개월"과 서버가 저장하는 구간이 갈라지면 안 되므로, 계산
 * 로직은 서버(`src/career_span.py`)와 **같은 규칙**을 쓴다 — 겹치는 기간은 한 번만
 * 센다. 여기(프론트)는 타이핑 중에 즉시 보여주기 위한 것이고, 저장되는 값의 근거는
 * 언제나 서버 쪽 계산이다.
 */
interface Props {
  companies: Company[];
  onChange: (next: Company[]) => void;
}

/** "2024-03" <-> <input type="month">가 쓰는 값이 같은 포맷이라 그대로 오간다. */
export function CareerHistoryForm({ companies, onChange }: Props) {
  const months = totalMonths(companies);

  const update = (index: number, patch: Partial<Company>) => {
    onChange(companies.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  };

  const remove = (index: number) => {
    onChange(companies.filter((_, i) => i !== index));
  };

  const add = () => {
    onChange([...companies, { name: "", started_at: "", ended_at: null }]);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-3">
        {companies.map((company, i) => {
          const current = company.ended_at === null;
          return (
            <div
              key={i}
              className="flex flex-col gap-3 rounded-[14px] border border-[#2e2e2e] bg-[#1c1c1c] p-3.5"
            >
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={company.name}
                  onChange={(e) => update(i, { name: e.target.value })}
                  placeholder={i === 0 ? "지금 회사" : "회사 이름"}
                  maxLength={100}
                  className="min-w-0 flex-1 rounded-[10px] bg-[#242424] px-3 py-2 text-[14px] text-[#f2f2f2] placeholder:text-[#5e5e5e] focus:outline-none focus:ring-1 focus:ring-[#5e5e5e]"
                />
                <button
                  type="button"
                  onClick={() => remove(i)}
                  aria-label={`${company.name || "회사"} 삭제`}
                  className="shrink-0 px-1 text-[15px] text-[#5e5e5e] transition-colors hover:text-[#f2f2f2]"
                >
                  ✕
                </button>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="month"
                  value={company.started_at}
                  onChange={(e) => update(i, { started_at: e.target.value })}
                  aria-label="입사 시기"
                  className="min-w-0 flex-1 rounded-[10px] bg-[#242424] px-3 py-2 text-[13px] text-[#f2f2f2] focus:outline-none focus:ring-1 focus:ring-[#5e5e5e]"
                />
                <span aria-hidden className="text-[13px] text-[#5e5e5e]">
                  ~
                </span>
                <input
                  type="month"
                  value={company.ended_at ?? ""}
                  onChange={(e) => update(i, { ended_at: e.target.value || null })}
                  disabled={current}
                  aria-label="퇴사 시기"
                  className="min-w-0 flex-1 rounded-[10px] bg-[#242424] px-3 py-2 text-[13px] text-[#f2f2f2] focus:outline-none focus:ring-1 focus:ring-[#5e5e5e] disabled:opacity-40"
                />
                <button
                  type="button"
                  onClick={() => update(i, { ended_at: current ? "" : null })}
                  aria-pressed={current}
                  className={`shrink-0 rounded-[10px] px-3 py-2 text-[12px] transition-colors ${
                    current
                      ? "bg-accent font-semibold text-accent-foreground"
                      : "bg-[#242424] text-[#a0a0a0] hover:bg-[#2a2a2a]"
                  }`}
                >
                  재직 중
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <button
        type="button"
        onClick={add}
        className="w-full rounded-[12px] border border-dashed border-[#3a3a3a] py-3.5 text-[13px] text-[#a0a0a0] transition-colors hover:border-[#5e5e5e] hover:text-[#f2f2f2]"
      >
        + 회사 추가
      </button>

      {/* 총 경력 미리보기 (Figma 268:5766) */}
      <div className="flex items-center rounded-[14px] bg-[#1c1c1c] px-4 py-4">
        <p className="text-[13px] text-[#a0a0a0]">지금까지</p>
        <div className="flex-1" />
        <p className="text-[22px] font-bold text-[#f2f2f2]">
          {months > 0 ? formatSpan(months) : "—"}
        </p>
      </div>

      <p className="text-[12px] leading-relaxed text-[#828282]">
        연차는 여기서 자동으로 계산해요. 따로 묻지 않을게요.
      </p>
    </div>
  );
}
