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
                SignalCenter, SignalCard, RiskCenter, PaperTradingCenter,
                AIAnalystCenter, AIAnalystPreview, WatchlistPreview,
                SignalPreview, RiskPreview, PortfolioPreview — real API data
                (Phase 3-8); alerts remains a mock placeholder until its owning phase lands
lib/            nav definitions, API fetch wrapper (api.ts), market data client
                (marketData.ts), technical-analysis client (analysis.ts), signal
                engine client (signals.ts), risk engine client (risk.ts), paper
                trading client (paperTrading.ts), AI Analyst client (aiAnalyst.ts)
styles/         design tokens (docs/ui-design-system.md)
```

`/markets`, `/signals`, `/risk`, `/paper`, `/ai-analyst`, and the dashboard are wired to the real backend: `GET /api/v1/assets`, `/market/{symbol}`, `/analysis/{symbol}`, `/analysis/{symbol}/indicators`, `POST /signals/evaluate/{symbol}`, `GET /risk`, `POST /risk/evaluate/{signal_id}`, `GET /paper/portfolio`, `POST /paper/execute/{signal_id}`, `GET /ai/status`, `POST /ai/analyze/{signal_id}`, `GET /ai/analyses` — the underlying market data itself is still mock end to end (docs/market-data.md, docs/technical-analysis.md, docs/signal-engine.md), always labeled `SOURCE: MOCK`. The dashboard's signature gauge is a real "Market State" visualization driven by the detected regime (descriptive); the Signal Center (`/signals`) is the separate, prescriptive-within-a-named-strategy view of what `trend_momentum_v1` currently suggests — see docs/signal-engine.md §10 for why these stay visually and conceptually distinct. The Risk Center (`/risk`) is the deterministic safety boundary's own view — portfolio state, active policy limits, and recent approve/reject decisions (docs/risk-engine.md §12). The Paper Trading Center (`/paper`) is where a risk-approved signal actually becomes a simulated position — account, positions, orders, and fills, all real (docs/paper-trading.md §20); the Signal Center shows each signal's live progress all the way through `Risk Approved → Paper Execution → Filled → Position Open`. The AI Analyst Center (`/ai-analyst`) reuses the Signal Center directly, adding an AI Analyst section (thesis, evidence, suggested action, qualitative uncertainty, and an explicit disagreement banner when the AI's suggestion differs from the deterministic signal) plus a cross-symbol history of recent analyses (docs/ai-analyst.md §18); the AI Analyst provides analytical interpretation only and never executes anything.

Design reference: [docs/ui-design-system.md](../../docs/ui-design-system.md) and the [Command Center canvas](../../docs/design/command-center/).
