import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { CompanyBrandMark } from '../../shared/company-brand/contract';
import { CompanyLogoBadge } from './CompanyLogoBadge';
import type { TrendPoint } from './analysis';

export interface BenchmarkScatterPoint {
  readonly companyId: string;
  readonly companyName: string;
  readonly brandMark?: CompanyBrandMark | null;
  readonly growth: number;
  readonly margin: number;
  readonly tone: 'selected' | 'compare-a' | 'compare-b' | 'default';
}

export function BenchmarkScatterTooltip({
  active,
  payload,
}: {
  readonly active?: boolean;
  readonly payload?: readonly { readonly payload: BenchmarkScatterPoint }[];
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="benchmark-scatter-tooltip">
      <strong>{point.companyName}</strong>
      <span>매출 성장률 <b>{point.growth.toFixed(1)}%</b></span>
      <span>영업이익률 <b>{point.margin.toFixed(1)}%</b></span>
    </div>
  );
}

export function FinancialTrendChart({
  points,
  color,
  gradientId,
  label,
  valueFormatter,
}: {
  readonly points: readonly TrendPoint[];
  readonly color: string;
  readonly gradientId: string;
  readonly label: string;
  readonly valueFormatter: (value: number) => string;
}) {
  const data = points;
  const periodLabel = data.length
    ? `${data[0].year}년부터 ${data[data.length - 1].year}년까지`
    : '관측 기간';

  return (
    <div className="analysis-trend-chart" role="img" aria-label={`${periodLabel} ${label} 추이`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 7, right: 5, bottom: 0, left: 5 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.22} />
              <stop offset="100%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="#e8efeb" strokeDasharray="2 3" />
          <XAxis dataKey="year" tick={{ fill: '#84928b', fontSize: 7.5 }} tickLine={false} axisLine={false} interval={0} />
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Tooltip
            formatter={(value) => [valueFormatter(Number(value)), label]}
            labelFormatter={(year) => `${year}년`}
            contentStyle={{ border: '1px solid #d7e4dd', borderRadius: 7, padding: '6px 8px', fontSize: 9 }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2.2}
            fill={`url(#${gradientId})`}
            dot={{ r: 2.5, fill: '#ffffff', stroke: color, strokeWidth: 1.5 }}
            activeDot={{ r: 4, fill: color, stroke: '#ffffff', strokeWidth: 1.5 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ComparisonTrendChart({
  first,
  second,
}: {
  readonly first: readonly TrendPoint[];
  readonly second: readonly TrendPoint[];
}) {
  const secondByYear = new Map(second.map((point) => [point.year, point.value]));
  const data = first.flatMap((point) => {
    const secondValue = secondByYear.get(point.year);
    return secondValue === undefined ? [] : [{ year: point.year, a: point.value, b: secondValue }];
  });
  const baseYear = data[0]?.year;
  return (
    <div className="analysis-trend-chart is-comparison" role="img" aria-label="두 기업의 공통 관측 기간 매출 성장 지수 비교">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 7, right: 5, bottom: 0, left: 5 }}>
          <CartesianGrid vertical={false} stroke="#e8efeb" strokeDasharray="2 3" />
          <XAxis dataKey="year" tick={{ fill: '#84928b', fontSize: 7.5 }} tickLine={false} axisLine={false} interval={0} />
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Tooltip
            formatter={(value, name) => [`${Number(value).toFixed(1)}`, name === 'a' ? '기업 A' : '기업 B']}
            labelFormatter={(year) => `${year}년 · ${baseYear ?? '기준연도'}=100`}
            contentStyle={{ border: '1px solid #d7e4dd', borderRadius: 7, padding: '6px 8px', fontSize: 9 }}
          />
          <Line type="monotone" dataKey="a" stroke="#107c41" strokeWidth={2.2} dot={{ r: 2.5, fill: '#fff', strokeWidth: 1.5 }} activeDot={{ r: 4 }} />
          <Line type="monotone" dataKey="b" stroke="#2563eb" strokeWidth={2.2} dot={{ r: 2.5, fill: '#fff', strokeWidth: 1.5 }} activeDot={{ r: 4 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

interface BenchmarkScatterMarkerProps {
  readonly cx?: number;
  readonly cy?: number;
  readonly payload?: BenchmarkScatterPoint;
}

function BenchmarkScatterMarker({ cx = 0, cy = 0, payload }: BenchmarkScatterMarkerProps) {
  if (!payload || payload.tone === 'default') {
    return <circle cx={cx} cy={cy} r={4} fill="#94a3b8" fillOpacity={0.35} stroke="#ffffff" strokeWidth={1} />;
  }
  const borderColor = payload.tone === 'compare-a' ? '#107c41' : '#2563eb';
  const baseName = payload.companyName
    .split(' (')[0]
    .replace(/\s+(Inc\.?|Co\.?|Systems|Labs|Networks|Tech|Digital|AI|Materials|Dynamics|Logic)$/i, '');
  const label = baseName.length > 13 ? `${baseName.slice(0, 12)}…` : baseName;
  const labelWidth = Math.min(88, Math.max(42, label.length * 5.2 + 12));
  const placeLabelLeft = payload.growth > 15;
  const labelX = placeLabelLeft ? cx - 13 - labelWidth : cx + 13;
  return (
    <g className="benchmark-logo-marker">
      <circle cx={cx} cy={cy} r={10.5} fill="#ffffff" stroke={borderColor} strokeWidth={1.5} />
      <foreignObject x={cx - 7} y={cy - 7} width={14} height={14}>
        <div className="benchmark-logo-marker-inner">
          <CompanyLogoBadge companyId={payload.companyId} companyName={payload.companyName} brandMark={payload.brandMark} size={14} />
        </div>
      </foreignObject>
      <g className="benchmark-logo-marker-label">
        <rect x={labelX} y={cy - 8} width={labelWidth} height={16} rx={4} fill="#ffffff" stroke={borderColor} strokeWidth={0.8} />
        <text x={labelX + 6} y={cy + 3} fill={borderColor}>{label}</text>
      </g>
    </g>
  );
}

export function renderBenchmarkScatterMarker(props: unknown) {
  return <BenchmarkScatterMarker {...(props as BenchmarkScatterMarkerProps)} />;
}
