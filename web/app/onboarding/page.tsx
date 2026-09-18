"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CareerHistoryForm } from "@/components/CareerHistoryForm";
import { JobPicker, keepKnownJobs } from "@/components/JobPicker";
import { ApiError, Company, JobField, Profile, getProfile, updateProfile } from "@/lib/api";
import { categoryOfJob } from "@/lib/jobTaxonomy";
import { markOnboardingSkipped } from "@/lib/onboardingSkip";
import { usePushSubscription } from "@/lib/usePushSubscription";

/**
 * 온보딩 (`/onboarding`) — Figma "00 · 온보딩" 섹션(`268:5731`) 4단계 재설계 (9/18).
 *
 * 그 전까지는 한 화면에 직군 6칩 → 세부직무 → 연차 4세그먼트 → 퇴근알림이 전부
 * 들어 있었고, 화면이 라이트 테마로 남아 있어 나머지 앱과도 따로 놀았다. 새 설계는
 * 네 단계로 나뉜다:
 *
 *   1/4 어떤 일을 하세요?      — 현재 직무 (단일)      `268:5827`
 *   2/4 어디로 가고 싶으세요?  — 목표 직무 (다중)      `268:5888`
 *   3/4 어디서 얼마나 일하셨어요? — 회사·기간 → 연차 자동 계산  `268:5732`
 *   4/4 언제 알려드릴까요?     — 퇴근 알림             `268:5777` (+거부 변형 `268:5806`)
 *
 * **왜 이게 CLAUDE.md 2.1을 안 깨는가**: 2.1이 막는 건 *매일* 반복되는 경로(메모 입력
 * → 변환)에 선택지를 끼우는 것이다. 이 화면은 연 1~3회짜리라 기준을 만족한다.
 *
 * **2.4 배제 목록과의 관계**: "연차 직접 입력"은 배제 항목이었고 그동안 4개 세그먼트로
 * 받았다. 3/4 화면이 그걸 대체한다 — 사용자가 이 Figma를 보고 명시적으로 "전부 구현"을
 * 지시해서 진행했다(2026-09-18). 저장되는 값은 **여전히 그 4개 구간**이고(서버가 회사
 * 기간에서 계산), 사람에게 묻는 방식만 바뀐 것이다.
 *
 * 설정 변경 목적으로 다시 들어온 경우(이미 프로필이 있음)엔 저장 후 `/`로 튕기지 않고
 * 화면에 남는다 — 9/15 피드백("퇴근 시각만 바꾸려는데 메인으로 나가버린다").
 */

type Step = 1 | 2 | 3 | 4;

/** 퇴근 시각에서 실제 발송 시각(15분 전)을 만들어 문구로 (Figma 268:5794). */
function reminderSentence(leaveTime: string): string | null {
  const [h, m] = leaveTime.split(":").map(Number);
  if (!Number.isInteger(h) || !Number.isInteger(m)) return null;
  const total = h * 60 + m - 15;
  if (total < 0) return null;
  const hour = Math.floor(total / 60) % 24;
  const minute = total % 60;
  const meridiem = hour < 12 ? "오전" : "저녁";
  const display = hour % 12 === 0 ? 12 : hour % 12;
  return `퇴근 15분 전, ${meridiem} ${display}시 ${minute}분에 보낼게요`;
}

const TIME_PRESETS = ["18:00", "19:00"];

function OnboardingPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  /**
   * 설정 → 알림에서 들어온 "알림만 고치기" 모드 (9/18 신규).
   *
   * 그 전까진 설정의 알림 행이 `/onboarding`으로 그냥 보내서, **알림 하나 바꾸려고
   * 직무·목표직무·회사를 전부 다시 거쳐야** 했다. 게다가 마지막 [시작하기]는
   * 이미 프로필이 있는 경우 화면에 머물면서 작은 메시지만 띄워서(아래 finish 참고),
   * 스크롤 밖이면 아무 반응이 없는 것처럼 보였다 — 사용자 신고(9/18).
   *
   * 이 모드에서는 4단계(알림)만 띄우고, 저장하면 설정으로 돌아간다.
   */
  const notifyOnly = searchParams.get("only") === "notify";

  const [step, setStep] = useState<Step>(notifyOnly ? 4 : 1);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const [currentJob, setCurrentJob] = useState<string[]>([]);
  const [targetJobs, setTargetJobs] = useState<string[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);

  // 설정 변경 방문인지 최초 온보딩인지. 로드 시점 스냅샷으로 한 번만 정한다 —
  // 폼을 만지는 동안 라벨이 흔들리지 않게(9/15).
  const [hasExistingProfile, setHasExistingProfile] = useState(false);

  const push = usePushSubscription();
  const [customTime, setCustomTime] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getProfile()
      .then((profile: Profile) => {
        if (cancelled) return;
        // 저장된 직무가 지금 분류표에 없으면(표를 갈아끼운 경우) 화면에서 뺀다 —
        // 칩으로 못 만드는 값이 선택된 것처럼 보이면 해제할 방법이 없다.
        setCurrentJob(profile.job_detail ? keepKnownJobs([profile.job_detail]) : []);
        setTargetJobs(keepKnownJobs(profile.target_jobs));
        setCompanies(profile.companies);
        setHasExistingProfile(profile.job_field !== null);
      })
      .catch(() => {
        // 조회 실패는 치명적이지 않다 — 빈 상태로 새로 시작하면 된다.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /** 프로필을 저장한다. 4단계 끝에서 한 번만 부르고, 그 전 단계는 화면 상태로만 든다. */
  const persist = async (): Promise<boolean> => {
    const job = currentJob[0];
    const category = job ? categoryOfJob(job) : null;
    if (!category) {
      setError("직무를 먼저 골라주세요.");
      setStep(1);
      return false;
    }
    setSaving(true);
    setError(null);
    try {
      await updateProfile({
        jobField: category as JobField,
        jobDetail: job,
        targetJobs,
        // 빈 배열도 그대로 보낸다 — "회사 정보 없이 시작할게요"로 넘어온 경우
        // 예전에 넣어둔 목록을 지우는 게 맞다.
        companies: companies.filter((c) => c.name.trim() && c.started_at),
      });
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "저장에 실패했습니다. 다시 시도해 주세요.");
      return false;
    } finally {
      setSaving(false);
    }
  };

  /** 마지막 단계 — 저장하고 (원하면) 알림까지 켠 뒤 홈으로. */
  const finish = async (withPush: boolean) => {
    if (withPush) {
      // 권한 요청은 반드시 이 클릭 핸들러 안에서 시작해야 한다(lib/usePushSubscription.ts).
      // 거부돼도 온보딩 자체는 계속 진행한다 — 알림은 필수가 아니다.
      await push.subscribe();
    }
    const ok = await persist();
    if (!ok) return;
    if (notifyOnly) {
      // 알림만 고치러 온 경우 — 저장하면 온 곳(설정)으로 돌려보낸다. 화면에 머물면서
      // 작은 메시지만 띄우면 "아무 반응이 없다"로 읽힌다(사용자 신고, 9/18).
      router.push("/settings");
      return;
    }
    if (hasExistingProfile) {
      setSavedMessage("저장했습니다.");
      return;
    }
    router.push("/");
  };

  if (loading) {
    return (
      <div className="px-5 pt-6">
        <p className="text-[13px] text-[#828282]">불러오는 중…</p>
      </div>
    );
  }

  // 알림만 고치러 온 경우엔 "4 / 4"가 의미 없다 — 단계가 하나뿐이다.
  const stepLabel = notifyOnly ? "알림" : `${step} / 4`;

  return (
    // 화면 높이를 확보해야 `flex-1` 스페이서가 버튼을 바닥으로 밀어낸다 — Figma의
    // 네 화면 모두 주요 버튼이 화면 하단에 붙어 있다. 하단 탭바는 이 화면에서 숨겨진다.
    //
    // `svh`와 `-mb-6`은 로그인 화면과 같은 이유다 (9/18) — dvh는 모바일 주소창이
    // 접히면 커져서 버튼이 아래로 밀리고, 레이아웃의 pb-6이 남으면 문서가 뷰포트보다
    // 24px 길어져 그 스크롤이 주소창 접힘을 유발한다.
    <div className="-mb-6 flex min-h-[100svh] flex-col px-5 pb-6 pt-2 text-[#f2f2f2]">
      {/* 헤더 — 4단계엔 Figma에도 헤더가 없다(뒤로 갈 곳이 아니라 끝내는 화면). */}
      {notifyOnly && (
        <div className="flex items-center gap-2 pt-2">
          <button
            type="button"
            onClick={() => router.push("/settings")}
            aria-label="뒤로"
            className="text-[17px] text-[#f2f2f2]"
          >
            ←
          </button>
          <p className="text-[15px] font-semibold text-[#f2f2f2]">알림 설정</p>
        </div>
      )}

      {step < 4 && (
        <div className="flex items-center gap-3 py-2">
          <button
            type="button"
            onClick={() => (step === 1 ? router.back() : setStep((s) => (s - 1) as Step))}
            aria-label="뒤로"
            className="text-[18px] text-[#f2f2f2]"
          >
            ‹
          </button>
          {step <= 2 && (
            <>
              <p className="text-[14px] text-[#f2f2f2]">직군 · 직무</p>
              <div className="flex-1" />
              <p className="text-[13px] text-[#828282]">{step === 1 ? "단일 선택" : "다중 선택"}</p>
            </>
          )}
        </div>
      )}

      <p className="pt-3 text-[13px] text-[#828282]">{stepLabel}</p>

      {step === 1 && (
        <>
          <h1 className="pt-3 text-[24px] font-bold tracking-[-0.4px]">어떤 일을 하세요?</h1>
          <p className="pt-2 pb-4 text-[14px] text-[#a0a0a0]">하나만 골라주세요</p>
          <JobPicker
            multiple={false}
            selected={currentJob}
            onChange={setCurrentJob}
            onConfirm={() => setStep(2)}
          />
        </>
      )}

      {step === 2 && (
        <>
          <h1 className="pt-3 text-[24px] font-bold tracking-[-0.4px]">어디로 가고 싶으세요?</h1>
          <p className="pt-2 pb-4 text-[14px] text-[#a0a0a0]">여러 개 골라도 됩니다</p>
          <JobPicker
            multiple
            selected={targetJobs}
            onChange={setTargetJobs}
            onConfirm={() => setStep(3)}
            footer={
              <button
                type="button"
                onClick={() => {
                  setTargetJobs([]);
                  setStep(3);
                }}
                className="w-full pt-3 text-center text-[13px] text-[#828282] underline underline-offset-2"
              >
                지금 하는 일을 계속할게요
              </button>
            }
          />
        </>
      )}

      {step === 3 && (
        <>
          <h1 className="pt-3 text-[24px] font-bold tracking-[-0.4px]">
            어디서 얼마나 일하셨어요?
          </h1>
          <p className="pt-2 text-[14px] leading-relaxed text-[#a0a0a0]">
            회사와 기간만 알려주시면, 기록이 비어 있는 구간을 짚어드릴 수 있어요.
          </p>

          <div className="pt-5">
            <CareerHistoryForm companies={companies} onChange={setCompanies} />
          </div>

          {error && (
            <p className="mt-4 rounded-lg bg-[#2a1614] px-3 py-2 text-[13px] text-[#f0645c]">
              {error}
            </p>
          )}

          <div className="flex-1" />

          <button
            type="button"
            onClick={() => setStep(4)}
            className="mt-6 w-full rounded-[12px] bg-accent py-4 text-[15px] font-semibold text-accent-foreground transition-colors hover:bg-[#ff7a2e]"
          >
            다음
          </button>
          <button
            type="button"
            onClick={() => {
              setCompanies([]);
              setStep(4);
            }}
            className="pt-3 text-center text-[13px] text-[#828282] underline underline-offset-2"
          >
            회사 정보 없이 시작할게요
          </button>
        </>
      )}

      {step === 4 && (
        <>
          <h1 className="pt-3 text-[24px] font-bold tracking-[-0.4px]">언제 알려드릴까요?</h1>

          {push.status === "denied" ? (
            /* 2.4-b 알림 권한 거부 (Figma 268:5806) */
            <>
              <p className="pt-3 text-[14px] leading-relaxed text-[#a0a0a0]">
                알림이 꺼져 있어요. 기기 설정에서 켜면 잊지 않고 알려드릴게요.
              </p>
              <p className="pt-6 text-[13px] text-[#828282]">알림 없이도 앱은 그대로 쓸 수 있어요</p>
              <div className="mt-3 rounded-[14px] bg-[#1c1c1c] px-4 py-5">
                <p className="text-[15px] font-semibold text-[#f2f2f2]">설정 › 알림 › 오늘의 흔적</p>
                <p className="pt-1.5 text-[13px] text-[#828282]">여기서 켤 수 있어요</p>
              </div>
            </>
          ) : (
            <>
              <p className="pt-3 text-[14px] leading-relaxed text-[#a0a0a0]">
                퇴근 무렵에 한 번만 보낼게요. 알림을 받고 싶지 않으면 건너뛰어도 돼요.
              </p>

              {/* 퇴근 시간 (Figma 268:5786) */}
              <div className="flex gap-2 pt-7">
                {TIME_PRESETS.map((time) => {
                  const active = !customTime && push.leaveTime === time;
                  return (
                    <button
                      key={time}
                      type="button"
                      onClick={() => {
                        setCustomTime(false);
                        push.setLeaveTime(time);
                      }}
                      aria-pressed={active}
                      className={`flex-1 rounded-[12px] py-4 text-[16px] transition-colors ${
                        active
                          ? "bg-accent font-semibold text-accent-foreground"
                          : "bg-[#1c1c1c] text-[#d4d4d4] hover:bg-[#242424]"
                      }`}
                    >
                      {time}
                    </button>
                  );
                })}
                <button
                  type="button"
                  onClick={() => setCustomTime(true)}
                  aria-pressed={customTime}
                  className={`flex-1 rounded-[12px] py-4 text-[14px] transition-colors ${
                    customTime
                      ? "bg-accent font-semibold text-accent-foreground"
                      : "bg-[#1c1c1c] text-[#d4d4d4] hover:bg-[#242424]"
                  }`}
                >
                  직접 입력
                </button>
              </div>

              {customTime && (
                <input
                  type="time"
                  value={push.leaveTime}
                  onChange={(e) => push.setLeaveTime(e.target.value)}
                  aria-label="퇴근 시각"
                  className="mt-3 w-full rounded-[12px] bg-[#1c1c1c] px-4 py-3 text-[15px] text-[#f2f2f2] focus:outline-none focus:ring-1 focus:ring-[#5e5e5e]"
                />
              )}

              <p className="pt-5 text-[13px] text-[#828282]">
                {reminderSentence(push.leaveTime) ?? "퇴근 15분 전에 보낼게요"}
              </p>

              {/* 주말 제외 (Figma 268:5796) */}
              <button
                type="button"
                onClick={() => push.setSkipWeekends(!push.skipWeekends)}
                role="switch"
                aria-checked={push.skipWeekends}
                className="mt-7 flex w-full items-center"
              >
                <span className="text-[15px] text-[#f2f2f2]">주말에는 쉬어요</span>
                <span className="flex-1" />
                <span
                  aria-hidden
                  className={`flex h-[30px] w-[50px] items-center rounded-full p-[3px] transition-colors ${
                    push.skipWeekends ? "bg-accent" : "bg-[#3a3a3a]"
                  }`}
                >
                  <span
                    className={`size-[24px] rounded-full bg-white transition-transform ${
                      push.skipWeekends ? "translate-x-[20px]" : ""
                    }`}
                  />
                </span>
              </button>
            </>
          )}

          {push.message && <p className="pt-4 text-[13px] text-[#828282]">{push.message}</p>}
          {error && (
            <p className="mt-4 rounded-lg bg-[#2a1614] px-3 py-2 text-[13px] text-[#f0645c]">
              {error}
            </p>
          )}
          {savedMessage && (
            <p className="mt-4 rounded-lg bg-[#16241c] px-3 py-2 text-[13px] text-emerald-400">
              {savedMessage}
            </p>
          )}

          <div className="flex-1" />

          <button
            type="button"
            onClick={() => finish(push.status !== "denied" && push.status !== "subscribed")}
            disabled={saving || push.status === "subscribing"}
            className="mt-6 w-full rounded-[12px] bg-accent py-4 text-[15px] font-semibold text-accent-foreground transition-colors hover:bg-[#ff7a2e] disabled:opacity-40"
          >
            {saving || push.status === "subscribing"
              ? "설정하는 중…"
              : notifyOnly
                ? "저장"
                : "시작하기"}
          </button>
          <button
            type="button"
            onClick={() => finish(false)}
            disabled={saving}
            className="pt-3 text-center text-[13px] text-[#828282] underline underline-offset-2 disabled:opacity-40"
          >
            {notifyOnly ? "알림 끄고 저장" : "알림 없이 시작하기"}
          </button>
        </>
      )}

      {/* 최초 온보딩일 때만 — 설정 변경으로 들어온 경우엔 나갈 길이 이미 헤더에 있다. */}
      {!hasExistingProfile && step < 4 && (
        <button
          type="button"
          onClick={() => {
            markOnboardingSkipped();
            router.push("/");
          }}
          className="pt-4 text-center text-[13px] text-[#5e5e5e] underline underline-offset-2"
        >
          나중에 설정하기
        </button>
      )}
    </div>
  );
}

/** `useSearchParams()`(설정에서 넘어오는 `?only=notify`)를 쓰므로 `<Suspense>`가 필요하다. */
export default function OnboardingPage() {
  return (
    <Suspense fallback={null}>
      <OnboardingPageInner />
    </Suspense>
  );
}
