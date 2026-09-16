"use client";

import { useState } from "react";
import { useProjects } from "@/lib/useProjects";
import { BottomSheet } from "./BottomSheet";

/**
 * 입력 화면 상단의 프로젝트 스위처 (`tasks/track-c-frontend.md` §3.1).
 *
 * 연 1~3회만 쓰는 화면이므로 이름 + 시작일만 받는다 (CLAUDE.md 2.4).
 * 매일 쓰는 입력 경로(`/`)와는 분리된 바텀시트라 평소 입력 비용에 영향이 없다 (2.1).
 *
 * **구현 노트 (9/14, "/stack에서 전환해도 새로고침해야 반영됨" 버그 수정)**: 예전엔
 * 이 컴포넌트가 `useProjects()`를 직접 호출했다. `/stack`처럼 이 컴포넌트를 렌더링하는
 * 화면 자체도 `useProjects()`를 따로 불러 카드 목록을 그 `currentProject.id`로
 * 필터링하고 있었는데, 훅을 두 번 부르면 서로 다른(동기화 안 되는) 상태 인스턴스가
 * 생긴다 — 여기서 프로젝트를 바꿔도 페이지 쪽 인스턴스는 그대로라 카드 목록이
 * 안 바뀌고, 새로고침으로 훅 인스턴스를 통째로 새로 만들어야만 반영됐다. 부모가
 * `useProjects()`를 한 번만 호출해서 그 결과를 그대로 넘겨받는 controlled 컴포넌트로
 * 바꿔서 상태를 하나로 합쳤다.
 */

// 프로젝트 개수가 이 이하면 검색창 없이도 한눈에 훑을 수 있어 굳이 안 보여준다
// (CLAUDE.md 2.1 — 필요 없는 화면 요소를 늘리지 않는다).
const PROJECT_SEARCH_THRESHOLD = 5;

export function ProjectSwitcher({
  projectsState,
}: {
  projectsState: ReturnType<typeof useProjects>;
}) {
  const { projects, currentProject, loading, error, switchCurrent, addProject } = projectsState;
  const [open, setOpen] = useState(false);
  const [showNewForm, setShowNewForm] = useState(false);
  const [name, setName] = useState("");
  const [startedAt, setStartedAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const filteredProjects = query.trim()
    ? projects.filter((p) => p.name.toLowerCase().includes(query.trim().toLowerCase()))
    : projects;

  const closeAll = () => {
    setOpen(false);
    setShowNewForm(false);
    setName("");
    setStartedAt("");
    setFormError(null);
    setQuery("");
  };

  const handleSwitch = async (id: number) => {
    try {
      await switchCurrent(id);
      closeAll();
    } catch {
      setFormError("프로젝트 전환에 실패했습니다.");
    }
  };

  const handleCreate = async () => {
    if (!name.trim() || !startedAt) {
      setFormError("이름과 시작일을 입력해 주세요.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await addProject(name.trim(), startedAt);
      closeAll();
    } catch {
      setFormError("프로젝트 생성에 실패했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex max-w-[220px] items-center gap-1 rounded-full border border-[#2e2e2e] bg-[#1e1e1e] px-3 py-1.5 text-sm font-medium text-[#f2f2f2] transition-colors hover:bg-[#262626] active:scale-[0.98]"
      >
        <span className="truncate">
          {loading ? "불러오는 중…" : currentProject ? currentProject.name : "프로젝트 없음"}
        </span>
        <span aria-hidden className="text-[#5e5e5e]">
          ›
        </span>
      </button>

      <BottomSheet open={open} onClose={closeAll} title="프로젝트">
        {error && <p className="mb-2 text-sm text-[#f0645c]">{error}</p>}

        {projects.length > PROJECT_SEARCH_THRESHOLD && (
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="프로젝트 이름 검색"
            className="mb-2 w-full rounded-md border border-[#333] bg-[#141414] px-3 py-2 text-sm text-[#f2f2f2] placeholder:text-[#5e5e5e] focus:border-[#5e5e5e] focus:outline-none"
          />
        )}

        <ul className="mb-3 max-h-64 overflow-y-auto">
          {filteredProjects.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => handleSwitch(p.id)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${
                  p.is_current
                    ? "bg-[#262626] font-semibold text-[#f2f2f2]"
                    : "text-[#d4d4d4] hover:bg-[#242424]"
                }`}
              >
                <span className="truncate">{p.name}</span>
                {p.is_current && <span className="text-xs text-[#a0a0a0]">현재</span>}
              </button>
            </li>
          ))}
          {projects.length === 0 && !loading && (
            <li className="px-3 py-2 text-sm text-[#828282]">아직 프로젝트가 없습니다.</li>
          )}
          {projects.length > 0 && filteredProjects.length === 0 && (
            <li className="px-3 py-2 text-sm text-[#828282]">일치하는 프로젝트가 없습니다.</li>
          )}
        </ul>

        {!showNewForm ? (
          <button
            type="button"
            onClick={() => setShowNewForm(true)}
            className="w-full rounded-lg border border-dashed border-[#3a3a3a] py-2.5 text-sm font-medium text-[#a0a0a0] transition-colors hover:bg-[#242424]"
          >
            + 새 프로젝트
          </button>
        ) : (
          <div className="space-y-2 rounded-lg border border-[#2e2e2e] p-3">
            <input
              type="text"
              placeholder="프로젝트 이름 (예: A은행 차세대)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border border-[#333] bg-[#141414] px-3 py-2 text-sm text-[#f2f2f2] placeholder:text-[#5e5e5e] focus:border-[#5e5e5e] focus:outline-none"
            />
            <input
              type="date"
              value={startedAt}
              onChange={(e) => setStartedAt(e.target.value)}
              className="w-full rounded-md border border-[#333] bg-[#141414] px-3 py-2 text-sm text-[#f2f2f2] [color-scheme:dark] focus:border-[#5e5e5e] focus:outline-none"
            />
            {formError && <p className="text-xs text-[#f0645c]">{formError}</p>}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleCreate}
                disabled={submitting}
                className="flex-1 rounded-md bg-[#f2f2f2] py-2 text-sm font-medium text-[#171717] transition-colors hover:bg-white disabled:opacity-50 disabled:hover:bg-[#f2f2f2]"
              >
                {submitting ? "생성 중…" : "만들기"}
              </button>
              <button
                type="button"
                onClick={() => setShowNewForm(false)}
                className="rounded-md border border-[#333] px-3 py-2 text-sm text-[#a0a0a0] transition-colors hover:bg-[#242424]"
              >
                취소
              </button>
            </div>
          </div>
        )}
      </BottomSheet>
    </>
  );
}
