# MarketPilot AI — Web

Next.js (App Router) frontend. Paper-trading infrastructure only — see the repository root [README.md](../../README.md).

## Local development (without Docker)

```bash
cd apps/web
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL` (see `.env.example` at the repo root) if the API isn't at `http://localhost:8000`.

## Commands

| Command | Purpose |
|---|---|
| `npm run dev` | Start the dev server |
| `npm run build` | Production build |
| `npm run lint` | ESLint |
| `npm run typecheck` | `tsc --noEmit` |
| `npm test` | Vitest |

## Structure

```
app/            routes (App Router) — one folder per screen in docs/ui-screen-map.md
components/
├── shell/      AppShell, Sidebar, TopBar — the persistent chrome
├── ui/         design-system primitives (Card, StatusTag, Skeleton, EmptyState, ErrorState)
└── market/     MarketExplorer, PriceChart, AnalysisPanel, MarketStateVisualization,
                SignalCenter, SignalCard, WatchlistPreview, SignalPreview — real API data
                (Phase 3/4/5); portfolio/risk/alerts remain mock placeholders until
                their owning phases land
lib/            nav definitions, API fetch wrapper (api.ts), market data client
                (marketData.ts), technical-analysis client (analysis.ts), signal
                engine client (signals.ts)
styles/         design tokens (docs/ui-design-system.md)
```

`/markets`, `/signals`, and the dashboard are wired to the real backend: `GET /api/v1/assets`, `/market/{symbol}`, `/analysis/{symbol}`, `/analysis/{symbol}/indicators`, `POST /signals/evaluate/{symbol}` — the underlying market data itself is still mock end to end (docs/market-data.md, docs/technical-analysis.md, docs/signal-engine.md), always labeled `SOURCE: MOCK`. The dashboard's signature gauge is a real "Market State" visualization driven by the detected regime (descriptive); the Signal Center (`/signals`) is the separate, prescriptive-within-a-named-strategy view of what `trend_momentum_v1` currently suggests — see docs/signal-engine.md §10 for why these stay visually and conceptually distinct.

Design reference: [docs/ui-design-system.md](../../docs/ui-design-system.md) and the [Command Center canvas](../../docs/design/command-center/).
