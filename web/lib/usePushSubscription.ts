"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  getPushSettings,
  getVapidPublicKey,
  subscribePush,
  unsubscribePush,
  updatePushSettings,
  type PushSettings,
} from "./api";
import { urlBase64ToUint8Array } from "./push";

/**
 * 퇴근 15분 전 웹 푸시 — Tier 2 (`docs/06-migration.md` §1).
 *
 * 9/18에 `components/PushSetup.tsx`에서 로직만 뽑아낸 훅이고, 9/23에 **상태의 출처를
 * localStorage에서 서버로 옮겼다.**
 *
 * **왜 옮겼나 (9/23, 사용자 신고)**: 설정 화면이 "꺼짐"인데 알림이 계속 왔다. 표시는
 * `localStorage["careerlog:leaveTime"]` 하나만 보고 있었고 — 서버에 되읽는 GET 자체가
 * 없었다 — 실제 발송은 서버 구독이 정했다. 둘이 서로를 전혀 참조하지 않으니 로그아웃이
 * localStorage만 비우는 순간(`lib/signOut.ts`가 `careerlog:` 키를 지운다) 표시와 실제가
 * 갈라졌다. 게다가 끄기를 호출하는 화면이 하나도 없어서 구독은 영영 남았다.
 *
 * **두 층으로 나눠 읽는다**:
 *   - **계정 단위**(`enabled` / `leaveTime` / `skipWeekends`) — 서버가 진실. 기기를
 *     바꿔도 따라온다.
 *   - **이 기기**(`thisDevice`) — 브라우저의 `PushManager.getSubscription()`이 진실.
 *     웹푸시 구독은 브라우저가 발급하고 그 브라우저로만 배달되므로 서버는 알 수 없다.
 *
 * 지켜야 하는 것(예전 컴포넌트 주석에서 그대로 옮김):
 *   - 권한 요청/구독은 **반드시 사용자 클릭 핸들러 안에서** 시작한다. 자동으로 하면
 *     최신 브라우저가 "사용자 제스처 없음"으로 판단해 조용히 막는다.
 */

export type PushStatus =
  | "loading"
  | "idle"
  | "subscribing"
  | "subscribed"
  | "denied"
  | "unavailable"
  | "error";

export interface PushSubscriptionState {
  status: PushStatus;
  message: string | null;
  /** 계정 기준으로 알림이 켜져 있는가(기기 무관). */
  enabled: boolean;
  /** 이 계정에 등록된 기기 수. */
  deviceCount: number;
  /** 지금 보고 있는 이 브라우저가 구독 중인가. */
  thisDevice: boolean;
  leaveTime: string;
  setLeaveTime: (value: string) => void;
  skipWeekends: boolean;
  setSkipWeekends: (value: boolean) => void;
  /** 켜기 — 권한 요청이 필요하므로 **클릭 핸들러 안에서** 부를 것. 성공하면 true. */
  subscribe: () => Promise<boolean>;
  /** 이미 켜져 있으면 값만 저장하고, 아니면 켠다. 저장 버튼이 쓰는 경로. */
  save: () => Promise<boolean>;
  /** 끄기 — 이 계정의 모든 기기. */
  unsubscribe: () => Promise<void>;
}

/** 서비스워커에 지금 살아 있는 구독이 있으면 돌려준다. 없거나 조회 실패면 null. */
async function currentBrowserSubscription(): Promise<PushSubscription | null> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator)) return null;
  try {
    const registration = await navigator.serviceWorker.getRegistration("/service-worker.js");
    return (await registration?.pushManager.getSubscription()) ?? null;
  } catch {
    return null;
  }
}

export function usePushSubscription(): PushSubscriptionState {
  const [settings, setSettings] = useState<PushSettings | null>(null);
  const [leaveTime, setLeaveTime] = useState("18:00");
  const [skipWeekends, setSkipWeekends] = useState(true); // Figma 4/4는 켜진 상태가 기본
  const [thisDevice, setThisDevice] = useState(false);
  const [status, setStatus] = useState<PushStatus>("loading");
  const [message, setMessage] = useState<string | null>(null);

  const applySettings = useCallback((next: PushSettings) => {
    setSettings(next);
    setLeaveTime(next.leave_time);
    setSkipWeekends(next.skip_weekends);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [loaded, browserSub] = await Promise.all([
        getPushSettings().catch(() => null),
        currentBrowserSubscription(),
      ]);
      if (cancelled) return;
      if (loaded) applySettings(loaded);
      setThisDevice(Boolean(browserSub));
      // 권한을 이미 거부해 둔 기기는 "켜기"를 눌러도 프롬프트가 안 뜨므로 먼저 알린다.
      const denied =
        typeof Notification !== "undefined" && Notification.permission === "denied";
      setStatus(denied ? "denied" : loaded?.enabled ? "subscribed" : "idle");
    })();
    return () => {
      cancelled = true;
    };
  }, [applySettings]);

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
      applySettings(
        await subscribePush({
          endpoint: json.endpoint,
          keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
          leave_time: leaveTime,
          skip_weekends: skipWeekends,
        }),
      );

      setThisDevice(true);
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
  }, [applySettings, leaveTime, skipWeekends]);

  const save = useCallback(async (): Promise<boolean> => {
    // 이 기기가 이미 구독 중이면 권한 요청 없이 값만 보낸다. 그전엔 이 경로가 없어서
    // **이미 켜진 사람이 시각을 바꿔도 서버에 아무것도 가지 않았다**(9/23 수정).
    if (settings?.enabled && thisDevice) {
      try {
        applySettings(await updatePushSettings({ leave_time: leaveTime, skip_weekends: skipWeekends }));
        setStatus("subscribed");
        setMessage(null);
        return true;
      } catch {
        setStatus("error");
        setMessage("알림 설정 저장에 실패했어요. 잠시 후 다시 시도해 주세요.");
        return false;
      }
    }
    return subscribe();
  }, [applySettings, leaveTime, settings?.enabled, skipWeekends, subscribe, thisDevice]);

  const unsubscribe = useCallback(async () => {
    try {
      // 서버가 먼저다 — 발송을 정하는 건 서버 쪽 구독이고, 브라우저 구독만 지우면
      // 계정에 남은 다른 기기로 계속 간다.
      applySettings(await unsubscribePush());
    } catch {
      setStatus("error");
      setMessage("알림을 끄지 못했어요. 잠시 후 다시 시도해 주세요.");
      return;
    }
    // 브라우저 쪽 구독도 정리한다. 실패해도(이미 없음 등) 서버에 행이 없으므로 알림은
    // 오지 않는다 — 여기서 막히면 안 된다.
    try {
      const browserSub = await currentBrowserSubscription();
      await browserSub?.unsubscribe();
    } catch {
      /* 무시 */
    }
    setThisDevice(false);
    setStatus("idle");
    setMessage("알림을 껐습니다.");
  }, [applySettings]);

  return {
    status,
    message,
    enabled: settings?.enabled ?? false,
    deviceCount: settings?.device_count ?? 0,
    thisDevice,
    leaveTime,
    setLeaveTime,
    skipWeekends,
    setSkipWeekends,
    subscribe,
    save,
    unsubscribe,
  };
}
