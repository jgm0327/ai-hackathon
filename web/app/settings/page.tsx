"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { BottomSheet } from "@/components/BottomSheet";
import { stackTheme as t } from "@/components/stackTheme";
import { setNotionToken as rememberNotionToken } from "@/lib/notionToken";
import { Toast, useToast } from "@/components/Toast";
import {
  ApiError,
  BackupFile,
  Profile,
  exportBackup,
  getProfile,
  getResumeDraft,
  importBackup,
  logout,
  NotionConnection,
  disconnectNotion,
  getNotionConnection,
  listNotionPages,
  notionOAuthStartUrl,
} from "@/lib/api";
import { useProjects } from "@/lib/useProjects";

/** 내려받을 파일 이름 — "career-log-backup-2026-09-18.json". */
function backupFileName(): string {
  const d = new Date();
  const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return `career-log-backup-${date}.json`;
}

/** 불러온 파일이 우리 백업 파일이 맞는지 최소한만 확인한다. 엄격하게 스키마 전체를
 * 검사하지는 않는다 — 서버가 어차피 Pydantic으로 다시 거르고, 여기서 막고 싶은 건
 * "완전히 엉뚱한 JSON을 통째로 업로드하는 것"뿐이다. */
function parseBackupFile(text: string): Pick<BackupFile, "projects" | "cards"> {
  const parsed = JSON.parse(text) as Partial<BackupFile>;
  if (!Array.isArray(parsed.projects) || !Array.isArray(parsed.cards)) {
    throw new Error("형식이 다릅니다");
  }
  return { projects: parsed.projects, cards: parsed.cards };
}

