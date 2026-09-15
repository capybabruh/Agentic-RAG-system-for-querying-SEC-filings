import { ExternalLink } from "lucide-react"

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import type { Citation } from "@/lib/api"

function formatFilingDate(value: string | null): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat("en-US", { year: "numeric", month: "short", day: "numeric" }).format(date)
}

function chipLabel(citation: Citation): string {
  const parts = [citation.ticker, citation.filing_type, formatFilingDate(citation.filing_date)].filter(Boolean)
  return parts.length > 0 ? parts.join(" · ") : "Source"
}

export function Citations({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {citations.map((citation, index) => (
        <Popover key={citation.id}>
          <PopoverTrigger className="rounded-full border border-citation/30 bg-citation/10 px-2.5 py-1 text-xs font-medium text-citation transition hover:border-citation/60 hover:bg-citation/15">
            [{index + 1}] {chipLabel(citation)}
          </PopoverTrigger>
          <PopoverContent className="text-foreground">
            <div className="text-sm font-medium text-citation">
              {citation.document_title ?? chipLabel(citation)}
            </div>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
              {citation.ticker && (
                <>
                  <dt className="text-muted-foreground/70">Ticker</dt>
                  <dd>{citation.ticker}</dd>
                </>
              )}
              {citation.filing_type && (
                <>
                  <dt className="text-muted-foreground/70">Filing</dt>
                  <dd>{citation.filing_type}</dd>
                </>
              )}
              {formatFilingDate(citation.filing_date) && (
                <>
                  <dt className="text-muted-foreground/70">Date</dt>
                  <dd>{formatFilingDate(citation.filing_date)}</dd>
                </>
              )}
              {(citation.section_label || citation.page_number !== null) && (
                <>
                  <dt className="text-muted-foreground/70">Location</dt>
                  <dd>
                    {[citation.section_label, citation.page_number ? `p. ${citation.page_number}` : null]
                      .filter(Boolean)
                      .join(", ")}
                  </dd>
                </>
              )}
            </dl>
            <blockquote className="border-l-2 border-citation/40 pl-3 text-sm leading-6 text-foreground/90 italic">
              "{citation.quote_text}"
            </blockquote>
            {citation.source_url && (
              <a
                href={citation.source_url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 text-xs font-medium text-citation hover:text-citation/80"
              >
                View original filing
                <ExternalLink aria-hidden="true" className="size-3" />
              </a>
            )}
          </PopoverContent>
        </Popover>
      ))}
    </div>
  )
}
