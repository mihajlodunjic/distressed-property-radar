import "./App.css";

import type { FormEvent, ReactElement, ReactNode } from "react";
import { useEffect, useState } from "react";

import {
  ApiError,
  HEALTH_URL,
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  clearAccessToken,
  setAccessToken,
} from "./api";
import {
  displayBoolean,
  displayDateTime,
  displayMoney,
  displayPercent,
  displayValue,
  displayWatchTrigger,
  statusTone,
} from "./format";
import type {
  ActionQueueItem,
  ActionQueueResponse,
  PipelineItem,
  PipelineResponse,
  PropertyDetail,
  PropertyListItem,
  PropertiesResponse,
  SettingsResponse,
  SourceWarning,
  SourcesResponse,
  WatchlistItem,
  WatchlistResponse,
} from "./types";

type ResourceState<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "unauthorized" }
  | { status: "error"; message: string };

type PageProps = {
  accessRevision: number;
  onAccessSaved: () => void;
};

type CommandResult = {
  status: string;
  invalidated_modules?: string[];
  reanalyzed_modules?: string[];
};

type Route = {
  path: string;
  activePath: string;
  label: string;
  element: ReactElement;
};

const actionOrder = ["URGENT_CALL", "CALL", "REVIEW", "WATCH"];
const pipelineStatuses = [
  "NEW",
  "REVIEWED",
  "CALLED",
  "VISIT_SCHEDULED",
  "VISITED",
  "DUE_DILIGENCE",
  "OFFERED",
  "NEGOTIATING",
  "WON",
  "LOST",
  "SKIPPED",
  "SOLD",
];
const reviewDecisions = ["INTERESTING", "NOT_INTERESTING", "UNSURE"];
const sellerMotivationLevels = ["", "LOW", "MEDIUM", "HIGH", "UNKNOWN"];
const reasonForSaleOptions = [
  "",
  "UNKNOWN",
  "MOVING",
  "MOVING_ABROAD",
  "NEEDS_LIQUIDITY",
  "INHERITANCE",
  "DIVORCE",
  "BUSINESS_LIQUIDITY",
  "BOUGHT_ANOTHER_PROPERTY",
  "VACANT_PROPERTY",
  "INVESTOR_EXIT",
  "TIME_DEADLINE",
  "OTHER",
];
const booleanOptions = [
  { label: "UNKNOWN", value: "" },
  { label: "YES", value: "true" },
  { label: "NO", value: "false" },
];
const skipReasonCodes = [
  "OVERPRICED",
  "NO_MARGIN",
  "BAD_LEGAL",
  "LOW_LIQUIDITY",
  "BAD_LOCATION",
  "BAD_BUILDING",
  "HEAVY_RENOVATION",
  "SELLER_UNREALISTIC",
  "LOW_CONFIDENCE",
  "FAKE_LISTING",
  "OTHER",
];
const offerStatuses = [
  "OPEN",
  "ACCEPTED",
  "REJECTED",
  "COUNTERED",
  "WITHDRAWN",
  "EXPIRED",
];
const outcomeTypes = [
  "STILL_ACTIVE",
  "REMOVED_UNKNOWN",
  "RELISTED",
  "LIKELY_SOLD",
  "CONFIRMED_SOLD",
  "BOUGHT_BY_USER",
  "LOST_TO_OTHER_BUYER",
  "SALE_CANCELLED",
  "OTHER",
];
const watchRuleTypes = [
  "",
  "ANY_PRICE_CHANGE",
  "PRICE_BELOW",
  "PRICE_DROP_PERCENT",
  "DESCRIPTION_CHANGE",
  "SELLER_CHANGE",
];

