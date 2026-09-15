import { useEffect, useState } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"

import { useAuth } from "@/auth/AuthProvider"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

type AuthPageProps = {
  mode: "login" | "signup"
}

export function AuthPage({ mode }: AuthPageProps) {
  const { session, signIn, signUp } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const isSignup = mode === "signup"

  useEffect(() => {
    if (session) {
      navigate("/app", { replace: true })
    }
  }, [navigate, session])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setNotice(null)
    setSubmitting(true)

    const result = isSignup
      ? await signUp(email, password)
      : await signIn(email, password)

    setSubmitting(false)

    if (result.error) {
      setError(result.error.message)
      return
    }

    if (isSignup) {
      setNotice("Check your email to confirm your account before signing in.")
      return
    }

    const destination = (location.state as { from?: string } | null)?.from ?? "/app"
    navigate(destination, { replace: true })
  }

  return (
    <main className="grid min-h-screen place-items-center bg-background px-6 py-12 text-foreground">
      <section className="w-full max-w-md rounded-2xl border border-border bg-card p-8 shadow-sm">
        <div className="mb-8">
          <div className="mb-3 flex items-center gap-2">
            <img src="/logo.jpg" alt="Document Copilot logo" className="h-8 w-8 shrink-0 rounded-full object-cover" />
            <p className="text-sm font-medium text-foreground">Document Copilot</p>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {isSignup ? "Create your analyst account" : "Welcome back"}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {isSignup
              ? "Use your work email to join the research workspace."
              : "Sign in to continue to your research workspace."}
          </p>
        </div>

        <form className="space-y-5" onSubmit={handleSubmit}>
          <label className="block text-sm font-medium text-foreground">
            Work email
            <Input
              required
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-2 h-10"
              placeholder="analyst@driftwood.example"
            />
          </label>

          <label className="block text-sm font-medium text-foreground">
            Password
            <Input
              required
              minLength={6}
              type="password"
              autoComplete={isSignup ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-2 h-10"
              placeholder="At least 6 characters"
            />
          </label>

          {error && (
            <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </p>
          )}
          {notice && (
            <p role="status" className="rounded-lg border border-info/20 bg-info/10 p-3 text-sm text-info">
              {notice}
            </p>
          )}

          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Working..." : isSignup ? "Create account" : "Sign in"}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          {isSignup ? "Already have an account?" : "Need an account?"}{" "}
          <Link
            className="font-medium text-foreground hover:underline"
            to={isSignup ? "/login" : "/signup"}
          >
            {isSignup ? "Sign in" : "Sign up"}
          </Link>
        </p>
      </section>
    </main>
  )
}
