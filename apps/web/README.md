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
                WatchlistPreview — real API data (Phase 3/4); portfolio/risk/signals/alerts
                remain mock placeholders until their owning phases land
lib/            nav definitions, API fetch wrapper (api.ts), market data client
                (marketData.ts), technical-analysis client (analysis.ts)
styles/         design tokens (docs/ui-design-system.md)
```

`/markets` and the dashboard are wired to the real backend: `GET /api/v1/assets`, `/market/{symbol}`, `/analysis/{symbol}`, `/analysis/{symbol}/indicators` — the underlying market data itself is still mock end to end (docs/market-data.md, docs/technical-analysis.md), always labeled `SOURCE: MOCK`. The dashboard's signature gauge is now a real "Market State" visualization driven by the detected regime — see docs/technical-analysis.md §13 for why it's no longer labeled "AI" (there is no AI in this system yet).

Design reference: [docs/ui-design-system.md](../../docs/ui-design-system.md) and the [Command Center canvas](../../docs/design/command-center/).
