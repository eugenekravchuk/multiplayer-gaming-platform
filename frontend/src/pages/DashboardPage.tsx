import { useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { Swords, Users, Trophy, Zap, Activity } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import { useGameStore } from '../store/gameStore'

const API = 'http://localhost:3000'

interface PlayerStats {
  wins: number
  losses: number
  score: number
  rank: number | null
}

export default function DashboardPage() {
  const { username, playerId } = useAuthStore()
  const { currentSession, currentLobby, matchmakingStatus } = useGameStore()
  const navigate = useNavigate()
  const [stats, setStats] = useState<PlayerStats | null>(null)

  useEffect(() => {
    if (!playerId) return
    fetch(`${API}/leaderboard/global/player/${playerId}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setStats({ wins: d.wins ?? 0, losses: d.losses ?? 0, score: d.score ?? 0, rank: d.rank ?? null }))
      .catch(() => {})
  }, [playerId])

  const quickActions = [
    {
      icon: Swords,
      title: 'Quick Match',
      desc: 'Jump into matchmaking instantly',
      color: 'from-brand-600 to-brand-700',
      onClick: () => navigate('/matchmaking'),
    },
    {
      icon: Users,
      title: 'Create Lobby',
      desc: 'Set up a custom game with friends',
      color: 'from-emerald-600 to-emerald-700',
      onClick: () => navigate('/lobby'),
    },
    {
      icon: Trophy,
      title: 'Leaderboard',
      desc: 'See the top ranked players',
      color: 'from-yellow-600 to-yellow-700',
      onClick: () => navigate('/leaderboard'),
    },
  ]

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">
          Welcome back, <span className="text-brand-400">{username}</span>
        </h1>
        <p className="text-slate-400 mt-1">Ready to play?</p>
      </div>

      {/* Active states */}
      {(currentSession || currentLobby || matchmakingStatus !== 'idle') && (
        <div className="glass rounded-xl p-4 border border-yellow-500/20 bg-yellow-500/5">
          <div className="flex items-center gap-2 text-yellow-400 font-semibold mb-2">
            <Activity className="w-4 h-4" />
            Active Session
          </div>
          {matchmakingStatus === 'searching' && (
            <p className="text-slate-300 text-sm">
              🔍 Searching for a match...{' '}
              <button onClick={() => navigate('/matchmaking')} className="text-brand-400 underline">View</button>
            </p>
          )}
          {currentLobby && !currentSession && (
            <p className="text-slate-300 text-sm">
              🏠 In lobby: <strong>{currentLobby.name}</strong> ({currentLobby.players.length}/{currentLobby.max_players} players){' '}
              <button onClick={() => navigate('/lobby')} className="text-brand-400 underline">View</button>
            </p>
          )}
          {currentSession && (
            <p className="text-slate-300 text-sm">
              🎮 Game in progress!{' '}
              <button onClick={() => navigate('/game')} className="text-brand-400 underline">Resume</button>
            </p>
          )}
        </div>
      )}

      {/* Quick Actions */}
      <div>
        <h2 className="text-lg font-semibold text-slate-300 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {quickActions.map(({ icon: Icon, title, desc, color, onClick }) => (
            <button
              key={title}
              onClick={onClick}
              className="glass rounded-xl p-6 text-left hover:scale-[1.02] transition-all group"
            >
              <div className={`inline-flex p-3 rounded-xl bg-gradient-to-br ${color} mb-4`}>
                <Icon className="w-6 h-6 text-white" />
              </div>
              <h3 className="font-semibold text-white group-hover:text-brand-300 transition-colors">
                {title}
              </h3>
              <p className="text-sm text-slate-500 mt-1">{desc}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Games Played', value: stats ? stats.wins + stats.losses : '—' },
          { label: 'Wins', value: stats ? stats.wins : '—' },
          { label: 'Win Rate', value: stats && (stats.wins + stats.losses) > 0 ? `${Math.round(stats.wins / (stats.wins + stats.losses) * 100)}%` : '—' },
          { label: 'Rating', value: stats ? stats.score : '—' },
        ].map(({ label, value }) => (
          <div key={label} className="glass rounded-xl p-4 text-center">
            <p className="text-2xl font-bold text-white">{value}</p>
            <p className="text-xs text-slate-500 mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* How to play */}
      <div className="glass rounded-xl p-6">
        <h2 className="font-semibold text-slate-300 mb-4 flex items-center gap-2">
          <Zap className="w-4 h-4 text-brand-400" />
          How to play
        </h2>
        <ol className="space-y-2 text-sm text-slate-400">
          <li className="flex gap-3"><span className="text-brand-400 font-bold">1.</span> Click <strong className="text-slate-300">Play</strong> to join matchmaking or <strong className="text-slate-300">Create Lobby</strong> for a custom game</li>
          <li className="flex gap-3"><span className="text-brand-400 font-bold">2.</span> Wait for opponents to be found — both players get notified</li>
          <li className="flex gap-3"><span className="text-brand-400 font-bold">3.</span> In the lobby, all players press <strong className="text-slate-300">Ready</strong> to start the session</li>
          <li className="flex gap-3"><span className="text-brand-400 font-bold">4.</span> Use the <strong className="text-slate-300">Chat</strong> button in the top bar to talk with other players</li>
        </ol>
      </div>
    </div>
  )
}
