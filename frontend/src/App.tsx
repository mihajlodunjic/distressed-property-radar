import "./App.css";

import type { ReactElement } from "react";

import { HEALTH_URL } from "./api";

type Route = {
  path: string;
  label: string;
  element: ReactElement;
};

function FoundationPage() {
  return (
    <section className="panel">
      <h2>Repository Foundation</h2>
      <p>Backend, database, migrations, and frontend shell are ready for the next phase.</p>
      <dl className="meta-list">
        <div className="meta-row">
          <dt>Runtime</dt>
          <dd>FastAPI, PostgreSQL/PostGIS, React</dd>
        </div>
        <div className="meta-row">
          <dt>Scope</dt>
          <dd>Phase 0 infrastructure only</dd>
        </div>
      </dl>
    </section>
  );
}

function SystemPage() {
  return (
    <section className="panel">
      <h2>System</h2>
      <dl className="meta-list">
        <div className="meta-row">
          <dt>Health endpoint</dt>
          <dd>
            <a href={HEALTH_URL}>{HEALTH_URL}</a>
          </dd>
        </div>
      </dl>
    </section>
  );
}

const routes: Route[] = [
  { path: "/", label: "Foundation", element: <FoundationPage /> },
  { path: "/system", label: "System", element: <SystemPage /> },
];

function currentRoute(): Route {
  return routes.find((route) => route.path === window.location.pathname) ?? routes[0];
}

export function App() {
  const route = currentRoute();

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <h1 className="brand-title">Distressed Property Radar</h1>
          <p className="brand-subtitle">Private acquisition decision support</p>
        </div>
        <nav className="nav" aria-label="Primary">
          {routes.map((item) => (
            <a
              aria-current={item.path === route.path ? "page" : undefined}
              href={item.path}
              key={item.path}
            >
              {item.label}
            </a>
          ))}
        </nav>
      </header>
      <main className="content">{route.element}</main>
    </div>
  );
}
