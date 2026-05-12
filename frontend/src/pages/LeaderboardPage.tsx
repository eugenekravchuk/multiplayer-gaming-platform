import { useEffect, useState } from 'react'
import { Trophy, RefreshCw, Medal } from 'lucide-react'
import { useAuthStore } from '../store/authStore'
import type { LeaderboardEntry } from '../types'

const API = 'http://localhost:3000'

const CATEGORIES = ['global', 'casual', 'ranked'] as const
type Category = typeof CATEGORIES[number]

export default function LeaderboardPage() {
  const [category, setCategory] = useState<Category>('global')
  const [entries, setEntries] = useState<LeaderboardEntry[]>([])
  const [loading, setLoading] = useState(false)
  const { playerId } = useAuthStore()

  const fetchLeaderboard = async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/leaderboard/${category}?limit=50`)
      const data = await res.json()
      setEntries(data.entries ?? [])
    } catch {
      setEntries([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLeaderboard()
  }, [category])

  const rankIcon = (rank: number) => {
    if (rank === 1) return <Trophy className="w-5 h-5 text-yellow-400" />
    if (rank === 2) return <Medal className="w-5 h-5 text-slate-300" />
    if (rank === 3) return <Medal className="w-5 h-5 text-amber-600" />
    return <span className="text-slate-500 text-sm font-mono w-5 text-center">#{rank}</span>
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Trophy className="w-6 h-6 text-yellow-400" />
            Leaderboard
          </h1>
          <p className="text-slate-400 mt-1">Top players across all modes</p>
        </div>
        <button
          onClick={fetchLeaderboard}
          className="p-2 rounded-lg bg-surface-700 hover:bg-surface-600 text-slate-400 hover:text-white transition-all"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Category tabs */}
      <div className="flex gap-1 p-1 bg-surface-800 rounded-xl">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setCategory(cat)}
            className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all capitalize ${
              category === cat ? 'bg-brand-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="glass rounded-xl overflow-hidden">
        <div className="grid grid-cols-[auto_1fr_auto_auto_auto] gap-0 text-xs text-slate-500 font-medium px-4 py-3 border-b border-surface-700 uppercase tracking-wide">
          <span className="w-8">Rank</span>
          <span>Player</span>
          <span className="text-right w-16">Score</span>
          <span className="text-right w-12">Wins</span>
          <span className="text-right w-16">W/L</span>
        </div>

        {loading ? (
          <div className="py-12 text-center">
            <RefreshCw className="w-6 h-6 animate-spin text-brand-400 mx-auto" />
          </div>
        ) : entries.length === 0 ? (
          <div className="py-12 text-center">
            <Trophy className="w-8 h-8 text-slate-700 mx-auto mb-2" />
            <p className="text-slate-600">No entries yet</p>
            <p className="text-slate-700 text-xs mt-1">Play a ranked game to appear here</p>
          </div>
        ) : (
          entries.map((entry, i) => {
            const rank = entry.rank ?? i + 1
            const isMe = entry.player_id === playerId
            const total = (entry.wins ?? 0) + (entry.losses ?? 0)
            const winRate = total > 0 ? Math.round(((entry.wins ?? 0) / total) * 100) : 0

            return (
              <div
                key={entry.player_id}
                className={`grid grid-cols-[auto_1fr_auto_auto_auto] gap-0 items-center px-4 py-3.5 border-b border-surface-700/50 last:border-0 transition-colors ${
                  isMe ? 'bg-brand-600/10' : 'hover:bg-surface-700/30'
                }`}
              >
                <div className="w-8 flex justify-center">{rankIcon(rank)}</div>
                <div className="flex items-center gap-2 min-w-0">
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                    isMe ? 'bg-brand-600' : 'bg-surface-600'
                  }`}>
                    {(entry.username ?? 'U')[0].toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <p className={`text-sm font-medium truncate ${isMe ? 'text-brand-300' : 'text-white'}`}>
                      {entry.username ?? entry.player_id.slice(-8)}
                      {isMe && <span className="ml-1.5 text-xs text-brand-500">(you)</span>}
                    </p>
                  </div>
                </div>
                <span className="text-right w-16 text-white font-semibold text-sm">{entry.score}</span>
                <span className="text-right w-12 text-slate-400 text-sm">{entry.wins ?? 0}W</span>
                <span className={`text-right w-16 text-xs font-medium ${
                  winRate >= 60 ? 'text-emerald-400' : winRate >= 40 ? 'text-yellow-400' : 'text-red-400'
                }`}>
                  {winRate}%
                </span>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
