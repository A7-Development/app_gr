import type { Metadata } from "next"
import { GeistSans } from "geist/font/sans"
import { ThemeProvider } from "next-themes"
import { Toaster } from "sonner"
import { QueryProvider } from "@/lib/QueryProvider"
import "./globals.css"

export const metadata: Metadata = {
  title: "A7 Credit",
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
      className={`${GeistSans.className} antialiased bg-gray-50 dark:bg-gray-950`}
      suppressHydrationWarning
    >
      <body>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <QueryProvider>{children}</QueryProvider>
          <Toaster position="bottom-right" richColors closeButton />
        </ThemeProvider>
      </body>
    </html>
  )
}
