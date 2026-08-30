import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import SourceCard from './SourceCard'
import type { Message } from '../App'

function AssistantContent({ content, streaming }: { content: string; streaming?: boolean }) {
  const cursor = streaming && content.length > 0
    ? <span className="inline-block w-0.5 h-4 bg-gray-400 ml-0.5 align-middle animate-pulse" />
    : null

  return (
    <div className="prose prose-invert prose-sm max-w-none
      prose-p:my-2 prose-p:leading-relaxed
      prose-code:bg-gray-700 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none
      prose-pre:bg-gray-900 prose-pre:border prose-pre:border-gray-700
      prose-headings:text-gray-100
      prose-strong:text-gray-100
      prose-li:my-0.5
      prose-ol:my-2 prose-ul:my-2
    ">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      {cursor}
    </div>
  )
}

export default function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex flex-col gap-3 w-[90%] mx-auto ${isUser ? 'items-end' : 'items-start'}`}>
      <div
        className={`rounded-2xl text-lg leading-relaxed px-4 py-3 mt-2.5 mb-2 max-w-[650px]
          ${isUser
            ? 'bg-violet-600 text-white rounded-br-sm whitespace-pre-wrap'
            : 'bg-gray-800 text-gray-100 rounded-bl-sm'
          }`}
      >
        {isUser
          ? <>
              {message.content}
              {message.streaming && message.content.length > 0 && (
                <span className="inline-block w-0.5 h-4 bg-gray-400 ml-0.5 align-middle animate-pulse" />
              )}
            </>
          : <AssistantContent content={message.content} streaming={message.streaming} />
        }
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
