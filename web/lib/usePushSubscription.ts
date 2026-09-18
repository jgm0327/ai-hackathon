"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, getVapidPublicKey, subscribePush, unsubscribePush } from "./api";
import { urlBase64ToUint8Array } from "./push";

/**
 * 퇴근 15분 전 웹 푸시 구독 — Tier 2 (`docs/06-migration.md` §1).
 *
 * 9/18에 `components/PushSetup.tsx`에서 로직만 뽑아낸 훅이다. Figma "00 · 온보딩"
 * 4/4 화면이 요구하는 모양(시각 칩 + 주말 토글 + 화면 하단의 "시작하기"가 구독까지
 * 처리)은 예전 컴포넌트의 "알림 켜기 버튼" 구조와 맞지 않는데, **권한 요청 순서에
 * 걸린 제약들은 그대로 지켜야** 해서 UI만 갈아끼우고 로직은 옮겨 담았다.
 *
 * 지켜야 하는 것들(예전 컴포넌트 주석에서 그대로 옮김):
 *   - 권한 요청/구독은 **반드시 사용자 클릭 핸들러 안에서** 시작한다. 자동으로 하면
 *     최신 브라우저가 "사용자 제스처 없음"으로 판단해 조용히 막는다.
 *   - 구독 여부의 진짜 소스오브트루스는 브라우저의 `PushManager.getSubscription()`이다.
 *     React state는 화면을 나갔다 오면 리셋되지만 서버 구독은 남아 있어서, 마운트
 *     시점에 실제 구독을 조회해야 "안 켜진 것처럼" 보이지 않는다.
 *   - 퇴근 시각은 마지막 선택값을 localStorage에 남긴다(서버에서 되읽는 GET이 없다).
 */

export type PushStatus = "idle" | "subscribing" | "subscribed" | "denied" | "unavailable" | "error";

const LEAVE_TIME_STORAGE_KEY = "careerlog:leaveTime";
const SKIP_WEEKENDS_STORAGE_KEY = "careerlog:skipWeekends";

export interface PushSubscriptionState {
  status: PushStatus;
  message: string | null;
  leaveTime: string;
  setLeaveTime: (value: string) => void;
  skipWeekends: boolean;
  setSkipWeekends: (value: boolean) => void;
  /** 클릭 핸들러 안에서 부를 것. 성공하면 true. */
  subscribe: () => Promise<boolean>;
  unsubscribe: () => Promise<void>;
}

export function usePushSubscription(): PushSubscriptionState {
  const [leaveTime, setLeaveTime] = useState("18:00");
  const [skipWeekends, setSkipWeekends] = useState(true); // Figma 4/4는 켜진 상태가 기본
  const [status, setStatus] = useState<PushStatus>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [subscription, setSubscription] = useState<PushSubscription | null>(null);

  useEffect(() => {
    try {
      const savedTime = localStorage.getItem(LEAVE_TIME_STORAGE_KEY);
      const savedSkip = localStorage.getItem(SKIP_WEEKENDS_STORAGE_KEY);
      // 마운트 직후 1회, 외부 저장소(localStorage)의 값으로 초기값을 갱신하는 표준 패턴.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (savedTime) setLeaveTime(savedTime);
      if (savedSkip !== null) setSkipWeekends(savedSkip === "1");
    } catch {
      // 접근 불가(프라이빗 모드 등) — 기본값으로 진행.
    }

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
        // 조회 실패해도 치명적이지 않다 — idle로 두면 사용자가 다시 켤 수 있다.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const subscribe = useCallback(async (): Promise<boolean> => {
    if (
      typeof window === "undefined" ||
      !("serviceWorker" in navigator) ||
      !("PushManager" in window)
    ) {
      setStatus("unavailable");
      setMessage("이 브라우저는 웹 푸시를 지원하지 않습니다.");
      return false;
    }

    setStatus("subscribing");
    setMessage(null);
    try {
      const publicKey = await getVapidPublicKey();

      // 권한 요청 — 반드시 클릭 핸들러 안에서. 거부는 에러가 아니라 하나의 결과라
      // 별도 상태로 구분한다(Figma "2.4-b 알림 권한 거부" 화면이 이걸 본다).
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setStatus("denied");
        setMessage(null);
        return false;
      }

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

      // 같은 endpoint로 다시 보내도 서버가 upsert하므로 "이미 구독됨" 분기가 필요 없다.
      await subscribePush({
        endpoint: json.endpoint,
        keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
        leave_time: leaveTime,
        skip_weekends: skipWeekends,
      });

      try {
        localStorage.setItem(LEAVE_TIME_STORAGE_KEY, leaveTime);
        localStorage.setItem(SKIP_WEEKENDS_STORAGE_KEY, skipWeekends ? "1" : "0");
      } catch {
        // 구독 자체는 이미 성공했으니 무시하고 진행.
      }

      setSubscription(sub);
      setStatus("subscribed");
      setMessage("퇴근 15분 전 알림이 설정됐어요. 탭을 닫아도 알림이 옵니다.");
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setStatus("unavailable");
        setMessage("서버에 웹 푸시가 아직 설정되어 있지 않습니다 (VAPID_PUBLIC_KEY).");
        return false;
      }
      setStatus("error");
      setMessage("알림 설정에 실패했어요. 잠시 후 다시 시도해 주세요.");
      return false;
    }
  }, [leaveTime, skipWeekends]);

  const unsubscribe = useCallback(async () => {
    if (!subscription) return;
    try {
      await unsubscribePush(subscription.endpoint);
    } catch {
      // 서버는 없는 구독을 지워도 204(멱등) — 실패해도 로컬 해제는 계속 진행.
    }
    try {
      await subscription.unsubscribe();
    } finally {
      setSubscription(null);
      setStatus("idle");
      setMessage("알림을 껐습니다.");
    }
  }, [subscription]);

  return {
    status,
    message,
    leaveTime,
    setLeaveTime,
    skipWeekends,
    setSkipWeekends,
    subscribe,
    unsubscribe,
  };
}
