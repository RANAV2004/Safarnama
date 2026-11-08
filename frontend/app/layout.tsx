// layout
import type { Metadata, Viewport } from "next";
import "@fontsource/mukta/400.css";
import "@fontsource/mukta/500.css";
import "@fontsource/mukta/700.css";
import "@fontsource/yatra-one/400.css";
import InstallApp from "@/components/InstallApp";
import "./globals.css";

export const metadata: Metadata = {
  title: "Safarnama",
  description: "Plan a trip with a team of AI agents.",
  applicationName: "Safarnama",
  appleWebApp: { capable: true, title: "Safarnama", statusBarStyle: "default" },
  icons: { icon: "/icons/icon-192.png", apple: "/icons/apple-touch-icon.png" },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  themeColor: "#c2185b",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <InstallApp />
      </body>
    </html>
  );
}
