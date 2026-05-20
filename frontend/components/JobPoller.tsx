'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { subscribeJobProgress, type ProgressEvent } from '@/lib/api'

interface Props {
  jobId: string
  status: string
}

/**
 * Client-side component that polls via SSE and redirects when the job finishes.
 * Used when the page is loaded and the job is still pending/running.
 */
export default function JobPoller({ jobId, status }: Props) {
  const router = useRouter()

  useEffect(() => {
    if (status !== 'pending' && status !== 'running') return

    let fallbackInterval: ReturnType<typeof setInterval> | null = null
    const cleanup = subscribeJobProgress(
      jobId,
      (_evt: ProgressEvent) => {
        // Progress events received — nothing to display here, parent handles UI
      },
      () => {
        // Done — refresh the server component to show results
        router.refresh()
        cleanup()
      },
      () => {
        // SSE error — fall back to polling every 5 s
        if (fallbackInterval == null) {
          fallbackInterval = setInterval(() => router.refresh(), 5000)
        }
      },
    )

    return () => {
      cleanup()
      if (fallbackInterval != null) {
        clearInterval(fallbackInterval)
      }
    }
  }, [jobId, status, router])

  return null
}
