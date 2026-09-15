import { createContext, useCallback, useContext, useEffect, useState } from "react"

import { api, type ChatThread } from "@/lib/api"
import type { ApiError } from "@/lib/http"

type ThreadsContextValue = {
  threads: ChatThread[]
  loading: boolean
  error: string | null
  createThread: () => Promise<ChatThread>
  deleteThread: (threadId: string) => Promise<void>
  setThreadTitle: (threadId: string, title: string) => void
}

const ThreadsContext = createContext<ThreadsContextValue | undefined>(undefined)

export function ThreadsProvider({ children }: { children: React.ReactNode }) {
  const [threads, setThreads] = useState<ChatThread[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void api
      .listThreads()
      .then(setThreads)
      .catch((requestError: unknown) => setError((requestError as ApiError).message))
      .finally(() => setLoading(false))
  }, [])

  const createThread = useCallback(async (): Promise<ChatThread> => {
    const thread = await api.createThread()
    setThreads((current) => [thread, ...current])
    return thread
  }, [])

  const deleteThread = useCallback(async (threadId: string): Promise<void> => {
    await api.deleteThread(threadId)
    setThreads((current) => current.filter((thread) => thread.id !== threadId))
  }, [])

  // Called once the backend derives a title from a thread's first message (delivered
  // over the chat stream as a `thread_title` event — see transport.ts) so the sidebar
  // reflects it immediately instead of waiting for the next full threads refetch.
  const setThreadTitle = useCallback((threadId: string, title: string) => {
    setThreads((current) =>
      current.map((thread) => (thread.id === threadId ? { ...thread, title } : thread)),
    )
  }, [])

  const value: ThreadsContextValue = {
    threads,
    loading,
    error,
    createThread,
    deleteThread,
    setThreadTitle,
  }

  return <ThreadsContext.Provider value={value}>{children}</ThreadsContext.Provider>
}

export function useThreads() {
  const context = useContext(ThreadsContext)
  if (!context) {
    throw new Error("useThreads must be used inside ThreadsProvider")
  }

  return context
}
