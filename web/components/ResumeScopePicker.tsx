"use client";

import { Card, Project, ResumeScope } from "@/lib/api";

/**
 * "4.2.1 범위 선택 — 그동안 이런 걸 하셨어요" (Figma `89:152` / `89:161`, 9/18 신규).
 *
 * `/stack`의 "마스터 경력기술서 초안 짜기"를 누르면 바로 초안을 만드는 게 아니라,
 * 먼저 **무엇을 넣을지** 고르게 한다. 그 전까지 `/resume`은 "현재 프로젝트 하나"로
 * 고정돼 있어서, 버튼 이름과 달리 실제로는 마스터 문서가 아니었다.
 *
 * **왜 이 화면이 2.1(입력 비용 0)을 안 깨는가**: CLAUDE.md 2.1이 막는 건 *매일*
 * 반복되는 경로(메모 입력 → 변환)에 선택지를 끼워 넣는 것이다. 여기는 이직 준비
 * 시점에만 오는 화면이라 "월 1회 이하" 기준을 만족한다.
 *
 * **기본값은 현재 프로젝트 하나**다 — 아무것도 안 건드리고 바로 버튼을 누르면
 * 9/18 이전과 똑같이 동작한다.
 */

/** "2023-02-01" -> "2023.02". 파싱 못 하면 원본 그대로. */
function shortMonth(isoDate: string | null): string | null {
  if (!isoDate) return null;
  const parts = isoDate.split("-");
  return parts.length >= 2 ? `${parts[0]}.${parts[1]}` : isoDate;
}

/** Figma 89:182 "2023.04 - 2024.01". 종료일이 없으면 "진행 중"으로 — 없는 날짜를
 * 지어내지 않는다(CLAUDE.md 2.2). 완성된 문서의 프로젝트 헤드(Figma 41:257)도
 * 같은 값을 써야 해서 `/resume`이 가져다 쓴다. */
export function formatProjectPeriod(project: Project): string {
  const start = shortMonth(project.started_at) ?? "";
  const end = shortMonth(project.ended_at);
  return end ? `${start} - ${end}` : `${start} - 진행 중`;
}

export interface ScopeStats {
  totalCards: number;
  projectCount: number;
  recordedDays: number;
}

/** 기록 요약(Figma 89:166) 계산. "기록한 날"은 서로 다른 `created_at` 날짜의 개수다. */
export function computeScopeStats(cards: Card[], projects: Project[]): ScopeStats {
  return {
    totalCards: cards.length,
    projectCount: projects.length,
    recordedDays: new Set(cards.map((c) => c.created_at)).size,
  };
}

interface Props {
  projects: Project[];
  cards: Card[];
  scope: ResumeScope;
  onChange: (scope: ResumeScope) => void;
  /** 고른 범위에 실제로 들어가는 카드 수 — 버튼 문구("N개를 경력기술서로 바꾸기")에 쓴다. */
  selectedCardCount: number;
  onSubmit: () => void;
  submitting: boolean;
  submitLabel?: string;
}

