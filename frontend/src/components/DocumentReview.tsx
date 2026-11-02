import { useState } from 'react'
import { decideDocument, documentFileUrl, selectGlAccount } from '../lib/api'
import { summarizeReview } from '../lib/review-outcome'
import type { Document, GlAccount } from '../lib/types'
import { DocumentPreview } from './DocumentPreview'
import { StatusBadge } from './StatusBadge'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { Card, CardContent, CardHeader } from './ui/Card'

interface DocumentReviewProps {
  document: Document
  accounts: GlAccount[]
  accountsLoading: boolean
  onRetryAccounts: () => void
  onChanged: (document: Document) => void
}

function formattedAmount(value: string | number | null | undefined, currency: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return 'Not found'
  const amount = Number(value)
  if (!Number.isFinite(amount)) return `${currency ?? ''} ${value}`.trim()
  try {
    return new Intl.NumberFormat('en-NL', { style: 'currency', currency: currency ?? 'EUR' }).format(amount)
  } catch {
    return `${currency ?? ''} ${value}`.trim()
  }
}

export function DocumentReview({
  document,
  accounts,
  accountsLoading,
  onRetryAccounts,
  onChanged,
}: DocumentReviewProps) {
  const [busy, setBusy] = useState<'account' | 'approved' | 'rejected' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const review = document.review_data
  const isReceipt = review?.document_type === 'receipt'
  const locked = document.status === 'approved' || document.status === 'rejected'
  const hasErrors = document.issues.some((issue) => issue.severity === 'error')
  const coding = document.accounting_coding
  const selectedCode = coding?.selected_gl_account_code ?? ''
  const canApprove = !locked && !hasErrors && Boolean(selectedCode)
  const outcome = summarizeReview(document.status, document.issues)

  async function handleAccountChange(code: string) {
    if (locked || busy) return
    setError(null)
    setBusy('account')
    try {
      const updated = await selectGlAccount(document.id, code)
      onChanged(updated)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not update GL account.')
    } finally {
      setBusy(null)
    }
  }

  async function handleDecision(decision: 'approved' | 'rejected') {
    if (locked || busy) return
    setError(null)
    setBusy(decision)
    try {
      const updated = await decideDocument(document.id, decision)
      onChanged(updated)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Could not ${decision} document.`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      {/* Top Header & Outcome Banner */}
      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-semibold text-zinc-950">
                {review?.vendor_name ?? document.original_filename}
              </h2>
              <StatusBadge status={document.status} />
            </div>
            <p className="mt-1 text-sm text-zinc-500">
              {document.original_filename} • {isReceipt ? 'Receipt' : 'Invoice'}
            </p>
          </div>
          {locked && (
            <Badge variant={document.status === 'approved' ? 'success' : 'destructive'} className="text-sm">
              Decision recorded: {document.status.toUpperCase()}
            </Badge>
          )}
        </CardHeader>
        <CardContent>
          <div
            className={`rounded-lg p-4 text-sm ${
              outcome.kind === 'failed' || hasErrors
                ? 'border border-red-200 bg-red-50 text-red-900'
                : outcome.warningCount > 0
                  ? 'border border-amber-200 bg-amber-50 text-amber-900'
                  : 'border border-emerald-200 bg-emerald-50 text-emerald-900'
            }`}
          >
            <p className="font-semibold">{outcome.title}</p>
            <p className="mt-0.5">{outcome.description}</p>
          </div>
          {error && (
            <div role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {error}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Main Review Grid */}
      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        {/* Left: Document Source File */}
        <div>
          <Card className="h-full">
            <CardHeader className="pb-3">
              <p className="text-sm font-medium text-zinc-900">Original document</p>
              <p className="text-xs text-zinc-500">Extracted and verified against Northstar policies</p>
            </CardHeader>
            <CardContent>
              <DocumentPreview
                src={documentFileUrl(document.id)}
                filename={document.original_filename}
                contentType={document.content_type}
                className="min-h-[580px]"
              />
            </CardContent>
          </Card>
        </div>

        {/* Right: Validation Issues, Fields, GL Coding, Actions */}
        <div className="space-y-6">
          {/* Policy Validation Findings */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-zinc-900">Northstar policy findings</p>
                <span className="text-xs text-zinc-500">
                  {document.issues.length} {document.issues.length === 1 ? 'issue' : 'issues'}
                </span>
              </div>
            </CardHeader>
            <CardContent>
              {document.issues.length === 0 ? (
                <p className="text-sm text-zinc-500">No validation issues found. All policy checks passed.</p>
              ) : (
                <ul className="space-y-2">
                  {document.issues.map((issue, idx) => (
                    <li
                      key={`${issue.code}-${idx}`}
                      className={`flex items-start gap-2.5 rounded-lg border p-3 text-sm ${
                        issue.severity === 'error'
                          ? 'border-red-200 bg-red-50/60 text-red-900'
                          : 'border-amber-200 bg-amber-50/60 text-amber-900'
                      }`}
                    >
                      <Badge
                        variant={issue.severity === 'error' ? 'destructive' : 'warning'}
                        className="mt-0.5 uppercase tracking-wider text-[10px]"
                      >
                        {issue.severity}
                      </Badge>
                      <div className="min-w-0 flex-1">
                        <span className="font-medium">{issue.code}</span>
                        {issue.field && <span className="ml-1 text-xs opacity-75">({issue.field})</span>}
                        <p className="mt-0.5 text-xs leading-relaxed">{issue.message}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {/* Extracted Fields */}
          <Card>
            <CardHeader className="pb-3">
              <p className="text-sm font-medium text-zinc-900">Extracted document fields</p>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-3 rounded-lg bg-zinc-50 p-3">
                <div>
                  <span className="text-xs text-zinc-500">Supplier / Merchant</span>
                  <p className="font-medium text-zinc-900">{review?.vendor_name ?? 'Not found'}</p>
                </div>
                <div>
                  <span className="text-xs text-zinc-500">Supplier VAT</span>
                  <p className="font-medium text-zinc-900">{review?.vendor_vat_id ?? (isReceipt ? 'N/A (Receipt)' : 'Not found')}</p>
                </div>
                <div>
                  <span className="text-xs text-zinc-500">Customer</span>
                  <p className="font-medium text-zinc-900">{review?.customer_name ?? (isReceipt ? 'N/A (Receipt)' : 'Not found')}</p>
                </div>
                <div>
                  <span className="text-xs text-zinc-500">Customer VAT</span>
                  <p className="font-medium text-zinc-900">{review?.customer_vat_id ?? (isReceipt ? 'N/A (Receipt)' : 'Not found')}</p>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3 rounded-lg bg-zinc-50 p-3">
                <div>
                  <span className="text-xs text-zinc-500">Invoice / Tx #</span>
                  <p className="font-medium text-zinc-900">{review?.invoice_number ?? (isReceipt ? 'N/A (Receipt)' : 'Not found')}</p>
                </div>
                <div>
                  <span className="text-xs text-zinc-500">Date</span>
                  <p className="font-medium text-zinc-900">{review?.invoice_date ?? 'Not found'}</p>
                </div>
                <div>
                  <span className="text-xs text-zinc-500">PO Number</span>
                  <p className="font-medium text-zinc-900">{review?.purchase_order ?? (isReceipt ? 'N/A (Receipt)' : 'Not found')}</p>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3 rounded-lg border border-zinc-200 bg-white p-3">
                <div>
                  <span className="text-xs text-zinc-500">Subtotal</span>
                  <p className="font-medium text-zinc-900">{formattedAmount(review?.subtotal, review?.currency)}</p>
                </div>
                <div>
                  <span className="text-xs text-zinc-500">VAT Total</span>
                  <p className="font-medium text-zinc-900">{formattedAmount(review?.total_tax, review?.currency)}</p>
                </div>
                <div>
                  <span className="text-xs text-zinc-500">Invoice Total</span>
                  <p className="text-base font-semibold text-zinc-950">{formattedAmount(review?.invoice_total, review?.currency)}</p>
                </div>
              </div>

              {/* Line Items if present */}
              {review?.line_items && review.line_items.length > 0 && (
                <div className="mt-2">
                  <span className="text-xs font-medium text-zinc-500">Line Items ({review.line_items.length})</span>
                  <div className="mt-1 divide-y divide-zinc-100 rounded-lg border border-zinc-200 text-xs">
                    {review.line_items.slice(0, 4).map((item, idx) => (
                      <div key={idx} className="flex justify-between p-2">
                        <span className="truncate pr-2">{item.description ?? 'Item'}</span>
                        <span className="font-mono tabular-nums">{formattedAmount(item.amount, review.currency)}</span>
                      </div>
                    ))}
                    {review.line_items.length > 4 && (
                      <p className="p-2 text-center text-xs text-zinc-400">+{review.line_items.length - 4} more items</p>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* General Ledger Account Suggestion & Selection */}
          <Card>
            <CardHeader className="pb-3">
              <p className="text-sm font-medium text-zinc-900">General Ledger account</p>
              <p className="text-xs text-zinc-500">
                Suggested by AI from Northstar catalog; reviewer makes the final selection.
              </p>
            </CardHeader>
            <CardContent className="space-y-3">
              {document.gl_suggestion && (
                <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-zinc-700">Model suggestion:</span>
                    <span className="text-zinc-500">{(document.gl_suggestion.confidence * 100).toFixed(0)}% confidence</span>
                  </div>
                  <p className="mt-1 text-zinc-600 leading-relaxed">{document.gl_suggestion.reasoning}</p>
                </div>
              )}

              <div>
                <label htmlFor="gl-select" className="block text-xs font-medium text-zinc-700 mb-1">
                  Selected Northstar account:
                </label>
                <select
                  id="gl-select"
                  disabled={locked || busy !== null || accountsLoading}
                  value={selectedCode}
                  onChange={(e) => void handleAccountChange(e.target.value)}
                  className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500 disabled:opacity-50"
                >
                  <option value="">-- Choose account --</option>
                  {accounts.map((acct) => (
                    <option key={acct.code} value={acct.code}>
                      {acct.code} — {acct.name}
                    </option>
                  ))}
                </select>
                {accountsLoading && (
                  <p className="mt-1 text-xs text-zinc-400">Loading catalog accounts…</p>
                )}
                {accounts.length === 0 && !accountsLoading && (
                  <Button variant="ghost" size="sm" onClick={onRetryAccounts} className="mt-1 text-xs">
                    Retry loading catalog
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Decision Actions */}
          {!locked && (
            <Card>
              <CardContent className="pt-6">
                <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
                  <Button
                    variant="destructive"
                    disabled={busy !== null}
                    onClick={() => void handleDecision('rejected')}
                    className="sm:w-32"
                  >
                    {busy === 'rejected' ? 'Rejecting…' : 'Reject'}
                  </Button>
                  <Button
                    variant="success"
                    disabled={!canApprove || busy !== null}
                    onClick={() => void handleDecision('approved')}
                    className="sm:w-32"
                  >
                    {busy === 'approved' ? 'Approving…' : 'Approve'}
                  </Button>
                </div>
                {!canApprove && (
                  <p className="mt-2 text-right text-xs text-zinc-500">
                    {hasErrors
                      ? 'Resolve blocking validation errors before approval.'
                      : !selectedCode
                        ? 'Select a GL account before approval.'
                        : ''}
                  </p>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
