import { apiBaseUrl } from './env'
import type { CorrectionEmail, Document, FieldCorrections, GlAccount } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    credentials: 'include',
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === 'string' && body.detail) {
        message = body.detail
      }
    } catch {
      // Keep the HTTP fallback when the server did not return JSON.
    }
    throw new Error(message)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export function listDocuments(): Promise<Document[]> {
  return request<Document[]>('/api/documents')
}

export function getDocument(id: string): Promise<Document> {
  return request<Document>(`/api/documents/${encodeURIComponent(id)}`)
}

export function uploadDocument(file: File): Promise<Document> {
  const body = new FormData()
  body.append('file', file)
  return request<Document>('/api/documents', { method: 'POST', body })
}

export function listGlAccounts(): Promise<GlAccount[]> {
  return request<GlAccount[]>('/api/accounting/gl-accounts')
}

export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/api/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function selectGlAccount(id: string, glAccountCode: string): Promise<Document> {
  return request<Document>(`/api/documents/${encodeURIComponent(id)}/accounting`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gl_account_code: glAccountCode }),
  })
}

export function decideDocument(id: string, decision: 'approved' | 'rejected'): Promise<Document> {
  return request<Document>(`/api/documents/${encodeURIComponent(id)}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision }),
  })
}

export function updateCorrections(id: string, corrections: FieldCorrections): Promise<Document> {
  return request<Document>(`/api/documents/${encodeURIComponent(id)}/corrections`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(corrections),
  })
}

export function draftCorrectionEmail(id: string): Promise<CorrectionEmail> {
  return request<CorrectionEmail>(`/api/documents/${encodeURIComponent(id)}/correction-email`, {
    method: 'POST',
  })
}

export function documentFileUrl(id: string): string {
  return `${apiBaseUrl}/api/documents/${encodeURIComponent(id)}/file`
}
