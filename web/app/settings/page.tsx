"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BottomSheet } from "@/components/BottomSheet";
import { ApiError, Profile, getProfile, getResumeDraft, syncNotion } from "@/lib/api";
import { useProjects } from "@/lib/useProjects";

const LEAVE_TIME_STORAGE_KEY = "careerlog:leaveTime";
const NOTION_CONNECTED_STORAGE_KEY = "careerlog:notionConnected";

function jobLabel(profile: Profile | null): string | null {
  if (!profile?.job_field) return null;
  const detail = profile.job_detail ?? profile.job_field;
  if (!profile.years_segment) return detail;
  const years = profile.years_segment === "10+" ? "10년 이상" : `${profile.years_segment}년차`;
  return `${detail} · ${years}`;
}

/**
 * 설정 (`/settings`, Figma "5.0 설정"). 실제 설정 변경은 대부분 기존 화면이 담당하고
 * 이 화면은 현황을 보여주는 진입점에 가깝다 — 직무·알림은 `/onboarding`(재방문 시
 * "직군·알림 설정" 모드로 이미 두 값을 함께 다룬다), 이력서는 `/resume`을 그대로 재사용한다.
 * 새로 만든 건 노션 연동 상태 표시(이 기기 로컬 기록, 서버에 연동 상태를 저장하는
 * OAuth가 없어 실제 연결 여부가 아니라 "마지막으로 이 기기에서 동기화했는지"를
 * 보여준다 — CLAUDE.md 2.2, 없는 사실을 지어내지 않는다)와 알림 시각 표시뿐이다.
 */
