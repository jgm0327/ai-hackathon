/**
 * 웹 푸시 구독 관련 작은 유틸리티.
 *
 * `PushManager.subscribe()`의 `applicationServerKey`는 `Uint8Array`를 요구하는데,
 * 서버(`GET /api/push/vapid-public-key`, `docs/05-api-contract.md` §7)는 VAPID 공개키를
 * base64url 문자열로 내려준다. 표준 `atob()`는 base64url(`-`, `_`, 패딩 없음)을 그대로
 * 못 읽으므로 변환이 필요하다 — 잘 알려진 방식(MDN 웹푸시 예제와 동일)을 그대로 옮김.
 */
export function urlBase64ToUint8Array(base64Url: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
  const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");

  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}