const LEAVE_TIME_STORAGE_KEY = "careerlog:leaveTime";

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
  const router = useRouter();
  const { currentProject } = useProjects();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [leaveTime, setLeaveTime] = useState<string | null>(null);
  // 노션 연결 상태는 **서버에서** 읽는다. 예전엔 localStorage 플래그를 봤는데,
  // 한 번 성공한 흔적이 남아서 실제로는 연결이 없어도 "연결됨"으로 보였다(9/18 버그).
  const [notionConn, setNotionConn] = useState<NotionConnection | null>(null);
  const [resumeRegistered, setResumeRegistered] = useState<boolean | null>(null);

  const [notionOpen, setNotionOpen] = useState(false);
  const [notionToken, setNotionToken] = useState("");
  const [notionSubmitting, setNotionSubmitting] = useState(false);
  const [notionError, setNotionError] = useState<string | null>(null);
  const [notionSuccess, setNotionSuccess] = useState<string | null>(null);
  const [appInfoOpen, setAppInfoOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  // 백업 내보내기 / 불러오기 (Figma 41:333 / 41:338, 9/18 신규)
  const [backupBusy, setBackupBusy] = useState<"export" | "import" | null>(null);
  const [backupError, setBackupError] = useState<string | null>(null);
  const [importConfirm, setImportConfirm] = useState<Pick<BackupFile, "projects" | "cards"> | null>(
    null,
  );
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [toast, showToast] = useToast();

  useEffect(() => {
    getProfile()
      .then(setProfile)
      .catch(() => {});
    getNotionConnection()
      .then(setNotionConn)
      .catch(() => {}); // 실패하면 "연결 안 됨"으로 보일 뿐이다
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLeaveTime(localStorage.getItem(LEAVE_TIME_STORAGE_KEY));
    } catch {
      // localStorage 접근 불가 — 값 없이 기본 표시로 진행
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    // 9/18부터 초안이 두 군데 있을 수 있다 — 프로젝트 단위 초안과 마스터 초안
    // (여러 프로젝트를 한 문서로). 둘 중 하나라도 있으면 "등록됨"이다.
    Promise.all([
      currentProject ? getResumeDraft(currentProject.id) : Promise.resolve(null),
      getResumeDraft(null),
    ])
      .then((drafts) => {
        if (!cancelled) setResumeRegistered(drafts.some((d) => Boolean(d?.content)));
      })
      .catch(() => {
        if (!cancelled) setResumeRegistered(false);
      });
    return () => {
      cancelled = true;
    };
  }, [currentProject]);

  /**
   * 노션 연결 확인 (9/18 재작성).
   *
   * 예전엔 여기서 **대량 가져오기**(`syncNotion`)를 했다 — 통합이 접근 가능한 모든
   * 페이지를 긁어 전부 LLM에 태워 카드로 저장했고, 노션의 권한 상속 때문에 사용자가
   * 의도하지 않은 문서까지 외부로 나갔다(사용자 신고, 9/18).
   *
   * 이제 여기서는 **토큰이 유효한지만 확인**한다. 실제 가져오기는 기록 화면의
   * [노션에서 가져오기] → 페이지 선택(3.0-b)에서, 사용자가 고른 한 페이지만 일어난다.
   */
  const handleNotionConnect = async () => {
    const trimmed = notionToken.trim();
    if (!trimmed || notionSubmitting) return;
    setNotionSubmitting(true);
    setNotionError(null);
    setNotionSuccess(null);
    try {
      const pages = await listNotionPages(trimmed);
      // 세션 저장소에 넣어야 기록 화면의 페이지 선택이 토큰을 다시 묻지 않는다.
      rememberNotionToken(trimmed);
      setNotionSuccess(
        `연결됐어요. 가져올 수 있는 페이지 ${pages.length}건 — 기록 화면에서 골라 주세요.`,
      );
    } catch (err) {
      setNotionError(err instanceof ApiError ? err.detail : "노션 연결에 실패했습니다.");
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

  const handleExportBackup = async () => {
    setBackupBusy("export");
    setBackupError(null);
    try {
      const file = await exportBackup();
      // 파일 내려받기는 브라우저 기본 동작으로 처리한다 — 서버가 JSON을 주고
      // 여기서 Blob으로 감싸 a[download]를 한 번 클릭시킨다(exportResumeDocx와 동일 패턴).
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(file, null, 2)], { type: "application/json" }),
      );
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = backupFileName();
      anchor.click();
      URL.revokeObjectURL(url);
      showToast(`기록 ${file.cards.length}개를 내보냈어요`);
    } catch (err) {
      setBackupError(err instanceof ApiError ? err.detail : "내보내기에 실패했습니다.");
    } finally {
      setBackupBusy(null);
    }
  };

  const handlePickBackupFile = async (file: File) => {
    setBackupError(null);
    try {
      setImportConfirm(parseBackupFile(await file.text()));
    } catch {
      setBackupError("백업 파일을 읽지 못했어요. 내보내기로 받은 JSON 파일인지 확인해 주세요.");
    }
  };

  const handleImportBackup = async () => {
    if (!importConfirm) return;
    setBackupBusy("import");
    setBackupError(null);
    try {
      const result = await importBackup(importConfirm);
      setImportConfirm(null);
      showToast(`기록 ${result.imported_cards}개를 불러왔어요`);
    } catch (err) {
      setBackupError(err instanceof ApiError ? err.detail : "불러오기에 실패했습니다.");
    } finally {
      setBackupBusy(null);
    }
  };

  const handleLogout = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await logout();
    } catch {
      // 세션이 이미 만료됐어도 서버가 204(멱등)를 주지만, 네트워크 실패 등으로
      // 여기서 예외가 나도 로컬에서는 로그아웃된 것처럼 로그인 화면으로 보낸다 —
      // 어차피 쿠키가 유효하지 않으면 다음 요청에서 401로 다시 걸러진다.
    } finally {
      router.replace("/login");
    }
  };

  return (
    /* 5.0 설정 (Figma `299:14444`, 9/19 구조 반영).
       행을 회색 카드(`rounded-14 border bg-#1e1e1e`)로 감싸고 있었는데, 목업은
       **화면 배경 위에 테두리 없이** 1px `line` 구분선으로만 나눈다. 그룹 사이만
       16px 띄운다. 색도 목업 토큰(bg/ground · text/1 · text/3 · line)으로 맞췄다. */
    <div
      style={{ backgroundColor: t.screenBg, color: t.text }}
      className="flex flex-1 flex-col gap-[16px] px-[22px] pt-[24px] pb-8"
    >
      <div className="flex items-center gap-[10px] pb-[6px]">
        <Link
          href="/"
          aria-label="뒤로"
          className="flex size-[22px] items-center justify-center transition-opacity active:opacity-60"
        >
          <Image src="/icons/chevron-left.svg" alt="" width={20} height={20} aria-hidden />
        </Link>
        <p className="text-[20px] font-bold leading-[32px]">설정</p>
      </div>

      <div className="flex flex-col">
        {/* 직무만 고치는 모드로 보낸다 — 그 전엔 최초 가입과 똑같이 1/4부터 시작해서
            알림 설정까지 다 거쳐야 끝났고, 중간에 나갈 길도 없었다(사용자 신고, 9/18).
            알림은 아래 자기 행이 따로 있다. */}
        <Link
          href="/onboarding?only=job"
          className="flex items-center gap-[10px] px-[16px] py-[13px] transition-opacity active:opacity-70"
        >
          <span className="text-[16px] font-medium leading-[28px]">직무 설정</span>
          <div className="flex-1" />
          <span style={{ color: t.textMuted }} className="text-[12px] leading-[20px]">{jobLabel(profile) ?? "설정하기"}</span>
          <Image src="/icons/chevron-right.svg" alt="" width={16} height={16} aria-hidden />
        </Link>
        <div style={{ backgroundColor: t.border }} className="h-px w-full" />
        {/* 알림만 고치는 모드로 보낸다 — 그 전엔 직무·목표직무·회사를 전부 다시
            거쳐야 했다(사용자 신고, 9/18). */}
        <Link
          href="/onboarding?only=notify"
          className="flex items-center gap-[10px] px-[16px] py-[13px] transition-opacity active:opacity-70"
        >
          <span className="text-[16px] font-medium leading-[28px]">알림</span>
          <div className="flex-1" />
          <span style={{ color: t.textMuted }} className="text-[12px] leading-[20px]">
            {leaveTime ? `매일 ${leaveTime}` : "꺼짐"}
          </span>
          <Image src="/icons/chevron-right.svg" alt="" width={16} height={16} aria-hidden />
        </Link>
        <div style={{ backgroundColor: t.border }} className="h-px w-full" />
        <button
          type="button"
          onClick={() => setNotionOpen(true)}
          className="flex items-center gap-[10px] px-[16px] py-[13px] text-left transition-opacity active:opacity-70"
        >
          <span className="text-[16px] font-medium leading-[28px]">노션 연동</span>
          <div className="flex-1" />
          <span style={{ color: t.textMuted }} className="text-[12px] leading-[20px]">
            {notionConn?.connected ? (notionConn.workspace_name ?? "연결됨") : "연결 안 됨"}
          </span>
          <Image src="/icons/chevron-right.svg" alt="" width={16} height={16} aria-hidden />
        </button>
        <div style={{ backgroundColor: t.border }} className="h-px w-full" />
        <Link
          href="/resume"
          className="flex items-center gap-[10px] px-[16px] py-[13px] transition-opacity active:opacity-70"
        >
          <span className="text-[16px] font-medium leading-[28px]">내 이력서</span>
          <div className="flex-1" />
          <span style={{ color: t.textMuted }} className="text-[12px] leading-[20px]">
            {resumeRegistered == null ? "확인 중…" : resumeRegistered ? "등록됨" : "등록 안 됨"}
          </span>
          <Image src="/icons/chevron-right.svg" alt="" width={16} height={16} aria-hidden />
        </Link>
      </div>

      {/* 백업 (Figma 41:333 / 41:338) — 기록이 이 서비스 안에만 갇혀 있지 않다는 걸
          보여주는 장치. 불러오기는 LLM을 타지 않고 저장된 문장을 그대로 되살린다. */}
      <div className="flex flex-col">
        <button
          type="button"
          onClick={handleExportBackup}
          disabled={backupBusy !== null}
          className="flex items-center gap-[10px] px-[16px] py-[13px] text-left transition-opacity active:opacity-70 disabled:opacity-50"
        >
          <span className="text-[16px] font-medium leading-[28px]">백업 내보내기</span>
          <div className="flex-1" />
          <span style={{ color: t.textMuted }} className="text-[12px] leading-[20px]">
            {backupBusy === "export" ? "내보내는 중…" : "JSON"}
          </span>
          <Image src="/icons/chevron-right.svg" alt="" width={16} height={16} aria-hidden />
        </button>
        <div style={{ backgroundColor: t.border }} className="h-px w-full" />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={backupBusy !== null}
          className="flex items-center gap-[10px] px-[16px] py-[13px] text-left transition-opacity active:opacity-70 disabled:opacity-50"
        >
          <span className="text-[16px] font-medium leading-[28px]">백업 불러오기</span>
          <div className="flex-1" />
          <Image src="/icons/chevron-right.svg" alt="" width={16} height={16} aria-hidden />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            // 같은 파일을 다시 골라도 change가 나도록 값을 비워둔다.
            e.target.value = "";
            if (file) handlePickBackupFile(file);
          }}
        />
      </div>

      {backupError && (
        <p className="rounded-lg bg-[#2a1614] px-3 py-2 text-sm text-[#f0645c]">{backupError}</p>
      )}

      <div className="flex flex-col">
        <button
          type="button"
          onClick={() => setAppInfoOpen(true)}
          className="flex items-center gap-[10px] px-[16px] py-[13px] text-left transition-opacity active:opacity-70"
        >
          <span className="text-[16px] font-medium leading-[28px]">앱 정보</span>
          <div className="flex-1" />
          <Image src="/icons/chevron-right.svg" alt="" width={16} height={16} aria-hidden />
        </button>
      </div>

      <div className="flex flex-col">
        <button
          type="button"
          onClick={handleLogout}
          disabled={loggingOut}
          className="flex items-center px-[16px] py-[13px] text-left transition-opacity active:opacity-70 disabled:opacity-50"
        >
          <span className="text-[16px] font-medium leading-[28px] text-[#e8736c]">
            {loggingOut ? "로그아웃 중…" : "로그아웃"}
          </span>
        </button>
      </div>

      {/* 저장 안내 (Figma 5.0 `299:14492`) — 자물쇠는 이모지가 아니라 `icon/lock`이다.
          **문구는 목업과 다르게 뒀다**: 목업은 "기록은 이 기기 안에만 저장됩니다"라고
          적지만 이 앱은 서버(SQLite)에 저장하므로 그건 사실이 아니다(CLAUDE.md 2.2). */}
      <div className="flex items-center justify-center gap-[10px] px-[16px] py-[14px]">
        <Image src="/icons/lock.svg" alt="" width={14} height={14} aria-hidden />
        <p className="text-[12px] leading-[20px] text-[#918c84]">
          카카오 로그인으로 안전하게 보관돼요.
        </p>
      </div>

      <BottomSheet
        open={notionOpen}
        onClose={closeNotionSheet}
        hideHandle
        panelClassName="relative w-full max-w-md rounded-tl-[24px] rounded-tr-[24px] bg-[#1e1e1e] px-5 pt-4 pb-[30px] shadow-xl"
      >
        <div className="flex flex-col gap-3">
          <p className="text-[14px] font-semibold text-[#f2f2f2]">노션 연결</p>

          {/* 이미 OAuth로 연결돼 있으면 연결 대상과 해제만 보여준다 — 토큰을 다시
              물을 이유가 없다. */}
          {notionConn?.connected ? (
            <>
              <p className="text-xs text-[#a0a0a0]">
                <b>{notionConn.workspace_name ?? "노션 워크스페이스"}</b>에 연결돼 있어요.
                가져오기는 기록 화면에서 페이지를 하나 고를 때만 일어납니다.
              </p>
              <button
                type="button"
                onClick={async () => {
                  await disconnectNotion().catch(() => {});
                  setNotionConn({ connected: false, workspace_name: null, oauth_available: notionConn.oauth_available });
                  setNotionSuccess("연결을 해제했어요.");
                }}
                className="w-full rounded-[999px] border border-[#2e2e2e] py-2.5 text-sm font-semibold text-[#f2f2f2] transition-colors hover:bg-[#242424]"
              >
                연결 해제
              </button>
            </>
          ) : (
            <>
              {/* OAuth 경로 — client_id가 있을 때만. 노션 인가 화면에서 가져올 페이지를
                  직접 고르게 되므로, 고르지 않은 페이지는 앱이 볼 수 없다. */}
              {notionConn?.oauth_available && (
                <>
                  <a
                    href={notionOAuthStartUrl()}
                    className="flex h-[44px] items-center justify-center rounded-[999px] bg-accent text-sm font-semibold text-accent-foreground transition-opacity active:opacity-80"
                  >
                    노션으로 연결하기
                  </a>
                  <p className="text-xs text-[#a0a0a0]">
                    노션 화면에서 가져올 페이지를 직접 고르게 돼요. 고르지 않은 페이지는 이
                    앱이 볼 수 없습니다.
                  </p>
                  <p className="border-t border-[#2e2e2e] pt-3 text-xs text-[#5e5e5e]">
                    또는 통합 토큰을 직접 넣기
                  </p>
                </>
              )}
              <p className="text-xs text-[#a0a0a0]">
                토큰이 유효한지만 확인해요. 실제로 가져오는 건 기록 화면에서 <b>페이지를 하나
                고를 때</b>뿐이고, 여기서 노션 내용을 저장하지는 않습니다.
              </p>
              <p className="text-xs text-[#5e5e5e]">
                토큰은 이 브라우저 탭에만 잠시 보관되고 서버에 저장하지 않아요.
              </p>
            </>
          )}
          {/* 메시지는 연결 여부와 무관하게 보인다 — 연결 해제 결과도 여기 뜬다. */}
          {notionError && <p className="text-xs text-[#f0645c]">{notionError}</p>}
          {notionSuccess && <p className="text-xs text-emerald-400">{notionSuccess}</p>}

          {!notionConn?.connected && (
            <>
              <input
                type="password"
                value={notionToken}
                onChange={(e) => setNotionToken(e.target.value)}
                placeholder="secret_..."
                autoComplete="off"
                className="w-full rounded-md border border-[#2e2e2e] bg-[#141414] px-3 py-2 text-sm text-[#f2f2f2] placeholder:text-[#5e5e5e] focus:border-[#5e5e5e] focus:outline-none"
              />
              <button
                type="button"
                onClick={handleNotionConnect}
                disabled={notionSubmitting || !notionToken.trim()}
                className="w-full rounded-[999px] bg-accent py-2.5 text-sm font-semibold text-accent-foreground transition-colors hover:bg-[#ff7a2e] disabled:opacity-40"
              >
                {notionSubmitting ? "확인하는 중…" : "연결 확인"}
              </button>
            </>
          )}
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

      {/* 불러오기 확인 — "복원"이라는 말 때문에 기존 기록이 지워질 거라 오해하기
          쉬워서, 실제 동작(덧붙이기)을 누르기 전에 분명히 말해둔다. */}
      <BottomSheet
        open={importConfirm !== null}
        onClose={() => setImportConfirm(null)}
        hideHandle
        panelClassName="relative w-full max-w-md rounded-tl-[24px] rounded-tr-[24px] bg-[#1e1e1e] px-5 pt-4 pb-[30px] shadow-xl"
      >
        {importConfirm && (
          <div className="flex flex-col gap-3">
            <p className="text-[15px] font-semibold text-[#f2f2f2]">이 백업을 불러올까요?</p>
            <p className="text-[13px] leading-relaxed text-[#a0a0a0]">
              프로젝트 {importConfirm.projects.length}개, 기록 {importConfirm.cards.length}개가
              들어옵니다.
              <br />
              지금 있는 기록은 <span className="text-[#f2f2f2]">그대로 두고 덧붙입니다</span> —
              같은 파일을 두 번 넣으면 기록이 두 벌 생겨요.
            </p>
            <div className="flex gap-2.5">
              <button
                type="button"
                onClick={handleImportBackup}
                disabled={backupBusy === "import"}
                className="flex flex-1 items-center justify-center rounded-[12px] bg-accent py-3.5 text-[14px] font-semibold text-accent-foreground disabled:opacity-40"
              >
                {backupBusy === "import" ? "불러오는 중…" : "불러오기"}
              </button>
              <button
                type="button"
                onClick={() => setImportConfirm(null)}
                className="flex flex-1 items-center justify-center rounded-[12px] border-[1.5px] border-[#333] py-3.5 text-[14px] font-semibold text-[#f2f2f2]"
              >
                취소
              </button>
            </div>
          </div>
        )}
      </BottomSheet>

      <Toast toast={toast} />
    </div>
  );
}
