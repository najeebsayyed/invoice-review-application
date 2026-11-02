import { useState } from 'react'
import type { Document } from '../lib/types'
import { StatusBadge } from './StatusBadge'

interface DocumentInboxProps {
  documents: Document[]
  onSelect: (document: Document) => void
  onDelete: (document: Document) => Promise<void>
}

function displayName(document: Document): string {
  return document.review_data?.vendor_name ?? document.original_filename
}

function amount(document: Document): string {
  const total = document.review_data?.invoice_total
  const currency = document.review_data?.currency
  if (!total) return '—'
  return currency ? `${currency} ${total}` : String(total)
}

function documentLabel(document: Document): string {
  const kind =
    document.review_data?.document_type ??
    (typeof document.classification?.document_kind === 'string'
      ? document.classification.document_kind
      : null)
  if (kind === 'receipt') return 'Receipt'
  if (kind === 'invoice') return 'Invoice'
  return kind ?? 'Document'
}

export function DocumentInbox({ documents, onSelect, onDelete }: DocumentInboxProps) {
  const [pendingDelete, setPendingDelete] = useState<Document | null>(null)
  const [deleting, setDeleting] = useState(false)

  async function remove() {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await onDelete(pendingDelete)
    } finally {
      setDeleting(false)
      setPendingDelete(null)
    }
  }

  if (documents.length === 0) {
    return <p className="py-12 text-center text-sm text-zinc-500">No documents reviewed yet.</p>
  }

  return (
    <>
      <div className="divide-y divide-zinc-100">
        {documents.map((document) => (
          <div key={document.id} className="group flex items-center gap-1 bg-white px-3 py-2">
            <button
              type="button"
              onClick={() => onSelect(document)}
              className="min-w-0 flex-1 rounded-lg px-2 py-2.5 text-left transition hover:bg-zinc-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 cursor-pointer"
            >
              <div className="flex items-baseline justify-between gap-3">
                <p className="truncate font-medium text-zinc-900">{displayName(document)}</p>
                <span className="shrink-0 font-medium tabular-nums text-zinc-900">
                  {amount(document)}
                </span>
              </div>
              <div className="mt-1.5 flex items-center justify-between gap-3">
                <p className="truncate text-sm text-zinc-500">
                  <span className="mr-2 font-medium text-zinc-700">{documentLabel(document)}</span>
                  {document.original_filename}
                </p>
                <StatusBadge status={document.status} />
              </div>
            </button>
            <button
              type="button"
              onClick={() => setPendingDelete(document)}
              aria-label={`Delete ${displayName(document)}`}
              title="Delete document"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 cursor-pointer"
            >
              <svg
                aria-hidden="true"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M3 6h18" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
                <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
          </div>
        ))}
      </div>

      {pendingDelete && (
        <div className="border-t border-zinc-100 bg-zinc-50 px-6 py-4">
          <p className="text-sm text-zinc-700">
            Delete <span className="font-medium">{displayName(pendingDelete)}</span>? This removes the
            saved review and the uploaded file.
          </p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              disabled={deleting}
              onClick={() => void remove()}
              className="rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 cursor-pointer"
            >
              {deleting ? 'Deleting…' : 'Delete'}
            </button>
            <button
              type="button"
              disabled={deleting}
              onClick={() => setPendingDelete(null)}
              className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </>
  )
}
