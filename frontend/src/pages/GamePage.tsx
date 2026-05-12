import { useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import { Heart, Star, Crosshair, MoveRight } from 'lucide-react'
import { useGameStore } from '../store/gameStore'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAuthStore } from '../store/authStore'

export default function GamePage() {
  const { currentSession } = useGameStore()
  const { send } = useWebSocket()
  const { playerId } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    if (!currentSession) navigate('/')
  }, [currentSession, navigate])

  if (!currentSession) return null

  const { state } = currentSession
  const players = Object.entries(state.players)

  const sendAction = (type: string, extra: Record<string, unknown> = {}) => {
    send('game.action', {
      session_id: currentSession.id,
      action: { type, ...extra },
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Game in Progress</h1>
          <p className="text-slate-400 text-sm">Session v{state.version} · Round {String(state.game_data.round ?? 1)}</p>
        </div>
        <div className="px-3 py-1 rounded-full bg-green-500/20 text-green-400 text-sm font-medium animate-pulse">
          ● Live
        </div>
      </div>

      {/* Player states */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {players.map(([pid, pdata]) => (
          <div
            key={pid}
            className={`glass rounded-xl p-5 ${pid === playerId ? 'border border-brand-500/40' : ''}`}
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-sm font-bold">
                  {pid.slice(-2)}
                </div>
                <div>
                  <p className="text-sm font-medium text-white">
                    {pid === playerId ? 'You' : `Player ${pid.slice(-6)}`}
                  </p>
                </div>
              </div>
              {pid === playerId && (
                <span className="text-xs text-brand-400 font-medium bg-brand-500/10 px-2 py-0.5 rounded-full">
                  You
                </span>
              )}
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-surface-700/50 rounded-lg p-3 text-center">
                <Heart className="w-4 h-4 text-red-400 mx-auto mb-1" />
                <p className="text-lg font-bold text-white">{pdata.health}</p>
                <p className="text-xs text-slate-500">Health</p>
              </div>
              <div className="bg-surface-700/50 rounded-lg p-3 text-center">
                <Star className="w-4 h-4 text-yellow-400 mx-auto mb-1" />
                <p className="text-lg font-bold text-white">{pdata.score}</p>
                <p className="text-xs text-slate-500">Score</p>
              </div>
              <div className="bg-surface-700/50 rounded-lg p-3 text-center">
                <MoveRight className="w-4 h-4 text-emerald-400 mx-auto mb-1" />
                <p className="text-sm font-bold text-white">
                  {pdata.position.x},{pdata.position.y}
                </p>
                <p className="text-xs text-slate-500">Pos</p>
              </div>
            </div>

            {/* Health bar */}
            <div className="mt-4">
              <div className="w-full bg-surface-700 rounded-full h-2">
                <div
                  className="bg-red-500 h-2 rounded-full transition-all"
                  style={{ width: `${Math.max(0, pdata.health)}%` }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="glass rounded-xl p-5">
        <h2 className="text-sm font-semibold text-slate-400 mb-4">Actions</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <button
            onClick={() => sendAction('move', { position: { x: Math.floor(Math.random() * 100), y: Math.floor(Math.random() * 100) } })}
            className="py-3 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-400 font-medium text-sm transition-all border border-emerald-500/20"
          >
            Move
          </button>
          <button
            onClick={() => {
              const others = players.filter(([pid]) => pid !== playerId)
              if (others.length > 0) {
                sendAction('attack', { target: others[0][0], damage: Math.floor(Math.random() * 20) + 5 })
              }
            }}
            className="py-3 rounded-xl bg-red-600/20 hover:bg-red-600/30 text-red-400 font-medium text-sm transition-all border border-red-500/20 flex items-center justify-center gap-2"
          >
            <Crosshair className="w-4 h-4" /> Attack
          </button>
          <button
            onClick={() => sendAction('score', { points: 10 })}
            className="py-3 rounded-xl bg-yellow-600/20 hover:bg-yellow-600/30 text-yellow-400 font-medium text-sm transition-all border border-yellow-500/20"
          >
            +10 Score
          </button>
          <button
            onClick={() => navigate('/')}
            className="py-3 rounded-xl bg-surface-700 hover:bg-surface-600 text-slate-400 font-medium text-sm transition-all"
          >
            Leave Game
          </button>
        </div>
      </div>

      {/* Event log */}
      <div className="glass rounded-xl p-5">
        <h2 className="text-sm font-semibold text-slate-400 mb-2">State</h2>
        <pre className="text-xs text-slate-500 overflow-auto max-h-32">
          {JSON.stringify(state.game_data, null, 2)}
        </pre>
      </div>
    </div>
  )
}
