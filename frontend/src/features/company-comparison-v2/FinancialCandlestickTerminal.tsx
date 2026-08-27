import { BarChart3 } from 'lucide-react';
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { FinancialCandle, LeagueCompany, LeagueEvidence } from './leagueTypes';

const COLORS = ['#34d399', '#60a5fa', '#fbbf24', '#c084fc', '#fb7185'];

interface CandleRow extends FinancialCandle {
  readonly range: readonly [number, number];
  readonly positive: boolean;
  readonly [key: `overlay${number}`]: number;
}

interface CandleShapeProps {
  readonly x?: number; readonly y?: number; readonly width?: number; readonly height?: number;
  readonly payload?: CandleRow;
}

function CandleShape({ x = 0, y = 0, width = 0, height = 0, payload }: CandleShapeProps) {
  if (!payload) return null;
  const range = Math.max(payload.high - payload.low, 0.0001);
  const bodyTop = y + ((payload.high - Math.max(payload.open, payload.close)) / range) * height;
  const bodyHeight = Math.max(3, Math.abs(payload.close - payload.open) / range * height);
  const color = payload.positive ? '#16a34a' : '#f97316';
  const center = x + width / 2;
  return <g opacity={payload.periodType === 'forecast' ? 0.68 : 1}><line x1={center} x2={center} y1={y} y2={y + height} stroke={color} strokeWidth={1.5} /><rect x={x + width * 0.2} y={bodyTop} width={width * 0.6} height={bodyHeight} rx={1.5} fill={color} /></g>;
}

