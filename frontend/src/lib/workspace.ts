/**
 * Utility for managing persistent anonymous workspace identification.
 *
 * Each browser/device generates and retains a cryptographically random UUID
 * stored in localStorage so that invoice histories, dashboard KPIs, and reviews
 * remain completely isolated between different users and devices without
 * requiring registration, login, or passwords.
 */

const WORKSPACE_STORAGE_KEY = 'invoice_review_workspace_id'

export function getWorkspaceId(): string {
  if (typeof window === 'undefined') {
    return ''
  }

  let id = localStorage.getItem(WORKSPACE_STORAGE_KEY)
  if (!id) {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      id = crypto.randomUUID()
    } else {
      // RFC4122 v4 UUID fallback if crypto.randomUUID is not supported
      id = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0
        const v = c === 'x' ? r : (r & 0x3) | 0x8
        return v.toString(16)
      })
    }
    localStorage.setItem(WORKSPACE_STORAGE_KEY, id)
  }

  return id
}
