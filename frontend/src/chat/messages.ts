import type { UIMessage } from "ai"

import type { ChatMessage, Citation } from "@/lib/api"

export function toUiMessage(message: ChatMessage): UIMessage {
  return {
    id: message.id,
    role: message.sender,
    metadata: message.message_metadata ?? undefined,
    parts: [{ type: "text", text: message.content }],
  }
}

export function citationsByMessageId(messages: ChatMessage[]): Record<string, Citation[]> {
  const result: Record<string, Citation[]> = {}
  for (const message of messages) {
    if (message.citations.length > 0) {
      result[message.id] = message.citations
    }
  }
  return result
}

export function hasSufficientEvidence(message: UIMessage): boolean | null {
  const metadata = message.metadata as { has_sufficient_evidence?: unknown } | undefined
  return typeof metadata?.has_sufficient_evidence === "boolean" ? metadata.has_sufficient_evidence : null
}
