import { EmptyState } from "@/components/ui/EmptyState";
import type { IndicatorPoint } from "@/lib/analysis";

const WIDTH = 600;
const PRICE_HEIGHT = 200;
const VOLUME_HEIGHT = 50;
const GAP = 8;

function scaleX(index: number, count: number): number {
  return (index / Math.max(count - 1, 1)) * WIDTH;
}

function toPath(values: (number | null)[], min: number, range: number, height: number): string {
  const segments: string[] = [];
  let drawing = false;
  values.forEach((value, i) => {
    if (value === null) {
      drawing = false;
      return;
    }
    const x = scaleX(i, values.length).toFixed(1);
    const y = (height - ((value - min) / range) * height).toFixed(1);
    segments.push(`${drawing ? "L" : "M"}${x},${y}`);
    drawing = true;
  });
  return segments.join(" ");
}

/**
 * Price + indicator overlay chart (Step 13). Renders only what's in
 * `points`, all of it backend-calculated (docs/technical-analysis.md) —
 * the frontend never computes an indicator, only scales coordinates for
 * display.
 */
export function PriceChart({ points }: { points: IndicatorPoint[] }) {
  if (points.length === 0) {
    return <EmptyState message="No historical data for this range yet." />;
  }

  const closes = points.map((p) => p.close);
  const priceValues = [
    ...closes,
    ...points.map((p) => p.bollinger_upper),
    ...points.map((p) => p.bollinger_lower),
    ...points.map((p) => p.ema9),
    ...points.map((p) => p.ema21),
    ...points.map((p) => p.sma20),
  ].filter((v): v is number => v !== null);

  const min = priceValues.length ? Math.min(...priceValues) : 0;
  const max = priceValues.length ? Math.max(...priceValues) : 1;
  const range = max - min || 1;

  const volumes = points.map((p) => p.volume ?? 0);
  const maxVolume = Math.max(...volumes, 1);
  const barWidth = WIDTH / points.length;

  const firstClose = closes[0] ?? 0;
  const lastClose = closes[closes.length - 1] ?? 0;
  const trendingUp = lastClose >= firstClose;

  return (
    <div className="flex flex-col gap-2">
      <svg
        viewBox={`0 0 ${WIDTH} ${PRICE_HEIGHT}`}
        className="h-48 w-full"
        preserveAspectRatio="none"
        role="img"
        aria-label="Price chart with moving average and Bollinger Band overlays"
      >
        <path
          d={toPath(points.map((p) => p.bollinger_upper), min, range, PRICE_HEIGHT)}
          fill="none"
          stroke="var(--color-border-default)"
          strokeWidth="1"
          strokeDasharray="3 3"
        />
        <path
          d={toPath(points.map((p) => p.bollinger_lower), min, range, PRICE_HEIGHT)}
          fill="none"
          stroke="var(--color-border-default)"
          strokeWidth="1"
          strokeDasharray="3 3"
        />
        <path
          d={toPath(points.map((p) => p.sma20), min, range, PRICE_HEIGHT)}
          fill="none"
          stroke="var(--color-accent-amber)"
          strokeWidth="1.25"
          opacity="0.8"
        />
        <path
          d={toPath(points.map((p) => p.ema21), min, range, PRICE_HEIGHT)}
          fill="none"
          stroke="var(--color-accent-teal)"
          strokeWidth="1.25"
          opacity="0.8"
        />
        <path
          d={toPath(points.map((p) => p.ema9), min, range, PRICE_HEIGHT)}
          fill="none"
          stroke="var(--color-accent-teal)"
          strokeWidth="1.25"
          opacity="0.45"
        />
        <path
          d={toPath(closes, min, range, PRICE_HEIGHT)}
          fill="none"
          stroke={trendingUp ? "var(--color-positive)" : "var(--color-negative)"}
          strokeWidth="2"
        />
      </svg>

      <svg
        viewBox={`0 0 ${WIDTH} ${VOLUME_HEIGHT}`}
        className="h-[50px] w-full"
        preserveAspectRatio="none"
        role="img"
        aria-label="Volume"
      >
        {points.map((point, i) => {
          const height = ((point.volume ?? 0) / maxVolume) * VOLUME_HEIGHT;
          return (
            <rect
              key={point.timestamp}
              x={(scaleX(i, points.length) - barWidth / 2 + GAP / 4).toFixed(1)}
              y={(VOLUME_HEIGHT - height).toFixed(1)}
              width={Math.max(barWidth - GAP / 2, 1).toFixed(1)}
              height={height.toFixed(1)}
              fill="var(--color-border-default)"
            />
          );
        })}
      </svg>

      <div className="flex flex-wrap gap-3 text-[10px] text-text-tertiary">
        <LegendItem color="var(--color-positive)" label="Close" />
        <LegendItem color="var(--color-accent-teal)" label="EMA 9 / 21" />
        <LegendItem color="var(--color-accent-amber)" label="SMA 20" />
        <LegendItem color="var(--color-border-default)" label="Bollinger Bands" dashed />
      </div>
    </div>
  );
}

function LegendItem({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="inline-block h-0.5 w-3"
        style={{ background: dashed ? "transparent" : color, borderTop: dashed ? `1px dashed ${color}` : undefined }}
      />
      {label}
    </span>
  );
}
