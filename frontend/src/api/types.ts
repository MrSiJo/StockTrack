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
  delivery: string              // lead-time string (e.g. "Delivery by Mon 30 Jun (carrier)"); "" when none
  current_in_stock: boolean
  current_price: number | null
  lowest_price: number | null
  muted_until: string | null    // ISO datetime; product is muted until then
  available_since: string | null
  last_checked: string | null
  spec_watts?: number | null
  price_per_watt?: number | null
}

// ── Price history (GET /api/products/{id}/price-history) ───────────────────

export interface PricePoint {
  ts: string
  kind: string
  price: number
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
  kind: 'early_access' | 'public' | 'oos' | 'price_drop' | 'new_product' | 'lead_time'
      | 'new_low' | 'price_rise' | 'price_target' | string
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
  track_price_rises: boolean
  price_drop_min_pct: number | null
  price_drop_min_abs: number | null
  price_target: number | null
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
  track_price_rises?: boolean
  price_drop_min_pct?: number | null
  price_drop_min_abs?: number | null
  price_target?: number | null
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
  track_price_rises?: boolean
  price_drop_min_pct?: number | null   // explicit null clears the override
  price_drop_min_abs?: number | null
  price_target?: number | null
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

// ── Restock Pattern (GET /api/watches/{id}/restock-pattern) ────────────────

export interface RestockPattern {
  watch_id: number
  store: string
  label: string
  samples: number
  by_hour: number[]
  by_weekday: number[]
  summary: string
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
  event_retention_days: number
  product_archive_days: number
  early_access_days: number
  ao_member: boolean
  price_drop_min_pct: number
  price_drop_min_abs: number
  price_drop_priority: number
  lead_time_priority: number
  lead_time_min_change_days: number
  new_product_priority: number
  alert_group_threshold: number
  price_drop_in_stock_only: boolean
  digest_cadence: string       // 'off' | 'daily' | 'weekly'
  digest_hour: number
  digest_priority: number
  dashboard_url: string
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
  event_retention_days?: number
  product_archive_days?: number
  early_access_days?: number
  ao_member?: boolean
  price_drop_min_pct?: number
  price_drop_min_abs?: number
  price_drop_priority?: number
  lead_time_priority?: number
  lead_time_min_change_days?: number
  new_product_priority?: number
  alert_group_threshold?: number
  price_drop_in_stock_only?: boolean
  digest_cadence?: string
  digest_hour?: number
  digest_priority?: number
  dashboard_url?: string
  cp_delivery_postcode?: string
  cp_collection_branch_id?: string
}
