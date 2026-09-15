import type { LucideIcon } from "lucide-react"

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon?: LucideIcon
  title: string
  description: string
  action?: React.ReactNode
}) {
  return (
    <div className="grid min-h-full place-items-center px-6 py-16 text-center">
      <div className="flex max-w-sm flex-col items-center">
        {Icon && <Icon aria-hidden="true" className="mb-4 size-8 text-muted-foreground" />}
        <h2 className="text-2xl font-semibold text-foreground">{title}</h2>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">{description}</p>
        {action && <div className="mt-5">{action}</div>}
      </div>
    </div>
  )
}
