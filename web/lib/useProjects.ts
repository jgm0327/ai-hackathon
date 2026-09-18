"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  Project,
  createProject as apiCreateProject,
  listProjects,
  updateProject as apiUpdateProject,
} from "./api";
import { getCached, navKey, setCached } from "./navCache";

/**
 * 프로젝트 목록 + 현재 프로젝트를 다루는 공용 훅.
 *
 * 프로젝트 스위처(`components/ProjectSwitcher.tsx`)와 `/resume`, `/projects` 화면이
 * 공유한다. 연 1~3회만 쓰는 화면이므로(CLAUDE.md 2.4) 전역 상태 라이브러리 없이
 * 화면마다 독립적으로 fetch해도 비용 문제가 없다.
 */
export function useProjects() {
  // 탭을 옮겨 다시 들어왔을 때 빈 목록에서 시작하지 않는다 — 마지막 값으로 첫 렌더를
  // 그리고 백그라운드로 갱신한다(9/18, `lib/navCache.ts` 참고). 최초 방문엔 캐시가
  // 비어 있으므로 예전과 동일하게 동작한다(서버 렌더와도 어긋나지 않는다).
  const cached = getCached<Project[]>(navKey.projects());
  const [projects, setProjects] = useState<Project[]>(cached ?? []);
  const [loading, setLoading] = useState(cached === undefined);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    // 이미 보여줄 값이 있으면 로딩 상태로 되돌리지 않는다 — 그래야 갱신 중에도
    // 화면이 비지 않는다.
    if (getCached<Project[]>(navKey.projects()) === undefined) setLoading(true);
    setError(null);
    try {
      const list = await listProjects();
      setProjects(list);
      setCached(navKey.projects(), list);
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
