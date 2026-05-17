import { useEffect, useRef } from 'react'

export default function LogViewer({ logs }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length])

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg h-96 overflow-y-auto font-mono text-xs p-3 space-y-0.5">
      {logs.length === 0 ? (
        <span className="text-gray-500">Waiting for output...</span>
      ) : (
        logs.map((line, i) => (
          <div
            key={i}
            className={
              line.includes('ERROR') || line.includes('error')
                ? 'text-red-400'
                : line.includes('✓') || line.includes('complete') || line.includes('done')
                ? 'text-emerald-400'
                : line.startsWith('[') && line.includes('Stage')
                ? 'text-blue-300 font-semibold'
                : 'text-gray-300'
            }
          >
            {line || ' '}
          </div>
        ))
      )}
      <div ref={bottomRef} />
    </div>
  )
}
