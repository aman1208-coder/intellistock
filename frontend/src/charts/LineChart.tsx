import { memo, useMemo, useRef } from 'react';
import type { ObservabilityHistorySample } from '../api';
import ChartCard from './ChartCard';

export interface LineSeries {
  key: string;
  label: string;
  color: string;
  values: Array<number | null>;
}

interface LineChartProps {
  title: string;
  description: string;
  samples: ObservabilityHistorySample[];
  series: LineSeries[];
  emptyMessage: string;
  filename: string;
  valueSuffix: string;
  area?: boolean;
}

const WIDTH = 720;
const HEIGHT = 300;
const LEFT = 56;
const RIGHT = 28;
const TOP = 20;
const BOTTOM = 62;
const PLOT_WIDTH = WIDTH - LEFT - RIGHT;
const PLOT_HEIGHT = HEIGHT - TOP - BOTTOM;

function timeLabel(timestamp: string): string {
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime())
    ? timestamp.slice(11, 16)
    : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function LineChart({ title, description, samples, series, emptyMessage, filename, valueSuffix, area = false }: LineChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const indices = useMemo(() => {
    if (samples.length <= 60) return samples.map((_, index) => index);
    return Array.from({ length: 60 }, (_, index) => Math.round(index * (samples.length - 1) / 59));
  }, [samples]);
  const sampledSeries = useMemo(() => series.map((entry) => ({
    ...entry,
    values: indices.map((index) => entry.values[index] ?? null),
  })), [indices, series]);
  const maxValue = Math.max(0, ...sampledSeries.flatMap((entry) => entry.values.filter((value): value is number => value != null)));
  const hasData = sampledSeries.some((entry) => entry.values.some((value) => value != null));
  const ceiling = maxValue > 0 ? maxValue * 1.12 : 1;

  const x = (index: number) => LEFT + (indices.length <= 1 ? PLOT_WIDTH / 2 : index * PLOT_WIDTH / (indices.length - 1));
  const y = (value: number) => TOP + PLOT_HEIGHT - (value / ceiling) * PLOT_HEIGHT;
  const getSegments = (values: Array<number | null>) => {
    const segments: Array<Array<{ index: number; value: number }>> = [];
    values.forEach((value, index) => {
      if (value == null || !Number.isFinite(value)) return;
      const current = segments[segments.length - 1];
      if (!current || current[current.length - 1].index !== index - 1) segments.push([]);
      segments[segments.length - 1].push({ index, value });
    });
    return segments;
  };

  const xTicks = indices.length ? [...new Set([0, Math.floor((indices.length - 1) / 2), indices.length - 1])] : [];
  const chartSummary = sampledSeries.map((entry) => `${entry.label}: ${entry.values.filter((value) => value != null).length} samples`).join('; ');

  return (
    <ChartCard title={title} description={description} filename={filename} svgRef={svgRef}>
      {hasData ? (
        <div className="chart-svg-scroll">
        <svg ref={svgRef} className="observability-chart-svg line-svg" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${title}. ${chartSummary}`}>
          <text className="chart-axis-title" x="14" y={TOP + PLOT_HEIGHT / 2} transform={`rotate(-90 14 ${TOP + PLOT_HEIGHT / 2})`}>{valueSuffix}</text>
          {[0, 1, 2, 3, 4].map((step) => {
            const value = ceiling * (4 - step) / 4;
            const yPosition = TOP + step * PLOT_HEIGHT / 4;
            return (
              <g key={step}>
                <line className="chart-gridline" x1={LEFT} x2={WIDTH - RIGHT} y1={yPosition} y2={yPosition} />
                <text className="chart-tick" x={LEFT - 9} y={yPosition + 4} textAnchor="end">{value.toFixed(maxValue < 10 ? 1 : 0)}</text>
              </g>
            );
          })}
          <line className="chart-axis" x1={LEFT} x2={LEFT} y1={TOP} y2={TOP + PLOT_HEIGHT} />
          <line className="chart-axis" x1={LEFT} x2={WIDTH - RIGHT} y1={TOP + PLOT_HEIGHT} y2={TOP + PLOT_HEIGHT} />
          {xTicks.map((index) => (
            <text key={index} className="chart-tick" x={x(index)} y={TOP + PLOT_HEIGHT + 20} textAnchor={index === 0 ? 'start' : index === indices.length - 1 ? 'end' : 'middle'}>
              {timeLabel(samples[indices[index]]?.timestamp ?? '')}
            </text>
          ))}
          {sampledSeries.map((entry, seriesIndex) => {
            const segments = getSegments(entry.values);
            return (
              <g key={entry.key}>
                {area && seriesIndex === 0 && segments.map((segment, segmentIndex) => segment.length > 1 && (
                  <path
                    key={`area-${segmentIndex}`}
                    d={`M ${x(segment[0].index)} ${TOP + PLOT_HEIGHT} ${segment.map((point) => `L ${x(point.index)} ${y(point.value)}`).join(' ')} L ${x(segment[segment.length - 1].index)} ${TOP + PLOT_HEIGHT} Z`}
                    fill={entry.color}
                    opacity="0.12"
                  />
                ))}
                {segments.map((segment, segmentIndex) => (
                  <path
                    key={`line-${segmentIndex}`}
                    d={segment.map((point, pointIndex) => `${pointIndex ? 'L' : 'M'} ${x(point.index)} ${y(point.value)}`).join(' ')}
                    fill="none"
                    stroke={entry.color}
                    strokeWidth="2.5"
                    strokeDasharray={seriesIndex === 2 ? '6 4' : undefined}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                ))}
                {entry.values.map((value, index) => value == null ? null : (
                  <circle key={`${entry.key}-${index}`} cx={x(index)} cy={y(value)} r="3" fill={entry.color}>
                    <title>{`${timeLabel(samples[indices[index]]?.timestamp ?? '')} · ${entry.label}: ${value.toFixed(2)} ${valueSuffix}`}</title>
                  </circle>
                ))}
              </g>
            );
          })}
          {sampledSeries.map((entry, index) => {
            const legendX = LEFT + index * 210;
            return (
              <g key={`legend-${entry.key}`} transform={`translate(${legendX}, ${HEIGHT - 12})`}>
                <line x1="0" x2="22" y1="0" y2="0" stroke={entry.color} strokeWidth="3" strokeDasharray={index === 2 ? '6 4' : undefined} />
                <text className="chart-legend-label" x="29" y="4">{entry.label}</text>
              </g>
            );
          })}
        </svg>
        </div>
      ) : (
        <div className="chart-empty" role="status">{emptyMessage}</div>
      )}
      <ul className="sr-only" aria-label={`${title} series summary`}>
        {sampledSeries.map((entry) => <li key={entry.key}>{entry.label}: {entry.values.filter((value) => value != null).length} recorded samples</li>)}
      </ul>
    </ChartCard>
  );
}

export default memo(LineChart);
