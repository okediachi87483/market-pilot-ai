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
└── market/     MarketExplorer, PriceChart, WatchlistPreview — real API data (Phase 3);
                remaining panels (AI/portfolio/risk/signals/alerts) are still mock placeholders
lib/            nav definitions, API fetch wrapper (api.ts), market data client (marketData.ts)
styles/         design tokens (docs/ui-design-system.md)
```

`/markets` and the dashboard's watchlist panel are wired to the real backend (`GET /api/v1/assets`, `/market/{symbol}`, `/market/{symbol}/history`) — the data itself is still mock market data end to end (docs/market-data.md), always labeled `SOURCE: MOCK`.

Design reference: [docs/ui-design-system.md](../../docs/ui-design-system.md) and the [Command Center canvas](../../docs/design/command-center/).
