"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PushSetup } from "@/components/PushSetup";
import {
  ApiError,
  DEV_JOB_DETAILS,
  JOB_FIELDS,
  JobField,
  Profile,
  YEARS_SEGMENTS,
  YearsSegment,
  getProfile,
  updateProfile,
} from "@/lib/api";
import { markOnboardingSkipped } from "@/lib/onboardingSkip";

/**
 * 온보딩 화면 (`/onboarding`, P2 — CLAUDE.md 6장 "온보딩(현재 직무/목표 직무/연차)",
 * Figma "2.0 목적지·푸시 설정" 대응).
 *
 * 연 1~3회 정도만 열어보는 화면이라 매일 쓰는 입력 경로(`/`)와는 완전히 분리돼 있다
 * (CLAUDE.md 2.1). 직군/연차는 자유 입력이 아니라 고정 칩만 허용한다(2.4) — 서버가
 * Pydantic `Literal`로 다시 한번 강제하므로, 여기서 잘못된 값을 보낼 방법 자체가 없다.
 *
 * 퇴근 시각 + 웹 푸시 설정은 이미 만들어진 `<PushSetup />`을 그대로 재사용한다 —
 * Figma 화면은 이 둘을 한 화면에 묶어서 보여주지만, 로직 자체는 독립적이라
 * 별도 컴포넌트로 나눠도 화면 구성만 합치면 된다.
 */
export default function OnboardingPage() {
  const router = useRouter();

  const [jobField, setJobField] = useState<JobField | null>(null);
  const [jobDetail, setJobDetail] = useState<string | null>(null);
  const [yearsSegment, setYearsSegment] = useState<YearsSegment | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  // 최초 온보딩인지, 이미 설정을 마친 뒤 다시 들어온(설정 변경) 건지 구분한다
  // (9/15 신규 — "퇴근 시각을 바꾸려고 들어왔는데 저장하면 메인으로 튕겨서 다시
  // 들어와야 한다"는 피드백 반영). 로드 시점의 스냅샷으로 한 번만 정하고, 그 뒤
  // 폼을 만지는 동안에는 안 바뀐다 — 안 그러면 저장 전에 라벨이 계속 흔들린다.
  const [hasExistingProfile, setHasExistingProfile] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getProfile()
      .then((profile: Profile) => {
        if (cancelled) return;
        setJobField(profile.job_field);
        setJobDetail(profile.job_detail);
        setYearsSegment(profile.years_segment);
        setHasExistingProfile(profile.job_field !== null && profile.years_segment !== null);
      })
      .catch(() => {
        // 프로필 조회 실패는 치명적이지 않다 — 빈 상태로 온보딩을 새로 시작하면 된다.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSelectJobField = (field: JobField) => {
    setJobField(field);
    // 직군이 바뀌면 이전 직군의 세부 직무는 더 이상 유효하지 않을 수 있으므로 초기화한다.
    if (field !== "개발") setJobDetail(null);
  };

  const canSubmit = jobField !== null && yearsSegment !== null && !saving;

  const handleSubmit = async () => {
    if (!jobField || !yearsSegment) return;
    setSaving(true);
    setError(null);
    setSavedMessage(null);
    try {
      await updateProfile(jobField, yearsSegment, jobDetail ?? undefined);
      if (hasExistingProfile) {
        // 설정 변경 방문이면 메인으로 돌려보내지 않는다 — 퇴근 알림도 여기서 같이
        // 만지는 경우가 많아서, 저장 후에도 화면에 남아 확인/재조정할 수 있어야 한다.
        setSavedMessage("저장했습니다.");
      } else {
        router.push("/");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "저장에 실패했습니다. 다시 시도해 주세요.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="px-4 pt-4">
        <p className="text-sm text-zinc-400">불러오는 중…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 px-4 pt-4 pb-8">
      <div>
        {hasExistingProfile && (
          <button
            type="button"
            onClick={() => router.back()}
            className="mb-2 text-sm text-zinc-400 hover:text-zinc-600"
          >
            ‹ 뒤로
          </button>
        )}
        <h1 className="text-lg font-semibold text-zinc-900">
          {hasExistingProfile ? "직군·알림 설정" : "커리어 스택 시작하기"}
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          {hasExistingProfile
            ? "직군·연차나 퇴근 알림이 바뀌었으면 여기서 바꿀 수 있어요."
            : "몇 가지만 알려주시면 기록을 더 잘 정리해 드려요. 나중에 언제든 바꿀 수 있어요."}
        </p>
      </div>

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-zinc-700">
          {hasExistingProfile ? "직군" : "어떤 일을 하세요?"}
        </h2>
        <div className="flex flex-wrap gap-2">
          {JOB_FIELDS.map((field) => (
            <ChipButton
              key={field}
              label={field}
              selected={jobField === field}
              onClick={() => handleSelectJobField(field)}
            />
          ))}
        </div>
      </section>

      {jobField === "개발" && (
        <section className="space-y-2">
          <h2 className="text-sm font-medium text-zinc-700">세부 직무</h2>
          <div className="flex flex-wrap gap-2">
            {DEV_JOB_DETAILS.map((detail) => (
              <ChipButton
                key={detail}
                label={detail}
                selected={jobDetail === detail}
                onClick={() => setJobDetail(jobDetail === detail ? null : detail)}
              />
            ))}
          </div>
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-zinc-700">연차</h2>
        <div className="flex flex-wrap gap-2">
          {YEARS_SEGMENTS.map((segment) => (
            <ChipButton
              key={segment}
              label={segment === "10+" ? "10년 이상" : `${segment}년`}
              selected={yearsSegment === segment}
              onClick={() => setYearsSegment(segment)}
            />
          ))}
        </div>
      </section>

      <section className="space-y-2 border-t border-zinc-200 pt-4">
        <h2 className="text-sm font-medium text-zinc-700">퇴근 알림</h2>
        <p className="text-xs text-zinc-500">
          퇴근 시각을 설정하면 15분 전에 오늘 기록을 남기라고 알려드려요. (건너뛰어도 괜찮아요)
        </p>
        <PushSetup />
      </section>

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}
      {savedMessage && (
        <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          {savedMessage}
        </p>
      )}

      <button
        type="button"
        onClick={handleSubmit}
        disabled={!canSubmit}
        className="w-full rounded-xl bg-zinc-900 py-3 text-base font-semibold text-white transition-colors hover:bg-zinc-800 disabled:opacity-40 disabled:hover:bg-zinc-900"
      >
        {saving ? "저장하는 중…" : hasExistingProfile ? "저장" : "내 커리어 스택 시작하기"}
      </button>

      {!hasExistingProfile && (
        <button
          type="button"
          onClick={() => {
            markOnboardingSkipped();
            router.push("/");
          }}
          className="text-center text-sm text-zinc-400 underline underline-offset-2"
        >
          나중에 설정하기
        </button>
      )}
    </div>
  );
}

function ChipButton({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors active:scale-[0.98] ${
        selected
          ? "border-zinc-900 bg-zinc-900 text-white hover:bg-zinc-800"
          : "border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50"
      }`}
    >
      {label}
    </button>
  );
}
