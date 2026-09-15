function getRequiredEnv(name: string): string {
  const value = import.meta.env[name]
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`Missing required environment variable: ${name}`)
  }

  return value.trim()
}

function getRequiredUrl(name: string): string {
  const value = getRequiredEnv(name)

  try {
    const url = new URL(value)
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      throw new Error()
    }
  } catch {
    throw new Error(`Environment variable ${name} must be a valid HTTP(S) URL`)
  }

  return value.replace(/\/$/, "")
}

export const env = {
  apiBaseUrl: getRequiredUrl("VITE_API_BASE_URL"),
  supabaseUrl: getRequiredUrl("VITE_SUPABASE_URL"),
  supabaseAnonKey: getRequiredEnv("VITE_SUPABASE_ANON_KEY"),
} as const
