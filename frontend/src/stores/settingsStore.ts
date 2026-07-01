import { create } from 'zustand'
import type {
  Settings,
  SettingsUpdate,
  Watch,
  WatchCreate,
  WatchUpdate,
  Store,
  PreviewRequest,
  PreviewProduct,
} from '../api/types'
import {
  getSettings,
  updateSettings,
  testGotify,
  getWatches,
  createWatch,
  updateWatch,
  deleteWatch,
  getStores,
  previewWatch,
} from '../api/endpoints'

interface SettingsState {
  settings: Settings | null
  watches: Watch[]
  stores: Store[]
  loading: boolean
  error: string | null

  fetchSettings: () => Promise<void>
  saveSettings: (update: SettingsUpdate) => Promise<void>
  sendTest: () => Promise<{ delivered: boolean }>

  fetchWatches: () => Promise<void>
  fetchStores: () => Promise<void>
  addWatch: (body: WatchCreate) => Promise<void>
  editWatch: (id: number, body: WatchUpdate) => Promise<void>
  removeWatch: (id: number) => Promise<void>
  preview: (body: PreviewRequest) => Promise<PreviewProduct[]>
}

export const useSettingsStore = create<SettingsState>((set) => ({
  settings: null,
  watches: [],
  stores: [],
  loading: false,
  error: null,

  fetchSettings: async () => {
    set({ loading: true, error: null })
    try {
      const settings = await getSettings()
      set({ settings, loading: false })
    } catch (e) {
      set({ error: String(e), loading: false })
    }
  },

  saveSettings: async (update) => {
    set({ loading: true, error: null })
    try {
      const settings = await updateSettings(update)
      set({ settings, loading: false })
    } catch (e) {
      set({ error: String(e), loading: false })
      throw e
    }
  },

  sendTest: async () => {
    return testGotify()
  },

  fetchWatches: async () => {
    set({ loading: true, error: null })
    try {
      const watches = await getWatches()
      set({ watches, loading: false })
    } catch (e) {
      set({ error: String(e), loading: false })
    }
  },

  fetchStores: async () => {
    try {
      const stores = await getStores()
      set({ stores })
    } catch (e) {
      set({ error: String(e) })
    }
  },

  addWatch: async (body) => {
    const watch = await createWatch(body)
    set((s) => ({ watches: [...s.watches, watch] }))
  },

  // Sets the store error for banner display AND rethrows so form callers can
  // show their own inline message.
  editWatch: async (id, body) => {
    try {
      const updated = await updateWatch(id, body)
      set((s) => ({
        watches: s.watches.map((w) => (w.id === id ? updated : w)),
        error: null,
      }))
    } catch (e) {
      set({ error: `Update failed: ${String(e)}` })
      throw e
    }
  },

  removeWatch: async (id) => {
    try {
      await deleteWatch(id)
      set((s) => ({ watches: s.watches.filter((w) => w.id !== id), error: null }))
    } catch (e) {
      set({ error: `Delete failed: ${String(e)}` })
    }
  },

  preview: (body) => previewWatch(body),
}))
