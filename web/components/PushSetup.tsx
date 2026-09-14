"use client";

import { useEffect, useState } from "react";
import { ApiError, getVapidPublicKey, subscribePush, unsubscribePush } from "@/lib/api";
import { urlBase64ToUint8Array } from "@/lib/push";

type Status = "idle" | "subscribing" | "subscribed" | "unavailable" | "error";

const LEAVE_TIME_STORAGE_KEY = "careerlog:leaveTime";

/**
 * 퇴근 15분 전 웹 푸시 구독 설정 — Tier 2 (`docs/06-migration.md` §1, Tier 1은 이번
 * 포팅에서 스킵함: 실 웹푸시가 있으니 탭이 열려 있을 때만 동작하는 구버전 타이머는
 * 굳이 옮길 이유가 없음).
 *
 * 권한 요청/구독은 반드시 이 버튼의 클릭 핸들러 안에서 시작한다 — 자동으로 하면
 * 최신 브라우저가 "사용자 제스처 없음"으로 판단해 조용히 막는다(Tier 1/2에서
 * 이미 겪은 문제, `tasks/track-e-push-notifications.md` 참고).
 *
 * **구현 노트 (9/14, 상태 초기화 버그 수정)**: 이 컴포넌트의 상태는 전부 `useState`뿐이라
 * `/onboarding`을 나갔다 들어오면(컴포넌트 재마운트) `leaveTime`이 기본값(18:00)으로,
 * `status`도 "idle"로 리셋되는 문제가 있었다 — 서버는 구독을 계속 들고 있는데 화면만
 * "안 켜진 것처럼" 보였다. 두 가지로 고친다:
 *   1. `leaveTime`은 사용자가 마지막으로 고른 값을 `localStorage`에 저장해 마운트 시 복원.
 *      (서버에 저장된 값을 되읽는 GET 엔드포인트가 아직 없어서 "마지막 선택값 기억" 수준의
 *      로컬 편의 기능이다 — 여러 기기 동기화는 스코프 밖.)
 *   2. 구독 여부는 브라우저의 실제 PushManager 상태(`getSubscription()`)를 마운트 시
 *      조회해서 반영한다 — 이게 진짜 소스오브트루스라 React state 리셋과 무관하게 정확하다.
 */
export function PushSetup() {
  const [leaveTime, setLeaveTime] = useState("18:00");
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [subscription, setSubscription] = useState<PushSubscription | null>(null);

  useEffect(() => {
    // 1. 마지막으로 선택했던 퇴근 시각 복원 (편의 기본값 — 서버 값과의 동기화는 아님).
    try {
      const saved = localStorage.getItem(LEAVE_TIME_STORAGE_KEY);
      // 마운트 직후 1회, 외부 저장소(localStorage)의 값으로 초기값을 갱신하는 표준 패턴
      // (VoiceInput.tsx의 지원 여부 체크와 동일한 이유로 억제).
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (saved) setLeaveTime(saved);
    } catch {
      // localStorage 접근 불가(프라이빗 모드 등) — 그냥 기본값으로 진행.
    }

    // 2. 이미 구독돼 있으면(같은 브라우저/기기) 그 상태를 그대로 반영 — "idle"로
    // 잘못 리셋되는 걸 막는다. 아직 서비스워커 등록조차 안 했으면 조용히 넘어간다.
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
    let cancelled = false;
    navigator.serviceWorker
      .getRegistration("/service-worker.js")
      .then((registration) => registration?.pushManager.getSubscription() ?? null)
      .then((sub) => {
        if (!cancelled && sub) {
          setSubscription(sub);
          setStatus("subscribed");
        }
      })
      .catch(() => {
        // 조회 실패해도 치명적이지 않다 — 기본 상태(idle)로 두면 사용자가 다시 켤 수 있다.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubscribe = async () => {
    if (
      typeof window === "undefined" ||
      !("serviceWorker" in navigator) ||
      !("PushManager" in window)
    ) {
      setStatus("unavailable");
      setMessage("이 브라우저는 웹 푸시를 지원하지 않습니다.");
      return;
    }

    setStatus("subscribing");
    setMessage(null);
    try {
      // 1. VAPID 공개키 확보 (서버 미설정 시 503 — catch에서 처리).
      const publicKey = await getVapidPublicKey();

      // 2. 권한 요청 — 반드시 이 클릭 핸들러 안에서.
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setStatus("idle");
        setMessage("알림 권한이 거부되어 웹 푸시를 켤 수 없습니다.");
        return;
      }

      // 3. 서비스워커 등록(이미 등록돼 있으면 재사용)+구독.
      const registration = await navigator.serviceWorker.register("/service-worker.js");
      await navigator.serviceWorker.ready;
      const sub = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });

      const json = sub.toJSON();
      if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
        throw new Error("구독 정보가 올바르지 않습니다.");
      }

      // 4. 서버에 저장 — 같은 endpoint로 다시 보내도 upsert되므로 "이미 구독됨" 분기 불필요.
      await subscribePush({
        endpoint: json.endpoint,
        keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
        leave_time: leaveTime,
      });

      try {
        localStorage.setItem(LEAVE_TIME_STORAGE_KEY, leaveTime);
      } catch {
        // localStorage 접근 불가해도 구독 자체는 이미 성공했으니 무시하고 진행.
      }

      setSubscription(sub);
      setStatus("subscribed");
      setMessage("퇴근 15분 전 알림이 설정됐어요. 탭을 닫아도 알림이 옵니다.");
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setStatus("unavailable");
        setMessage("서버에 웹 푸시가 아직 설정되어 있지 않습니다 (VAPID_PUBLIC_KEY).");
        return;
      }
      setStatus("error");
      setMessage("웹 푸시 설정에 실패했습니다. 다시 시도해 주세요.");
    }
  };

  const handleUnsubscribe = async () => {
    if (!subscription) return;
    try {
      await unsubscribePush(subscription.endpoint);
    } catch {
      // 서버는 존재하지 않는 구독을 지워도 204(멱등) — 실패해도 로컬 해제는 계속 진행.
    }
    try {
      await subscription.unsubscribe();
    } finally {
      setSubscription(null);
      setStatus("idle");
      setMessage("알림을 껐습니다.");
    }
  };

  if (status === "unavailable") {
    return (
      <p className="text-xs text-zinc-400">
        {message ?? "이 환경에서는 웹 푸시를 사용할 수 없습니다."}
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-1.5 text-xs text-zinc-500">
        퇴근 시각
        <input
          type="time"
          value={leaveTime}
          onChange={(e) => setLeaveTime(e.target.value)}
          disabled={status === "subscribed"}
          className="rounded-md border border-zinc-300 px-2 py-1 text-xs disabled:opacity-50"
        />
      </label>

      {status === "subscribed" ? (
        <button
          type="button"
          onClick={handleUnsubscribe}
          className="rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-600 transition-colors hover:bg-zinc-50 active:scale-[0.98]"
        >
          🔕 알림 끄기
        </button>
      ) : (
        <button
          type="button"
          onClick={handleSubscribe}
          disabled={status === "subscribing"}
          className="rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 transition-colors hover:bg-zinc-50 active:scale-[0.98] disabled:opacity-50"
        >
          {status === "subscribing" ? "설정 중…" : "🔔 퇴근 알림 켜기"}
        </button>
      )}

      {message && <p className="w-full text-xs text-zinc-500">{message}</p>}
    </div>
  );
}
