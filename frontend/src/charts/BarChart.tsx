import { memo, useMemo, useRef } from 'react';
import type { RouteBreakdown } from '../api';
import ChartCard from './ChartCard';

interface BarChartProps {
  title: string;
  description: string;
  routes: RouteBreakdown[];
  emptyMessage: string;
  filename: string;
}

const WIDTH = 720;
const ROW_HEIGHT = 30;

function BarChart({ title, description, routes, emptyMessage, filename }: BarChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const rows = useMemo(() => [...routes].sort((a, b) => b.count - a.count || a.route.localeCompare(b.route)).slice(0, 8), [routes]);
  const maxCount = Math.max(0, ...rows.map((route) => route.count));
  const height = Math.max(120, 74 + rows.length * ROW_HEIGHT);

  return (
    <ChartCard title={title} description={description} filename={filename} svgRef={svgRef}>
      {rows.length > 0 ? (
        <div className="chart-svg-scroll">
        <svg ref={svgRef} className="observability-chart-svg bar-svg" viewBox={`0 0 ${WIDTH} ${height}`} role="img" aria-label={`${title}. Top routes: ${rows.map((route) => `${route.route}, ${route.count} requests`).join('; ')}`}>
          <text className="chart-axis-title" x="250" y="18">Request count · p95 latency shown at right</text>
          {rows.map((route, index) => {
            const y = 42 + index * ROW_HEIGHT;
            const barWidth = maxCount > 0 ? Math.max(2, route.count / maxCount * 330) : 0;
            return (
              <g key={route.route}>
                <text className="chart-route-label" x="4" y={y + 4}>{route.route}</text>
                <rect className="chart-bar-track" x="250" y={y - 9} width="330" height="14" rx="7" />
                <rect x="250" y={y - 9} width={barWidth} height="14" rx="7" fill={index % 2 ? '#b99cff' : '#60d7ff'} />
                <text className="chart-value-label" x="592" y={y + 3}>{route.count}</text>
                <text className="chart-tick" x="714" y={y + 3} textAnchor="end">{route.p95_ms == null ? 'p95 unavailable' : `p95 ${route.p95_ms.toFixed(1)} ms`}</text>
                <title>{`${route.route}: ${route.count} requests, ${route.samples} recent latency samples`}</title>
              </g>
            );
          })}
        </svg>
        </div>
      ) : (
        <div className="chart-empty" role="status">{emptyMessage}</div>
      )}
      <ul className="sr-only" aria-label={`${title} values`}>
        {rows.map((route) => <li key={route.route}>{route.route}: {route.count} requests, p95 {route.p95_ms == null ? 'unavailable' : `${route.p95_ms.toFixed(1)} milliseconds`}</li>)}
      </ul>
    </ChartCard>
  );
}

export default memo(BarChart);
