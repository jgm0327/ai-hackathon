/**
 * 업로드 전 사진 줄이기 — Figma "03 · 커리어 스택" 4.1-b "첨부한 사진" (9/18 신규).
 *
 * **왜 클라이언트에서 줄이는가**: 서버에 Pillow를 올리면 배포 이미지가 커지고, OCI
 * AMD Micro(RAM 1GB)에서 FastAPI + Chroma와 메모리를 다퉈야 한다
 * (`tasks/track-d-deploy.md` 2장). 브라우저 canvas는 공짜고, 덤으로 **업로드 자체가
 * 빨라진다** — 자차 이동 중 모바일 회선으로 올리는 게 사용 맥락이라(CLAUDE.md 1장)
 * 4MB 원본을 그대로 보내면 체감이 나쁘다.
 *
 * 줄이지 못하면(디코딩 실패, canvas 미지원 등) **원본을 그대로 돌려준다.** 사진을
 * 붙이는 것 자체가 실패하는 것보다 큰 파일을 올리는 게 낫다 — 서버가 8MB에서
 * 걸러 주므로 최악의 경우에도 안전하게 실패한다.
 */

/** 긴 변 기준 최대 픽셀. 390px 폭 화면의 168px 썸네일과 전체화면 보기에 충분하다. */
const MAX_EDGE = 1600;
const JPEG_QUALITY = 0.82;

export interface ResizedImage {
  blob: Blob;
  filename: string;
}

/**
 * 이미지 파일을 긴 변 `MAX_EDGE` 이하의 JPEG로 줄인다.
 *
 * 이미 충분히 작으면 원본을 그대로 쓴다 — 다시 인코딩하면 화질만 손해다.
 * GIF는 건드리지 않는다(캔버스로 그리면 애니메이션이 첫 프레임만 남는다).
 */
export async function resizeImageForUpload(file: File): Promise<ResizedImage> {
  const fallback: ResizedImage = { blob: file, filename: file.name || "photo" };
  if (file.type === "image/gif") return fallback;

  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    return fallback;
  }

  try {
    const longEdge = Math.max(bitmap.width, bitmap.height);
    if (longEdge <= MAX_EDGE) return fallback;

    const scale = MAX_EDGE / longEdge;
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return fallback;
    ctx.drawImage(bitmap, 0, 0, width, height);

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
    );
    if (!blob) return fallback;

    // 확장자도 실제 포맷(JPEG)에 맞춰 바꾼다 — 서버가 확장자를 저장 파일명에 쓴다.
    const base = (file.name || "photo").replace(/\.[^.]+$/, "");
    return { blob, filename: `${base}.jpg` };
  } finally {
    // 비트맵은 GC를 기다리지 않고 바로 해제한다 — 여러 장을 연속으로 올릴 때
    // 원본 디코딩 버퍼가 쌓이면 모바일에서 탭이 죽는다.
    bitmap.close();
  }
}
