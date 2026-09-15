export function TypingIndicator() {
  return (
    <span className="inline-flex items-center gap-1" role="status" aria-label="Assistant is working">
      <span className="size-1.5 animate-bounce rounded-full bg-info [animation-delay:-0.3s]" />
      <span className="size-1.5 animate-bounce rounded-full bg-info [animation-delay:-0.15s]" />
      <span className="size-1.5 animate-bounce rounded-full bg-info" />
    </span>
  )
}
