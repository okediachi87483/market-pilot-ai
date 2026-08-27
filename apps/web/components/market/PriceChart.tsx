import { EmptyState } from "@/components/ui/EmptyState";
import type { OHLCVBar } from "@/lib/marketData";

/**
 * Renders only what's in `bars` — no fabricated values (Step 14). A
 * simple SVG close-price line; real candlesticks/volume overlay can
 * follow once there's a heavier charting need than this.
 */
export function PriceChart({ bars }: { bars: OHLCVBar[] }) {
  if (bars.length === 0) {
    return <EmptyState message="No historical data for this range yet." />;
  }

  const closes = bars.map((bar) => Number(bar.close));
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const width = 600;
  const height = 160;

  const points = closes
    .map((close, i) => {
      const x = (i / Math.max(closes.length - 1, 1)) * width;
      const y = height - ((close - min) / range) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const firstClose = closes[0] ?? 0;
  const lastClose = closes[closes.length - 1] ?? 0;
  const trendingUp = lastClose >= firstClose;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-40 w-full" preserveAspectRatio="none" role="img" aria-label="Historical close price">
      <polyline
        points={points}
        fill="none"
        stroke={trendingUp ? "var(--color-positive)" : "var(--color-negative)"}
        strokeWidth="2"
      />
    </svg>
  );
}
