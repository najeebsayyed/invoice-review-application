import { useState } from 'react'
import {
  decideDocument,
  documentFileUrl,
  draftCorrectionEmail,
  selectGlAccount,
  updateCorrections,
} from '../lib/api'
import { summarizeReview } from '../lib/review-outcome'
import type { CorrectionEmail, Document, FieldCorrections, GlAccount } from '../lib/types'
import { DocumentPreview } from './DocumentPreview'
import { StatusBadge } from './StatusBadge'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { Card, CardContent, CardHeader } from './ui/Card'
import { Dialog } from './ui/Dialog'

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

function ProvenanceBadge({
  source,
  hasConflict,
}: {
  source?: 'primary' | 'secondary' | 'user'
  hasConflict?: boolean
}) {
  if (!source && !hasConflict) return null
  return (
    <div className="flex items-center gap-1">
      {source === 'secondary' && (
        <span
          className="rounded border border-indigo-200 bg-indigo-50 px-1.5 py-0.5 text-[10px] font-medium text-indigo-700"
          title="Field filled from secondary Azure OpenAI extraction"
        >
          OpenAI fallback
        </span>
      )}
      {source === 'user' && (
        <span
          className="rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700"
          title="Manually corrected by reviewer"
        >
          Manual edit
        </span>
      )}
      {hasConflict && (
        <span
          className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700"
          title="Primary and secondary extraction readings differed"
        >
          Conflict
        </span>
      )}
    </div>
  )
}

