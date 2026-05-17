import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api/client'
import LogViewer from '../components/LogViewer'
import StageProgress from '../components/StageProgress'

const STATUS_COLORS = {
  completed: 'bg-emerald-900 text-emerald-300 border-emerald-600',
  failed: 'bg-red-900 text-red-300 border-red-600',
  running: 'bg-blue-900 text-blue-300 border-blue-600',
  pending: 'bg-yellow-900 text-yellow-300 border-yellow-600',
}

export default function RunDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [run, setRun] = useState(null)
  const [logs, setLogs] = useState([])
  const esRef = useRef(null)

  // Poll run status every 3s until terminal state
  useEffect(() => {
    let interval
    async function fetchRun() {
      const { data } = await api.get(`/runs/${id}`)
      setRun(data)
      if (data.status === 'completed' || data.status === 'failed') {
        clearInterval(interval)
      }
    }
    fetchRun()
    interval = setInterval(fetchRun, 3000)
    return () => clearInterval(interval)
  }, [id])

  // SSE log stream
  useEffect(() => {
    const es = new EventSource(`/api/runs/${id}/logs`)
    esRef.current = es

    es.onmessage = (e) => {
      if (e.data === '[DONE]') {
        es.close()
        return
      }
      setLogs(prev => [...prev, e.data])
    }

    es.onerror = () => es.close()

    return () => es.close()
  }, [id])

  function download() {
    window.open(`/api/runs/${id}/download`, '_blank')
  }

  if (!run) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center text-gray-400">
        Loading...
      </div>
    )
  }

  const statusCls = STATUS_COLORS[run.status] || 'bg-gray-800 text-gray-300 border-gray-600'
  const elapsed = run.finished_at
    ? Math.round((new Date(run.finished_at) - new Date(run.started_at)) / 1000)
    : null

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-8">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate('/')}
          className="text-gray-400 hover:text-white text-sm transition-colors"
        >
          ← Back
        </button>
        <span className="text-gray-600">|</span>
        <span className="font-mono text-sm text-gray-400">{run.id}</span>
        <span className="font-semibold text-white">{run.dashboard}</span>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${statusCls}`}>
          {run.status}
        </span>
        {elapsed && (
          <span className="text-xs text-gray-500 ml-auto">{elapsed}s</span>
        )}
      </div>

      {/* Stage progress */}
      <div className="mb-5">
        <StageProgress logs={logs} status={run.status} />
      </div>

      {/* Options used */}
      <div className="mb-4 flex flex-wrap gap-2">
        {Object.entries(run.options)
          .filter(([, v]) => v)
          .map(([k, v]) => (
            <span key={k} className="text-xs bg-gray-800 border border-gray-600 text-gray-400 px-2 py-0.5 rounded">
              {k.replace(/_/g, '-')}{typeof v === 'number' ? `=${v}` : ''}
            </span>
          ))}
      </div>

      {/* Log viewer */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Logs</span>
          <span className="text-xs text-gray-500">{logs.length} lines</span>
        </div>
        <LogViewer logs={logs} />
      </div>

      {/* Download */}
      {run.status === 'completed' && (
        <button
          onClick={download}
          className="px-5 py-2.5 bg-emerald-700 hover:bg-emerald-600 rounded-lg text-sm font-semibold transition-colors"
        >
          ↓ Download Story Guide (.docx)
        </button>
      )}

      {run.status === 'failed' && (
        <p className="text-sm text-red-400 mt-2">
          Pipeline failed (exit code {run.return_code}). Check logs above for details.
        </p>
      )}
    </div>
  )
}
