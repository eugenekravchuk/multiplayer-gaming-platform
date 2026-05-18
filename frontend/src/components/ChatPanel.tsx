import { useState, useRef, useEffect } from 'react'
import { Send } from 'lucide-react'
import { useGameStore } from '../store/gameStore'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAuthStore } from '../store/authStore'

export default function ChatPanel() {
  const [input, setInput] = useState('')
  const { messages, activeChannel } = useGameStore()
  const { send } = useWebSocket()
  const { playerId } = useAuthStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  const channelMessages = messages[activeChannel] ?? []

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [channelMessages])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim()) return
    send('chat.message', { channel_id: activeChannel, content: input.trim() })
    setInput('')
  }

  const formatTime = (ts: string) =>
    new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

  return (
    <div className="flex flex-col h-full bg-surface-800">
      <div className="p-3 border-b border-surface-700 flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-300">
          #{activeChannel}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
        {channelMessages.length === 0 && (
          <p className="text-center text-slate-600 text-xs mt-4">No messages yet</p>
        )}
        {channelMessages.map((msg) => (
          <div key={msg.id} className={`flex flex-col ${msg.sender_id === playerId ? 'items-end' : 'items-start'}`}>
            <span className="text-xs text-slate-500 mb-0.5 px-1">
              {msg.sender_id === playerId ? 'You' : (msg.sender_username ?? msg.sender_id.slice(-6))}
              {' · '}{formatTime(msg.timestamp)}
            </span>
            <div
              className={`max-w-[85%] px-3 py-2 rounded-xl text-sm ${
                msg.sender_id === playerId
                  ? 'bg-brand-600 text-white rounded-br-sm'
                  : 'bg-surface-700 text-slate-200 rounded-bl-sm'
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={submit} className="p-3 border-t border-surface-700 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message..."
          className="flex-1 bg-surface-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 outline-none focus:ring-1 focus:ring-brand-500"
        />
        <button
          type="submit"
          disabled={!input.trim()}
          className="p-2 rounded-lg bg-brand-600 hover:bg-brand-500 disabled:opacity-40 transition-colors"
        >
          <Send className="w-4 h-4 text-white" />
        </button>
      </form>
    </div>
  )
}
