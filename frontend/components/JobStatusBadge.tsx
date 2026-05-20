interface Props {
  status: string
}

const STATUS_STYLES: Record<string, string> = {
  done: 'text-green-400 bg-green-400/10 border-green-400/20',
  running: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20',
  pending: 'text-blue-400 bg-blue-400/10 border-blue-400/20',
  failed: 'text-red-400 bg-red-400/10 border-red-400/20',
}

const STATUS_ICONS: Record<string, string> = {
  done: '✓',
  running: '⟳',
  pending: '○',
  failed: '✕',
}

export default function JobStatusBadge({ status }: Props) {
  const styles = STATUS_STYLES[status] ?? 'text-gray-400 bg-gray-400/10 border-gray-400/20'
  const icon = STATUS_ICONS[status] ?? '?'
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${styles}`}>
      <span>{icon}</span>
      <span className="capitalize">{status}</span>
    </span>
  )
}
