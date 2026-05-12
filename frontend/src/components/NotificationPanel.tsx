import { X, Bell } from 'lucide-react'
import { useGameStore } from '../store/gameStore'

interface Props {
  onClose: () => void
}

export default function NotificationPanel({ onClose }: Props) {
  const { notifications, markNotificationsRead } = useGameStore()

  const handleOpen = () => {
    markNotificationsRead()
  }

  const typeColor: Record<string, string> = {
    match: 'bg-green-500',
    ranking: 'bg-yellow-500',
    lobby: 'bg-blue-500',
    score: 'bg-purple-500',
    info: 'bg-slate-500',
    broadcast: 'bg-brand-500',
  }

  return (
    <div className="glass rounded-xl shadow-2xl overflow-hidden" onClick={handleOpen}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-700">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-300">
          <Bell className="w-4 h-4" />
          Notifications
        </div>
        <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="max-h-80 overflow-y-auto">
        {notifications.length === 0 ? (
          <p className="text-center text-slate-600 text-sm py-8">No notifications</p>
        ) : (
          notifications.slice(0, 20).map((n) => (
            <div
              key={n.id}
              className={`px-4 py-3 border-b border-surface-700/50 flex gap-3 ${
                n.read ? 'opacity-50' : ''
              }`}
            >
              <div
                className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${
                  typeColor[n.type] ?? 'bg-slate-500'
                }`}
              />
              <div>
                <p className="text-sm font-medium text-slate-200">{n.title}</p>
                <p className="text-xs text-slate-500 mt-0.5">{n.message}</p>
                <p className="text-xs text-slate-600 mt-1">
                  {new Date(n.created_at).toLocaleTimeString()}
                </p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
