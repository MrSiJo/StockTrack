// Availability is the 3-state stock phase. Handlers that can't detect early
// leave it blank (""); the poller then derives "oos"/"public" from in_stock.
export type Availability = 'oos' | 'early' | 'public' | string

// ── Status (GET /api/status) ────────────────────────────────────────────────

export interface Product {
  id: number
  store: string
  code: string
  title: string
  url: string
  brand: string
  availability: Availability
  basket_url: string            // empty string when store doesn't expose one
  current_in_stock: boolean
  current_price: number | null
  available_since: string | null
  last_checked: string | null
}

export interface WatchStatus {
  id: number
  store: string
  url: string
  label: string
  enabled: boolean
  last_checked_at: string | null
  last_ok_at: string | null
  consecutive_failures: number
  last_error: string
  products: Product[]
}

// ── Events (GET /api/events) ────────────────────────────────────────────────

export interface StockEvent {
  id: number
  ts: string                   // ISO datetime
  kind: 'early_access' | 'public' | 'oos' | string
  price: number | null
  available_seconds: number | null
  product_title: string
  store: string
  url: string
  basket_url: string
}

// ── Watches (GET/POST/PUT/DELETE /api/watches) ──────────────────────────────

export interface Watch {
  id: number
  store: string
  url: string
  label: string
  kind: string
  include_filter: string
  exclude_filter: string
  interval_seconds: number
  enabled: boolean
  track_price_drops: boolean
  created_at: string
  last_checked_at: string | null
  last_ok_at: string | null
  consecutive_failures: number
  last_error: string
}

export interface WatchCreate {
  store: string
  url: string
  label?: string
  kind?: string
  include_filter?: string
  exclude_filter?: string
  interval_seconds?: number
  enabled?: boolean
  track_price_drops?: boolean
}

export interface WatchUpdate {
  store?: string
  url?: string
  label?: string
  kind?: string
  include_filter?: string
  exclude_filter?: string
  interval_seconds?: number
  enabled?: boolean
  track_price_drops?: boolean
}

// ── Stores (GET /api/stores) ────────────────────────────────────────────────

export interface StoreSetting {
  key: string
  label: string
  type: string                 // 'bool' | 'int' | 'float' | 'str'
  default: boolean | number | string
}

export interface Store {
  name: string
  kinds: string[]
  supported: boolean
  settings: StoreSetting[]
}

// ── Preview (POST /api/watches/preview) ────────────────────────────────────

export interface PreviewRequest {
  store: string
  url: string
  kind?: string
  include_filter?: string
  exclude_filter?: string
}

export interface PreviewProduct {
  code: string
  title: string
  brand: string
  url: string
  in_stock: boolean
  price: number | null
  delivery: string
  availability: Availability
  basket_url: string
}

// ── Settings (GET/PUT /api/settings) ───────────────────────────────────────

export interface Settings {
  gotify_url: string
  gotify_token_set: boolean   // true when a token is stored (never returned)
  gotify_priority: number
  restock_priority: number
  oos_priority: number
  gotify_send_retries: number
  default_interval_seconds: number
  failure_alert_after: number
  heartbeat_hours: number
  early_access_days: number
  ao_member: boolean
  price_drop_min_pct: number
  price_drop_min_abs: number
  price_drop_priority: number
  lead_time_priority: number
  cp_delivery_postcode: string
  cp_collection_branch_id: string
}

// ── Check result (POST /api/watches/{id}/check) ────────────────────────────

export interface CheckResult {
  parsed: number
  early: number
  public: number
  oos: number
  notified: boolean
}

export interface SettingsUpdate {
  gotify_url?: string
  gotify_token?: string       // write-only; only sent when user changes it
  gotify_priority?: number
  restock_priority?: number
  oos_priority?: number
  gotify_send_retries?: number
  default_interval_seconds?: number
  failure_alert_after?: number
  heartbeat_hours?: number
  early_access_days?: number
  ao_member?: boolean
  price_drop_min_pct?: number
  price_drop_min_abs?: number
  price_drop_priority?: number
  lead_time_priority?: number
  cp_delivery_postcode?: string
  cp_collection_branch_id?: string
}
