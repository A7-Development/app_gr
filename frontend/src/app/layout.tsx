import type { Metadata } from "next"
import { GeistSans } from "geist/font/sans"
import "./globals.css"

export const metadata: Metadata = {
  title: "App GR",
  description: "Sistema de controladoria financeira",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="pt-BR"
      className={`${GeistSans.className} antialiased dark:bg-gray-950`}
    >
      <body>{children}</body>
    </html>
  )
}
