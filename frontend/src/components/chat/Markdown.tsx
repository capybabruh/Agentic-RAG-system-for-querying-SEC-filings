import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"

const components: Components = {
  p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
  h1: ({ children }) => <h1 className="mt-4 mb-2 text-base font-semibold first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="mt-4 mb-2 text-base font-semibold first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mt-4 mb-2 text-sm font-semibold first:mt-0">{children}</h3>,
  ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="leading-6">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="font-medium text-citation underline underline-offset-2 hover:text-citation/80"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-2 border-border pl-3 text-muted-foreground italic last:mb-0">
      {children}
    </blockquote>
  ),
  code: ({ children }) => (
    <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
  ),
  pre: ({ children }) => (
    <pre className="mb-3 overflow-x-auto rounded-lg bg-muted p-3 font-mono text-[0.85em] last:mb-0">{children}</pre>
  ),
  hr: () => <hr className="my-4 border-border" />,
  table: ({ children }) => (
    <div className="mb-3 overflow-x-auto last:mb-0">
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border-b border-border py-1.5 pr-3 font-medium">{children}</th>,
  td: ({ children }) => <td className="border-b border-border py-1.5 pr-3 align-top">{children}</td>,
}

export function Markdown({ children }: { children: string }) {
  return (
    <div className="text-sm leading-6">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  )
}
