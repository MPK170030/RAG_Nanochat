import { useState } from 'react'

interface Props {
  onSubmit: (query: string) => void
  disabled: boolean
}

export default function ChatInput({ onSubmit, disabled }: Props) {
  const [value, setValue] = useState('')

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  function submit() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed)
    setValue('')
  }

  return (
    <div className="px-4 py-4 border-t border-gray-800 bg-gray-900">
      <div className="relative w-[90%] mx-auto">
        <textarea
          className="resize-none rounded-xl bg-gray-800 border border-gray-700 text-gray-100
                     placeholder-gray-500 text-base focus:outline-none focus:border-violet-500
                     transition-colors p-4 pr-[5.5rem] w-full min-h-20"
          rows={1}
          placeholder="Ask a question about the nanochat codebase…"
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />
        <button
          onClick={submit}
          disabled={disabled || !value.trim()}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 px-3.5 py-1.5 rounded-lg
                     bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed
                     text-white text-sm font-medium transition-colors"
        >
          Send
        </button>
      </div>
    </div>
  )
}
