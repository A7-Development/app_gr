import type { Metadata } from "next"
import { ThemeProvider } from "next-themes"
import { Toaster } from "sonner"
import { inter } from "@/lib/fonts"
import { QueryProvider } from "@/lib/QueryProvider"
import "./globals.css"

export const metadata: Metadata = {
  title: "Strata",
  description: "Inteligencia de dados para FIDCs",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="pt-BR"
      className={`${inter.variable} ${inter.className} antialiased bg-gray-50 dark:bg-gray-950`}
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
