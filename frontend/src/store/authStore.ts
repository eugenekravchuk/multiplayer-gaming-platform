import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  token: string | null
  playerId: string | null
  username: string | null
  setAuth: (token: string, playerId: string, username: string) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      playerId: null,
      username: null,
      setAuth: (token, playerId, username) => set({ token, playerId, username }),
      clearAuth: () => set({ token: null, playerId: null, username: null }),
    }),
    { name: 'auth' }
  )
)
