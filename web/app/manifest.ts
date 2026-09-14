import type { MetadataRoute } from "next";

/**
 * PWA manifest — Next.js App Router 관례(`app/manifest.ts`)로 생성한다
 * (`docs/06-migration.md` §1·§4). `src/frontend/static/manifest.json`(Streamlit용,
 * "신입사원 온보딩 다이어리")의 모양을 기반으로 하되, 이름을 CLAUDE.md의 현재
 * 제품명("커리어 로그")으로 갱신했다 — 이 파일만 최소로 정리한 것이고, 나머지
 * 제품명 문자열(README 등) 정리는 CLAUDE.md 우선순위상 9/18로 미뤄도 된다.
 *
 * 아이콘은 실제 디자인 에셋이 없어 `public/icon.svg` 플레이스홀더를 쓴다 —
 * 디자이너 확정 시 PNG로 교체할 것.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "커리어 로그",
    short_name: "커리어로그",
    description: "퇴근 전 한 줄 메모를 이직 시 경력기술서로 바꿔주는 서비스",
    start_url: "/",
    display: "standalone",
    background_color: "#fafafa",
    theme_color: "#18181b",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
      },
    ],
  };
}
