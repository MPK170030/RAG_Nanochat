interface Props {
  k: number
  onKChange: (k: number) => void
  onClear: () => void
  messageCount: number
}

export default function Sidebar({ k, onKChange, onClear, messageCount }: Props) {
  return (
    <aside className="w-64 shrink-0 flex flex-col border-r border-gray-800 bg-gray-900 px-3 py-6 gap-6">
      <div>
        <p className="text-lg font-bold text-gray-100 tracking-tight mb-1">NanoChat RAG</p>
        <p className="text-sm text-gray-400">Karpathy&apos;s codebase, indexed.</p>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium text-gray-300">
          Retrieved sources (k = {k})
        </label>
        <input
          type="range"
          min={1}
          max={10}
          value={k}
          onChange={e => onKChange(Number(e.target.value))}
          className="w-full accent-violet-500"
        />
        <p className="text-sm text-gray-400">Chunks sent as context to the LLM.</p>
      </div>

      <div className="space-y-2">
        <p className="text-sm font-medium text-gray-300">Model</p>
        <p className="text-sm font-mono text-gray-400">qwen/qwen3.6-27b</p>
        <p className="text-sm font-medium text-gray-300 mt-2">Embeddings</p>
        <p className="text-sm font-mono text-gray-400">bge-small-en-v1.5</p>
        <p className="text-sm font-medium text-gray-300 mt-2">Vector store</p>
        <p className="text-sm font-mono text-gray-400">Chroma (local)</p>
      </div>

      <div className="mt-auto">
        <button
          onClick={onClear}
          disabled={messageCount === 0}
          className="w-full px-3 py-2 rounded-lg border border-gray-700 text-sm text-gray-300
                     hover:border-gray-600 hover:text-gray-200 disabled:opacity-30 disabled:cursor-not-allowed
                     transition-colors"
        >
          Clear conversation
        </button>
      </div>
    </aside>
  )
}
