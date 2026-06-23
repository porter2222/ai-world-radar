import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppHeader } from "../components/AppHeader";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI World Radar",
  description: "面向中文用户的全球 AI 事件雷达"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="app">
          <AppHeader />
          {children}
        </div>
      </body>
    </html>
  );
}
