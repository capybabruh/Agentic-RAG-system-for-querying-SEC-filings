import { useChat } from "@ai-sdk/react"
import type { UIMessage } from "ai"
import { ArrowUp, Square } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { MessageList } from "@/components/chat/MessageList"
import { TypingIndicator } from "@/components/chat/TypingIndicator"
import { citationsByMessageId, toUiMessage } from "@/chat/messages"
import { FastApiChatTransport } from "@/chat/transport"
import { useThreads } from "@/chat/ThreadsProvider"
import { api, type Citation } from "@/lib/api"

const DEFAULT_STREAMING_LABEL = "Assistant is responding..."

function formatSeconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`
}

export function ChatSession({
  threadId,
  initialMessages,
  initialCitations,
}: {
  threadId: string
  initialMessages: UIMessage[]
  initialCitations: Record<string, Citation[]>
}) {
  const [input, setInput] = useState("")
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [citations, setCitations] = useState<Record<string, Citation[]>>(initialCitations)
  const [elapsedMs, setElapsedMs] = useState<number | null>(null)
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null)
  const startedAtRef = useRef<number | null>(null)
  const endOfMessages = useRef<HTMLDivElement>(null)
  const { setThreadTitle } = useThreads()

  const transport = useMemo(
    () =>
      new FastApiChatTransport(threadId, {
        onStatus: (_stage, message) => setStatusMessage(message),
        onThreadTitle: (title) => setThreadTitle(threadId, title),
      }),
    [threadId, setThreadTitle],
  )

  const { messages, setMessages, sendMessage, status, error, stop } = useChat({
    id: threadId,
    messages: initialMessages,
    transport,
    // The typing effect can deliver many small text-delta chunks in quick succession
    // for a long answer; without throttling, each one triggers a full React re-render
    // (and, via MessageList, a full markdown re-parse of the accumulated text) —
    // for a long multi-company answer that's enough renders in a few seconds to
    // visibly lag or freeze the tab. Batches updates instead of rendering every delta.
    throttle: 50,
    onFinish: ({ isAbort, isError }) => {
      setStatusMessage(null)
      setElapsedMs(null)
      // Only record a latency reading for a turn that actually produced an answer —
      // an aborted (Stop clicked) or errored turn didn't "respond," so timing it would
      // be measuring the wrong thing.
      if (!isAbort && !isError && startedAtRef.current !== null) {
        setLastLatencyMs(performance.now() - startedAtRef.current)
      }
      startedAtRef.current = null
      // Refetches the persisted, citation-enriched version of this turn. If this fails,
      // the already-streamed text stays visible (we just skip the replacement) rather
      // than silently leaving the user with nothing — log it so it's diagnosable.
      void api
        .getMessages(threadId)
        .then((persisted) => {
          setMessages(persisted.map(toUiMessage))
          setCitations(citationsByMessageId(persisted))
        })
        .catch((requestError: unknown) => {
          console.error("Failed to refresh messages after a chat turn:", requestError)
        })
    },
  })
  const isStreaming = status === "submitted" || status === "streaming"

  useEffect(() => {
    endOfMessages.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  useEffect(() => {
    if (!isStreaming) return
    const interval = setInterval(() => {
      if (startedAtRef.current !== null) {
        setElapsedMs(performance.now() - startedAtRef.current)
      }
    }, 100)
    return () => clearInterval(interval)
  }, [isStreaming])

  const displayedStatus = isStreaming
    ? (statusMessage ?? DEFAULT_STREAMING_LABEL)
    : lastLatencyMs !== null
      ? `Answered in ${formatSeconds(lastLatencyMs)}`
      : null

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const text = input.trim()
    if (!text || isStreaming) return
    setInput("")
    setStatusMessage("Sending your question...")
    setLastLatencyMs(null)
    startedAtRef.current = performance.now()
    setElapsedMs(0)
    await sendMessage({ text })
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col bg-background">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <MessageList messages={messages} citations={citations} />
        <div ref={endOfMessages} />
      </div>

      {error && (
        <p role="alert" className="mx-auto mb-3 w-full max-w-3xl px-4 text-sm text-destructive sm:px-6">
          {error.message}
        </p>
      )}

      <div className="border-t border-border bg-background p-4 sm:p-6">
        <form onSubmit={handleSubmit} className="mx-auto flex max-w-3xl items-end gap-3">
          <label className="sr-only" htmlFor="chat-input">Ask a question</label>
          <textarea
            id="chat-input"
            rows={1}
            value={input}
            disabled={isStreaming}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault()
                event.currentTarget.form?.requestSubmit()
              }
            }}
            placeholder="Ask a question about the filings..."
            className="min-h-11 flex-1 resize-none rounded-xl border border-border bg-card px-4 py-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-ring"
          />
          {isStreaming ? (
            <Button type="button" size="icon" variant="outline" onClick={stop} title="Stop response">
              <Square aria-hidden="true" className="fill-current" />
              <span className="sr-only">Stop response</span>
            </Button>
          ) : (
            <Button type="submit" size="icon" disabled={!input.trim()} title="Send message">
              <ArrowUp aria-hidden="true" />
              <span className="sr-only">Send message</span>
            </Button>
          )}
        </form>
        <p className="mx-auto mt-3 flex max-w-3xl items-center justify-center gap-2 text-center text-xs text-muted-foreground">
          {isStreaming && <TypingIndicator />}
          <span className={isStreaming ? "text-info" : undefined}>
            {displayedStatus ?? "Ask about the ingested SEC filing corpus"}
          </span>
          {isStreaming && elapsedMs !== null && (
            <span className="tabular-nums text-info">· {formatSeconds(elapsedMs)}</span>
          )}
        </p>
      </div>
    </section>
  )
}
