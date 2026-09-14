"use client";

import { useState } from "react";
import { useProjects } from "@/lib/useProjects";
import { BottomSheet } from "./BottomSheet";

/**
 * 입력 화면 상단의 프로젝트 스위처 (`tasks/track-c-frontend.md` §3.1).
 *
 * 연 1~3회만 쓰는 화면이므로 이름 + 시작일만 받는다 (CLAUDE.md 2.4).
 * 매일 쓰는 입력 경로(`/`)와는 분리된 바텀시트라 평소 입력 비용에 영향이 없다 (2.1).
 */
export function ProjectSwitcher() {
  const { projects, currentProject, loading, error, switchCurrent, addProject } = useProjects();
  const [open, setOpen] = useState(false);
  const [showNewForm, setShowNewForm] = useState(false);
  const [name, setName] = useState("");
  const [startedAt, setStartedAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const closeAll = () => {
    setOpen(false);
    setShowNewForm(false);
    setName("");
    setStartedAt("");
    setFormError(null);
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
        className="inline-flex max-w-[220px] items-center gap-1 rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-800 shadow-sm active:scale-[0.98]"
      >
        <span className="truncate">
          {loading ? "불러오는 중…" : currentProject ? currentProject.name : "프로젝트 없음"}
        </span>
        <span aria-hidden className="text-zinc-400">
          ›
        </span>
      </button>

      <BottomSheet open={open} onClose={closeAll} title="프로젝트">
        {error && <p className="mb-2 text-sm text-red-600">{error}</p>}

        <ul className="mb-3 max-h-64 overflow-y-auto">
          {projects.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => handleSwitch(p.id)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm ${
                  p.is_current ? "bg-zinc-100 font-semibold text-zinc-900" : "text-zinc-700"
                }`}
              >
                <span className="truncate">{p.name}</span>
                {p.is_current && <span className="text-xs text-zinc-500">현재</span>}
              </button>
            </li>
          ))}
          {projects.length === 0 && !loading && (
            <li className="px-3 py-2 text-sm text-zinc-500">아직 프로젝트가 없습니다.</li>
          )}
        </ul>

        {!showNewForm ? (
          <button
            type="button"
            onClick={() => setShowNewForm(true)}
            className="w-full rounded-lg border border-dashed border-zinc-300 py-2.5 text-sm font-medium text-zinc-600"
          >
            + 새 프로젝트
          </button>
        ) : (
          <div className="space-y-2 rounded-lg border border-zinc-200 p-3">
            <input
              type="text"
              placeholder="프로젝트 이름 (예: A은행 차세대)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
            />
            <input
              type="date"
              value={startedAt}
              onChange={(e) => setStartedAt(e.target.value)}
              className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
            />
            {formError && <p className="text-xs text-red-600">{formError}</p>}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleCreate}
                disabled={submitting}
                className="flex-1 rounded-md bg-zinc-900 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {submitting ? "생성 중…" : "만들기"}
              </button>
              <button
                type="button"
                onClick={() => setShowNewForm(false)}
                className="rounded-md border border-zinc-300 px-3 py-2 text-sm text-zinc-600"
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
