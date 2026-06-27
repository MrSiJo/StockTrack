import { api } from './client'
import type {
  WatchStatus,
  StockEvent,
  Watch,
  WatchCreate,
  WatchUpdate,
  Store,
  PreviewRequest,
  PreviewProduct,
  Settings,
  SettingsUpdate,
  CheckResult,
} from './types'

export const getStatus = () => api.get<WatchStatus[]>('/status')
export const getEvents = (limit = 50) =>
  api.get<StockEvent[]>(`/events?limit=${limit}`)
export const getWatches = () => api.get<Watch[]>('/watches')
export const createWatch = (body: WatchCreate) =>
  api.post<Watch>('/watches', body)
export const updateWatch = (id: number, body: WatchUpdate) =>
  api.put<Watch>(`/watches/${id}`, body)
export const deleteWatch = (id: number) => api.delete(`/watches/${id}`)
export const checkWatchNow = (id: number) =>
  api.post<CheckResult>(`/watches/${id}/check?notify=true`)
export const previewWatch = (body: PreviewRequest) =>
  api.post<PreviewProduct[]>('/watches/preview', body)
export const getStores = () => api.get<Store[]>('/stores')
export const getSettings = () => api.get<Settings>('/settings')
export const updateSettings = (body: SettingsUpdate) =>
  api.put<Settings>('/settings', body)
export const testGotify = () =>
  api.post<{ delivered: boolean }>('/settings/test')
