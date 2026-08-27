import SourceCard from './SourceCard'
import type { Message } from '../App'

export default function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex flex-col gap-3 w-[90%] mx-auto ${isUser ? 'items-end' : 'items-start'}`}>
      <div
        className={`rounded-2xl text-lg leading-relaxed whitespace-pre-wrap px-4 py-3 mt-2.5 mb-2 max-w-[650px]
          ${isUser
            ? 'bg-violet-600 text-white rounded-br-sm'
            : 'bg-gray-800 text-gray-100 rounded-bl-sm'
          }`}
      >
        {message.content}
        {message.streaming && message.content.length > 0 && (
          <span className="inline-block w-0.5 h-4 bg-gray-400 ml-0.5 align-middle animate-pulse" />
        )}
      </div>

      {message.sources && message.sources.length > 0 && (
        <div className="w-full space-y-2 max-w-[650px]">
          <p className="text-xs text-gray-500 font-medium uppercase tracking-wide px-1">Sources</p>
          {message.sources.map((source, i) => (
            <SourceCard
              key={`${source.file_path}:${source.name}:${source.start_line}`}
              source={source}
              index={i + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}
