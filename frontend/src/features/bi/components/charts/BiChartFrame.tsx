import type { ReactNode } from 'react';
import type { TooltipContentProps, TooltipValueType } from 'recharts';
import type { BiChartPoint, BiChartSeriesMeta } from '../../selectors/chartViewModel';
import { formatChartValue } from '../../selectors/chartViewModel';
import type { MetricSeries, ValueKind } from '../../types';

interface BiChartFrameProps {
  readonly title: string;
  readonly description: string;
  readonly data: readonly BiChartPoint[];
  readonly series: readonly BiChartSeriesMeta[];
  readonly valueKind: ValueKind;
  readonly unit?: Pick<MetricSeries, 'currency' | 'scale'> | null;
  readonly controls?: ReactNode;
  readonly children: ReactNode;
}

interface BiChartTooltipProps extends TooltipContentProps<TooltipValueType, number | string> {
  readonly data: readonly BiChartPoint[];
  readonly valueKind: ValueKind;
  readonly unit?: Pick<MetricSeries, 'currency' | 'scale'> | null;
}

export function BiChartTooltip(props: BiChartTooltipProps) {
  if (!props.active || props.payload.length === 0) return null;
  const point = props.data.find((candidate) => candidate.periodLabel === String(props.label ?? ''));
  const firstEvidence = point?.evidence[0];

  return (
    <div className="bi-chart-tooltip">
      <strong>{props.label}</strong>
      <ul>
        {props.payload.map((item) => {
          const numericValue = typeof item.value === 'number' ? item.value : Number(item.value);
          const value = Number.isFinite(numericValue)
            ? formatChartValue(numericValue, props.valueKind, props.unit ?? null)
            : '데이터 없음';
          return <li key={`${String(item.name)}-${String(item.dataKey)}`}><span>{item.name}</span><b>{value}</b></li>;
        })}
      </ul>
      {firstEvidence ? <small>근거 {firstEvidence.sheetName}!{firstEvidence.cellCoord}</small> : null}
    </div>
  );
}

export function BiChartFrame(props: BiChartFrameProps) {
  return (
    <section className="bi-chart-frame" aria-label={props.title}>
      <div className="bi-chart-frame__header">
        <div>
          <strong>{props.title}</strong>
          <span>{props.description}</span>
        </div>
        {props.controls}
      </div>
      <div className="bi-chart-frame__visual" role="img" aria-label={`${props.title}. ${props.description}`}>
        {props.children}
      </div>
      <table className="bi-visually-hidden">
        <caption>{props.title} 데이터</caption>
        <thead><tr><th>기간</th>{props.series.map((item) => <th key={item.metricId}>{item.label}</th>)}</tr></thead>
        <tbody>
          {props.data.map((point) => (
            <tr key={point.periodId}>
              <th>{point.periodLabel}</th>
              {props.series.map((item) => (
                <td key={item.metricId}>{formatChartValue(point.values[item.metricId] ?? null, props.valueKind, props.unit ?? null)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
