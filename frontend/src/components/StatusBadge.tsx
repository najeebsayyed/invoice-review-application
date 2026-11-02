import type { DocumentStatus } from '../lib/types'
import { Badge } from './ui/Badge'

const labels: Record<DocumentStatus, string> = {
  processing: 'Processing',
  ready: 'Ready',
  needs_review: 'Needs review',
  approved: 'Approved',
  rejected: 'Rejected',
  failed: 'Failed',
}

const variants: Record<
  DocumentStatus,
  'default' | 'secondary' | 'outline' | 'success' | 'warning' | 'destructive'
> = {
  processing: 'secondary',
  ready: 'success',
  needs_review: 'warning',
  approved: 'success',
  rejected: 'destructive',
  failed: 'destructive',
}

export function StatusBadge({ status }: { status: DocumentStatus }) {
  return <Badge variant={variants[status]}>{labels[status]}</Badge>
}
