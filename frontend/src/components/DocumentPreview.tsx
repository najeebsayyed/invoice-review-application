import { useEffect, useState } from 'react'

interface DocumentPreviewProps {
  src: string
  filename: string
  contentType: string
  className?: string
}

export function DocumentPreview({ src, filename, contentType, className = '' }: DocumentPreviewProps) {
  const isImage = contentType.startsWith('image/')
  const isDirectUrl = src.startsWith('blob:') || src.startsWith('data:')

  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(!isDirectUrl)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (isDirectUrl) return

    let active = true
    let createdObjectUrl: string | null = null

    fetch(src, { credentials: 'include' })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Failed to load document (${res.status})`)
        }
        return res.blob()
      })
      .then((blob) => {
        if (!active) return
        createdObjectUrl = URL.createObjectURL(blob)
        setBlobUrl(createdObjectUrl)
        setLoading(false)
      })
      .catch((err) => {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Could not load document preview.')
        setLoading(false)
      })

    return () => {
      active = false
      if (createdObjectUrl) {
        URL.revokeObjectURL(createdObjectUrl)
      }
    }
  }, [src, isDirectUrl])

  const previewUrl = isDirectUrl ? src : blobUrl
  const frameClass = `h-full min-h-[580px] w-full rounded-xl border border-zinc-200 bg-zinc-100 ${className}`

  if (loading) {
    return (
      <div className={`${frameClass} flex flex-col items-center justify-center p-8 text-center`}>
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-900" />
        <p className="mt-4 text-sm font-medium text-zinc-700">Loading document preview...</p>
        <p className="mt-1 text-xs text-zinc-500">{filename}</p>
      </div>
    )
  }

  if (error || !previewUrl) {
    return (
      <div className={`${frameClass} flex flex-col items-center justify-center p-8 text-center`}>
        <p className="text-sm font-medium text-zinc-900">Preview unavailable in-frame</p>
        <p className="mt-1 text-xs text-zinc-500">
          {error ?? 'Your browser blocked the embedded document preview.'}
        </p>
        <div className="mt-4 flex items-center gap-2">
          <a
            href={src}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-800"
          >
            Open in new tab
          </a>
          <a
            href={src}
            download={filename}
            className="inline-flex items-center rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50"
          >
            Download file
          </a>
        </div>
      </div>
    )
  }

  if (isImage) {
    return (
      <div className={`${frameClass} flex items-center justify-center overflow-hidden p-4`}>
        <img
          src={previewUrl}
          alt={`Source document: ${filename}`}
          className="max-h-[720px] max-w-full rounded object-contain shadow-sm"
        />
      </div>
    )
  }

  return (
    <div className={`${frameClass} flex flex-col overflow-hidden`}>
      <div className="flex items-center justify-between border-b border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-600">
        <span className="truncate font-medium">{filename}</span>
        <div className="flex items-center gap-3">
          <a
            href={src}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-zinc-600 hover:text-zinc-950"
          >
            Open full view ↗
          </a>
          <a
            href={src}
            download={filename}
            className="font-medium text-zinc-600 hover:text-zinc-950"
          >
            Download
          </a>
        </div>
      </div>
      <iframe
        src={previewUrl}
        title={`Source document: ${filename}`}
        className="h-full min-h-[540px] w-full flex-1 border-0 bg-white"
      />
    </div>
  )
}
