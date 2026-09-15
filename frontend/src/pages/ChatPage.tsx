import type { UIMessage } from "ai"
import { AlertCircle } from "lucide-react"
import { useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"

import { ChatSession } from "@/components/chat/ChatSession"
import { ThreadSidebar } from "@/components/chat/ThreadSidebar"
import { EmptyState } from "@/components/EmptyState"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { citationsByMessageId, toUiMessage } from "@/chat/messages"
import { ThreadsProvider } from "@/chat/ThreadsProvider"
import { api } from "@/lib/api"
import type { Citation } from "@/lib/api"
import type { ApiError } from "@/lib/http"

export function ChatPage() {
  const { threadId } = useParams<{ threadId: string }>()
  const navigate = useNavigate()
  const [initialMessages, setInitialMessages] = useState<UIMessage[] | null>(null)
  const [initialCitations, setInitialCitations] = useState<Record<string, Citation[]>>({})
  const [loading, setLoading] = useState(Boolean(threadId))
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!threadId) {
      setLoading(false)
      setInitialMessages(null)
      setInitialCitations({})
      return
    }

    setLoading(true)
    setError(null)
    void api
      .getMessages(threadId)
      .then((messages) => {
        setInitialMessages(messages.map(toUiMessage))
        setInitialCitations(citationsByMessageId(messages))
      })
      .catch((requestError: unknown) => setError((requestError as ApiError).message))
      .finally(() => setLoading(false))
  }, [threadId])

  return (
    <ThreadsProvider>
      <SidebarProvider>
        <ThreadSidebar />
        <SidebarInset>
          <header className="flex items-center gap-2 border-b border-border px-3 py-2 md:hidden">
            <SidebarTrigger />
            <img src="/logo.jpg" alt="Document Copilot logo" className="h-6 w-6 shrink-0 rounded-full object-cover" />
            <p className="text-sm font-medium text-foreground">Document Copilot</p>
          </header>

          <div className="flex min-h-0 flex-1 flex-col">
            {!threadId ? (
              <EmptyState
                title="Start a conversation"
                description="Choose an existing thread from the sidebar or create a new chat to ask questions about SEC filings."
              />
            ) : loading ? (
              <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-4 py-8 sm:px-6">
                <Skeleton className="h-16 w-2/3" />
                <Skeleton className="ml-auto h-10 w-1/2" />
                <Skeleton className="h-24 w-3/4" />
              </div>
            ) : error ? (
              <EmptyState
                icon={AlertCircle}
                title="Couldn't load this conversation"
                description={error}
                action={<Button onClick={() => navigate("/app")}>Back to conversations</Button>}
              />
            ) : (
              <ChatSession
                key={threadId}
                threadId={threadId}
                initialMessages={initialMessages ?? []}
                initialCitations={initialCitations}
              />
            )}
          </div>
        </SidebarInset>
      </SidebarProvider>
    </ThreadsProvider>
  )
}
