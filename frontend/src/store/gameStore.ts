import { create } from 'zustand'
import type { Lobby, Match, GameSession, ChatMessage, Notification, LeaderboardEntry } from '../types'

interface GameState {
  // Matchmaking
  matchmakingStatus: 'idle' | 'searching' | 'found'
  currentMatch: Match | null

  // Lobby
  currentLobby: Lobby | null
  lobbies: Lobby[]

  // Session
  currentSession: GameSession | null

  // Chat
  messages: Record<string, ChatMessage[]>
  activeChannel: string

  // Notifications
  notifications: Notification[]
  unreadCount: number

  // Leaderboard
  leaderboard: LeaderboardEntry[]

  // Actions
  setMatchmakingStatus: (status: 'idle' | 'searching' | 'found') => void
  setCurrentMatch: (match: Match | null) => void
  setCurrentLobby: (lobby: Lobby | null) => void
  updateLobbyPlayers: (players: string[]) => void
  setLobbies: (lobbies: Lobby[]) => void
  setCurrentSession: (session: GameSession | null) => void
  updateSessionState: (state: GameSession['state']) => void
  addMessage: (channelId: string, message: ChatMessage) => void
  setMessages: (channelId: string, messages: ChatMessage[]) => void
  setActiveChannel: (channel: string) => void
  addNotification: (notification: Notification) => void
  setUnreadCount: (count: number) => void
  markNotificationsRead: () => void
  setLeaderboard: (entries: LeaderboardEntry[]) => void
}

export const useGameStore = create<GameState>((set) => ({
  matchmakingStatus: 'idle',
  currentMatch: null,
  currentLobby: null,
  lobbies: [],
  currentSession: null,
  messages: { global: [] },
  activeChannel: 'global',
  notifications: [],
  unreadCount: 0,
  leaderboard: [],

  setMatchmakingStatus: (status) => set({ matchmakingStatus: status }),
  setCurrentMatch: (match) => set({ currentMatch: match, matchmakingStatus: match ? 'found' : 'idle' }),
  setCurrentLobby: (lobby) => set({ currentLobby: lobby }),
  updateLobbyPlayers: (players) =>
    set((s) => s.currentLobby ? { currentLobby: { ...s.currentLobby, players } } : {}),
  setLobbies: (lobbies) => set({ lobbies }),
  setCurrentSession: (session) => set({ currentSession: session }),
  updateSessionState: (state) =>
    set((s) => s.currentSession ? { currentSession: { ...s.currentSession, state } } : {}),
  addMessage: (channelId, message) =>
    set((s) => ({
      messages: {
        ...s.messages,
        [channelId]: [...(s.messages[channelId] ?? []), message],
      },
    })),
  setMessages: (channelId, messages) =>
    set((s) => ({ messages: { ...s.messages, [channelId]: messages } })),
  setActiveChannel: (channel) => set({ activeChannel: channel }),
  addNotification: (notification) =>
    set((s) => ({ notifications: [notification, ...s.notifications] })),
  setUnreadCount: (count) => set({ unreadCount: count }),
  markNotificationsRead: () =>
    set((s) => ({
      notifications: s.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    })),
  setLeaderboard: (entries) => set({ leaderboard: entries }),
}))
