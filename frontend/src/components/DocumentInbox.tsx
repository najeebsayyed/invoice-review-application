import { useId, useMemo, useState } from 'react'
import type { Document, DocumentStats, DocumentStatus } from '../lib/types'
import { StatusBadge } from './StatusBadge'

interface DocumentInboxProps {
  documents: Document[]
  stats?: DocumentStats | null
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

function formatEuro(val: number | string | undefined): string {
  const num = typeof val === 'number' ? val : parseFloat(String(val || 0))
  if (isNaN(num)) return '€0.00'
  return new Intl.NumberFormat('en-IE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num)
}

export function DocumentInbox({ documents, stats, onSelect, onDelete }: DocumentInboxProps) {
  const [pendingDelete, setPendingDelete] = useState<Document | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedStatus, setSelectedStatus] = useState<'all' | DocumentStatus>('all')
  const searchInputId = useId()

  const totalDocs = stats?.total_documents ?? documents.length
  const needsReviewCount =
    stats?.needs_review_count ?? documents.filter((d) => d.status === 'needs_review').length
  const readyCount = stats?.ready_count ?? documents.filter((d) => d.status === 'ready').length
  const approvedCount =
    stats?.approved_count ?? documents.filter((d) => d.status === 'approved').length
  const rejectedCount =
    stats?.rejected_count ?? documents.filter((d) => d.status === 'rejected').length

  const computedSpend = useMemo(() => {
    if (stats?.total_spend !== undefined) {
      return stats.total_spend
    }
    return documents
      .filter((d) => d.status === 'approved')
      .reduce((acc, d) => {
        const val = parseFloat(String(d.review_data?.invoice_total || 0))
        return acc + (isNaN(val) ? 0 : val)
      }, 0)
  }, [stats, documents])

  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      if (selectedStatus !== 'all' && doc.status !== selectedStatus) {
        return false
      }
      if (searchTerm.trim()) {
        const query = searchTerm.trim().toLowerCase()
        const vendor = (doc.review_data?.vendor_name || '').toLowerCase()
        const invNum = (doc.review_data?.invoice_number || '').toLowerCase()
        const filename = doc.original_filename.toLowerCase()
        if (!vendor.includes(query) && !invNum.includes(query) && !filename.includes(query)) {
          return false
        }
      }
      return true
    })
  }, [documents, selectedStatus, searchTerm])

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

  return (
    <div className="space-y-6">
      {/* KPI Overview Cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
        <div className="rounded-xl border border-zinc-200/80 bg-white p-4 shadow-xs">
          <p className="text-xs font-medium text-zinc-500">Total Documents</p>
          <p className="mt-1.5 text-2xl font-bold tracking-tight text-zinc-950">{totalDocs}</p>
          <p className="mt-1 text-xs text-zinc-400">Processed in local store</p>
        </div>

        <div className="rounded-xl border border-amber-200/80 bg-amber-50/50 p-4 shadow-xs">
          <p className="text-xs font-medium text-amber-800">Needs Review</p>
          <p className="mt-1.5 text-2xl font-bold tracking-tight text-amber-900">
            {needsReviewCount}
          </p>
          <p className="mt-1 text-xs text-amber-700/80">Pending human validation</p>
        </div>

        <div className="rounded-xl border border-blue-200/80 bg-blue-50/50 p-4 shadow-xs">
          <p className="text-xs font-medium text-blue-800">Ready</p>
          <p className="mt-1.5 text-2xl font-bold tracking-tight text-blue-900">{readyCount}</p>
          <p className="mt-1 text-xs text-blue-700/80">Awaiting sign-off</p>
        </div>

        <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/50 p-4 shadow-xs">
          <p className="text-xs font-medium text-emerald-800">Approved Spend</p>
          <p className="mt-1.5 text-2xl font-bold tracking-tight text-emerald-900">
            {formatEuro(computedSpend)}
          </p>
          <p className="mt-1 text-xs text-emerald-700/80">{approvedCount} approved invoices</p>
        </div>
      </div>

      {/* Search and Filters Bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative min-w-64 max-w-sm flex-1">
          <label htmlFor={searchInputId} className="sr-only">
            Search documents
          </label>
          <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-zinc-400">
            <svg
              className="h-4 w-4"
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
                clipRule="evenodd"
              />
            </svg>
          </div>
          <input
            id={searchInputId}
            type="search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search vendor, invoice #, file..."
            className="block w-full rounded-lg border border-zinc-200 bg-white py-2 pr-8 pl-9 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-400 focus:ring-2 focus:ring-zinc-400/20 focus:outline-none"
          />
          {searchTerm && (
            <button
              type="button"
              onClick={() => setSearchTerm('')}
              className="absolute inset-y-0 right-0 flex items-center pr-2.5 text-zinc-400 hover:text-zinc-600"
              aria-label="Clear search"
            >
              <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
              </svg>
            </button>
          )}
        </div>

        {/* Status Filter Tabs */}
        <div className="flex flex-wrap items-center gap-1.5" role="tablist" aria-label="Status filters">
          <button
            type="button"
            onClick={() => setSelectedStatus('all')}
            className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition cursor-pointer ${
              selectedStatus === 'all'
                ? 'bg-zinc-900 text-white shadow-xs'
                : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200 hover:text-zinc-900'
            }`}
          >
            All ({totalDocs})
          </button>
          <button
            type="button"
            onClick={() => setSelectedStatus('needs_review')}
            className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition cursor-pointer ${
              selectedStatus === 'needs_review'
                ? 'bg-amber-600 text-white shadow-xs'
                : 'bg-zinc-100 text-zinc-600 hover:bg-amber-100 hover:text-amber-900'
            }`}
          >
            Needs Review ({needsReviewCount})
          </button>
          <button
            type="button"
            onClick={() => setSelectedStatus('ready')}
            className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition cursor-pointer ${
              selectedStatus === 'ready'
                ? 'bg-blue-600 text-white shadow-xs'
                : 'bg-zinc-100 text-zinc-600 hover:bg-blue-100 hover:text-blue-900'
            }`}
          >
            Ready ({readyCount})
          </button>
          <button
            type="button"
            onClick={() => setSelectedStatus('approved')}
            className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition cursor-pointer ${
              selectedStatus === 'approved'
                ? 'bg-emerald-600 text-white shadow-xs'
                : 'bg-zinc-100 text-zinc-600 hover:bg-emerald-100 hover:text-emerald-900'
            }`}
          >
            Approved ({approvedCount})
          </button>
          <button
            type="button"
            onClick={() => setSelectedStatus('rejected')}
            className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition cursor-pointer ${
              selectedStatus === 'rejected'
                ? 'bg-rose-600 text-white shadow-xs'
                : 'bg-zinc-100 text-zinc-600 hover:bg-rose-100 hover:text-rose-900'
            }`}
          >
            Rejected ({rejectedCount})
          </button>
        </div>
      </div>

      {/* Main Table Container */}
      <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-xs">
        {documents.length === 0 ? (
          <div className="py-14 text-center">
            <svg
              className="mx-auto h-10 w-10 text-zinc-300"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.5"
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <p className="mt-3 font-medium text-zinc-900">No documents reviewed yet</p>
            <p className="mt-1 text-xs text-zinc-500">
              Upload an invoice or receipt to begin automated review.
            </p>
          </div>
        ) : filteredDocuments.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-sm font-medium text-zinc-900">No matching documents found</p>
            <p className="mt-1 text-xs text-zinc-500">
              Try adjusting your search query or status filter.
            </p>
            <button
              type="button"
              onClick={() => {
                setSearchTerm('')
                setSelectedStatus('all')
              }}
              className="mt-3 inline-flex items-center rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 cursor-pointer"
            >
              Reset filters
            </button>
          </div>
        ) : (
          <div className="divide-y divide-zinc-100">
            {filteredDocuments.map((document) => (
              <div
                key={document.id}
                className="group flex items-center gap-1 bg-white px-3 py-2 transition hover:bg-zinc-50/70"
              >
                <button
                  type="button"
                  onClick={() => onSelect(document)}
                  className="min-w-0 flex-1 rounded-lg px-2 py-2.5 text-left transition focus-visible:ring-2 focus-visible:ring-zinc-400 focus-visible:outline-none cursor-pointer"
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="truncate font-medium text-zinc-900">{displayName(document)}</p>
                    <span className="shrink-0 font-medium tabular-nums text-zinc-900">
                      {amount(document)}
                    </span>
                  </div>
                  <div className="mt-1.5 flex items-center justify-between gap-3">
                    <p className="truncate text-xs text-zinc-500">
                      <span className="mr-2 font-medium text-zinc-700">
                        {documentLabel(document)}
                      </span>
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
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-zinc-400 opacity-60 transition-colors group-hover:opacity-100 hover:bg-red-50 hover:text-red-600 focus-visible:ring-2 focus-visible:ring-zinc-400 focus-visible:outline-none cursor-pointer"
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
        )}

        {/* Delete Confirmation Modal / Bar */}
        {pendingDelete && (
          <div className="border-t border-red-100 bg-red-50/60 px-6 py-4">
            <p className="text-sm text-zinc-800">
              Permanently delete <span className="font-semibold">{displayName(pendingDelete)}</span>?
              This removes the review record, line items, and binary file from disk.
            </p>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                disabled={deleting}
                onClick={() => void remove()}
                className="rounded-lg bg-red-600 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50 cursor-pointer"
              >
                {deleting ? 'Deleting…' : 'Delete permanently'}
              </button>
              <button
                type="button"
                disabled={deleting}
                onClick={() => setPendingDelete(null)}
                className="rounded-lg border border-zinc-200 bg-white px-3.5 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 cursor-pointer"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
