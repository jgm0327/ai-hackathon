import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AppIntro } from "@/components/AppIntro";
import { AuthGate } from "@/components/AuthGate";
import { ServiceWorkerRegistration } from "@/components/ServiceWorkerRegistration";
import { TabBar } from "@/components/TabBar";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "커리어 로그",
  description: "퇴근 전 한 줄 메모를 이직 시 경력기술서로 바꿔주는 서비스",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="ko"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      {/* 배경/글자색은 globals.css의 body{} 규칙(레이어 밖 — Tailwind 유틸리티보다
          우선)이 실제로 적용하는 색이다. 여기 className에 배경/글자색 클래스를 다시
          줘도 무시되므로(9/16 실측) 레이아웃 관련 클래스만 둔다. */}
      <body className="min-h-full flex flex-col">
        {/* 앱을 열 때마다 도는 스플래시 인트로 (9/19) — 문서가 새로 뜰 때 한 번만
            마운트되므로 탭 이동으로는 다시 돌지 않는다. `/login`에서는 그 화면이
            같은 장면을 직접 재생하므로 뜨지 않는다. */}
        <AppIntro />
        <AuthGate />
        <ServiceWorkerRegistration />
        <div className="mx-auto flex w-full max-w-md flex-1 flex-col">
          {/* 9/19 — `flex flex-col`이 붙어 있어야 페이지 루트가 `flex-1`로 남은
              높이를 채운다. 예전엔 페이지들이 `min-h-full`(= height 100%)로 채웠는데,
              퍼센트 높이는 부모 높이가 확정돼야 풀린다. iOS Safari는 flex-basis로
              정해진 높이를 그 "확정된 높이"로 안 쳐주는 경우가 있어서 100%가 0으로
              풀렸고, 그러면 화면 위쪽에 body 배경이 그대로 드러난다(아이폰에서만
              상단에 빈 칸이 보인다는 신고, 9/19). flex로 채우면 그 계산이 사라진다. */}
          <main className="flex flex-1 flex-col pb-6">{children}</main>
          <TabBar />
        </div>
      </body>
    </html>
  );
}
