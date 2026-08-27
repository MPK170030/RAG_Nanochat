import { useState, useRef, useEffect } from 'react'
import ChatInput from './components/ChatInput'
import MessageBubble from './components/MessageBubble'
import Sidebar from './components/Sidebar'

export interface Source {
  file_path: string
  chunk_type: string
  name: string
  start_line: number
  end_line: number
  score: number
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  streaming?: boolean
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [k, setK] = useState(5)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSubmit(query: string) {
    setError(null)
    setMessages(prev => [
      ...prev,
      { role: 'user', content: query },
      { role: 'assistant', content: '', streaming: true },
    ])
    setIsStreaming(true)

    try {
      const res = await fetch('/ask/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, k }),
      })

      if (!res.ok || !res.body) {
        const data: { detail?: string } = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? `Server error ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buf += decoder.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() ?? ''

        for (const part of parts) {
          if (!part.startsWith('data: ')) continue
          const payload = JSON.parse(part.slice(6)) as
            | { token: string }
            | { done: true; sources: Source[] }

          if ('token' in payload) {
            setMessages(prev => {
              const msgs = [...prev]
              const last = { ...msgs[msgs.length - 1] }
              last.content += payload.token
              return [...msgs.slice(0, -1), last]
            })
          } else {
            setMessages(prev => {
              const msgs = [...prev]
              const last = { ...msgs[msgs.length - 1] }
              last.sources = payload.sources
              last.streaming = false
              return [...msgs.slice(0, -1), last]
            })
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setIsStreaming(false)
    }
  }

  function handleClear() {
    setMessages([])
    setError(null)
  }

  const lastMsg = messages[messages.length - 1]
  const showBounce = isStreaming && (!lastMsg || lastMsg.content === '')

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      <Sidebar k={k} onKChange={setK} onClear={handleClear} messageCount={messages.length} />

      <div className="flex flex-col flex-1 min-w-0">
        <header className="flex items-center gap-3 px-6 py-4 border-b border-gray-800 bg-gray-900">
          <div className="w-2 h-2 rounded-full bg-emerald-400" />
          <span className="font-mono text-sm text-gray-400">nanochat RAG</span>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
          {messages.length === 0 && !isStreaming && (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-600">
              <p className="text-lg font-medium">Ask anything about the nanochat codebase</p>
              <p className="text-sm">e.g. &quot;How does nanochat implement rotary embeddings?&quot;</p>
            </div>
          )}

          {messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} />
          ))}

          {showBounce && (
            <div className="flex gap-2 items-center text-gray-500 w-[90%] mx-auto">
              <span className="w-2 h-2 rounded-full bg-gray-500 animate-bounce [animation-delay:0ms]" />
              <span className="w-2 h-2 rounded-full bg-gray-500 animate-bounce [animation-delay:150ms]" />
              <span className="w-2 h-2 rounded-full bg-gray-500 animate-bounce [animation-delay:300ms]" />
            </div>
          )}

          {error && (
            <div className="px-4 py-3 rounded-lg bg-red-950 border border-red-800 text-red-300 text-sm w-[90%] mx-auto">
              {error}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <ChatInput onSubmit={handleSubmit} disabled={isStreaming} />
      </div>
    </div>
  )
}
