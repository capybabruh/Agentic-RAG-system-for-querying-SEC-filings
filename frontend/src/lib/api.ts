import type { User } from "@supabase/supabase-js"

import { http } from "@/lib/http"

export type HealthResponse = {
  status: string
  service: string
}

export type CurrentUserResponse = {
  user: User
}

export type ChatThread = {
  id: string
  title: string | null
  status: string
  created_at: string
  updated_at: string
}

export type Citation = {
  id: string
  chunk_id: string | null
  quote_text: string
  page_number: number | null
  section_label: string | null
  ticker: string | null
  filing_type: string | null
  filing_date: string | null
  document_title: string | null
  source_url: string | null
}

export type ChatMessage = {
  id: string
  thread_id: string
  sender: "user" | "assistant"
  content: string
  message_metadata: Record<string, unknown> | null
  created_at: string
  citations: Citation[]
}

export const api = {
  createThread: (title?: string) =>
    http.post<ChatThread>("/chat/threads", { title: title ?? null }),
  deleteThread: (threadId: string) =>
    http.delete<void>(`/chat/threads/${threadId}`),
  getCurrentUser: () => http.get<CurrentUserResponse>("/me"),
  getHealth: () => http.get<HealthResponse>("/health"),
  getMessages: (threadId: string) =>
    http.get<ChatMessage[]>(`/chat/threads/${threadId}/messages`),
  listThreads: () => http.get<ChatThread[]>("/chat/threads"),
}

export type ApiUser = User
