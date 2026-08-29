import "./App.css";

import type { FormEvent, ReactElement, ReactNode } from "react";
import { useEffect, useState } from "react";

import { ApiError, HEALTH_URL, apiGet, clearAccessToken, setAccessToken } from "./api";
import {
  displayBoolean,
  displayDateTime,
  displayMoney,
  displayPercent,
  displayValue,
  statusTone,
} from "./format";
import type {
  ActionQueueItem,
  ActionQueueResponse,
  PropertyDetail,
  PropertyListItem,
  PropertiesResponse,
  SettingsResponse,
  SourceWarning,
  SourcesResponse,
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

type Route = {
  path: string;
  activePath: string;
  label: string;
  element: ReactElement;
};

const actionOrder = ["URGENT_CALL", "CALL", "REVIEW", "WATCH"];

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
      {(detail) => <PropertyDetailContent detail={detail} />}
    </ResourceView>
  );
}

function PropertyDetailContent({ detail }: { detail: PropertyDetail }) {
  const currency = detail.decision.currency;
  const riskGate = detail.decision.risk_gate;

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
