# ADR-005: Next.js for the Frontend

## Context

The frontend is data-dense, chart-heavy, needs strong performance (a "fast" instrument-panel feel is a stated product requirement — [ui-design-system.md](../ui-design-system.md) §1), needs to support near-real-time updates, and needs accessible, maintainable, typed component architecture at production quality.

## Decision

Use **Next.js (App Router)** with **React**, **TypeScript strict**, and **Tailwind CSS**.

## Alternatives considered

- **Plain React (Vite/CRA-style SPA), no framework.** Rejected: Next.js's built-in routing, server components (letting data-heavy panels fetch server-side and ship less client JS), and image/font optimization all directly serve the "fast" requirement without hand-assembling the equivalent tooling.
- **Remix.** A reasonable alternative with a similar server-rendering philosophy; not chosen because Next.js has the larger ecosystem and more first-party charting/UI library compatibility, and no requirement here specifically favors Remix's data-loading model over Next's.
- **SvelteKit / Vue-based framework.** Rejected: React's ecosystem has the deepest bench of production-grade charting libraries (needed for `PriceChart`/`PerformanceChart`) and the team-familiarity/hiring argument favors React for a project explicitly aiming at production-grade, long-lived quality.

## Consequences

- Positive: server components reduce client bundle size for data-heavy dashboard panels, directly supporting the product's "fast" requirement.
- Positive: one dominant framework convention (App Router, file-based routing matching the twelve routes in [ui-screen-map.md](../ui-screen-map.md)) keeps the codebase predictable to navigate as it grows.
- Negative: App Router's server/client component split has a real learning curve and occasionally awkward edges (e.g. context providers, some third-party chart libraries assuming a client-only mount) — accepted as a one-time cost against the ongoing performance benefit.
