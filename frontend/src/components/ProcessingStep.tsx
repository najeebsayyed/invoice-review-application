import { useEffect, useState } from 'react'
import { PROCESSING_STEPS, processingStepAt } from '../lib/processing-progress'
import { Card } from './ui/Card'

export function ProcessingStep({ filename }: { filename: string }) {
  const [elapsedMs, setElapsedMs] = useState(0)

  useEffect(() => {
    const startedAt = Date.now()
    const timer = window.setInterval(() => {
      const nextElapsedMs = Date.now() - startedAt
      setElapsedMs(nextElapsedMs)
      if (nextElapsedMs >= 12000) window.clearInterval(timer)
    }, 250)
    return () => window.clearInterval(timer)
  }, [])

  const activeIndex = processingStepAt(elapsedMs)

  return (
    <main className="mx-auto flex min-h-[70vh] max-w-2xl items-center justify-center px-6 py-12 text-center">
      <Card className="w-full">
        <div className="p-8 sm:p-10">
          <div className="flex justify-center">
            <div
              className="h-9 w-9 animate-spin rounded-full border-2 border-zinc-200 border-t-zinc-800"
              aria-hidden="true"
            />
          </div>
          <p className="mt-6 text-sm text-zinc-500">Step 2 of 3</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Processing document</h1>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-zinc-600">
            Working through the review pipeline for{' '}
            <span className="font-medium text-zinc-800">{filename}</span>.
          </p>

          <ol className="mx-auto mt-8 max-w-lg space-y-2 text-left" aria-label="Document processing progress">
            {PROCESSING_STEPS.map((step, index) => {
              const completed = index < activeIndex
              const active = index === activeIndex
              return (
                <li
                  key={step.title}
                  className={`flex gap-4 rounded-lg border p-4 transition-colors ${
                    active ? 'border-zinc-300 bg-zinc-50' : 'border-zinc-200 bg-white'
                  }`}
                >
                  <span
                    className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-medium ${
                      completed
                        ? 'bg-zinc-900 text-white'
                        : active
                          ? 'border border-zinc-300 bg-white text-zinc-900'
                          : 'bg-zinc-100 text-zinc-500'
                    }`}
                  >
                    {completed ? (
                      '✓'
                    ) : active ? (
                      <span
                        className="h-3 w-3 animate-spin rounded-full border border-zinc-300 border-t-zinc-900"
                        aria-hidden="true"
                      />
                    ) : (
                      index + 1
                    )}
                  </span>
                  <div>
                    <p
                      className={`text-sm font-medium ${
                        active || completed ? 'text-zinc-900' : 'text-zinc-500'
                      }`}
                    >
                      {step.title}
                    </p>
                    <p className="mt-1 text-sm leading-5 text-zinc-500">{step.description}</p>
                  </div>
                </li>
              )
            })}
          </ol>

          <p aria-live="polite" className="mt-6 text-xs text-zinc-500">
            Current step: {PROCESSING_STEPS[activeIndex].title}
          </p>
        </div>
      </Card>
    </main>
  )
}
