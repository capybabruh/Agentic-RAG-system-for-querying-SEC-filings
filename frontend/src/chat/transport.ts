import type { ChatTransport, UIMessage, UIMessageChunk } from "ai"

import { http } from "@/lib/http"

type StreamPayload = {
  threadId: string
  messages: BackendMessage[]
}

type BackendMessage = {
  id: string
  role: UIMessage["role"]
  parts: { type: "text"; text: string }[]
}

function toBackendMessage(message: UIMessage): BackendMessage {
  return {
    id: message.id,
    role: message.role,
    parts: message.parts
      .filter((part) => part.type === "text")
      .map((part) => ({ type: "text", text: part.text })),
  }
}

export type StatusCallback = (stage: string, message: string) => void
export type ThreadTitleCallback = (title: string) => void

export class FastApiChatTransport implements ChatTransport<UIMessage> {
  private readonly threadId: string
  private readonly onStatus?: StatusCallback
  private readonly onThreadTitle?: ThreadTitleCallback

  constructor(
    threadId: string,
    options: { onStatus?: StatusCallback; onThreadTitle?: ThreadTitleCallback } = {},
  ) {
    this.threadId = threadId
    this.onStatus = options.onStatus
    this.onThreadTitle = options.onThreadTitle
  }

  async sendMessages({
    messages,
    abortSignal,
  }: Parameters<ChatTransport<UIMessage>["sendMessages"]>[0]): Promise<ReadableStream<UIMessageChunk>> {
    const response = await http.stream(
      "/chat/stream",
      {
        threadId: this.threadId,
        messages: messages.map(toBackendMessage),
      } satisfies StreamPayload,
      abortSignal,
    )
    if (!response.body) {
      throw new Error("The backend returned an empty stream")
    }

    return parseBackendStream(response.body, this.onStatus, this.onThreadTitle)
  }

  async reconnectToStream(): Promise<ReadableStream<UIMessageChunk> | null> {
    return null
  }
}

function parseBackendStream(
  body: ReadableStream<Uint8Array>,
  onStatus?: StatusCallback,
  onThreadTitle?: ThreadTitleCallback,
): ReadableStream<UIMessageChunk> {
  const decoder = new TextDecoder()
  const messageId = `assistant-${crypto.randomUUID()}`
  let buffer = ""
  let started = false
  let finished = false

  function finish(controller: TransformStreamDefaultController<UIMessageChunk>) {
    if (started) {
      controller.enqueue({ type: "text-end", id: messageId })
    }
    controller.enqueue({ type: "finish" })
    finished = true
  }

  function consumeEvent(event: string, controller: TransformStreamDefaultController<UIMessageChunk>) {
    const eventName = event.match(/^event: (.+)$/m)?.[1]
    const data = event.match(/^data: (.+)$/m)?.[1]
    if (!eventName || !data) return

    if (eventName === "status") {
      const payload = JSON.parse(data) as { stage: string; message: string }
      onStatus?.(payload.stage, payload.message)
    } else if (eventName === "thread_title") {
      const payload = JSON.parse(data) as { title: string }
      onThreadTitle?.(payload.title)
    } else if (eventName === "text_delta") {
      if (!started) {
        controller.enqueue({ type: "text-start", id: messageId })
        started = true
        // The status caption otherwise stays frozen on the last real status
        // ("Checking citations...") for the entire typing phase, which reads as
        // stuck even though text is actively arriving.
        onStatus?.("typing", "Drafting your answer...")
      }
      const payload = JSON.parse(data) as { text: string }
      controller.enqueue({ type: "text-delta", id: messageId, delta: payload.text })
    } else if (eventName === "error") {
      const payload = JSON.parse(data) as { message: string }
      throw new Error(payload.message)
    } else if (eventName === "done") {
      finish(controller)
    }

    // Citations are fetched from the persisted messages in ChatSession.onFinish.
  }

  // A transform keeps reading even when a chunk only contains status/citations or
  // part of an event. A pull() that returns without enqueueing can stall its reader.
  return body.pipeThrough(new TransformStream<Uint8Array, UIMessageChunk>({
    transform(value, controller) {
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split("\n\n")
      buffer = events.pop() ?? ""
      for (const event of events) {
        consumeEvent(event, controller)
        if (finished) {
          // The application is done; don't wait for the HTTP connection to close.
          controller.terminate()
          return
        }
      }
    },
    flush(controller) {
      buffer += decoder.decode()
      if (buffer.trim()) consumeEvent(buffer, controller)
      if (!finished) finish(controller)
    },
  }))
}
