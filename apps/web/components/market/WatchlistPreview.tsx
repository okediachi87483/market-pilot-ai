import { Card } from "@/components/ui/Card";

const MOCK_ROWS = [
  { symbol: "NVDA", price: "128.44", change: "+2.14%", positive: true },
  { symbol: "AAPL", price: "191.02", change: "+0.84%", positive: true },
  { symbol: "TSLA", price: "241.08", change: "-1.32%", positive: false },
];

/** Placeholder — see docs/component-architecture.md (Watchlist). */
export function WatchlistPreview() {
  return (
    <Card eyebrow="Watchlist" mock>
      <table className="w-full text-sm">
        <tbody>
          {MOCK_ROWS.map((row) => (
            <tr key={row.symbol} className="border-b border-border-subtle last:border-0">
              <td className="py-2 font-semibold text-text-primary">{row.symbol}</td>
              <td className="py-2 text-right font-mono text-text-primary">{row.price}</td>
              <td
                className={`py-2 text-right font-mono ${row.positive ? "text-positive" : "text-negative"}`}
              >
                {row.change}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
