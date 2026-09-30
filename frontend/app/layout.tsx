import type { Metadata } from "next";
import "@fontsource-variable/figtree";
import "@fontsource-variable/noto-sans";
import "./globals.css";

export const metadata: Metadata = {
  title: "RadAssist 3D — AI-Assisted Quantitative Medical Imaging",
  description:
    "AI-assisted medical imaging research workstation for CT and MRI segmentation, MPR, 3D reconstruction, quantitative QA, provenance, and research export.",
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
