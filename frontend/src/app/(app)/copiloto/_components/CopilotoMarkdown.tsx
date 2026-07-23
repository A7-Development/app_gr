"use client"

/**
 * Render markdown das respostas do Strata AI na pagina /copiloto.
 * Derivado do ChatBubble interno do AIPanel (nao exportado), redimensionado
 * para leitura em pagina (text-sm) mantendo o tom violeta de IA do DS.
 */

import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

export function CopilotoMarkdown({ text }: { text: string }) {
  return (
    <div className="ai-markdown text-sm leading-relaxed text-gray-900 dark:text-gray-100">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          ul: ({ children }) => (
            <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>
          ),
          li: ({ children }) => <li>{children}</li>,
          code: ({ children, className }) => {
            const isBlock = className?.includes("language-")
            return isBlock ? (
              <code className="block overflow-x-auto rounded bg-gray-900 p-3 font-mono text-xs text-gray-100 dark:bg-gray-800">
                {children}
              </code>
            ) : (
              <code className="rounded bg-gray-100 px-1 font-mono text-xs dark:bg-gray-800">
                {children}
              </code>
            )
          },
          pre: ({ children }) => <div className="mb-2 last:mb-0">{children}</div>,
          table: ({ children }) => (
            <div className="mb-2 overflow-x-auto last:mb-0">
              <table className="min-w-full text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-violet-200 px-2 py-1.5 text-left font-semibold dark:border-violet-700/40">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-violet-100 px-2 py-1.5 dark:border-violet-700/20">
              {children}
            </td>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-gray-900 dark:text-gray-50">
              {children}
            </strong>
          ),
          a: ({ children, href }) => (
            <a
              href={href}
              className="text-violet-600 underline dark:text-violet-400"
              target="_blank"
              rel="noreferrer"
            >
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}
