import type { Metadata } from "next";
import "@fontsource-variable/figtree";
import "@fontsource-variable/noto-sans";
import "./globals.css";

export const metadata: Metadata = {
  title: "RadAssist 3D — Imaging Workstation",
  description:
    "Research-oriented 3D CT segmentation, MPR visualization, volumetrics, and surface analytics.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
