export type Pagination = {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type LocationSummary = {
  label: string | null;
  city: string | null;
  municipality: string | null;
  neighborhood: string | null;
  micro_location: string | null;
  street: string | null;
};

export type SourceWarning = {
  source_id: string;
  source_code: string;
  source_name: string;
  status: string;
  last_error_at: string | null;
  last_error_type: string | null;
  last_error_message: string | null;
};

export type ListingSummary = {
  listing_id: string | null;
  source_code: string | null;
  source_name: string | null;
  status: string | null;
  url: string | null;
  canonical_url?: string | null;
};

export type ActionQueueItem = {
  property_id: string;
  property_label: string | null;
  recommended_action: string;
  action_priority: number | null;
  reason_codes: string[];
  location: LocationSummary;
  property_type: string;
  size_m2: string | null;
  rooms: string | null;
  asking_price: string | null;
  currency: string | null;
  fair_value_low: string | null;
  fair_value_base: string | null;
  fair_value_high: string | null;
  fast_sale_base: string | null;
  max_buy_price: string | null;
  expected_profit: string | null;
  downside_profit: string | null;
  liquidity_score: string | null;
  valuation_confidence: string | null;
  risk_gate: string | null;
  property_market_age_days: number | null;
  last_change: string | null;
  analysis_status: string;
  is_stale: boolean;
  current_listing: ListingSummary;
};

export type ActionQueueResponse = {
  items: ActionQueueItem[];
  pagination: Pagination;
  summary: {
    status: string;
    total: number;
    by_action: Record<string, number>;
  };
  source_warnings: SourceWarning[];
};

export type PropertyListItem = {
  property_id: string;
  property_label: string | null;
  location: LocationSummary;
  property_type: string;
  pipeline_status: string;
  size_m2: string | null;
  rooms: string | null;
  active_listing_count: number;
  known_listing_count: number | null;
  property_market_age_days: number | null;
  recommended_action: string | null;
  reason_codes: string[];
  risk_gate: string | null;
  asking_price: string | null;
  max_buy_price: string | null;
  expected_profit: string | null;
  downside_profit: string | null;
  last_change: string | null;
  analysis_status: string;
  current_listing: ListingSummary;
};

export type PropertiesResponse = {
  items: PropertyListItem[];
  pagination: Pagination;
};

export type PropertyDetail = {
  property: Record<string, unknown> & {
    property_id: string;
    property_label: string | null;
    location: LocationSummary;
  };
  decision: Record<string, unknown> & {
    property_label: string | null;
    recommended_action: string | null;
    reason_codes: string[];
    risk_gate: string | null;
    currency: string | null;
  };
  freshness: {
    last_listing_update: string | null;
    last_analysis: string | null;
    is_stale: boolean;
    statuses: Record<string, string>;
  };
  listings: Array<
    Record<string, unknown> & {
      listing_id: string;
      source_code: string;
      source_name: string;
      url: string | null;
      canonical_url: string | null;
      title: string | null;
      status: string;
      currency: string | null;
    }
  >;
  history: Array<Record<string, unknown> & { event_type: string; detected_at: string | null }>;
  comparables: {
    status: string;
    items: Array<Record<string, unknown> & { comparable_type: string }>;
  } & Record<string, unknown>;
  valuation: Record<string, unknown> & { status: string };
  liquidity: {
    assessment: (Record<string, unknown> & { status: string }) | null;
    fast_sale: (Record<string, unknown> & { status: string }) | null;
  };
  seller: Record<string, unknown> & { status: string };
  risk: Record<string, unknown> & {
    status: string;
    gate: string | null;
    flags: Array<Record<string, unknown> & { code: string; gate_effect: string }>;
  };
  deal: Record<string, unknown> & {
    status: string;
    costs?: Record<string, unknown>;
    scenarios: Array<Record<string, unknown> & { scenario_type: string }>;
  };
};

export type SourcesResponse = {
  items: Array<
    Record<string, unknown> & {
      source_id: string;
      name: string;
      code: string;
      enabled: boolean;
      health_status: string;
      last_success_at: string | null;
      last_error_at: string | null;
      last_error_type: string | null;
      last_error_message: string | null;
    }
  >;
  summary: Record<string, number>;
  source_warnings: SourceWarning[];
};

export type SettingsResponse = {
  app: {
    environment: string;
    base_url: string;
    auth_mode: string;
    production_access_configured: boolean;
  };
  api: {
    cors_allowed_origins: string[];
  };
  notifications: {
    telegram_configured: boolean;
    telegram_channel: string;
  };
  investment_profiles: Array<Record<string, unknown> & { name: string; version: string }>;
  cost_profiles: Array<Record<string, unknown> & { name: string; code: string; version: string }>;
  sources: {
    enabled: number;
    disabled: number;
  };
};
