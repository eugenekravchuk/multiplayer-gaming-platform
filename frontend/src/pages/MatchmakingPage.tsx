import { useState } from 'react'
import { Swords, Loader2, X, Zap } from 'lucide-react'
import { useWebSocket } from '../hooks/useWebSocket'
import { useGameStore } from '../store/gameStore'

type Mode = 'casual' | 'ranked'

export default function MatchmakingPage() {
  const [selectedMode, setSelectedMode] = useState<Mode>('casual')
  const { send } = useWebSocket()
  const { matchmakingStatus, setMatchmakingStatus } = useGameStore()

  const searching = matchmakingStatus === 'searching'

  const joinQueue = () => {
    send('matchmaking.join', { game_mode: selectedMode, rating: 1000 })
  }

  const cancelQueue = () => {
    send('matchmaking.cancel', {})
    setMatchmakingStatus('idle')
  }

  const modes = [
    { id: 'casual' as Mode, label: 'Casual', desc: 'Relaxed gameplay, no rank at stake', color: 'border-emerald-500/50 bg-emerald-500/10' },
    { id: 'ranked' as Mode, label: 'Ranked', desc: 'Compete for rating and leaderboard position', color: 'border-brand-500/50 bg-brand-500/10' },
  ]

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Find a Match</h1>
        <p className="text-slate-400 mt-1">Select a mode and join the queue</p>
      </div>

      {/* Mode selector */}
      <div className="space-y-3">
        {modes.map((mode) => (
          <button
            key={mode.id}
            onClick={() => !searching && setSelectedMode(mode.id)}
            disabled={searching}
            className={`w-full glass rounded-xl p-5 text-left transition-all border-2 ${
              selectedMode === mode.id ? mode.color : 'border-transparent hover:border-surface-600'
            } ${searching ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
          >
            <div className="font-semibold text-white">{mode.label}</div>
            <div className="text-sm text-slate-400 mt-0.5">{mode.desc}</div>
          </button>
        ))}
      </div>

      {/* Action */}
      {!searching ? (
        <button
          onClick={joinQueue}
          className="w-full py-4 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-bold text-lg flex items-center justify-center gap-3 glow transition-all"
        >
          <Swords className="w-5 h-5" />
          Find Match
        </button>
      ) : (
        <div className="glass rounded-xl p-6 text-center space-y-4">
          <div className="flex items-center justify-center gap-3 text-brand-400">
            <Loader2 className="w-6 h-6 animate-spin" />
            <span className="font-semibold text-lg">Searching for opponents...</span>
          </div>

          <div className="flex justify-center gap-1.5">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="w-2 h-2 rounded-full bg-brand-400 animate-bounce"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </div>

          <p className="text-slate-500 text-sm">
            Mode: <span className="text-slate-300 font-medium capitalize">{selectedMode}</span>
          </p>

          <button
            onClick={cancelQueue}
            className="flex items-center gap-2 mx-auto text-sm text-slate-500 hover:text-red-400 transition-colors"
          >
            <X className="w-4 h-4" />
            Cancel Search
          </button>
        </div>
      )}

      {/* Tips */}
      <div className="glass rounded-xl p-4">
        <div className="flex items-center gap-2 text-xs text-slate-500 font-medium mb-2">
          <Zap className="w-3.5 h-3.5" />
          Tips
        </div>
        <ul className="text-xs text-slate-500 space-y-1">
          <li>• The system matches players with similar skill ratings</li>
          <li>• Rating window expands the longer you wait</li>
          <li>• Open two browser tabs to test with two players</li>
        </ul>
      </div>
    </div>
  )
}