function formatCompact(value: number) {
  return new Intl.NumberFormat('ko-KR', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

export function FinancialCandlestickTerminal({ companies, evidence, selectedYear, onYearChange, onEvidence }: {
  readonly companies: readonly LeagueCompany[];
  readonly evidence: readonly LeagueEvidence[];
  readonly selectedYear: number;
  readonly onYearChange: (year: number) => void;
  readonly onEvidence: (item: LeagueEvidence) => void;
}) {
  if (companies.length === 0) return <section className="league-panel terminal-empty"><BarChart3 /><h2>차트에 표시할 기업을 선택하세요</h2><p>리그 테이블 체크박스에서 최대 5개 시나리오를 선택할 수 있습니다.</p></section>;
  const leader = companies[0];
  const rows: CandleRow[] = leader.candles.map((candle, index) => {
    const overlays = Object.fromEntries(companies.map((company, companyIndex) => [`overlay${companyIndex}`, company.candles[index]?.revenue ?? 0]));
    return { ...candle, ...overlays, range: [candle.low, candle.high], positive: index === 0 || candle.revenue >= leader.candles[index - 1].revenue } as CandleRow;
  });
  const evidenceById = new Map(evidence.map((item) => [item.evidenceId, item]));
  const selectedCandle = leader.candles.find((item) => item.year === selectedYear) ?? leader.candles[leader.candles.length - 1];
  const selectedEvidence = evidenceById.get(selectedCandle?.evidenceId ?? '');
  const tooltip = ({ active, label }: { active?: boolean; label?: string | number }) => {
    if (!active) return null;
    const candle = rows.find((item) => item.year === Number(label));
    const source = candle ? evidenceById.get(candle.evidenceId) : undefined;
    if (!candle) return null;
    return <div className="terminal-tooltip"><header><strong>{leader.displayName}</strong><span>{candle.year} · {candle.periodType === 'forecast' ? '예측' : '실적'}</span></header><dl><div><dt>분기 연환산 범위</dt><dd>{formatCompact(candle.low)} – {formatCompact(candle.high)}</dd></div><div><dt>연 매출</dt><dd>{formatCompact(candle.revenue)}</dd></div><div><dt>영업이익률</dt><dd>{candle.operatingMargin.toFixed(1)}%</dd></div></dl>{source ? <button type="button" onMouseDown={(event) => { event.preventDefault(); onEvidence(source); }}>🔍 근거 보기 · {source.sheetName}!{source.cellCoord}</button> : null}</div>;
  };
  return (
    <section className="league-panel terminal-panel">
      <div className="league-panel-heading terminal-heading"><div><span>FINANCIAL CHART TERMINAL</span><h2>{leader.displayName}</h2><p>캔들: 분기 연환산 최저–최고 · 라인: 선택 기업 연 매출</p></div><div className="terminal-heading-actions"><div className="terminal-legend"><span><i className="up" />성장</span><span><i className="down" />역성장</span><span className="forecast">2026–2028 예측</span></div>{selectedEvidence ? <button type="button" className="terminal-evidence-button" onClick={() => onEvidence(selectedEvidence)}>🔍 {selectedYear}년 근거 보기</button> : null}</div></div>
      <div className="terminal-year-switcher" role="group" aria-label="조회 연도">{leader.candles.map((candle) => <button type="button" key={candle.year} className={selectedYear === candle.year ? 'is-active' : ''} data-period={candle.periodType} onClick={() => onYearChange(candle.year)}>{candle.year}<small>{candle.periodType === 'forecast' ? 'E' : 'A'}</small></button>)}</div>
      {selectedCandle ? <div className="selected-year-metrics"><div><span>선택 연도</span><strong>{selectedCandle.year}</strong><small>{selectedCandle.periodType === 'forecast' ? 'Forecast · 예측' : 'Actual · 실적'}</small></div><div><span>연 매출</span><strong>{formatCompact(selectedCandle.revenue)}</strong><small>{leader.currency} · {leader.scale}</small></div><div><span>분기 연환산 범위</span><strong>{formatCompact(selectedCandle.low)} – {formatCompact(selectedCandle.high)}</strong><small>Low / High</small></div><div><span>영업이익</span><strong>{formatCompact(selectedCandle.operatingIncome)}</strong><small>Margin {selectedCandle.operatingMargin.toFixed(1)}%</small></div></div> : null}
      <div className="terminal-chart terminal-chart-main"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={rows} syncId="financial-terminal" margin={{ top: 16, right: 20, left: 4, bottom: 0 }}><CartesianGrid stroke="#dce9e1" strokeDasharray="2 5" vertical={false} /><XAxis dataKey="year" stroke="#789087" tick={{ fontSize: 11 }} /><YAxis stroke="#789087" tick={{ fontSize: 10 }} tickFormatter={formatCompact} width={54} /><Tooltip content={tooltip} /><ReferenceLine x={2025.5} stroke="#d97706" strokeDasharray="5 5" label={{ value: '실적  |  예측', fill: '#a16207', fontSize: 10, position: 'insideTopRight' }} /><ReferenceLine x={selectedYear} stroke="#107c41" strokeWidth={2} strokeDasharray="3 3" /><Bar dataKey="range" shape={<CandleShape />} barSize={22} name="분기 범위" />{companies.map((company, index) => <Line key={company.companyId} type="monotone" dataKey={`overlay${index}`} name={company.displayName} stroke={COLORS[index]} strokeWidth={index === 0 ? 2.4 : 1.6} dot={{ r: 2.5 }} />)}<Legend wrapperStyle={{ fontSize: 10, paddingTop: 8 }} /></ComposedChart></ResponsiveContainer></div>
      <div className="terminal-subtitle"><span>VOLUME</span><strong>연도별 매출 규모</strong></div>
      <div className="terminal-chart terminal-chart-volume"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={rows} syncId="financial-terminal" margin={{ top: 2, right: 20, left: 4, bottom: 0 }}><CartesianGrid stroke="#dce9e1" strokeDasharray="2 5" vertical={false} /><XAxis dataKey="year" hide /><YAxis stroke="#789087" tick={{ fontSize: 9 }} tickFormatter={formatCompact} width={54} /><Bar dataKey="revenue" fill="#107c41" opacity={0.76} barSize={26} /></ComposedChart></ResponsiveContainer></div>
      <div className="terminal-subtitle"><span>OSCILLATOR</span><strong>영업이익률 모멘텀</strong></div>
      <div className="terminal-chart terminal-chart-oscillator"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={rows} syncId="financial-terminal" margin={{ top: 2, right: 20, left: 4, bottom: 4 }}><CartesianGrid stroke="#dce9e1" strokeDasharray="2 5" vertical={false} /><XAxis dataKey="year" stroke="#789087" tick={{ fontSize: 10 }} /><YAxis stroke="#789087" tick={{ fontSize: 9 }} unit="%" width={54} /><ReferenceLine y={0} stroke="#a8bbb0" /><Bar dataKey="operatingMargin" fill="#16a34a" opacity={0.82} barSize={26} /></ComposedChart></ResponsiveContainer></div>
    </section>
  );
}
