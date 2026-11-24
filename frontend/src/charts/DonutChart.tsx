import { memo, useMemo, useRef } from 'react';
import type { BreakdownCount } from '../api';
import ChartCard from './ChartCard';

interface DonutChartProps {
  title: string;
  description: string;
  segments: BreakdownCount[];
  emptyMessage: string;
  filename: string;
}

const COLORS = ['#60d7ff', '#b99cff', '#ffc36b', '#65e6ae', '#ff8298', '#82a7ff', '#f08be0', '#9bd58a', '#c6d2e3'];

function DonutChart({ title, description, segments, emptyMessage, filename }: DonutChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const total = useMemo(() => segments.reduce((sum, segment) => sum + segment.count, 0), [segments]);
  const summary = segments.map((segment) => `${segment.name}: ${segment.count} (${segment.percentage}%)`).join(', ');

  return (
    <ChartCard title={title} description={description} filename={filename} svgRef={svgRef}>
      {total > 0 ? (
        <div className="chart-svg-scroll">
        <svg className="observability-chart-svg donut-svg" ref={svgRef} viewBox="0 0 620 260" role="img" aria-label={`${title}. Total ${total}. ${summary}`}>
          <circle cx="130" cy="130" r="61" fill="none" stroke="rgba(192, 214, 248, 0.13)" strokeWidth="25" />
          {(() => {
            let offset = 0;
            return segments.map((segment, index) => {
              const percentage = segment.count * 100 / total;
              const currentOffset = offset;
              offset += percentage;
              return (
                <circle
                  key={segment.name}
                  cx="130"
                  cy="130"
                  r="61"
                  fill="none"
                  stroke={COLORS[index % COLORS.length]}
                  strokeWidth="25"
                  strokeDasharray={`${percentage} ${100 - percentage}`}
                  strokeDashoffset={-currentOffset}
                  pathLength="100"
                  transform="rotate(-90 130 130)"
                >
                  <title>{`${segment.name}: ${segment.count} events, ${percentage.toFixed(1)}%`}</title>
                </circle>
              );
            });
          })()}
          <text className="donut-total" x="130" y="126" textAnchor="middle">{total}</text>
          <text className="chart-tick" x="130" y="148" textAnchor="middle">total</text>
          {segments.map((segment, index) => (
            <g key={`legend-${segment.name}`} transform={`translate(255, ${34 + index * 25})`}>
              <rect x="0" y="-10" width="12" height="12" rx="3" fill={COLORS[index % COLORS.length]} />
              <text className="chart-legend-label" x="21" y="0">{segment.name}</text>
              <text className="chart-tick" x="340" y="0" textAnchor="end">{segment.count} · {((segment.count * 100) / total).toFixed(1)}%</text>
            </g>
          ))}
        </svg>
        </div>
      ) : (
        <div className="chart-empty" role="status">{emptyMessage}</div>
      )}
      <ul className="sr-only" aria-label={`${title} values`}>
        {segments.map((segment) => <li key={segment.name}>{segment.name}: {segment.count}, {segment.percentage}%</li>)}
      </ul>
    </ChartCard>
  );
}

export default memo(DonutChart);
