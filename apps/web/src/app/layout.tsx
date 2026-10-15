import type { Metadata } from "next";
import "./globals.css";
import { StudioProvider } from "../components/studio";

export const metadata: Metadata = {
  title: "BIA Agent Studio",
  description: "Configuración y catálogos de BIA Agent Studio",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>
        <StudioProvider>{children}</StudioProvider>
      </body>
    </html>
  );
}
