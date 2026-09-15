import { env } from "@/lib/env"
import { supabase } from "@/lib/supabase"

function handleUnauthorized(status: number): void {
  if (status === 401) {
    void supabase.auth.signOut()
  }
}

const DEFAULT_TIMEOUT_MS = 15_000

type HttpRequestInit = Omit<RequestInit, "body"> & {
  body?: unknown
}

type ErrorPayload = {
  detail?: string
  message?: string
}

export class ApiError extends Error {
  readonly status: number | null
  readonly isNetworkError: boolean

  constructor(
    message: string,
    options: { status?: number | null; isNetworkError?: boolean } = {},
  ) {
    super(message)
    this.name = "ApiError"
    this.status = options.status ?? null
    this.isNetworkError = options.isNetworkError ?? false
  }
}

async function getAccessToken(): Promise<string | null> {
  const { data, error } = await supabase.auth.getSession()
  if (error) {
    throw new ApiError("Unable to read the authentication session")
  }

  return data.session?.access_token ?? null
}

async function parseResponseBody(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) {
    return null
  }

  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}

function getErrorMessage(payload: unknown, fallback: string): string {
  if (typeof payload === "object" && payload !== null) {
    const errorPayload = payload as ErrorPayload
    if (typeof errorPayload.detail === "string") {
      return errorPayload.detail
    }
    if (typeof errorPayload.message === "string") {
      return errorPayload.message
    }
  }

  return fallback
}

async function request<T>(path: string, options: HttpRequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)
  const headers = new Headers(options.headers)
  headers.set("Accept", "application/json")

  if (options.body !== undefined && options.body !== null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  const accessToken = await getAccessToken()
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`)
  }

  const body =
    options.body === undefined || options.body === null || typeof options.body === "string"
      ? options.body
      : JSON.stringify(options.body)

  try {
    const response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...options,
      body,
      headers,
      signal: controller.signal,
    })
    const payload = await parseResponseBody(response)

    if (!response.ok) {
      handleUnauthorized(response.status)
      throw new ApiError(
        getErrorMessage(payload, `Request failed with status ${response.status}`),
        { status: response.status },
      )
    }

    return payload as T
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }

    const isAbort = error instanceof DOMException && error.name === "AbortError"
    throw new ApiError(
      isAbort ? "The request timed out" : "Unable to reach the backend",
      { isNetworkError: true },
    )
  } finally {
    clearTimeout(timeoutId)
  }
}

export const http = {
  delete: <T>(path: string, options?: HttpRequestInit) =>
    request<T>(path, { ...options, method: "DELETE" }),
  get: <T>(path: string, options?: HttpRequestInit) =>
    request<T>(path, { ...options, method: "GET" }),
  patch: <T>(path: string, body: unknown, options?: HttpRequestInit) =>
    request<T>(path, { ...options, body, method: "PATCH" }),
  post: <T>(path: string, body: unknown, options?: HttpRequestInit) =>
    request<T>(path, { ...options, body, method: "POST" }),
  put: <T>(path: string, body: unknown, options?: HttpRequestInit) =>
    request<T>(path, { ...options, body, method: "PUT" }),
  stream: async (path: string, body: unknown, signal?: AbortSignal): Promise<Response> => {
    const headers = new Headers({ "Content-Type": "application/json" })
    headers.set("Accept", "text/event-stream")

    const accessToken = await getAccessToken()
    if (accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`)
    }

    let response: Response
    try {
      response = await fetch(`${env.apiBaseUrl}${path}`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal,
      })
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error
      }
      throw new ApiError("Unable to reach the backend", { isNetworkError: true })
    }

    if (!response.ok) {
      const payload = await parseResponseBody(response)
      handleUnauthorized(response.status)
      throw new ApiError(
        getErrorMessage(payload, `Request failed with status ${response.status}`),
        { status: response.status },
      )
    }

    return response
  },
}
