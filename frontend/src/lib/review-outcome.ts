import type { DocumentStatus, ValidationIssue } from './types'

export interface ReviewOutcome {
  kind: 'passed' | 'attention' | 'failed'
  title: string
  description: string
  errorCount: number
  warningCount: number
}

function noun(count: number, singular: string): string {
  return `${count} ${singular}${count === 1 ? '' : 's'}`
}

export function summarizeReview(
  status: DocumentStatus,
  issues: ValidationIssue[],
): ReviewOutcome {
  const errorCount = issues.filter((issue) => issue.severity === 'error').length
  const warningCount = issues.filter((issue) => issue.severity === 'warning').length

  if (status === 'failed') {
    return {
      kind: 'failed',
      title: 'Processing failed',
      description:
        'The document could not be extracted. Try another file or check the provider configuration.',
      errorCount,
      warningCount,
    }
  }

  if (errorCount > 0) {
    const warningCopy =
      warningCount > 0
        ? ` ${noun(warningCount, 'warning')} also ${warningCount === 1 ? 'needs' : 'need'} review.`
        : ''
    return {
      kind: 'attention',
      title: 'Needs attention',
      description: `${noun(errorCount, 'blocking error')} must be resolved before approval.${warningCopy}`,
      errorCount,
      warningCount,
    }
  }

  if (warningCount > 0) {
    return {
      kind: 'attention',
      title: 'Needs attention',
      description: `${noun(warningCount, 'warning')} should be verified before approval.`,
      errorCount,
      warningCount,
    }
  }

  return {
    kind: 'passed',
    title: 'Passed automatic checks',
    description: 'No validation issues were found. Confirm the GL account before approval.',
    errorCount: 0,
    warningCount: 0,
  }
}