function useApiResource<T>(path: string, accessRevision: number) {
  const [reloadRevision, setReloadRevision] = useState(0);
  const [state, setState] = useState<ResourceState<T>>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    apiGet<T>(path)
      .then((data) => {
        if (!cancelled) {
          setState({ status: "ready", data });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          setState({ status: "unauthorized" });
          return;
        }
        const message = error instanceof Error ? error.message : "Request failed";
        setState({ status: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [path, accessRevision, reloadRevision]);

  return {
    state,
    reload: () => setReloadRevision((value) => value + 1),
  };
}

function valueAsString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function valueAsBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function booleanFromSelect(value: string): boolean | null {
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  return null;
}

function ValueText({ children }: { children: ReactNode }) {
  const text = String(children);
  return <span className={text === "UNKNOWN" ? "unknown-value" : undefined}>{children}</span>;
}

function StatusBadge({ status }: { status: string | null | undefined }) {
  const label = displayValue(status);
  return <span className={`status-badge tone-${statusTone(status)}`}>{label}</span>;
}

function ReasonCodes({ codes }: { codes: string[] }) {
  if (codes.length === 0) {
    return <span className="muted">No reason codes</span>;
  }
  return (
    <div className="tag-list">
      {codes.map((code) => (
        <span className="tag" key={code}>
          {code}
        </span>
      ))}
    </div>
  );
}

function Section({
  title,
  eyebrow,
  children,
}: {
  title: string;
  eyebrow?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="section">
      <div className="section-heading">
        <h2>{title}</h2>
        {eyebrow ? <div className="section-eyebrow">{eyebrow}</div> : null}
      </div>
      {children}
    </section>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: ReactNode;
  tone?: "critical" | "warning" | "ok" | "action";
}) {
  return (
    <div className={`metric ${tone ? `metric-${tone}` : ""}`}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Notice({
  title,
  detail,
  tone = "neutral",
}: {
  title: string;
  detail?: string;
  tone?: "neutral" | "warning" | "critical";
}) {
  return (
    <div className={`notice notice-${tone}`}>
      <strong>{title}</strong>
      {detail ? <span>{detail}</span> : null}
    </div>
  );
}

function AccessRequired({ onAccessSaved }: Pick<PageProps, "onAccessSaved">) {
  const [token, setToken] = useState("");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = token.trim();
    if (!trimmed) {
      return;
    }
    setAccessToken(trimmed);
    setToken("");
    onAccessSaved();
  }

  return (
    <section className="section narrow-section">
      <h2>Private API Token Required</h2>
      <form className="access-form" onSubmit={submit}>
        <label htmlFor="api-token">Access token</label>
        <div className="inline-form">
          <input
            autoComplete="current-password"
            id="api-token"
            onChange={(event) => setToken(event.target.value)}
            type="password"
            value={token}
          />
          <button type="submit">Unlock</button>
        </div>
      </form>
    </section>
  );
}

function ResourceView<T>({
  state,
  onRetry,
  onAccessSaved,
  children,
}: {
  state: ResourceState<T>;
  onRetry: () => void;
  onAccessSaved: () => void;
  children: (data: T) => ReactNode;
}) {
  if (state.status === "loading") {
    return <Notice title="Loading" detail="Fetching current backend data." />;
  }
  if (state.status === "unauthorized") {
    return <AccessRequired onAccessSaved={onAccessSaved} />;
  }
  if (state.status === "error") {
    return (
      <Notice
        detail={state.message}
        title="Unable to load dashboard data"
        tone="critical"
      />
    );
  }
  return (
    <>
      {children(state.data)}
      <button className="secondary-action" onClick={onRetry} type="button">
        Refresh
      </button>
    </>
  );
}

function SourceWarningBanner({ warnings }: { warnings: SourceWarning[] }) {
  if (warnings.length === 0) {
    return null;
  }
  return (
    <Notice
      detail={warnings
        .map((warning) => `${warning.source_code}: ${warning.status}`)
        .join(", ")}
      title="Source warning"
      tone="warning"
    />
  );
}

function ExternalListingLink({ url }: { url: string | null | undefined }) {
  if (!url) {
    return <ValueText>UNKNOWN</ValueText>;
  }
  return (
    <a href={url} rel="noreferrer" target="_blank">
      Open listing
    </a>
  );
}

function ActionQueuePage({ accessRevision, onAccessSaved }: PageProps) {
  const { state, reload } = useApiResource<ActionQueueResponse>(
    "/api/v1/action-queue",
    accessRevision,
  );

  return (
    <ResourceView state={state} onAccessSaved={onAccessSaved} onRetry={reload}>
      {(data) => (
        <>
          <Section
            eyebrow={<StatusBadge status={data.summary.status} />}
            title="Action Queue"
          >
            <SourceWarningBanner warnings={data.source_warnings} />
            <dl className="metric-grid">
              <Metric label="Total" value={data.summary.total} />
              {actionOrder.map((action) => (
                <Metric
                  key={action}
                  label={action.replace("_", " ")}
                  value={data.summary.by_action[action] ?? 0}
                />
              ))}
            </dl>
            {data.items.length === 0 ? (
              <Notice
                detail="The queue loaded successfully and no current opportunity meets action thresholds."
                title="No qualifying opportunities."
              />
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Action</th>
                      <th>Location</th>
                      <th>Property</th>
                      <th>Asking</th>
                      <th>FMV</th>
                      <th>Fast Sale</th>
                      <th>Max Buy</th>
                      <th>Expected Profit</th>
                      <th>Downside</th>
                      <th>Liquidity</th>
                      <th>Confidence</th>
                      <th>Market Age</th>
                      <th>Last Change</th>
                      <th>Listing</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((item) => (
                      <ActionQueueRow item={item} key={item.property_id} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </>
      )}
    </ResourceView>
  );
}

function ActionQueueRow({ item }: { item: ActionQueueItem }) {
  return (
    <tr>
      <td>
        <div className="stack">
          <StatusBadge status={item.recommended_action} />
          {item.is_stale ? <StatusBadge status="STALE" /> : null}
          <ReasonCodes codes={item.reason_codes} />
        </div>
      </td>
      <td>
        <ValueText>{displayValue(item.location.label)}</ValueText>
      </td>
      <td>
        <a href={`/properties/${item.property_id}`}>
          <ValueText>{displayValue(item.property_label)}</ValueText>
        </a>
        <div className="subtle-line">
          {displayValue(item.property_type)} / {displayValue(item.size_m2, " m2")} /{" "}
          {displayValue(item.rooms)} rooms
        </div>
      </td>
      <td>{displayMoney(item.asking_price, item.currency)}</td>
      <td>{displayMoney(item.fair_value_base, item.currency)}</td>
      <td>{displayMoney(item.fast_sale_base, item.currency)}</td>
      <td>{displayMoney(item.max_buy_price, item.currency)}</td>
      <td>{displayMoney(item.expected_profit, item.currency)}</td>
      <td>{displayMoney(item.downside_profit, item.currency)}</td>
      <td>
        <ValueText>{displayValue(item.liquidity_score)}</ValueText>
      </td>
      <td>
        <ValueText>{displayValue(item.valuation_confidence)}</ValueText>
      </td>
      <td>
        <ValueText>{displayValue(item.property_market_age_days)}</ValueText>
      </td>
      <td>{displayDateTime(item.last_change)}</td>
      <td>
        <ExternalListingLink url={item.current_listing.url} />
      </td>
    </tr>
  );
}

function PropertiesPage({ accessRevision, onAccessSaved }: PageProps) {
  const { state, reload } = useApiResource<PropertiesResponse>(
    "/api/v1/properties",
    accessRevision,
  );

  return (
    <ResourceView state={state} onAccessSaved={onAccessSaved} onRetry={reload}>
      {(data) => (
        <Section title="Properties">
          {data.items.length === 0 ? (
            <Notice title="No properties yet." />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Property</th>
                    <th>Location</th>
                    <th>Action</th>
                    <th>Risk</th>
                    <th>Asking</th>
                    <th>Max Buy</th>
                    <th>Expected Profit</th>
                    <th>Downside</th>
                    <th>Status</th>
                    <th>Listing</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <PropertyListRow item={item} key={item.property_id} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}
    </ResourceView>
  );
}

function PropertyListRow({ item }: { item: PropertyListItem }) {
  return (
    <tr>
      <td>
        <a href={`/properties/${item.property_id}`}>
          <ValueText>{displayValue(item.property_label)}</ValueText>
        </a>
        <div className="subtle-line">
          {displayValue(item.size_m2, " m2")} / {displayValue(item.rooms)} rooms
        </div>
      </td>
      <td>
        <ValueText>{displayValue(item.location.label)}</ValueText>
      </td>
      <td>
        <StatusBadge status={item.recommended_action} />
        <ReasonCodes codes={item.reason_codes} />
      </td>
      <td>
        <StatusBadge status={item.risk_gate} />
      </td>
      <td>{displayMoney(item.asking_price)}</td>
      <td>{displayMoney(item.max_buy_price)}</td>
      <td>{displayMoney(item.expected_profit)}</td>
      <td>{displayMoney(item.downside_profit)}</td>
      <td>
        <StatusBadge status={item.analysis_status} />
      </td>
      <td>
        <ExternalListingLink url={item.current_listing.url} />
      </td>
    </tr>
  );
}

function WatchlistPage({ accessRevision, onAccessSaved }: PageProps) {
  const { state, reload } = useApiResource<WatchlistResponse>(
    "/api/v1/watchlist",
    accessRevision,
  );

  return (
    <ResourceView state={state} onAccessSaved={onAccessSaved} onRetry={reload}>
      {(data) => (
        <Section title="Watchlist">
          {data.items.length === 0 ? (
            <Notice title="No watched properties." />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Location</th>
                    <th>Property</th>
                    <th>Asking</th>
                    <th>Max Buy</th>
                    <th>Gap</th>
                    <th>Last Price Cut</th>
                    <th>Market Age</th>
                    <th>Watch Trigger</th>
                    <th>Last Change</th>
                    <th>Action</th>
                    <th>Listing</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <WatchlistRow item={item} key={item.property_id} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}
    </ResourceView>
  );
}

function WatchlistRow({ item }: { item: WatchlistItem }) {
  return (
    <tr>
      <td>
        <ValueText>{displayValue(item.location.label)}</ValueText>
      </td>
      <td>
        <a href={`/properties/${item.property_id}`}>
          <ValueText>{displayValue(item.property_label)}</ValueText>
        </a>
      </td>
      <td>{displayMoney(item.asking_price, item.currency)}</td>
      <td>{displayMoney(item.max_buy_price, item.currency)}</td>
      <td>{displayMoney(item.gap_to_max_buy, item.currency)}</td>
      <td>{displayDateTime(item.last_price_cut)}</td>
      <td>
        <ValueText>{displayValue(item.property_market_age_days)}</ValueText>
      </td>
      <td>
        {displayWatchTrigger(
          item.watch_rule?.rule_type,
          item.watch_rule?.threshold_numeric,
        )}
      </td>
      <td>
        {displayDateTime(item.last_change)}
        {item.last_change_summary ? (
          <div className="subtle-line">
            {displayValue(item.last_change_summary.summary_text)}
          </div>
        ) : null}
      </td>
      <td>
        <div className="stack">
          <StatusBadge status={item.recommended_action} />
          <StatusBadge status={item.analysis_status} />
        </div>
      </td>
      <td>
        <ExternalListingLink url={item.current_listing.url} />
      </td>
    </tr>
  );
}

function PipelinePage({ accessRevision, onAccessSaved }: PageProps) {
  const [selectedStatus, setSelectedStatus] = useState("");
  const path = selectedStatus
    ? `/api/v1/pipeline?pipeline_status=${encodeURIComponent(selectedStatus)}`
    : "/api/v1/pipeline";
  const { state, reload } = useApiResource<PipelineResponse>(path, accessRevision);

  return (
    <ResourceView state={state} onAccessSaved={onAccessSaved} onRetry={reload}>
      {(data) => (
        <Section title="Pipeline">
          <form
            className="watch-form"
            onSubmit={(event) => event.preventDefault()}
          >
            <label className="watch-field" htmlFor="pipeline-filter">
              <span>Status</span>
              <select
                id="pipeline-filter"
                onChange={(event) => setSelectedStatus(event.target.value)}
                value={selectedStatus}
              >
                <option value="">ALL</option>
                {pipelineStatuses.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </label>
          </form>
          <dl className="metric-grid">
            {pipelineStatuses.map((status) => (
              <Metric
                key={status}
                label={status.replaceAll("_", " ")}
                value={<StatusCount count={data.summary[status] ?? 0} status={status} />}
              />
            ))}
          </dl>
          {data.items.length === 0 ? (
            <Notice title="No properties in this pipeline view." />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Property</th>
                    <th>Pipeline</th>
                    <th>Action</th>
                    <th>Last Interaction</th>
                    <th>Next Follow-Up</th>
                    <th>Latest Offer</th>
                    <th>Skip / Outcome</th>
                    <th>Listing</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <PipelineRow item={item} key={item.property_id} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}
    </ResourceView>
  );
}

function PipelineRow({ item }: { item: PipelineItem }) {
  const pipeline = item.pipeline;
  return (
    <tr>
      <td>
        <a href={`/properties/${item.property_id}`}>
          <ValueText>{displayValue(item.property_label)}</ValueText>
        </a>
        <div className="subtle-line">
          {displayValue(item.location.label)} / {displayValue(item.size_m2, " m2")}
        </div>
      </td>
      <td>
        <div className="stack">
          <StatusBadge status={pipeline.status} />
          <span className="subtle-line">
            {displayDateTime(pipeline.status_updated_at)}
          </span>
        </div>
      </td>
      <td>
        <div className="stack">
          <StatusBadge status={item.recommended_action} />
          <ReasonCodes codes={item.reason_codes} />
        </div>
      </td>
      <td>
        {pipeline.latest_interaction ? (
          <div className="stack">
            <StatusBadge status={pipeline.latest_interaction.interaction_type} />
            <span>{displayDateTime(pipeline.latest_interaction.occurred_at)}</span>
            <span className="subtle-line">
              {displayValue(pipeline.latest_interaction.notes)}
            </span>
          </div>
        ) : (
          <ValueText>UNKNOWN</ValueText>
        )}
      </td>
      <td>
        {pipeline.next_follow_up ? (
          <div className="stack">
            <span>{displayDateTime(pipeline.next_follow_up.follow_up_at)}</span>
            <span className="subtle-line">
              {displayValue(pipeline.next_follow_up.follow_up_notes)}
            </span>
          </div>
        ) : (
          <ValueText>UNKNOWN</ValueText>
        )}
      </td>
      <td>
        {pipeline.latest_offer ? (
          <div className="stack">
            <StatusBadge status={pipeline.latest_offer.status} />
            <span>
              {displayMoney(
                pipeline.latest_offer.amount,
                pipeline.latest_offer.currency,
              )}
            </span>
            <span className="subtle-line">
              Counter:{" "}
              {displayMoney(
                pipeline.latest_offer.counteroffer_amount,
                pipeline.latest_offer.currency,
              )}
            </span>
          </div>
        ) : (
          <ValueText>UNKNOWN</ValueText>
        )}
      </td>
      <td>
        <div className="stack">
          {pipeline.latest_skip ? (
            <StatusBadge status={pipeline.latest_skip.reason_code} />
          ) : null}
          {pipeline.latest_outcome ? (
            <StatusBadge status={pipeline.latest_outcome.outcome_type} />
          ) : null}
          {!pipeline.latest_skip && !pipeline.latest_outcome ? (
            <ValueText>UNKNOWN</ValueText>
          ) : null}
        </div>
      </td>
      <td>
        <ExternalListingLink url={item.current_listing.url} />
      </td>
    </tr>
  );
}

function PropertyDetailPage({
  propertyId,
  accessRevision,
  onAccessSaved,
}: PageProps & { propertyId: string }) {
  const { state, reload } = useApiResource<PropertyDetail>(
    `/api/v1/properties/${propertyId}`,
    accessRevision,
  );

  return (
    <ResourceView state={state} onAccessSaved={onAccessSaved} onRetry={reload}>
      {(detail) => <PropertyDetailContent detail={detail} onReload={reload} />}
    </ResourceView>
  );
}

function PropertyDetailContent({
  detail,
  onReload,
}: {
  detail: PropertyDetail;
  onReload: () => void;
}) {
  const currency = detail.decision.currency;
  const riskGate = detail.decision.risk_gate;
  const [watchRuleType, setWatchRuleType] = useState(
    detail.watch.active_rule?.rule_type ?? "",
  );
  const [watchThreshold, setWatchThreshold] = useState(
    detail.watch.active_rule?.threshold_numeric ?? "",
  );
  const [commandMessage, setCommandMessage] = useState<string | null>(null);
  const [commandPending, setCommandPending] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState(detail.acquisition.pipeline_status);
  const [pipelineReason, setPipelineReason] = useState("");
  const [reviewDecision, setReviewDecision] = useState("INTERESTING");
  const [reviewNotes, setReviewNotes] = useState("");
  const [reviewManualFmv, setReviewManualFmv] = useState("");
  const [reviewManualFastSale, setReviewManualFastSale] = useState("");
  const [reviewManualMaxBuy, setReviewManualMaxBuy] = useState("");
  const [callSellerMotivation, setCallSellerMotivation] = useState("");
  const [callReasonForSale, setCallReasonForSale] = useState("");
  const [callLowestPrice, setCallLowestPrice] = useState("");
  const [callCashPreferred, setCallCashPreferred] = useState("");
  const [callViewingAvailable, setCallViewingAvailable] = useState("");
  const [callClaimedRegistered, setCallClaimedRegistered] = useState("");
  const [callClaimedOwner, setCallClaimedOwner] = useState("");
  const [callClaimedMortgage, setCallClaimedMortgage] = useState("");
  const [callTenantPresent, setCallTenantPresent] = useState("");
  const [callDesiredClosingDays, setCallDesiredClosingDays] = useState("");
  const [callFollowUpAt, setCallFollowUpAt] = useState("");
  const [callFollowUpNotes, setCallFollowUpNotes] = useState("");
  const [callNotes, setCallNotes] = useState("");
  const [visitCondition, setVisitCondition] = useState("");
  const [visitRenovationBase, setVisitRenovationBase] = useState("");
  const [visitElevatorVerified, setVisitElevatorVerified] = useState("");
  const [visitManualFmv, setVisitManualFmv] = useState("");
  const [visitManualFastSale, setVisitManualFastSale] = useState("");
  const [visitManualMaxBuy, setVisitManualMaxBuy] = useState("");
  const [visitVisibleDefects, setVisitVisibleDefects] = useState("");
  const [visitNotes, setVisitNotes] = useState("");
  const [offerAmount, setOfferAmount] = useState("");
  const [offerStatus, setOfferStatus] = useState("OPEN");
  const [offerCounteroffer, setOfferCounteroffer] = useState("");
  const [offerNotes, setOfferNotes] = useState("");
  const [skipReason, setSkipReason] = useState("OVERPRICED");
  const [skipNotes, setSkipNotes] = useState("");
  const [outcomeType, setOutcomeType] = useState("STILL_ACTIVE");
  const [outcomeSalePrice, setOutcomeSalePrice] = useState("");
  const [outcomeNotes, setOutcomeNotes] = useState("");

  useEffect(() => {
    setWatchRuleType(detail.watch.active_rule?.rule_type ?? "");
    setWatchThreshold(detail.watch.active_rule?.threshold_numeric ?? "");
  }, [detail.watch.active_rule?.rule_type, detail.watch.active_rule?.threshold_numeric]);

  useEffect(() => {
    setPipelineStatus(detail.acquisition.pipeline_status);
  }, [detail.acquisition.pipeline_status]);

  async function runCommand(
    action: () => Promise<CommandResult>,
    failureMessage: string,
  ) {
    setCommandPending(true);
    setCommandMessage(null);
    try {
      const response = await action();
      const invalidated = response.invalidated_modules?.join(", ");
      const reanalyzed = response.reanalyzed_modules?.join(", ");
      setCommandMessage(
        [
          response.status,
          invalidated ? `invalidated: ${invalidated}` : null,
          reanalyzed ? `reanalyzed: ${reanalyzed}` : null,
        ]
          .filter(Boolean)
          .join(" / "),
      );
      onReload();
    } catch (error) {
      setCommandMessage(error instanceof Error ? error.message : failureMessage);
    } finally {
      setCommandPending(false);
    }
  }

  async function submitPipelineStatus(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runCommand(
      () =>
        apiPatch<CommandResult>(
          `/api/v1/properties/${detail.property.property_id}/pipeline-status`,
          {
            status: pipelineStatus,
            reason: emptyToNull(pipelineReason),
          },
        ),
      "Pipeline update failed",
    );
  }

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runCommand(
      () =>
        apiPost<CommandResult>(`/api/v1/properties/${detail.property.property_id}/review`, {
          decision: reviewDecision,
          manual_fmv: emptyToNull(reviewManualFmv),
          manual_fast_sale_value: emptyToNull(reviewManualFastSale),
          manual_max_buy_price: emptyToNull(reviewManualMaxBuy),
          notes: emptyToNull(reviewNotes),
        }),
      "Review request failed",
    );
  }

  async function submitCall(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runCommand(
      () =>
        apiPost<CommandResult>(
          `/api/v1/properties/${detail.property.property_id}/interactions/call`,
          {
            seller_motivation: callSellerMotivation || null,
            reason_for_sale: callReasonForSale || null,
            lowest_indicated_price: emptyToNull(callLowestPrice),
            cash_preferred: booleanFromSelect(callCashPreferred),
            desired_closing_days: emptyToNull(callDesiredClosingDays),
            viewing_available: booleanFromSelect(callViewingAvailable),
            claimed_registered: booleanFromSelect(callClaimedRegistered),
            claimed_owner_1_1: booleanFromSelect(callClaimedOwner),
            claimed_mortgage: booleanFromSelect(callClaimedMortgage),
            tenant_present: booleanFromSelect(callTenantPresent),
            follow_up_at: emptyToNull(callFollowUpAt),
            follow_up_notes: emptyToNull(callFollowUpNotes),
            notes: emptyToNull(callNotes),
          },
        ),
      "Call feedback request failed",
    );
  }

  async function submitVisit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const visibleDefects = visitVisibleDefects
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    await runCommand(
      () =>
        apiPost<CommandResult>(
          `/api/v1/properties/${detail.property.property_id}/interactions/visit`,
          {
            condition_category: emptyToNull(visitCondition),
            estimated_renovation_base: emptyToNull(visitRenovationBase),
            elevator_verified: booleanFromSelect(visitElevatorVerified),
            visible_defects: visibleDefects,
            manual_fmv: emptyToNull(visitManualFmv),
            manual_fast_sale_value: emptyToNull(visitManualFastSale),
            manual_max_buy_price: emptyToNull(visitManualMaxBuy),
            notes: emptyToNull(visitNotes),
          },
        ),
      "Visit feedback request failed",
    );
  }

  async function submitOffer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runCommand(
      () =>
        apiPost<CommandResult>(`/api/v1/properties/${detail.property.property_id}/offers`, {
          amount: offerAmount,
          currency: currency ?? "EUR",
          status: offerStatus,
          counteroffer_amount: emptyToNull(offerCounteroffer),
          notes: emptyToNull(offerNotes),
        }),
      "Offer request failed",
    );
  }

  async function submitSkip(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runCommand(
      () =>
        apiPost<CommandResult>(`/api/v1/properties/${detail.property.property_id}/skip`, {
          reason_code: skipReason,
          notes: emptyToNull(skipNotes),
        }),
      "Skip request failed",
    );
  }

  async function submitOutcome(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runCommand(
      () =>
        apiPost<CommandResult>(`/api/v1/properties/${detail.property.property_id}/outcomes`, {
          outcome_type: outcomeType,
          sale_price: emptyToNull(outcomeSalePrice),
          currency: currency ?? "EUR",
          source_kind: "MANUAL",
          notes: emptyToNull(outcomeNotes),
        }),
      "Outcome request failed",
    );
  }

  async function submitWatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCommandPending(true);
    setCommandMessage(null);
    try {
      await apiPost(`/api/v1/properties/${detail.property.property_id}/watch`, {
        rule_type: watchRuleType || null,
        threshold_numeric: watchThreshold || null,
      });
      setCommandMessage("WATCHED");
      onReload();
    } catch (error) {
      setCommandMessage(error instanceof Error ? error.message : "Watch request failed");
    } finally {
      setCommandPending(false);
    }
  }

  async function unwatch() {
    setCommandPending(true);
    setCommandMessage(null);
    try {
      await apiDelete(`/api/v1/properties/${detail.property.property_id}/watch`);
      setCommandMessage("UNWATCHED");
      onReload();
    } catch (error) {
      setCommandMessage(error instanceof Error ? error.message : "Unwatch request failed");
    } finally {
      setCommandPending(false);
    }
  }

  async function reanalyze() {
    setCommandPending(true);
    setCommandMessage(null);
    try {
      const response = await apiPost<{ status: string }>(
        `/api/v1/properties/${detail.property.property_id}/reanalyze`,
      );
      setCommandMessage(response.status);
      onReload();
    } catch (error) {
      setCommandMessage(error instanceof Error ? error.message : "Reanalysis request failed");
    } finally {
      setCommandPending(false);
    }
  }

  return (
    <>
      <Section
        eyebrow={<StatusBadge status={detail.decision.recommended_action} />}
        title={displayValue(detail.decision.property_label)}
      >
        {detail.freshness.is_stale ? (
          <Notice
            detail="At least one current analysis result predates the latest listing input."
            title="STALE analysis"
            tone="warning"
          />
        ) : null}
        {riskGate === "BLOCK" ? (
          <Notice
            detail="Backend risk gate is BLOCK. Do not treat this as an aggressive action candidate."
            title="Risk Gate: BLOCK"
            tone="critical"
          />
        ) : null}
        <dl className="metric-grid primary-metrics">
          <Metric
            label="Asking"
            value={displayMoney(valueAsString(detail.decision.asking_price), currency)}
          />
          <Metric
            label="FMV Base"
            value={displayMoney(valueAsString(detail.decision.fair_value_base), currency)}
          />
          <Metric
            label="Fast Sale"
            value={displayMoney(valueAsString(detail.decision.fast_sale_base), currency)}
          />
          <Metric
            label="Max Buy"
            value={displayMoney(valueAsString(detail.decision.max_buy_price), currency)}
            tone="action"
          />
          <Metric
            label="Expected Profit"
            value={displayMoney(valueAsString(detail.decision.expected_profit), currency)}
          />
          <Metric
            label="Downside"
            value={displayMoney(valueAsString(detail.decision.downside_profit), currency)}
            tone={valueAsString(detail.decision.downside_profit)?.startsWith("-") ? "critical" : undefined}
          />
          <Metric
            label="Liquidity"
            value={displayValue(detail.decision.liquidity_score)}
          />
          <Metric
            label="Confidence"
            value={displayValue(detail.decision.valuation_confidence)}
          />
          <Metric label="Risk Gate" value={<StatusBadge status={riskGate} />} />
        </dl>
        <ReasonCodes codes={detail.decision.reason_codes} />
        <div className="freshness-row">
          <span>Last Listing Update: {displayDateTime(detail.freshness.last_listing_update)}</span>
          <span>Last Analysis: {displayDateTime(detail.freshness.last_analysis)}</span>
        </div>
      </Section>

      <Section
        title="Watch"
        eyebrow={
          <StatusBadge status={detail.watch.is_watched ? "WATCH" : "NOT_WATCHED"} />
        }
      >
        <form className="watch-form" onSubmit={submitWatch}>
          <label className="watch-field" htmlFor="watch-rule">
            <span>Watch Trigger</span>
            <select
              id="watch-rule"
              onChange={(event) => setWatchRuleType(event.target.value)}
              value={watchRuleType}
            >
              {watchRuleTypes.map((ruleType) => (
                <option key={ruleType || "DEFAULT"} value={ruleType}>
                  {ruleType || "DEFAULT_RELEVANT_CHANGE"}
                </option>
              ))}
            </select>
          </label>
          <label className="watch-field" htmlFor="watch-threshold">
            <span>Threshold</span>
            <input
              id="watch-threshold"
              inputMode="decimal"
              onChange={(event) => setWatchThreshold(event.target.value)}
              placeholder="UNKNOWN"
              value={watchThreshold}
            />
          </label>
          <div className="watch-actions">
            <button disabled={commandPending} type="submit">
              Watch
            </button>
            <button disabled={commandPending} onClick={unwatch} type="button">
              Unwatch
            </button>
            <button disabled={commandPending} onClick={reanalyze} type="button">
              Reanalyze
            </button>
          </div>
        </form>
        {commandMessage ? <StatusBadge status={commandMessage} /> : null}
        <KeyValueGrid
          rows={[
            [
              "Active Trigger",
              displayWatchTrigger(
                detail.watch.active_rule?.rule_type,
                detail.watch.active_rule?.threshold_numeric,
              ),
            ],
            [
              "Last Evaluated",
              displayDateTime(detail.watch.active_rule?.last_evaluated_at),
            ],
            ["Last Triggered", displayDateTime(detail.watch.active_rule?.triggered_at)],
          ]}
        />
      </Section>

      <Section
        title="Acquisition Workflow"
        eyebrow={<StatusBadge status={detail.acquisition.pipeline_status} />}
      >
        {commandMessage ? <StatusBadge status={commandMessage} /> : null}
        <div className="crm-grid">
          <form className="crm-form" onSubmit={submitPipelineStatus}>
            <h3>Pipeline Status</h3>
            <label className="watch-field" htmlFor="pipeline-status">
              <span>Status</span>
              <select
                id="pipeline-status"
                onChange={(event) => setPipelineStatus(event.target.value)}
                value={pipelineStatus}
              >
                {pipelineStatuses.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </label>
            <label className="watch-field" htmlFor="pipeline-reason">
              <span>Reason</span>
              <input
                id="pipeline-reason"
                onChange={(event) => setPipelineReason(event.target.value)}
                value={pipelineReason}
              />
            </label>
            <button disabled={commandPending} type="submit">
              Update Status
            </button>
          </form>

          <form className="crm-form" onSubmit={submitReview}>
            <h3>Review</h3>
            <label className="watch-field" htmlFor="review-decision">
              <span>Decision</span>
              <select
                id="review-decision"
                onChange={(event) => setReviewDecision(event.target.value)}
                value={reviewDecision}
              >
                {reviewDecisions.map((decision) => (
                  <option key={decision} value={decision}>
                    {decision}
                  </option>
                ))}
              </select>
            </label>
            <div className="crm-form-row">
              <label className="watch-field" htmlFor="review-fmv">
                <span>Manual FMV</span>
                <input
                  id="review-fmv"
                  inputMode="decimal"
                  onChange={(event) => setReviewManualFmv(event.target.value)}
                  placeholder="UNKNOWN"
                  value={reviewManualFmv}
                />
              </label>
              <label className="watch-field" htmlFor="review-fast-sale">
                <span>Fast Sale</span>
                <input
                  id="review-fast-sale"
                  inputMode="decimal"
                  onChange={(event) => setReviewManualFastSale(event.target.value)}
                  placeholder="UNKNOWN"
                  value={reviewManualFastSale}
                />
              </label>
              <label className="watch-field" htmlFor="review-max-buy">
                <span>Max Buy</span>
                <input
                  id="review-max-buy"
                  inputMode="decimal"
                  onChange={(event) => setReviewManualMaxBuy(event.target.value)}
                  placeholder="UNKNOWN"
                  value={reviewManualMaxBuy}
                />
              </label>
            </div>
            <label className="watch-field" htmlFor="review-notes">
              <span>Notes</span>
              <textarea
                id="review-notes"
                onChange={(event) => setReviewNotes(event.target.value)}
                value={reviewNotes}
              />
            </label>
            <button disabled={commandPending} type="submit">
              Save Review
            </button>
          </form>

          <form className="crm-form wide-form" onSubmit={submitCall}>
            <h3>Log Call</h3>
            <div className="crm-form-row">
              <label className="watch-field" htmlFor="call-motivation">
                <span>Motivation</span>
                <select
                  id="call-motivation"
                  onChange={(event) => setCallSellerMotivation(event.target.value)}
                  value={callSellerMotivation}
                >
                  {sellerMotivationLevels.map((level) => (
                    <option key={level || "UNKNOWN"} value={level}>
                      {level || "UNKNOWN"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="watch-field" htmlFor="call-reason">
                <span>Reason For Sale</span>
                <select
                  id="call-reason"
                  onChange={(event) => setCallReasonForSale(event.target.value)}
                  value={callReasonForSale}
                >
                  {reasonForSaleOptions.map((reason) => (
                    <option key={reason || "UNKNOWN"} value={reason}>
                      {reason || "UNKNOWN"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="watch-field" htmlFor="call-lowest-price">
                <span>Lowest Price</span>
                <input
                  id="call-lowest-price"
                  inputMode="decimal"
                  onChange={(event) => setCallLowestPrice(event.target.value)}
                  placeholder="UNKNOWN"
                  value={callLowestPrice}
                />
              </label>
            </div>
            <div className="crm-form-row">
              <label className="watch-field" htmlFor="call-cash">
                <span>Cash Preferred</span>
                <select
                  id="call-cash"
                  onChange={(event) => setCallCashPreferred(event.target.value)}
                  value={callCashPreferred}
                >
                  {booleanOptions.map((option) => (
                    <option key={option.label} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="watch-field" htmlFor="call-viewing">
                <span>Viewing</span>
                <select
                  id="call-viewing"
                  onChange={(event) => setCallViewingAvailable(event.target.value)}
                  value={callViewingAvailable}
                >
                  {booleanOptions.map((option) => (
                    <option key={option.label} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="watch-field" htmlFor="call-days">
                <span>Closing Days</span>
                <input
                  id="call-days"
                  inputMode="numeric"
                  onChange={(event) => setCallDesiredClosingDays(event.target.value)}
                  placeholder="UNKNOWN"
                  value={callDesiredClosingDays}
                />
              </label>
            </div>
            <div className="crm-form-row">
              <label className="watch-field" htmlFor="call-registered">
                <span>Claimed Registered</span>
                <select
                  id="call-registered"
                  onChange={(event) => setCallClaimedRegistered(event.target.value)}
                  value={callClaimedRegistered}
                >
                  {booleanOptions.map((option) => (
                    <option key={option.label} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="watch-field" htmlFor="call-owner">
                <span>Claimed Owner 1/1</span>
                <select
                  id="call-owner"
                  onChange={(event) => setCallClaimedOwner(event.target.value)}
                  value={callClaimedOwner}
                >
                  {booleanOptions.map((option) => (
                    <option key={option.label} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="watch-field" htmlFor="call-mortgage">
                <span>Claimed Mortgage</span>
                <select
                  id="call-mortgage"
                  onChange={(event) => setCallClaimedMortgage(event.target.value)}
                  value={callClaimedMortgage}
                >
                  {booleanOptions.map((option) => (
                    <option key={option.label} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="watch-field" htmlFor="call-tenant">
                <span>Tenant</span>
                <select
                  id="call-tenant"
                  onChange={(event) => setCallTenantPresent(event.target.value)}
                  value={callTenantPresent}
                >
                  {booleanOptions.map((option) => (
                    <option key={option.label} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="crm-form-row">
              <label className="watch-field" htmlFor="call-follow-up-at">
                <span>Follow-Up At</span>
                <input
                  id="call-follow-up-at"
                  onChange={(event) => setCallFollowUpAt(event.target.value)}
                  type="datetime-local"
                  value={callFollowUpAt}
                />
              </label>
              <label className="watch-field" htmlFor="call-follow-up-notes">
                <span>Follow-Up Notes</span>
                <input
                  id="call-follow-up-notes"
                  onChange={(event) => setCallFollowUpNotes(event.target.value)}
                  value={callFollowUpNotes}
                />
              </label>
            </div>
            <label className="watch-field" htmlFor="call-notes">
              <span>Notes</span>
              <textarea
                id="call-notes"
                onChange={(event) => setCallNotes(event.target.value)}
                value={callNotes}
              />
            </label>
            <button disabled={commandPending} type="submit">
              Save Call
            </button>
          </form>

          <form className="crm-form wide-form" onSubmit={submitVisit}>
            <h3>Log Visit</h3>
            <div className="crm-form-row">
              <label className="watch-field" htmlFor="visit-condition">
                <span>Condition</span>
                <input
                  id="visit-condition"
                  onChange={(event) => setVisitCondition(event.target.value)}
                  placeholder="UNKNOWN"
                  value={visitCondition}
                />
              </label>
              <label className="watch-field" htmlFor="visit-renovation">
                <span>Renovation Base</span>
                <input
                  id="visit-renovation"
                  inputMode="decimal"
                  onChange={(event) => setVisitRenovationBase(event.target.value)}
                  placeholder="UNKNOWN"
                  value={visitRenovationBase}
                />
              </label>
              <label className="watch-field" htmlFor="visit-elevator">
                <span>Elevator Verified</span>
                <select
                  id="visit-elevator"
                  onChange={(event) => setVisitElevatorVerified(event.target.value)}
                  value={visitElevatorVerified}
                >
                  {booleanOptions.map((option) => (
                    <option key={option.label} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="crm-form-row">
              <label className="watch-field" htmlFor="visit-fmv">
                <span>Manual FMV</span>
                <input
                  id="visit-fmv"
                  inputMode="decimal"
                  onChange={(event) => setVisitManualFmv(event.target.value)}
                  placeholder="UNKNOWN"
                  value={visitManualFmv}
                />
              </label>
              <label className="watch-field" htmlFor="visit-fast-sale">
                <span>Fast Sale</span>
                <input
                  id="visit-fast-sale"
                  inputMode="decimal"
                  onChange={(event) => setVisitManualFastSale(event.target.value)}
                  placeholder="UNKNOWN"
                  value={visitManualFastSale}
                />
              </label>
              <label className="watch-field" htmlFor="visit-max-buy">
                <span>Max Buy</span>
                <input
                  id="visit-max-buy"
                  inputMode="decimal"
                  onChange={(event) => setVisitManualMaxBuy(event.target.value)}
                  placeholder="UNKNOWN"
                  value={visitManualMaxBuy}
                />
              </label>
            </div>
            <label className="watch-field" htmlFor="visit-defects">
              <span>Visible Defects</span>
              <input
                id="visit-defects"
                onChange={(event) => setVisitVisibleDefects(event.target.value)}
                placeholder="comma separated"
                value={visitVisibleDefects}
              />
            </label>
            <label className="watch-field" htmlFor="visit-notes">
              <span>Notes</span>
              <textarea
                id="visit-notes"
                onChange={(event) => setVisitNotes(event.target.value)}
                value={visitNotes}
              />
            </label>
            <button disabled={commandPending} type="submit">
              Save Visit
            </button>
          </form>

          <form className="crm-form" onSubmit={submitOffer}>
            <h3>Offer</h3>
            <label className="watch-field" htmlFor="offer-amount">
              <span>Amount</span>
              <input
                id="offer-amount"
                inputMode="decimal"
                onChange={(event) => setOfferAmount(event.target.value)}
                required
                value={offerAmount}
              />
            </label>
            <label className="watch-field" htmlFor="offer-status">
              <span>Status</span>
              <select
                id="offer-status"
                onChange={(event) => setOfferStatus(event.target.value)}
                value={offerStatus}
              >
                {offerStatuses.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </label>
            <label className="watch-field" htmlFor="offer-counter">
              <span>Counteroffer</span>
              <input
                id="offer-counter"
                inputMode="decimal"
                onChange={(event) => setOfferCounteroffer(event.target.value)}
                placeholder="UNKNOWN"
                value={offerCounteroffer}
              />
            </label>
            <label className="watch-field" htmlFor="offer-notes">
              <span>Notes</span>
              <textarea
                id="offer-notes"
                onChange={(event) => setOfferNotes(event.target.value)}
                value={offerNotes}
              />
            </label>
            <button disabled={commandPending} type="submit">
              Save Offer
            </button>
          </form>

          <form className="crm-form" onSubmit={submitSkip}>
            <h3>Skip</h3>
            <label className="watch-field" htmlFor="skip-reason">
              <span>Reason</span>
              <select
                id="skip-reason"
                onChange={(event) => setSkipReason(event.target.value)}
                value={skipReason}
              >
                {skipReasonCodes.map((reason) => (
                  <option key={reason} value={reason}>
                    {reason}
                  </option>
                ))}
              </select>
            </label>
            <label className="watch-field" htmlFor="skip-notes">
              <span>Notes</span>
              <textarea
                id="skip-notes"
                onChange={(event) => setSkipNotes(event.target.value)}
                value={skipNotes}
              />
            </label>
            <button disabled={commandPending} type="submit">
              Skip Property
            </button>
          </form>

          <form className="crm-form" onSubmit={submitOutcome}>
            <h3>Outcome</h3>
            <label className="watch-field" htmlFor="outcome-type">
              <span>Outcome</span>
              <select
                id="outcome-type"
                onChange={(event) => setOutcomeType(event.target.value)}
                value={outcomeType}
              >
                {outcomeTypes.map((outcome) => (
                  <option key={outcome} value={outcome}>
                    {outcome}
                  </option>
                ))}
              </select>
            </label>
            <label className="watch-field" htmlFor="outcome-sale-price">
              <span>Sale Price</span>
              <input
                id="outcome-sale-price"
                inputMode="decimal"
                onChange={(event) => setOutcomeSalePrice(event.target.value)}
                placeholder="UNKNOWN"
                value={outcomeSalePrice}
              />
            </label>
            <label className="watch-field" htmlFor="outcome-notes">
              <span>Notes</span>
              <textarea
                id="outcome-notes"
                onChange={(event) => setOutcomeNotes(event.target.value)}
                value={outcomeNotes}
              />
            </label>
            <button disabled={commandPending} type="submit">
              Save Outcome
            </button>
          </form>
        </div>
        <KeyValueGrid
          rows={[
            ["Status Updated", displayDateTime(detail.acquisition.pipeline_status_updated_at)],
            ["Reviews", detail.acquisition.reviews.length],
            ["Interactions", detail.acquisition.interactions.length],
            ["Offers", detail.acquisition.offers.length],
            ["Manual Overrides", detail.acquisition.overrides.length],
          ]}
        />
      </Section>

      <Section title="Acquisition Timeline">
        {detail.acquisition.timeline.length === 0 ? (
          <Notice title="No acquisition activity yet." />
        ) : (
          <DataTable
            columns={["When", "Type", "Summary", "Follow-Up", "Notes"]}
            rows={detail.acquisition.timeline.map((item) => [
              displayDateTime(item.occurred_at),
              <StatusBadge status={item.type} key={`${item.record_id}-type`} />,
              displayValue(item.summary),
              item.follow_up_at
                ? `${displayDateTime(item.follow_up_at)} ${displayValue(item.follow_up_notes)}`
                : "UNKNOWN",
              displayValue(item.notes),
            ])}
          />
        )}
      </Section>

      <Section title="What Changed">
        {detail.watch.latest_changes.length === 0 ? (
          <Notice title="No watch-triggered changes." />
        ) : (
          <DataTable
            columns={["When", "Trigger", "Change", "Invalidated", "Reanalyzed"]}
            rows={detail.watch.latest_changes.map((change) => [
              displayDateTime(change.triggered_at),
              displayWatchTrigger(change.trigger_type, null),
              displayValue(change.summary.summary_text),
              change.invalidated_modules.join(", ") || "UNKNOWN",
              change.reanalyzed_modules.join(", ") || "UNKNOWN",
            ])}
          />
        )}
      </Section>

      <Section title="Deal Summary" eyebrow={<StatusBadge status={detail.deal.status} />}>
        <KeyValueGrid
          rows={[
            ["Assumed Purchase", displayMoney(valueAsString(detail.deal.assumed_purchase_price), currency)],
            ["Total Cost Basis", displayMoney(valueAsString(detail.deal.total_cost_basis), currency)],
            ["Expected Exit", displayMoney(valueAsString(detail.deal.expected_exit_price), currency)],
            ["Required Negotiation", displayMoney(valueAsString(detail.deal.required_negotiation_amount), currency)],
            ["Required Negotiation Pct", displayPercent(valueAsString(detail.deal.required_negotiation_pct))],
            ["ROI", displayPercent(valueAsString(detail.deal.roi))],
            ["Annualized ROI", displayPercent(valueAsString(detail.deal.annualized_roi))],
            ["Holding Days", displayValue(detail.deal.expected_holding_days)],
            ["Formula Version", displayValue(detail.deal.formula_version)],
          ]}
        />
        <h3>Costs</h3>
        <KeyValueGrid
          rows={Object.entries(detail.deal.costs ?? {}).map(([key, value]) => [
            key.replaceAll("_", " "),
            displayMoney(valueAsString(value), currency),
          ])}
        />
        {detail.deal.scenarios.length > 0 ? (
          <DataTable
            columns={["Scenario", "Purchase", "Exit", "Cost Basis", "Profit", "ROI", "Days"]}
            rows={detail.deal.scenarios.map((scenario) => [
              displayValue(scenario.scenario_type),
              displayMoney(valueAsString(scenario.purchase_price), currency),
              displayMoney(valueAsString(scenario.exit_price), currency),
              displayMoney(valueAsString(scenario.cost_basis), currency),
              displayMoney(valueAsString(scenario.profit), currency),
              displayPercent(valueAsString(scenario.roi)),
              displayValue(scenario.holding_days),
            ])}
          />
        ) : (
          <Notice title="No scenarios calculated." />
        )}
      </Section>

      <Section title="Property Data">
        <KeyValueGrid
          rows={[
            ["Location", displayValue(detail.property.location.label)],
            ["Type", displayValue(detail.property.property_type)],
            ["Size", displayValue(detail.property.size_m2, " m2")],
            ["Rooms", displayValue(detail.property.rooms)],
            ["Floor", displayValue(detail.property.floor)],
            ["Elevator", displayBoolean(valueAsBoolean(detail.property.elevator))],
            ["Parking", displayBoolean(valueAsBoolean(detail.property.parking))],
            ["Condition", displayValue(detail.property.condition_category)],
            ["Market Age", displayValue(detail.property.property_market_age_days)],
            ["Active Listings", displayValue(detail.property.active_listing_count)],
            ["Relists", displayValue(detail.property.relist_count)],
          ]}
        />
      </Section>

      <Section title="Listings">
        {detail.listings.length === 0 ? (
          <Notice title="No linked listings." />
        ) : (
          <DataTable
            columns={[
              "Source",
              "Status",
              "Seller",
              "Agency",
              "Price",
              "First Seen",
              "Last Seen",
              "Original",
            ]}
            rows={detail.listings.map((listing) => [
              `${listing.source_name} (${listing.source_code})`,
              <StatusBadge status={listing.status} key={`${listing.listing_id}-status`} />,
              displayValue(listing.seller_name),
              displayValue(listing.agency_name),
              displayMoney(valueAsString(listing.asking_price), listing.currency),
              displayDateTime(valueAsString(listing.first_seen_at)),
              displayDateTime(valueAsString(listing.last_seen_at)),
              <ExternalListingLink key={listing.listing_id} url={listing.url} />,
            ])}
          />
        )}
      </Section>

      <Section title="Price & Listing History">
        {detail.history.length === 0 ? (
          <Notice title="No listing history yet." />
        ) : (
          <DataTable
            columns={["When", "Event", "Source", "Old Price", "New Price"]}
            rows={detail.history.map((item) => [
              displayDateTime(valueAsString(item.detected_at)),
              displayValue(item.event_type),
              displayValue(item.source_code),
              displayMoney(valueAsString(item.old_price), currency),
              displayMoney(valueAsString(item.new_price), currency),
            ])}
          />
        )}
      </Section>

      <Section title="Valuation" eyebrow={<StatusBadge status={detail.valuation.status} />}>
        <KeyValueGrid
          rows={[
            ["FMV Low", displayMoney(valueAsString(detail.valuation.fair_value_low), currency)],
            ["FMV Base", displayMoney(valueAsString(detail.valuation.fair_value_base), currency)],
            ["FMV High", displayMoney(valueAsString(detail.valuation.fair_value_high), currency)],
            ["Confidence", displayValue(detail.valuation.confidence)],
            ["Model", displayValue(detail.valuation.model_version)],
          ]}
        />
      </Section>

      <Section title="Comparables" eyebrow={<StatusBadge status={detail.comparables.status} />}>
        {detail.comparables.items.length === 0 ? (
          <Notice title="No comparable set available." />
        ) : (
          <DataTable
            columns={[
              "Type",
              "Listing",
              "Distance",
              "Age",
              "Price",
              "Price/m2",
              "Similarity",
              "Weight",
              "Included",
              "Exclusion",
            ]}
            rows={detail.comparables.items.map((item) => [
              displayValue(item.comparable_type),
              displayValue(item.listing_title),
              displayValue(item.distance_m, " m"),
              displayValue(item.age_days_at_analysis),
              displayMoney(valueAsString(item.price), currency),
              displayMoney(valueAsString(item.price_per_m2), currency),
              displayValue(item.similarity_score),
              displayValue(item.weight),
              displayBoolean(valueAsBoolean(item.included_in_valuation)),
              displayValue(item.exclusion_reason),
            ])}
          />
        )}
      </Section>

      <Section
        title="Liquidity"
        eyebrow={<StatusBadge status={detail.liquidity.assessment?.status ?? "NOT_RUN"} />}
      >
        <KeyValueGrid
          rows={[
            ["Liquidity Score", displayValue(detail.liquidity.assessment?.liquidity_score)],
            ["Confidence", displayValue(detail.liquidity.assessment?.confidence)],
            ["30d Sale Probability", displayPercent(valueAsString(detail.liquidity.assessment?.probability_sale_30d))],
            ["60d Sale Probability", displayPercent(valueAsString(detail.liquidity.assessment?.probability_sale_60d))],
            ["90d Sale Probability", displayPercent(valueAsString(detail.liquidity.assessment?.probability_sale_90d))],
            ["Fast-Sale Low", displayMoney(valueAsString(detail.liquidity.fast_sale?.value_low), currency)],
            ["Fast-Sale Base", displayMoney(valueAsString(detail.liquidity.fast_sale?.value_base), currency)],
            ["Fast-Sale High", displayMoney(valueAsString(detail.liquidity.fast_sale?.value_high), currency)],
            ["Target Days", displayValue(detail.liquidity.fast_sale?.target_days)],
          ]}
        />
      </Section>

      <Section title="Seller" eyebrow={<StatusBadge status={detail.seller.status} />}>
        <KeyValueGrid
          rows={[
            ["Motivation", displayValue(detail.seller.seller_motivation_level)],
            ["Motivation Score", displayValue(detail.seller.seller_motivation_score)],
            ["Motivation Confidence", displayValue(detail.seller.seller_motivation_confidence)],
            ["Negotiability", displayValue(detail.seller.negotiability_level)],
            ["Negotiability Score", displayValue(detail.seller.negotiability_score)],
            ["Cash Preferred", displayBoolean(valueAsBoolean(detail.seller.cash_preferred))],
            ["Reason For Sale", displayValue(detail.seller.reason_for_sale)],
            ["Model Version", displayValue(detail.seller.model_version)],
          ]}
        />
      </Section>

      <Section title="Risk" eyebrow={<StatusBadge status={detail.risk.gate} />}>
        <KeyValueGrid
          rows={[
            ["Gate", displayValue(detail.risk.gate)],
            ["Status", displayValue(detail.risk.status)],
            ["Score", displayValue(detail.risk.risk_score)],
            ["Confidence", displayValue(detail.risk.confidence)],
            ["Rules Version", displayValue(detail.risk.rules_version)],
          ]}
        />
        {detail.risk.flags.length === 0 ? (
          <Notice title="No risk flags recorded." />
        ) : (
          <DataTable
            columns={["Code", "Severity", "Gate Effect", "Source", "Confidence", "Evidence"]}
            rows={detail.risk.flags.map((flag) => [
              displayValue(flag.code),
              displayValue(flag.severity),
              <StatusBadge status={String(flag.gate_effect)} key={flag.code} />,
              displayValue(flag.source_kind),
              displayValue(flag.confidence),
              displayValue(flag.description),
            ])}
          />
        )}
      </Section>
    </>
  );
}

function KeyValueGrid({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <dl className="key-value-grid">
      {rows.map(([label, value]) => (
        <div className="key-value-row" key={label}>
          <dt>{label}</dt>
          <dd>
            <ValueText>{value}</ValueText>
          </dd>
        </div>
      ))}
    </dl>
  );
}

function DataTable({ columns, rows }: { columns: string[]; rows: ReactNode[][] }) {
  return (
    <div className="table-wrap compact-table">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourcesPage({ accessRevision, onAccessSaved }: PageProps) {
  const { state, reload } = useApiResource<SourcesResponse>("/api/v1/sources", accessRevision);

  return (
    <ResourceView state={state} onAccessSaved={onAccessSaved} onRetry={reload}>
      {(data) => (
        <Section title="Source Health">
          <SourceWarningBanner warnings={data.source_warnings} />
          <dl className="metric-grid">
            {Object.entries(data.summary).map(([status, count]) => (
              <Metric
                key={status}
                label={status.replace("_", " ")}
                value={<StatusCount count={count} status={status} />}
              />
            ))}
          </dl>
          {data.items.length === 0 ? (
            <Notice title="No sources configured." />
          ) : (
            <DataTable
              columns={[
                "Source",
                "Status",
                "Enabled",
                "Last Success",
                "Last Error",
                "HTTP Errors",
                "Parse Errors",
                "Latest Job",
              ]}
              rows={data.items.map((source) => [
                `${source.name} (${source.code})`,
                <StatusBadge status={source.health_status} key={source.source_id} />,
                displayBoolean(source.enabled),
                displayDateTime(source.last_success_at),
                source.last_error_type
                  ? `${source.last_error_type}: ${displayValue(source.last_error_message)}`
                  : "UNKNOWN",
                displayValue(source.recent_http_error_count),
                displayValue(source.recent_parse_error_count),
                displayValue(
                  typeof source.latest_job === "object" &&
                    source.latest_job !== null &&
                    "status" in source.latest_job
                    ? String(source.latest_job.status)
                    : null,
                ),
              ])}
            />
          )}
        </Section>
      )}
    </ResourceView>
  );
}

function StatusCount({ status, count }: { status: string; count: number }) {
  return (
    <span className={`status-count tone-${statusTone(status)}`}>
      {status}: {count}
    </span>
  );
}

function SettingsPage({ accessRevision, onAccessSaved }: PageProps) {
  const { state, reload } = useApiResource<SettingsResponse>("/api/v1/settings", accessRevision);

  return (
    <ResourceView state={state} onAccessSaved={onAccessSaved} onRetry={reload}>
      {(data) => (
        <>
          <Section title="Settings">
            <KeyValueGrid
              rows={[
                ["Environment", data.app.environment],
                ["Base URL", data.app.base_url],
                ["Auth Mode", data.app.auth_mode],
                ["Production Access Configured", displayBoolean(data.app.production_access_configured)],
                ["Telegram Configured", displayBoolean(data.notifications.telegram_configured)],
                ["CORS Origins", data.api.cors_allowed_origins.join(", ") || "UNKNOWN"],
                ["Sources Enabled", data.sources.enabled],
                ["Sources Disabled", data.sources.disabled],
              ]}
            />
          </Section>
          <Section title="Investment Profiles">
            {data.investment_profiles.length === 0 ? (
              <Notice title="No investment profiles configured." />
            ) : (
              <DataTable
                columns={["Name", "Version", "Min Profit", "Downside", "Min ROI", "Liquidity"]}
                rows={data.investment_profiles.map((profile) => [
                  displayValue(profile.name),
                  displayValue(profile.version),
                  displayMoney(valueAsString(profile.min_expected_profit)),
                  displayMoney(valueAsString(profile.min_downside_profit)),
                  displayPercent(valueAsString(profile.min_roi)),
                  displayValue(profile.min_liquidity_score),
                ])}
              />
            )}
          </Section>
          <Section title="Cost Profiles">
            {data.cost_profiles.length === 0 ? (
              <Notice title="No cost profiles configured." />
            ) : (
              <DataTable
                columns={["Name", "Code", "Currency", "Active", "Version"]}
                rows={data.cost_profiles.map((profile) => [
                  displayValue(profile.name),
                  displayValue(profile.code),
                  displayValue(profile.currency),
                  displayBoolean(valueAsBoolean(profile.is_active)),
                  displayValue(profile.version),
                ])}
              />
            )}
          </Section>
        </>
      )}
    </ResourceView>
  );
}

function currentRoute(props: PageProps): Route {
  const path = window.location.pathname;
  const propertyMatch = path.match(/^\/properties\/([^/]+)$/);
  if (propertyMatch) {
    const propertyId = decodeURIComponent(propertyMatch[1]);
    return {
      path,
      activePath: "/properties",
      label: "Property Detail",
      element: <PropertyDetailPage {...props} propertyId={propertyId} />,
    };
  }
  if (path === "/properties") {
    return {
      path,
      activePath: "/properties",
      label: "Properties",
      element: <PropertiesPage {...props} />,
    };
  }
  if (path === "/watchlist") {
    return {
      path,
      activePath: "/watchlist",
      label: "Watchlist",
      element: <WatchlistPage {...props} />,
    };
  }
  if (path === "/pipeline") {
    return {
      path,
      activePath: "/pipeline",
      label: "Pipeline",
      element: <PipelinePage {...props} />,
    };
  }
  if (path === "/sources") {
    return {
      path,
      activePath: "/sources",
      label: "Source Health",
      element: <SourcesPage {...props} />,
    };
  }
  if (path === "/settings") {
    return {
      path,
      activePath: "/settings",
      label: "Settings",
      element: <SettingsPage {...props} />,
    };
  }
  return {
    path: "/",
    activePath: "/",
    label: "Action Queue",
    element: <ActionQueuePage {...props} />,
  };
}

const navItems = [
  { path: "/", label: "Action Queue" },
  { path: "/properties", label: "Properties" },
  { path: "/watchlist", label: "Watchlist" },
  { path: "/pipeline", label: "Pipeline" },
  { path: "/sources", label: "Sources" },
  { path: "/settings", label: "Settings" },
];

export function App() {
  const [accessRevision, setAccessRevision] = useState(0);
  const route = currentRoute({
    accessRevision,
    onAccessSaved: () => setAccessRevision((value) => value + 1),
  });

  function forgetToken() {
    clearAccessToken();
    setAccessRevision((value) => value + 1);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <h1 className="brand-title">Distressed Property Radar</h1>
          <p className="brand-subtitle">Private acquisition decision support</p>
        </div>
        <nav className="nav" aria-label="Primary">
          {navItems.map((item) => (
            <a
              aria-current={item.path === route.activePath ? "page" : undefined}
              href={item.path}
              key={item.path}
            >
              {item.label}
            </a>
          ))}
        </nav>
        <div className="topbar-actions">
          <a href={HEALTH_URL} rel="noreferrer" target="_blank">
            Health
          </a>
          <button onClick={forgetToken} type="button">
            Lock
          </button>
        </div>
      </header>
      <main className="content">{route.element}</main>
    </div>
  );
}
