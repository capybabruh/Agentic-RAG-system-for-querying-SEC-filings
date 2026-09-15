import type { UIMessage } from "ai"
import { MessagesSquare } from "lucide-react"

import { Citations } from "@/components/chat/Citations"
import { Markdown } from "@/components/chat/Markdown"
import { EmptyState } from "@/components/EmptyState"
import { hasSufficientEvidence } from "@/chat/messages"
import type { Citation } from "@/lib/api"

export function MessageList({
  messages,
  citations,
}: {
  messages: UIMessage[]
  citations: Record<string, Citation[]>
}) {
  if (messages.length === 0) {
    return (
      <EmptyState
        icon={MessagesSquare}
        title="Ask about the filing corpus"
        description="Ask a question about any ingested SEC filing to get a cited answer."
      />
    )
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-8 sm:px-6">
      {messages.map((message) => {
        const messageCitations = citations[message.id] ?? []
        const sufficientEvidence = message.role === "assistant" ? hasSufficientEvidence(message) : null

        return (
          <article
            key={message.id}
            className={`flex flex-col gap-1.5 ${message.role === "user" ? "items-end" : "items-start"}`}
          >
            {sufficientEvidence === false && (
              <span className="rounded-full bg-info/10 px-2.5 py-0.5 text-xs font-medium text-info">
                Limited evidence found in the corpus
              </span>
            )}
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6 ${message.role === "user" ? "bg-muted text-foreground" : "border border-border bg-card text-foreground"}`}
            >
              <p className="mb-1 text-xs font-medium text-muted-foreground">
                {message.role === "user" ? "You" : "Assistant"}
              </p>
              {message.parts.map((part, index) => {
                if (part.type !== "text") return null
                return message.role === "assistant" ? (
                  <Markdown key={`${message.id}-${index}`}>{part.text}</Markdown>
                ) : (
                  <span key={`${message.id}-${index}`}>{part.text}</span>
                )
              })}
              {message.role === "assistant" && <Citations citations={messageCitations} />}
            </div>
          </article>
        )
      })}
    </div>
  )
}
