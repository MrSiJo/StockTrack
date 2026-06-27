import { create } from 'zustand'
import type { WatchStatus, StockEvent, CheckResult } from '../api/types'
import { getStatus, getEvents, checkWatchNow } from '../api/endpoints'

interface StatusState {
  watches: WatchStatus[]
  events: StockEvent[]
  loading: boolean
  error: string | null
  checkToast: string | null
  fetchAll: () => Promise<void>
  checkNow: (id: number) => Promise<CheckResult | null>
  clearCheckToast: () => void
}

export const useStatusStore = create<StatusState>((set) => ({
  watches: [],
  events: [],
  loading: false,
  error: null,
  checkToast: null,

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

  checkNow: async (id: number) => {
    try {
      const result = await checkWatchNow(id)
      return result
    } catch (e) {
      set({ error: String(e) })
      return null
    }
  },

  clearCheckToast: () => set({ checkToast: null }),
}))
