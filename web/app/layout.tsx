import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
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
      <body className="min-h-full flex flex-col bg-[#f1f1f3] text-[#18181b]">
        <ServiceWorkerRegistration />
        <div className="mx-auto flex w-full max-w-md flex-1 flex-col">
          <main className="flex-1 pb-6">{children}</main>
          <TabBar />
        </div>
      </body>
    </html>
  );
}
