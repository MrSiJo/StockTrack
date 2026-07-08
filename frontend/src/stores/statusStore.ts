import { create } from 'zustand'
import type { WatchStatus, StockEvent, CheckResult } from '../api/types'
import { getStatus, getEvents, checkWatchNow } from '../api/endpoints'

interface StatusState {
  watches: WatchStatus[]
  events: StockEvent[]
  loading: boolean
  error: string | null
  fetchAll: () => Promise<void>
  // Throws on failure — callers surface the error next to the watch they checked.
  checkNow: (id: number) => Promise<CheckResult>
}

export const useStatusStore = create<StatusState>((set) => ({
  watches: [],
  events: [],
  loading: false,
  error: null,

  fetchAll: async () => {
    set({ loading: true, error: null })
    try {
      const [watches, events] = await Promise.all([
        getStatus(),
        getEvents(50),
      ])
      set({ watches, events, loading: false })
    } catch (e) {
      set({ error: String(e), loading: false })
    }
  },

  checkNow: (id: number) => checkWatchNow(id),
}))
