import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import LogViewer from '../components/LogViewer'
import StageProgress from '../components/StageProgress'

const STATUS_COLORS = {
  completed: 'bg-emerald-900 text-emerald-300 border-emerald-600',
  failed:    'bg-red-900 text-red-300 border-red-600',
  running:   'bg-blue-900 text-blue-300 border-blue-600',
  pending:   'bg-yellow-900 text-yellow-300 border-yellow-600',
}

const EMPTY_FORM = {
  name: '',
  display_name: '',
  domain: '',
  users: '',
  pain_points: '',
}

export default function Home() {
  const navigate = useNavigate()
  const [dashConfig, setDashConfig] = useState({})
  const [recentRuns, setRecentRuns] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [smFiles, setSmFiles] = useState([])
  const [rpFiles, setRpFiles] = useState([])
  const [smFolderName, setSmFolderName] = useState('')
  const [rpFolderName, setRpFolderName] = useState('')
  const [errors, setErrors] = useState({})
  const [runId, setRunId] = useState(null)
  const [run, setRun] = useState(null)
  const [logs, setLogs] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(null)

  const smInputRef = useRef(null)
  const rpInputRef = useRef(null)
  const esRef = useRef(null)

  // Set webkitdirectory on hidden inputs (non-standard attribute needs imperative set)
  useEffect(() => {
    if (smInputRef.current) smInputRef.current.setAttribute('webkitdirectory', '')
    if (rpInputRef.current) rpInputRef.current.setAttribute('webkitdirectory', '')
  }, [])

  useEffect(() => {
    Promise.all([
      api.get('/dashboards/config'),
      api.get('/runs'),
    ]).then(([cfgRes, runsRes]) => {
      setDashConfig(cfgRes.data)
      setRecentRuns(runsRes.data.slice(0, 5))
    })
  }, [])

  function onNameChange(value) {
    const known = dashConfig[value] || {}
    setForm(p => ({
      ...p,
      name: value,
      display_name: known.display_name || p.display_name,
      domain: known.domain || p.domain,
      users: known.users || p.users,
      pain_points: known.common_pain_points
        ? known.common_pain_points.join('\n')
        : p.pain_points,
    }))
    setErrors(e => ({ ...e, name: '' }))
  }

  function setField(key, value) {
    setForm(p => ({ ...p, [key]: value }))
    setErrors(e => ({ ...e, [key]: '' }))
  }

  function handleSmChange(e) {
    const files = Array.from(e.target.files)
    setSmFiles(files)
    setSmFolderName(files.length > 0 ? files[0].webkitRelativePath.split('/')[0] : '')
    setErrors(e2 => ({ ...e2, sm: '' }))
  }

  function handleRpChange(e) {
    const files = Array.from(e.target.files)
    setRpFiles(files)
    setRpFolderName(files.length > 0 ? files[0].webkitRelativePath.split('/')[0] : '')
    setErrors(e2 => ({ ...e2, rp: '' }))
  }

  function validate() {
    const e = {}
    if (!form.name.trim()) e.name = 'Dashboard ID is required'
    else if (!/^[a-z0-9-]+$/.test(form.name.trim())) e.name = 'Lowercase letters, numbers, hyphens only'
    if (!form.display_name.trim()) e.display_name = 'Display name is required'
    if (smFiles.length === 0) e.sm = 'Select your .SemanticModel folder'
    if (rpFiles.length === 0) e.rp = 'Select your .Report folder'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  async function generate() {
    if (!validate()) return
    setSubmitting(true)
    setUploadProgress('Uploading files…')
    try {
      const pain_points = form.pain_points
        .split('\n').map(s => s.trim()).filter(Boolean)

      const fd = new FormData()
      fd.append('name', form.name.trim())
      fd.append('display_name', form.display_name.trim())
      fd.append('domain', form.domain.trim())
      fd.append('users', form.users.trim())
      fd.append('common_pain_points', JSON.stringify(pain_points))

      const smPaths = []
      for (const file of smFiles) {
        fd.append('sm_files', file)
        smPaths.push(file.webkitRelativePath)
      }
      fd.append('sm_paths', JSON.stringify(smPaths))

      const rpPaths = []
      for (const file of rpFiles) {
        fd.append('rp_files', file)
        rpPaths.push(file.webkitRelativePath)
      }
      fd.append('rp_paths', JSON.stringify(rpPaths))

      await api.post('/dashboards/setup', fd)

      setUploadProgress('Starting pipeline…')
      const { data } = await api.post('/runs', { dashboard: form.name.trim() })
      setRunId(data.id)
      setRun(data)
      setLogs([])
      setUploadProgress(null)

      const es = new EventSource(`/api/runs/${data.id}/logs`)
      esRef.current = es
      es.onmessage = (e) => {
        if (e.data === '[DONE]') { es.close(); return }
        setLogs(prev => [...prev, e.data])
      }
      es.onerror = () => es.close()
    } catch (err) {
      const msg = err?.response?.data?.detail || 'Upload failed. Check the server logs.'
      setErrors({ _global: msg })
      setUploadProgress(null)
    } finally {
      setSubmitting(false)
    }
  }

  useEffect(() => {
    if (!runId) return
    const interval = setInterval(async () => {
      const { data } = await api.get(`/runs/${runId}`)
      setRun(data)
      if (data.status === 'completed' || data.status === 'failed') clearInterval(interval)
    }, 3000)
    return () => clearInterval(interval)
  }, [runId])

  function download() {
    window.open(`/api/runs/${runId}/download`, '_blank')
  }

  function newRun() {
    if (esRef.current) { esRef.current.close(); esRef.current = null }
    setRunId(null); setRun(null); setLogs([])
    setForm(EMPTY_FORM)
    setSmFiles([]); setRpFiles([])
    setSmFolderName(''); setRpFolderName('')
    setErrors({}); setUploadProgress(null)
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <div className="max-w-2xl mx-auto px-6 py-10">

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white tracking-tight">Story Guide Generator</h1>
          <p className="text-gray-400 mt-1.5 text-sm">
            Fill in your dashboard details and upload input files to generate a story guide.
          </p>
        </div>

        {/* Hidden folder inputs */}
        <input
          ref={smInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleSmChange}
        />
        <input
          ref={rpInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleRpChange}
        />

        {/* ── FORM ── */}
        {!runId && (
          <div className="space-y-5">

            {errors._global && (
              <div className="bg-red-950 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-3">
                {errors._global}
              </div>
            )}

            {/* Dashboard identity */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Dashboard</p>

              <div>
                <label className="text-xs text-gray-400 mb-1.5 block">
                  Dashboard ID
                  <span className="text-gray-600 font-normal ml-1">lowercase, hyphens — e.g. risk-dash</span>
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={e => onNameChange(e.target.value)}
                  placeholder="my-dashboard"
                  className={`w-full bg-gray-800 border rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none transition-colors ${errors.name ? 'border-red-500' : 'border-gray-600 focus:border-blue-500'}`}
                />
                {errors.name && <p className="text-xs text-red-400 mt-1">{errors.name}</p>}
              </div>

              <div>
                <label className="text-xs text-gray-400 mb-1.5 block">Display Name</label>
                <input
                  type="text"
                  value={form.display_name}
                  onChange={e => setField('display_name', e.target.value)}
                  placeholder="Risk Management Dashboard"
                  className={`w-full bg-gray-800 border rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none transition-colors ${errors.display_name ? 'border-red-500' : 'border-gray-600 focus:border-blue-500'}`}
                />
                {errors.display_name && <p className="text-xs text-red-400 mt-1">{errors.display_name}</p>}
              </div>
            </div>

            {/* Details */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Details</p>

              <div>
                <label className="text-xs text-gray-400 mb-1.5 block">Domain</label>
                <input
                  type="text"
                  value={form.domain}
                  onChange={e => setField('domain', e.target.value)}
                  placeholder="Healthcare risk adjustment — HCC coding, RAF scores, gap closure"
                  className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500 transition-colors"
                />
              </div>

              <div>
                <label className="text-xs text-gray-400 mb-1.5 block">Users / Audience</label>
                <input
                  type="text"
                  value={form.users}
                  onChange={e => setField('users', e.target.value)}
                  placeholder="Care Manager, Medical Director, Payer Analyst"
                  className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500 transition-colors"
                />
              </div>

              <div>
                <label className="text-xs text-gray-400 mb-1.5 block">
                  Common Pain Points
                  <span className="text-gray-600 font-normal ml-1">(one per line)</span>
                </label>
                <textarea
                  rows={4}
                  value={form.pain_points}
                  onChange={e => setField('pain_points', e.target.value)}
                  placeholder={"Numbers differ from colleague\nWhich filter to set first\nYoY showing blank or zero"}
                  className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500 transition-colors resize-none"
                />
              </div>
            </div>

            {/* Input Files — folder upload */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Input Files</p>

              {/* Semantic Model picker */}
              <div>
                <p className="text-xs text-gray-400 mb-2">Semantic Model folder</p>
                <button
                  type="button"
                  onClick={() => smInputRef.current?.click()}
                  className={`w-full flex items-center gap-3 border rounded-lg px-4 py-3 text-sm transition-colors text-left ${
                    smFolderName
                      ? 'border-blue-500 bg-blue-950'
                      : errors.sm
                      ? 'border-red-500 bg-gray-800'
                      : 'border-gray-600 bg-gray-800 hover:border-gray-400'
                  }`}
                >
                  <span className="text-lg shrink-0">{smFolderName ? '📁' : '📂'}</span>
                  {smFolderName ? (
                    <div className="min-w-0">
                      <p className="text-gray-100 font-mono text-xs truncate">{smFolderName}</p>
                      <p className="text-gray-500 text-xs mt-0.5">{smFiles.length} files selected</p>
                    </div>
                  ) : (
                    <span className="text-gray-400">Choose .SemanticModel folder…</span>
                  )}
                  {smFolderName && (
                    <span className="ml-auto text-xs text-gray-500 shrink-0">Change</span>
                  )}
                </button>
                {errors.sm && <p className="text-xs text-red-400 mt-1">{errors.sm}</p>}
              </div>

              {/* Report picker */}
              <div>
                <p className="text-xs text-gray-400 mb-2">Report folder</p>
                <button
                  type="button"
                  onClick={() => rpInputRef.current?.click()}
                  className={`w-full flex items-center gap-3 border rounded-lg px-4 py-3 text-sm transition-colors text-left ${
                    rpFolderName
                      ? 'border-blue-500 bg-blue-950'
                      : errors.rp
                      ? 'border-red-500 bg-gray-800'
                      : 'border-gray-600 bg-gray-800 hover:border-gray-400'
                  }`}
                >
                  <span className="text-lg shrink-0">{rpFolderName ? '📁' : '📂'}</span>
                  {rpFolderName ? (
                    <div className="min-w-0">
                      <p className="text-gray-100 font-mono text-xs truncate">{rpFolderName}</p>
                      <p className="text-gray-500 text-xs mt-0.5">{rpFiles.length} files selected</p>
                    </div>
                  ) : (
                    <span className="text-gray-400">Choose .Report folder…</span>
                  )}
                  {rpFolderName && (
                    <span className="ml-auto text-xs text-gray-500 shrink-0">Change</span>
                  )}
                </button>
                {errors.rp && <p className="text-xs text-red-400 mt-1">{errors.rp}</p>}
              </div>
            </div>

            {/* Generate button */}
            <button
              disabled={submitting}
              onClick={generate}
              className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 rounded-xl text-sm font-semibold transition-colors"
            >
              {uploadProgress || 'Generate Story Guide'}
            </button>

            {/* Recent Runs */}
            {recentRuns.length > 0 && (
              <div className="pt-2">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Recent Runs</p>
                <div className="space-y-2">
                  {recentRuns.map(r => (
                    <div
                      key={r.id}
                      onClick={() => navigate(`/runs/${r.id}`)}
                      className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-lg px-4 py-3 cursor-pointer hover:border-gray-600 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-sm text-gray-200">{r.dashboard}</span>
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${STATUS_COLORS[r.status] || 'bg-gray-800 text-gray-300 border-gray-600'}`}>
                          {r.status}
                        </span>
                      </div>
                      <span className="text-xs text-gray-500">
                        {new Date(r.started_at).toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── RUN PROGRESS ── */}
        {runId && run && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="font-semibold text-white">{run.dashboard}</span>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${STATUS_COLORS[run.status] || 'bg-gray-800 text-gray-300 border-gray-600'}`}>
                  {run.status}
                </span>
              </div>
              <button onClick={newRun} className="text-xs text-gray-400 hover:text-white transition-colors">
                ← New Run
              </button>
            </div>

            <StageProgress logs={logs} status={run.status} />

            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Logs</span>
                <span className="text-xs text-gray-500">{logs.length} lines</span>
              </div>
              <LogViewer logs={logs} />
            </div>

            {run.status === 'completed' && (
              <button
                onClick={download}
                className="w-full py-3 bg-emerald-700 hover:bg-emerald-600 rounded-xl text-sm font-semibold transition-colors"
              >
                Download Story Guide (.docx)
              </button>
            )}

            {run.status === 'failed' && (
              <p className="text-sm text-red-400">
                Pipeline failed (exit code {run.return_code}). Check logs above.
              </p>
            )}
          </div>
        )}

      </div>
    </div>
  )
}