export function DocumentReview({
  document,
  accounts,
  accountsLoading,
  onRetryAccounts,
  onChanged,
}: DocumentReviewProps) {
  const [busy, setBusy] = useState<'account' | 'approved' | 'rejected' | 'saving' | 'drafting' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null)

  // Correction email modal state
  const [emailModalOpen, setEmailModalOpen] = useState(false)
  const [emailDraft, setEmailDraft] = useState<CorrectionEmail | null>(null)

  const review = document.review_data
  const isReceipt = review?.document_type === 'receipt'
  const locked = document.status === 'approved' || document.status === 'rejected'
  const hasErrors = document.issues.some((issue) => issue.severity === 'error')
  const coding = document.accounting_coding
  const selectedCode = coding?.selected_gl_account_code ?? ''
  const canApprove = !locked && !hasErrors && Boolean(selectedCode)
  const outcome = summarizeReview(document.status, document.issues)

  // Edit form state
  const [editForm, setEditForm] = useState<FieldCorrections>({
    vendor_name: review?.vendor_name ?? '',
    vendor_vat_id: review?.vendor_vat_id ?? '',
    customer_name: review?.customer_name ?? '',
    customer_vat_id: review?.customer_vat_id ?? '',
    invoice_number: review?.invoice_number ?? '',
    purchase_order: review?.purchase_order ?? '',
    invoice_date: review?.invoice_date ?? '',
    due_date: review?.due_date ?? '',
    currency: review?.currency ?? 'EUR',
    subtotal: review?.subtotal ?? '',
    total_tax: review?.total_tax ?? '',
    invoice_total: review?.invoice_total ?? '',
  })

  function startEditing() {
    if (locked) return
    setEditForm({
      vendor_name: review?.vendor_name ?? '',
      vendor_vat_id: review?.vendor_vat_id ?? '',
      customer_name: review?.customer_name ?? '',
      customer_vat_id: review?.customer_vat_id ?? '',
      invoice_number: review?.invoice_number ?? '',
      purchase_order: review?.purchase_order ?? '',
      invoice_date: review?.invoice_date ?? '',
      due_date: review?.due_date ?? '',
      currency: review?.currency ?? 'EUR',
      subtotal: review?.subtotal ?? '',
      total_tax: review?.total_tax ?? '',
      invoice_total: review?.invoice_total ?? '',
    })
    setIsEditing(true)
    setError(null)
  }

  function cancelEditing() {
    setIsEditing(false)
    setError(null)
  }

  async function handleSaveCorrections() {
    if (locked || busy) return
    setError(null)
    setBusy('saving')
    try {
      const updated = await updateCorrections(document.id, editForm)
      onChanged(updated)
      setIsEditing(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save corrections.')
    } finally {
      setBusy(null)
    }
  }

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

  async function handleDraftEmail() {
    setError(null)
    setBusy('drafting')
    try {
      const draft = await draftCorrectionEmail(document.id)
      setEmailDraft(draft)
      setEmailModalOpen(true)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not draft correction email.')
    } finally {
      setBusy(null)
    }
  }

  function copyToClipboard(text: string, label: string) {
    void navigator.clipboard.writeText(text).then(() => {
      setCopyFeedback(label)
      setTimeout(() => setCopyFeedback(null), 2500)
    })
  }

  const provMap = review?.provenance ?? {}
  const confMap = review?.conflicts ?? {}

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
          <div className="flex items-center gap-2">
            {!locked && !isEditing && (
              <Button onClick={startEditing} variant="outline" size="sm">
                Edit fields
              </Button>
            )}
            <Button
              onClick={() => void handleDraftEmail()}
              variant="outline"
              size="sm"
              disabled={busy === 'drafting'}
            >
              {busy === 'drafting' ? 'Drafting email…' : 'Draft correction email'}
            </Button>
            {locked && (
              <Badge variant={document.status === 'approved' ? 'success' : 'destructive'} className="text-sm">
                Decision: {document.status.toUpperCase()}
              </Badge>
            )}
          </div>
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
              <p className="text-xs text-zinc-500">Dual-extracted with Document Intelligence & OpenAI fallback</p>
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

          {/* Extracted / Editable Document Fields */}
          <Card>
            <CardHeader className="flex items-center justify-between pb-3">
              <div>
                <p className="text-sm font-medium text-zinc-900">Document fields</p>
                <p className="text-xs text-zinc-500">
                  {isEditing ? 'Correct values below then save to revalidate.' : 'Showing merged values and field provenance.'}
                </p>
              </div>
              {!locked && !isEditing && (
                <Button variant="ghost" size="sm" onClick={startEditing} className="text-xs">
                  Edit
                </Button>
              )}
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              {isEditing ? (
                /* Inline Edit Mode */
                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    void handleSaveCorrections()
                  }}
                  className="space-y-4"
                >
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-zinc-700">Vendor / Merchant</label>
                      <input
                        type="text"
                        value={editForm.vendor_name ?? ''}
                        onChange={(e) => setEditForm((f) => ({ ...f, vendor_name: e.target.value }))}
                        className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-zinc-700">Vendor VAT ID</label>
                      <input
                        type="text"
                        value={editForm.vendor_vat_id ?? ''}
                        onChange={(e) => setEditForm((f) => ({ ...f, vendor_vat_id: e.target.value }))}
                        className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-zinc-700">Customer Name</label>
                      <input
                        type="text"
                        value={editForm.customer_name ?? ''}
                        onChange={(e) => setEditForm((f) => ({ ...f, customer_name: e.target.value }))}
                        className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-zinc-700">Customer VAT ID</label>
                      <input
                        type="text"
                        value={editForm.customer_vat_id ?? ''}
                        onChange={(e) => setEditForm((f) => ({ ...f, customer_vat_id: e.target.value }))}
                        className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-zinc-700">Invoice #</label>
                      <input
                        type="text"
                        value={editForm.invoice_number ?? ''}
                        onChange={(e) => setEditForm((f) => ({ ...f, invoice_number: e.target.value }))}
                        className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-zinc-700">Date (YYYY-MM-DD)</label>
                      <input
                        type="text"
                        value={editForm.invoice_date ?? ''}
                        onChange={(e) => setEditForm((f) => ({ ...f, invoice_date: e.target.value }))}
                        className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-zinc-700">PO Number</label>
                      <input
                        type="text"
                        value={editForm.purchase_order ?? ''}
                        onChange={(e) => setEditForm((f) => ({ ...f, purchase_order: e.target.value }))}
                        className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-zinc-700">Subtotal</label>
                      <input
                        type="text"
                        value={editForm.subtotal ?? ''}
                        onChange={(e) => setEditForm((f) => ({ ...f, subtotal: e.target.value }))}
                        className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-zinc-700">VAT Total</label>
                      <input
                        type="text"
                        value={editForm.total_tax ?? ''}
                        onChange={(e) => setEditForm((f) => ({ ...f, total_tax: e.target.value }))}
                        className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-zinc-700">Invoice Total</label>
                      <input
                        type="text"
                        value={editForm.invoice_total ?? ''}
                        onChange={(e) => setEditForm((f) => ({ ...f, invoice_total: e.target.value }))}
                        className="mt-1 w-full rounded-md border border-zinc-300 px-2.5 py-1.5 text-xs font-semibold"
                      />
                    </div>
                  </div>

                  <div className="flex justify-end gap-2 pt-2 border-t border-zinc-200">
                    <Button type="button" variant="outline" size="sm" onClick={cancelEditing}>
                      Cancel
                    </Button>
                    <Button type="submit" size="sm" disabled={busy === 'saving'}>
                      {busy === 'saving' ? 'Saving…' : 'Save & revalidate'}
                    </Button>
                  </div>
                </form>
              ) : (
                /* Display Mode with Provenance */
                <>
                  <div className="grid grid-cols-2 gap-3 rounded-lg bg-zinc-50 p-3">
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500">Supplier / Merchant</span>
                        <ProvenanceBadge source={provMap.vendor_name} hasConflict={Boolean(confMap.vendor_name)} />
                      </div>
                      <p className="mt-0.5 font-medium text-zinc-900">{review?.vendor_name ?? 'Not found'}</p>
                    </div>
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500">Supplier VAT</span>
                        <ProvenanceBadge source={provMap.vendor_vat_id} hasConflict={Boolean(confMap.vendor_vat_id)} />
                      </div>
                      <p className="mt-0.5 font-medium text-zinc-900">
                        {review?.vendor_vat_id ?? (isReceipt ? 'N/A (Receipt)' : 'Not found')}
                      </p>
                    </div>
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500">Customer</span>
                        <ProvenanceBadge source={provMap.customer_name} hasConflict={Boolean(confMap.customer_name)} />
                      </div>
                      <p className="mt-0.5 font-medium text-zinc-900">
                        {review?.customer_name ?? (isReceipt ? 'N/A (Receipt)' : 'Not found')}
                      </p>
                    </div>
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500">Customer VAT</span>
                        <ProvenanceBadge source={provMap.customer_vat_id} hasConflict={Boolean(confMap.customer_vat_id)} />
                      </div>
                      <p className="mt-0.5 font-medium text-zinc-900">
                        {review?.customer_vat_id ?? (isReceipt ? 'N/A (Receipt)' : 'Not found')}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-3 rounded-lg bg-zinc-50 p-3">
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500">Invoice / Tx #</span>
                        <ProvenanceBadge source={provMap.invoice_number} hasConflict={Boolean(confMap.invoice_number)} />
                      </div>
                      <p className="mt-0.5 font-medium text-zinc-900">
                        {review?.invoice_number ?? (isReceipt ? 'N/A (Receipt)' : 'Not found')}
                      </p>
                    </div>
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500">Date</span>
                        <ProvenanceBadge source={provMap.invoice_date} hasConflict={Boolean(confMap.invoice_date)} />
                      </div>
                      <p className="mt-0.5 font-medium text-zinc-900">{review?.invoice_date ?? 'Not found'}</p>
                    </div>
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500">PO Number</span>
                        <ProvenanceBadge source={provMap.purchase_order} hasConflict={Boolean(confMap.purchase_order)} />
                      </div>
                      <p className="mt-0.5 font-medium text-zinc-900">
                        {review?.purchase_order ?? (isReceipt ? 'N/A (Receipt)' : 'Not found')}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-3 rounded-lg border border-zinc-200 bg-white p-3">
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500">Subtotal</span>
                        <ProvenanceBadge source={provMap.subtotal} hasConflict={Boolean(confMap.subtotal)} />
                      </div>
                      <p className="mt-0.5 font-medium text-zinc-900">{formattedAmount(review?.subtotal, review?.currency)}</p>
                    </div>
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500">VAT Total</span>
                        <ProvenanceBadge source={provMap.total_tax} hasConflict={Boolean(confMap.total_tax)} />
                      </div>
                      <p className="mt-0.5 font-medium text-zinc-900">{formattedAmount(review?.total_tax, review?.currency)}</p>
                    </div>
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-500">Invoice Total</span>
                        <ProvenanceBadge source={provMap.invoice_total} hasConflict={Boolean(confMap.invoice_total)} />
                      </div>
                      <p className="mt-0.5 text-base font-semibold text-zinc-950">
                        {formattedAmount(review?.invoice_total, review?.currency)}
                      </p>
                    </div>
                  </div>

                  {/* Line Items if present */}
                  {review?.line_items && review.line_items.length > 0 && (
                    <div className="mt-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-zinc-500">Line Items ({review.line_items.length})</span>
                        <ProvenanceBadge source={provMap.items} />
                      </div>
                      <div className="mt-1 divide-y divide-zinc-100 rounded-lg border border-zinc-200 text-xs">
                        {review.line_items.slice(0, 4).map((item, idx) => (
                          <div key={idx} className="flex justify-between p-2">
                            <span className="truncate pr-2">{item.description ?? 'Item'}</span>
                            <span className="font-mono tabular-nums">{formattedAmount(item.amount, review.currency)}</span>
                          </div>
                        ))}
                        {review.line_items.length > 4 && (
                          <p className="p-2 text-center text-xs text-zinc-400">
                            +{review.line_items.length - 4} more items
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </>
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

      {/* Supplier Correction Email Modal Dialog */}
      <Dialog
        open={emailModalOpen}
        title="Supplier correction request"
        description="Generated by Azure OpenAI based on Northstar review findings. Northstar never sends emails automatically — review, copy, and send via your email client."
        onClose={() => setEmailModalOpen(false)}
      >
        <div className="p-6 space-y-4">
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold text-zinc-700">Subject</label>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => copyToClipboard(emailDraft?.subject ?? '', 'Subject')}
                className="text-xs h-6 px-2"
              >
                Copy subject
              </Button>
            </div>
            <input
              type="text"
              readOnly
              value={emailDraft?.subject ?? ''}
              className="w-full rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs font-medium text-zinc-900 select-all"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold text-zinc-700">Email Body</label>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => copyToClipboard(emailDraft?.body ?? '', 'Body')}
                className="text-xs h-6 px-2"
              >
                Copy body
              </Button>
            </div>
            <textarea
              readOnly
              rows={10}
              value={emailDraft?.body ?? ''}
              className="w-full rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs font-mono text-zinc-800 leading-relaxed select-all"
            />
          </div>

          {copyFeedback && (
            <p className="text-xs font-medium text-emerald-600 animate-pulse">
              ✓ {copyFeedback} copied to clipboard!
            </p>
          )}

          <div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-100">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                if (!emailDraft) return
                const fullText = `Subject: ${emailDraft.subject}\n\n${emailDraft.body}`
                copyToClipboard(fullText, 'Complete email')
              }}
            >
              Copy entire email
            </Button>
            <Button size="sm" onClick={() => setEmailModalOpen(false)}>
              Close
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
