export type DocumentStatus =
  | 'processing'
  | 'ready'
  | 'needs_review'
  | 'approved'
  | 'rejected'
  | 'failed'

export type IssueSeverity = 'error' | 'warning'
export type DocumentType = 'invoice' | 'receipt'
export type ExpenseCategory = 'fuel' | 'meals' | 'travel' | 'supplies' | 'other'

export interface ReviewLineItem {
  description: string | null
  quantity: number | null
  unit_price: string | number | null
  amount: string | number | null
}

export interface ReviewData {
  document_type: DocumentType
  expense_category: ExpenseCategory | null
  vendor_name: string | null
  vendor_vat_id: string | null
  customer_name: string | null
  customer_vat_id: string | null
  invoice_number: string | null
  purchase_order: string | null
  invoice_date: string | null
  due_date: string | null
  currency: string | null
  subtotal: string | number | null
  total_tax: string | number | null
  invoice_total: string | number | null
  amount_due: string | number | null
  line_items: ReviewLineItem[]
  provenance?: Record<string, 'primary' | 'secondary' | 'user'>
  conflicts?: Record<string, { primary: unknown; secondary: unknown }>
}

export interface FieldCorrections {
  vendor_name?: string
  vendor_vat_id?: string
  customer_name?: string
  customer_vat_id?: string
  invoice_number?: string
  purchase_order?: string
  invoice_date?: string
  due_date?: string
  currency?: string
  subtotal?: number | string
  total_tax?: number | string
  invoice_total?: number | string
}

export interface CorrectionEmail {
  subject: string
  body: string
}

export interface ValidationIssue {
  code: string
  field: string | null
  severity: IssueSeverity
  message: string
}

export interface GlAccount {
  code: string
  name: string
  description: string
}

export interface AccountingSuggestion {
  gl_account_code: string
  category: string
  rationale: string
  confidence: number
}

export interface AccountingCoding {
  suggestion: AccountingSuggestion | null
  selected_gl_account_code: string | null
  overridden: boolean
  error_message: string | null
}

export interface DocumentStats {
  total_documents: number
  needs_review_count: number
  ready_count: number
  approved_count: number
  rejected_count: number
  total_spend: number | string
  currency: string
}

export interface Document {
  id: string
  original_filename: string
  content_type: string
  status: DocumentStatus
  classification: Record<string, unknown> | null
  extraction: Record<string, unknown> | null
  validation: Record<string, unknown> | null
  gl_suggestion: {
    account_code: string
    confidence: number
    reasoning: string
  } | null
  review_data: ReviewData | null
  accounting_coding: AccountingCoding | null
  issues: ValidationIssue[]
  error_message: string | null
  created_at: string
  updated_at: string
}
