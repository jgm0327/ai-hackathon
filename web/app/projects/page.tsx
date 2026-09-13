"use client";

import { FormEvent, useState } from "react";
import { useProjects } from "@/lib/useProjects";

/**
 * 프로젝트 목록 + 생성 (`/projects`).
 *
 * 이름과 시작일만 받는다 — 폴더 CRUD 고도화는 스코프 밖이다 (CLAUDE.md 2.4).
 */
export default function ProjectsPage() {
  const { projects, loading, error, switchCurrent, addProject } = useProjects();
  const [name, setName] = useState("");
  const [startedAt, setStartedAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !startedAt) {
      setFormError("이름과 시작일을 입력해 주세요.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await addProject(name.trim(), startedAt);
      setName("");
      setStartedAt("");
    } catch {
      setFormError("프로젝트 생성에 실패했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 px-4 pt-4">
      <h1 className="text-lg font-semibold">프로젝트</h1>

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

      {loading && <p className="text-sm text-zinc-400">불러오는 중…</p>}

      <ul className="flex flex-col gap-2">
        {projects.map((p) => (
          <li key={p.id} className="rounded-xl border border-zinc-200 bg-white p-3 shadow-sm">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate font-medium text-zinc-900">{p.name}</p>
                <p className="text-xs text-zinc-400">
                  {p.started_at} ~ {p.ended_at ?? "진행중"}
                </p>
              </div>
              {p.is_current ? (
                <span className="shrink-0 rounded-full bg-zinc-900 px-2.5 py-1 text-xs text-white">
                  현재
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => switchCurrent(p.id)}
                  className="shrink-0 rounded-full border border-zinc-300 px-2.5 py-1 text-xs text-zinc-600"
                >
                  현재로 설정
                </button>
              )}
            </div>
          </li>
        ))}
        {!loading && projects.length === 0 && (
          <li className="px-1 py-6 text-center text-sm text-zinc-400">
            아직 프로젝트가 없습니다. 아래에서 만들어 보세요.
          </li>
        )}
      </ul>

      <form onSubmit={handleCreate} className="space-y-2 rounded-xl border border-zinc-200 bg-white p-4">
        <p className="text-sm font-medium text-zinc-700">새 프로젝트</p>
        <input
          type="text"
          placeholder="이름 (예: A은행 차세대)"
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
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-zinc-900 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {submitting ? "만드는 중…" : "만들기"}
        </button>
      </form>
    </div>
  );
}
