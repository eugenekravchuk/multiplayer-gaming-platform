import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { Gamepad2, Swords, Users, Trophy, LogOut, Bell } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import { useGameStore } from '../store/gameStore'
import { useWebSocket } from '../hooks/useWebSocket'
import ChatPanel from './ChatPanel'
import NotificationPanel from './NotificationPanel'
import { useState } from 'react'

export default function Layout() {
  useWebSocket()
  const { username, clearAuth } = useAuthStore()
  const { unreadCount } = useGameStore()
  const navigate = useNavigate()
  const [showNotifications, setShowNotifications] = useState(false)
  const [showChat, setShowChat] = useState(false)

  const logout = () => {
    clearAuth()
    navigate('/login')
  }

  const navItems = [
    { to: '/', icon: Gamepad2, label: 'Dashboard', exact: true },
    { to: '/matchmaking', icon: Swords, label: 'Play' },
    { to: '/lobby', icon: Users, label: 'Lobbies' },
    { to: '/leaderboard', icon: Trophy, label: 'Leaderboard' },
  ]

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top Nav */}
      <header className="glass border-b border-brand-700/30 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-2 font-bold text-xl text-brand-400">
              <Gamepad2 className="w-6 h-6" />
              <span>GameZone</span>
            </div>
            <nav className="flex items-center gap-1">
              {navItems.map(({ to, icon: Icon, label, exact }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={exact}
                  className={({ isActive }) =>
                    `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                      isActive
                        ? 'bg-brand-600 text-white'
                        : 'text-slate-400 hover:text-white hover:bg-surface-700'
                    }`
                  }
                >
                  <Icon className="w-4 h-4" />
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            {/* Notifications */}
            <button
              onClick={() => setShowNotifications(!showNotifications)}
              className="relative p-2 rounded-lg text-slate-400 hover:text-white hover:bg-surface-700 transition-all"
            >
              <Bell className="w-5 h-5" />
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full text-xs flex items-center justify-center text-white font-bold">
                  {unreadCount > 9 ? '9+' : unreadCount}
                </span>
              )}
            </button>

            {/* Chat toggle */}
            <button
              onClick={() => setShowChat(!showChat)}
              className="px-3 py-1.5 text-sm rounded-lg bg-surface-700 hover:bg-surface-600 text-slate-300 transition-all"
            >
              Chat
            </button>

            <div className="flex items-center gap-2 pl-3 border-l border-surface-600">
              <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-sm font-bold">
                {username?.[0]?.toUpperCase()}
              </div>
              <span className="text-sm text-slate-300 font-medium">{username}</span>
              <button
                onClick={logout}
                className="p-1.5 rounded text-slate-500 hover:text-red-400 transition-colors"
                title="Logout"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Main content */}
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-7xl mx-auto px-4 py-6">
            <Outlet />
          </div>
        </main>

        {/* Chat Panel */}
        {showChat && (
          <aside className="w-80 border-l border-surface-700 flex flex-col">
            <ChatPanel />
          </aside>
        )}
      </div>

      {/* Notification Panel (overlay) */}
      {showNotifications && (
        <div className="fixed top-16 right-4 z-50 w-80">
          <NotificationPanel onClose={() => setShowNotifications(false)} />
        </div>
      )}
    </div>
  )
}