export default function SettingsPage() {
  const { currentProject } = useProjects();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [leaveTime, setLeaveTime] = useState<string | null>(null);
  const [notionConnected, setNotionConnected] = useState(false);
  const [resumeRegistered, setResumeRegistered] = useState<boolean | null>(null);

  const [notionOpen, setNotionOpen] = useState(false);
  const [notionToken, setNotionToken] = useState("");
  const [notionSubmitting, setNotionSubmitting] = useState(false);
  const [notionError, setNotionError] = useState<string | null>(null);
  const [notionSuccess, setNotionSuccess] = useState<string | null>(null);
  const [appInfoOpen, setAppInfoOpen] = useState(false);

  useEffect(() => {
    getProfile()
      .then(setProfile)
      .catch(() => {});
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLeaveTime(localStorage.getItem(LEAVE_TIME_STORAGE_KEY));
      setNotionConnected(localStorage.getItem(NOTION_CONNECTED_STORAGE_KEY) === "1");
    } catch {
      // localStorage 접근 불가 — 값 없이 기본 표시로 진행
    }
  }, []);

  useEffect(() => {
    if (!currentProject) return;
    let cancelled = false;
    getResumeDraft(currentProject.id)
      .then((draft) => {
        if (!cancelled) setResumeRegistered(Boolean(draft.content));
      })
      .catch(() => {
        if (!cancelled) setResumeRegistered(false);
      });
    return () => {
      cancelled = true;
    };
  }, [currentProject]);

  const handleNotionSync = async () => {
    const trimmed = notionToken.trim();
    if (!trimmed || notionSubmitting) return;
    setNotionSubmitting(true);
    setNotionError(null);
    setNotionSuccess(null);
    try {
      const res = await syncNotion(trimmed);
      setNotionSuccess(`${res.imported}개 페이지를 가져왔어요.`);
      setNotionToken("");
      setNotionConnected(true);
      try {
        localStorage.setItem(NOTION_CONNECTED_STORAGE_KEY, "1");
      } catch {
        // 로컬 기억 실패해도 동기화 자체는 이미 성공
      }
    } catch (err) {
      setNotionError(err instanceof ApiError ? err.detail : "노션 동기화에 실패했습니다.");
    } finally {
      setNotionSubmitting(false);
    }
  };

  const closeNotionSheet = () => {
    setNotionOpen(false);
    setNotionToken("");
    setNotionError(null);
    setNotionSuccess(null);
  };

  return (
    <div className="flex min-h-full flex-col gap-4 bg-[#121212] px-5 pb-8">
      <div className="flex items-center gap-[10px] pb-[6px] pt-[8px]">
        <Link href="/" aria-label="뒤로" className="text-[17px] text-[#f2f2f2]">
          ←
        </Link>
        <p className="text-[15px] font-bold text-[#f2f2f2]">설정</p>
      </div>

      <div className="flex flex-col overflow-hidden rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e]">
        <Link
          href="/onboarding"
          className="flex items-center gap-2 px-4 py-[13px] transition-colors hover:bg-[#242424]"
        >
          <span className="text-[14px] text-[#f2f2f2]">직무 설정</span>
          <div className="flex-1" />
          <span className="text-[13px] text-[#a0a0a0]">{jobLabel(profile) ?? "설정하기"}</span>
          <span className="text-[#5e5e5e]">›</span>
        </Link>
        <div className="h-px w-full bg-[#2e2e2e]" />
        <Link
          href="/onboarding"
          className="flex items-center gap-2 px-4 py-[13px] transition-colors hover:bg-[#242424]"
        >
          <span className="text-[14px] text-[#f2f2f2]">알림</span>
          <div className="flex-1" />
          <span className="text-[13px] text-[#a0a0a0]">
            {leaveTime ? `매일 ${leaveTime}` : "꺼짐"}
          </span>
          <span className="text-[#5e5e5e]">›</span>
        </Link>
        <div className="h-px w-full bg-[#2e2e2e]" />
        <button
          type="button"
          onClick={() => setNotionOpen(true)}
          className="flex items-center gap-2 px-4 py-[13px] text-left transition-colors hover:bg-[#242424]"
        >
          <span className="text-[14px] text-[#f2f2f2]">노션 연동</span>
          <div className="flex-1" />
          <span className="text-[13px] text-[#a0a0a0]">{notionConnected ? "연결됨" : "연결 안 됨"}</span>
          <span className="text-[#5e5e5e]">›</span>
        </button>
        <div className="h-px w-full bg-[#2e2e2e]" />
        <Link
          href="/resume"
          className="flex items-center gap-2 px-4 py-[13px] transition-colors hover:bg-[#242424]"
        >
          <span className="text-[14px] text-[#f2f2f2]">내 이력서</span>
          <div className="flex-1" />
          <span className="text-[13px] text-[#a0a0a0]">
            {resumeRegistered == null ? "확인 중…" : resumeRegistered ? "등록됨" : "등록 안 됨"}
          </span>
          <span className="text-[#5e5e5e]">›</span>
        </Link>
      </div>

      <div className="flex flex-col overflow-hidden rounded-[14px] border border-[#2e2e2e] bg-[#1e1e1e]">
        <button
          type="button"
          onClick={() => setAppInfoOpen(true)}
          className="flex items-center gap-2 px-4 py-[13px] text-left transition-colors hover:bg-[#242424]"
        >
          <span className="text-[14px] text-[#f2f2f2]">앱 정보</span>
          <div className="flex-1" />
          <span className="text-[#5e5e5e]">›</span>
        </button>
      </div>

      <p className="px-1 text-[11px] text-[#828282]">
        🔒 카카오 로그인으로 안전하게 보관돼요.
      </p>

      <BottomSheet
        open={notionOpen}
        onClose={closeNotionSheet}
        hideHandle
        panelClassName="relative w-full max-w-md rounded-tl-[24px] rounded-tr-[24px] bg-[#1e1e1e] px-5 pt-4 pb-[30px] shadow-xl"
      >
        <div className="flex flex-col gap-3">
          <p className="text-[14px] font-semibold text-[#f2f2f2]">노션에서 가져오기</p>
          <p className="text-xs text-[#a0a0a0]">
            노션 통합(integration) 토큰을 입력하면 접근 가능한 페이지를 가져와 카드로
            저장해요. 페이지가 많으면 다소 걸릴 수 있어요.
          </p>
          <input
            type="password"
            value={notionToken}
            onChange={(e) => setNotionToken(e.target.value)}
            placeholder="secret_..."
            autoComplete="off"
            className="w-full rounded-md border border-[#2e2e2e] bg-[#141414] px-3 py-2 text-sm text-[#f2f2f2] placeholder:text-[#5e5e5e] focus:border-[#5e5e5e] focus:outline-none"
          />
          {notionError && (
            <p className="text-xs text-[#f0645c]">{notionError}</p>
          )}
          {notionSuccess && <p className="text-xs text-emerald-400">{notionSuccess}</p>}
          <button
            type="button"
            onClick={handleNotionSync}
            disabled={notionSubmitting || !notionToken.trim()}
            className="w-full rounded-[999px] bg-[#f2f2f2] py-2.5 text-sm font-semibold text-[#171717] transition-colors hover:bg-white disabled:opacity-40"
          >
            {notionSubmitting ? "가져오는 중…" : "동기화"}
          </button>
        </div>
      </BottomSheet>

      <BottomSheet
        open={appInfoOpen}
        onClose={() => setAppInfoOpen(false)}
        hideHandle
        panelClassName="relative w-full max-w-md rounded-tl-[24px] rounded-tr-[24px] bg-[#1e1e1e] px-5 pt-4 pb-[30px] shadow-xl"
      >
        <div className="flex flex-col gap-2">
          <p className="text-[14px] font-semibold text-[#f2f2f2]">커리어 로그</p>
          <p className="text-xs leading-relaxed text-[#a0a0a0]">
            퇴근 전 한 줄 메모를 이직 시 경력기술서로 바꿔주는 서비스.
          </p>
        </div>
      </BottomSheet>
    </div>
  );
}
