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

export type WatchRule = {
  watch_rule_id: string;
  property_id: string;
  is_active: boolean;
  rule_type: string | null;
  threshold_numeric: string | null;
  rule_config: Record<string, unknown>;
  created_at: string | null;
  triggered_at: string | null;
  last_evaluated_at: string | null;
};

export type WatchTriggerEvent = {
  watch_trigger_event_id: string;
  watch_rule_id: string;
  property_id: string;
  listing_event_id: string | null;
  trigger_type: string | null;
  triggered_at: string | null;
  summary: Record<string, unknown>;
  invalidated_modules: string[];
  reanalyzed_modules: string[];
  previous_opportunity_assessment_id: string | null;
  new_opportunity_assessment_id: string | null;
  alert_id: string | null;
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

export type WatchlistItem = {
  property_id: string;
  property_label: string | null;
  location: LocationSummary;
  asking_price: string | null;
  currency: string | null;
  max_buy_price: string | null;
  gap_to_max_buy: string | null;
  last_price_cut: string | null;
  property_market_age_days: number | null;
  watch_rule: WatchRule | null;
  last_change: string | null;
  last_change_summary: Record<string, unknown> | null;
  recommended_action: string | null;
  reason_codes: string[];
  analysis_status: string;
  current_listing: ListingSummary;
};

export type WatchlistResponse = {
  items: WatchlistItem[];
  pagination: Pagination;
};

export type PropertyReview = {
  review_id: string;
  property_id: string;
  reviewed_at: string | null;
  decision: string;
  manual_fmv: string | null;
  manual_fast_sale_value: string | null;
  manual_max_buy_price: string | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type CallFeedback = {
  seller_motivation: string | null;
  reason_for_sale: string | null;
  lowest_indicated_price: string | null;
  cash_preferred: boolean | null;
  desired_closing_days: number | null;
  viewing_available: boolean | null;
  claimed_registered: boolean | null;
  claimed_owner_1_1: boolean | null;
  claimed_mortgage: boolean | null;
  tenant_present: boolean | null;
  structured_notes: Record<string, unknown>;
};

export type VisitFeedback = {
  condition_category: string | null;
  estimated_renovation_low: string | null;
  estimated_renovation_base: string | null;
  estimated_renovation_high: string | null;
  layout_score: number | null;
  light_score: number | null;
  noise_score: number | null;
  building_score: number | null;
  entrance_score: number | null;
  parking_score: number | null;
  elevator_verified: boolean | null;
  visible_defects: unknown[];
  manual_fmv: string | null;
  manual_fast_sale_value: string | null;
  manual_max_buy_price: string | null;
  notes: string | null;
};

export type InteractionRecord = {
  interaction_id: string;
  property_id: string;
  interaction_type: string;
  occurred_at: string | null;
  follow_up_at: string | null;
  follow_up_notes: string | null;
  notes: string | null;
  created_at: string | null;
  call_feedback: CallFeedback | null;
  visit_feedback: VisitFeedback | null;
};

export type OfferRecord = {
  offer_id: string;
  property_id: string;
  offered_at: string | null;
  amount: string | null;
  currency: string | null;
  offer_type: string | null;
  conditions: Record<string, unknown>;
  status: string;
  seller_response_at: string | null;
  counteroffer_amount: string | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type SkipRecord = {
  skip_record_id: string;
  property_id: string;
  reason_code: string;
  notes: string | null;
  skipped_at: string | null;
};

export type PropertyOutcome = {
  outcome_id: string;
  property_id: string;
  outcome_type: string;
  outcome_date: string | null;
  sale_price: string | null;
  currency: string | null;
  confidence: string | null;
  source_kind: string | null;
  source_reference: string | null;
  notes: string | null;
  created_at: string | null;
};

export type PropertyOverride = {
  override_id: string;
  property_id: string;
  field_name: string;
  value: unknown;
  source_kind: string;
  source_reference: string | null;
  reason: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type PipelineStatusEvent = {
  pipeline_status_event_id: string;
  property_id: string;
  old_status: string | null;
  new_status: string;
  source_kind: string;
  source_reference: string | null;
  reason: string | null;
  occurred_at: string | null;
  created_at: string | null;
};

export type AcquisitionTimelineItem = {
  type: string;
  occurred_at: string | null;
  summary: string | null;
  record_id: string;
  notes: string | null;
  follow_up_at?: string | null;
  follow_up_notes?: string | null;
};

export type AcquisitionDetail = {
  pipeline_status: string;
  pipeline_status_updated_at: string | null;
  reviews: PropertyReview[];
  interactions: InteractionRecord[];
  offers: OfferRecord[];
  skip_records: SkipRecord[];
  outcomes: PropertyOutcome[];
  overrides: PropertyOverride[];
  pipeline_events: PipelineStatusEvent[];
  timeline: AcquisitionTimelineItem[];
};

export type PipelineItem = PropertyListItem & {
  pipeline: {
    status: string;
    status_updated_at: string | null;
    latest_review: PropertyReview | null;
    latest_interaction: InteractionRecord | null;
    next_follow_up: InteractionRecord | null;
    latest_offer: OfferRecord | null;
    latest_skip: SkipRecord | null;
    latest_outcome: PropertyOutcome | null;
  };
};

export type PipelineResponse = {
  items: PipelineItem[];
  pagination: Pagination;
  summary: Record<string, number>;
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
  watch: {
    is_watched: boolean;
    active_rule: WatchRule | null;
    latest_changes: WatchTriggerEvent[];
  };
  acquisition: AcquisitionDetail;
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
