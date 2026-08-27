import { useState } from 'react'
import type { Source } from '../App'

type ChunkType =
  | 'function'
  | 'class'
  | 'module_summary'
  | 'markdown_section'
  | 'shell_script'
  | 'project_metadata'

const CHUNK_TYPE_COLORS: Record<ChunkType, string> = {
  function: 'bg-blue-900 text-blue-300',
  class: 'bg-emerald-900 text-emerald-300',
  module_summary: 'bg-amber-900 text-amber-300',
  markdown_section: 'bg-gray-700 text-gray-300',
  shell_script: 'bg-orange-900 text-orange-300',
  project_metadata: 'bg-pink-900 text-pink-300',
}

interface Props {
  source: Source
  index: number
}

export default function SourceCard({ source, index }: Props) {
  const [open, setOpen] = useState(false)
  const typeColor = CHUNK_TYPE_COLORS[source.chunk_type as ChunkType] ?? 'bg-gray-700 text-gray-300'
  const scorePercent = Math.round(source.score * 100)

  return (
    <button
      onClick={() => setOpen(o => !o)}
      className="w-full text-left rounded-xl border border-gray-700 bg-gray-900 hover:border-gray-600 transition-colors mb-1.5"
    >
      <div className="flex items-center gap-3 px-4 py-3">
        <span className="text-sm text-gray-600 font-mono w-4 shrink-0">{index}</span>

        <span className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${typeColor}`}>
          {source.chunk_type}
        </span>

        <span className="font-mono text-sm text-gray-300 truncate flex-1">
          {source.file_path}
          <span className="text-gray-500"> :: </span>
          {source.name}
        </span>

        <span className="text-sm text-gray-500 shrink-0">
          L{source.start_line}–{source.end_line}
        </span>

        <span
          className={`text-sm font-medium shrink-0 ${
            scorePercent >= 80
              ? 'text-emerald-400'
              : scorePercent >= 60
              ? 'text-amber-400'
              : 'text-gray-500'
          }`}
        >
          {scorePercent}%
        </span>

        <svg
          className={`w-4 h-4 text-gray-600 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>

      {open && (
        <div className="px-4 pb-3 text-sm text-gray-500 border-t border-gray-800 pt-3 font-mono">
          {source.file_path} · lines {source.start_line}–{source.end_line} · score {source.score.toFixed(3)}
        </div>
      )}
    </button>
  )
}