export function ResumeScopePicker({
  projects,
  cards,
  scope,
  onChange,
  selectedCardCount,
  onSubmit,
  submitting,
  submitLabel,
}: Props) {
  const stats = computeScopeStats(cards, projects);
  const unassignedCount = cards.filter((c) => c.project_id === null).length;

  const toggleProject = (id: number) => {
    const next = scope.projectIds.includes(id)
      ? scope.projectIds.filter((p) => p !== id)
      : // 프로젝트 목록(최신순)과 같은 순서를 유지한다 — 이 순서가 그대로 문서의
        // 프로젝트 헤드 순서가 된다.
        projects.filter((p) => p.id === id || scope.projectIds.includes(p.id)).map((p) => p.id);
    onChange({ ...scope, projectIds: next });
  };

  const nothingSelected = selectedCardCount === 0;

  return (
    <div className="flex flex-col gap-3 rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e] p-4">
      <div>
        {/* 목업은 20px/32다(307:18420 — 346×32). 17px로 잡혀 있었다. */}
        <p className="text-[20px] font-bold leading-[32px] text-[#ede9e2]">
          그동안 이런 걸 하셨어요
        </p>
        <p className="mt-1 text-[12px] text-[#a0a0a0]">
          {stats.totalCards > 0
            ? `기록 ${stats.totalCards}개를 모았어요. 포함할 범위를 골라주세요.`
            : "아직 기록이 없어요. 먼저 한 줄 남겨보세요."}
        </p>
      </div>

      {/* 기록 요약 (Figma 89:166) — 전부 실제로 센 값이다. */}
      <div className="flex rounded-[12px] bg-[#181818] px-4 py-3">
        {[
          { value: `${stats.totalCards}`, label: "기록" },
          { value: `${stats.projectCount}`, label: "프로젝트" },
          { value: `${stats.recordedDays}일`, label: "기록한 날" },
        ].map((stat) => (
          <div key={stat.label} className="flex flex-1 flex-col gap-1">
            <p className="text-[18px] font-bold leading-[24px] text-[#f2f2f2]">{stat.value}</p>
            <p className="text-[11px] text-[#828282]">{stat.label}</p>
          </div>
        ))}
      </div>

      {/* 포함 범위 선택 (Figma 89:177) */}
      <div className="flex flex-col overflow-hidden rounded-[12px] border border-[#2e2e2e]">
        {projects.map((project, i) => {
          const count = cards.filter((c) => c.project_id === project.id).length;
          const checked = scope.projectIds.includes(project.id);
          return (
            <button
              key={project.id}
              type="button"
              onClick={() => toggleProject(project.id)}
              aria-pressed={checked}
              className={`flex items-center gap-3 px-3 py-3 text-left transition-colors hover:bg-[#232323] ${
                i > 0 ? "border-t border-[#2e2e2e]" : ""
              }`}
            >
              <Checkbox checked={checked} />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[14px] text-[#f2f2f2]">{project.name}</span>
                <span className="text-[11px] text-[#828282]">{formatProjectPeriod(project)}</span>
              </span>
              <span className="shrink-0 text-[12px] text-[#a0a0a0]">{count}개</span>
            </button>
          );
        })}

        {/* 미분류 기록 — 프로젝트가 아니라 "남은 것들"이라 항상 맨 아래, 기본 꺼짐 */}
        {unassignedCount > 0 && (
          <button
            type="button"
            onClick={() => onChange({ ...scope, includeUnassigned: !scope.includeUnassigned })}
            aria-pressed={scope.includeUnassigned}
            className={`flex items-center gap-3 px-3 py-3 text-left transition-colors hover:bg-[#232323] ${
              projects.length > 0 ? "border-t border-[#2e2e2e]" : ""
            }`}
          >
            <Checkbox checked={scope.includeUnassigned} />
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-[14px] text-[#f2f2f2]">미분류 기록</span>
              <span className="text-[11px] text-[#828282]">기간 없음</span>
            </span>
            <span className="shrink-0 text-[12px] text-[#a0a0a0]">{unassignedCount}개</span>
          </button>
        )}

        {projects.length === 0 && unassignedCount === 0 && (
          <p className="px-3 py-4 text-[12px] text-[#828282]">
            아직 기록이 없어요. 먼저 일지를 남기면 여기에 범위가 생깁니다.
          </p>
        )}
      </div>

      {/* 선택 안내 (Figma 89:197) */}
      <div className="flex items-start gap-2 rounded-[10px] bg-[#181818] px-3 py-2.5">
        <span aria-hidden className="mt-[6px] h-1.5 w-1.5 shrink-0 rounded-full bg-[#5e5e5e]" />
        <p className="text-[11px] leading-relaxed text-[#a0a0a0]">
          고른 범위만 초안에 들어갑니다. 나중에 다시 만들 수 있어요.
          {scope.projectIds.length > 1 && (
            <>
              <br />
              프로젝트끼리 섞지 않고 각각 따로 묶어요 — 고른 수만큼 시간이 더 걸립니다.
            </>
          )}
        </p>
      </div>

      <button
        type="button"
        onClick={onSubmit}
        disabled={submitting || nothingSelected}
        // 목업은 높이 50 · 라운드 8 · 14px bold다(307:18459, Button 컴포넌트 설명과 동일).
        className="flex h-[50px] w-full items-center justify-center rounded-[8px] bg-accent text-[14px] font-bold text-accent-foreground transition-colors hover:bg-[#ff7a2e] disabled:opacity-40 disabled:hover:bg-accent"
      >
        {submitting
          ? "경력기술서 만드는 중…"
          : nothingSelected
            ? "포함할 범위를 골라주세요"
            : (submitLabel ?? `${selectedCardCount}개를 경력기술서로 바꾸기`)}
      </button>
    </div>
  );
}

function Checkbox({ checked }: { checked: boolean }) {
  return (
    <span
      aria-hidden
      className={`flex size-[19px] shrink-0 items-center justify-center rounded-[5px] border text-[11px] ${
        checked
          ? "border-accent bg-accent text-accent-foreground"
          : "border-[#3a3a3a] bg-transparent text-transparent"
      }`}
    >
      ✓
    </span>
  );
}
