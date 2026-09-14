"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  Project,
  createProject as apiCreateProject,
  listProjects,
  updateProject as apiUpdateProject,
} from "./api";

/**
 * 프로젝트 목록 + 현재 프로젝트를 다루는 공용 훅.
 *
 * 프로젝트 스위처(`components/ProjectSwitcher.tsx`)와 `/resume`, `/projects` 화면이
 * 공유한다. 연 1~3회만 쓰는 화면이므로(CLAUDE.md 2.4) 전역 상태 라이브러리 없이
 * 화면마다 독립적으로 fetch해도 비용 문제가 없다.
 */
export function useProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await listProjects();
      setProjects(list);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "프로젝트를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // 마운트 시 최초 로드 — 표준 데이터 페칭 패턴. refresh() 내부에서 setLoading(true)를
    // 동기적으로 호출하지만 cleanup이 필요 없는 단순 GET이라 안전하다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
  }, [refresh]);

  const switchCurrent = useCallback(
    async (id: number) => {
      await apiUpdateProject(id, { is_current: true });
      await refresh();
    },
    [refresh],
  );

  const addProject = useCallback(
    async (name: string, startedAt: string) => {
      const created = await apiCreateProject(name, startedAt);
      await refresh();
      return created;
    },
    [refresh],
  );

  const currentProject = projects.find((p) => p.is_current) ?? null;

  return { projects, currentProject, loading, error, refresh, switchCurrent, addProject };
}
