const STAGES = [
  { id: 1, label: 'Extraction' },
  { id: 2, label: 'Stage 2' },
  { id: 3, label: 'Page-wise' },
  { id: 4, label: 'Overview' },
  { id: 5, label: 'Word Doc' },
]

function detectActiveStage(logs) {
  let active = 1
  for (const line of logs) {
    const m = line.match(/[Ss]tage\s+(\d)/)
    if (m) active = Math.max(active, parseInt(m[1]))
  }
  return active
}

export default function StageProgress({ logs, status }) {
  const active = detectActiveStage(logs)

  return (
    <div className="flex gap-2 flex-wrap">
      {STAGES.map((s) => {
        const done = status === 'completed' || s.id < active
        const running = status === 'running' && s.id === active
        const pending = !done && !running

        let cls = 'px-3 py-1 rounded-full text-xs font-medium border '
        if (done)    cls += 'bg-emerald-900 border-emerald-600 text-emerald-300'
        else if (running) cls += 'bg-blue-900 border-blue-500 text-blue-200 animate-pulse'
        else         cls += 'bg-gray-800 border-gray-600 text-gray-400'

        return (
          <span key={s.id} className={cls}>
            {done ? '✓ ' : running ? '● ' : ''}{s.id}. {s.label}
          </span>
        )
      })}
    </div>
  )
}
