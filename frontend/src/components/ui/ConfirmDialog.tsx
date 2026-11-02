import { useEffect, useRef, type ReactNode } from 'react'
import { Button } from './Button'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description?: ReactNode
  confirmLabel: string
  busy?: boolean
  busyLabel?: string
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  busy = false,
  busyLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      aria-labelledby="confirm-dialog-title"
      onCancel={(event) => {
        event.preventDefault()
        if (!busy) onCancel()
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel()
      }}
      className="confirm-dialog m-auto w-full max-w-sm rounded-xl border border-zinc-200 bg-white p-0 text-zinc-950 shadow-xl backdrop:bg-zinc-950/30"
    >
      <div className="p-6">
        <h2 id="confirm-dialog-title" className="text-base font-semibold text-zinc-950">
          {title}
        </h2>
        {description && <div className="mt-2 text-sm leading-6 text-zinc-600">{description}</div>}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" size="sm" disabled={busy} onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="danger" size="sm" disabled={busy} onClick={onConfirm}>
            {busy ? busyLabel ?? confirmLabel : confirmLabel}
          </Button>
        </div>
      </div>
    </dialog>
  )
}
