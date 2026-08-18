import { useEffect, useMemo, useState } from 'react';
import { BarChart3, Check, Play, X } from 'lucide-react';
import { pipelineApi } from '../services/api';
import type { BenchmarkCase, BenchmarkComparison, WorkflowDocument } from '../types';

// This is the repeatable, scored set.  Keep the matching JSON file in
// data/benchmark_sets in sync so the benchmark can also be rerun via API.
const DEFAULT_CASES: BenchmarkCase[] = [
  { id: '01-ltm-revenue', question: 'IBM의 LTM 매출은 얼마인가?', expected_numbers: [67535], expected_target: 'get_ibm_key_financials' },
  { id: '02-fy24-revenue', question: 'IBM의 2024년 총매출은 얼마인가?', expected_numbers: [62753], expected_target: 'get_ibm_key_financials' },
  { id: '03-fy23-revenue', question: 'IBM의 2023년 총매출은 얼마인가?', expected_numbers: [61860], expected_target: 'get_ibm_key_financials' },
  { id: '04-revenue-growth', question: 'IBM FY2025 매출 성장률은 몇 %인가?', expected_numbers: [7.62], expected_target: 'get_ibm_key_financials' },
  { id: '05-gross-profit', question: 'IBM LTM 매출총이익은 얼마인가?', expected_numbers: [39297], expected_target: 'get_ibm_key_financials' },
  { id: '06-operating-income', question: 'IBM LTM 영업이익은 얼마인가?', expected_numbers: [11757], expected_target: 'get_ibm_key_financials' },
  { id: '07-ebitda', question: 'IBM LTM EBITDA는 얼마인가?', expected_numbers: [16778], expected_target: 'get_ibm_key_financials' },
  { id: '08-ebitda-margin', question: 'IBM LTM EBITDA 마진은 몇 %인가?', expected_numbers: [24.8434], expected_target: 'get_ibm_key_financials' },
  { id: '09-eps-dps', question: '2024-12-31 기준 IBM 희석 EPS와 DPS는 각각 얼마인가?', expected_numbers: [6.429, 6.67], expected_target: 'get_ibm_key_financials' },
  { id: '10-cash', question: '2025년 IBM 현금 및 단기투자자산 총액은 얼마인가?', expected_numbers: [14417], expected_target: 'get_ibm_key_financials' },
  { id: '11-assets-liabilities', question: '2025년 IBM 총자산과 총부채는 각각 얼마인가?', expected_numbers: [151880, 119139], expected_target: 'get_ibm_key_financials' },
  { id: '12-ocf-capex', question: '2025년 IBM 영업현금흐름과 CAPEX는 각각 얼마인가?', expected_numbers: [13193, -1617], expected_target: 'get_ibm_key_financials' },
  { id: '13-dividends', question: '2025년 IBM 총 배당금 지급액은 얼마인가?', expected_numbers: [-6255], expected_target: 'get_ibm_key_financials' },
  { id: '14-market-cap', question: 'IBM LTM 시가총액은 얼마인가?', expected_numbers: [270970.3889], expected_target: 'get_ibm_key_financials' },
  { id: '15-tev', question: 'IBM LTM TEV는 얼마인가?', expected_numbers: [321253.3889], expected_target: 'get_ibm_key_financials' },
  { id: '16-tev-ebitda', question: 'IBM LTM TEV/EBITDA 배수는 얼마인가?', expected_numbers: [20.0857], expected_target: 'get_ibm_key_financials' },
  { id: '17-revenue-comparison', question: 'IBM의 2024년과 2025년 매출을 비교해줘.', expected_numbers: [62753, 67535], expected_target: 'get_ibm_key_financials' },
  { id: '18-revenue-trend', question: 'IBM의 2021년부터 2025년까지 매출 추이를 알려줘.', expected_numbers: [57351, 60530, 61860, 62753, 67535], expected_target: 'get_ibm_key_financials' },
  { id: '19-2025-eps', question: 'IBM FY2025 희석 EPS는 얼마인가?', expected_numbers: [11.14], expected_target: 'get_ibm_key_financials' },
  { id: '20-2026-revenue', question: 'IBM의 2026년 예상 매출은 얼마인가?', expected_numbers: [71183.3116], expected_target: 'get_ibm_key_financials' },
  { id: '21-2027-revenue', question: 'IBM의 2027년 예상 매출은 얼마인가?', expected_numbers: [74255.1489], expected_target: 'get_ibm_key_financials' },
  { id: '22-2028-revenue', question: 'IBM의 2028년 예상 매출은 얼마인가?', expected_numbers: [78520.452], expected_target: 'get_ibm_key_financials' },
  { id: '23-2026-eps', question: 'IBM의 2026년 예상 희석 EPS는 얼마인가?', expected_numbers: [12.4142], expected_target: 'get_ibm_key_financials' },
  { id: '24-2028-eps', question: 'IBM의 2028년 예상 희석 EPS는 얼마인가?', expected_numbers: [14.7463], expected_target: 'get_ibm_key_financials' },
];

const WORKFLOW_HINTS: Record<string, string> = {
  default: '기존 기준선: LLM 분해 + BM25/Dense RRF',
  rag1_dense_baseline: 'Dense 검색 기준선', rag3_llm_router_dense: 'LLM 라우팅 + Dense',
  rag4_hybrid_rrf: 'BM25 + Dense + RRF', rag5_decomposition_hybrid: 'LLM 분해 + Hybrid',
  rag6_semantic_router_dense: '시맨틱 매칭 + Dense', rag7_adaptive_semantic_hybrid: 'Adaptive Semantic + Hybrid',
  rag8_optimized_router_hybrid: 'RAG 7과 동일한 중복 워크플로우 (비교 제외 권장)',
};

interface BenchmarkPanelProps { isOpen: boolean; onClose: () => void; }

function casesFromLines(value: string): BenchmarkCase[] {
  return value.split(/\r?\n/).map((question) => question.trim()).filter(Boolean)
    .map((question, index) => ({ id: `free-${String(index + 1).padStart(3, '0')}`, question }));
}

export function BenchmarkPanel({ isOpen, onClose }: BenchmarkPanelProps) {
  const [workflows, setWorkflows] = useState<WorkflowDocument[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [mode, setMode] = useState<'scored' | 'lines'>('scored');
  const [questionsText, setQuestionsText] = useState(DEFAULT_CASES.map((item) => item.question).join('\n'));
  const [result, setResult] = useState<BenchmarkComparison | null>(null);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(false);
  // RAG8 is intentionally omitted: its saved graph is currently identical to RAG7.
  const ragWorkflows = useMemo(() => workflows.filter((workflow) => (workflow.id === 'default' || workflow.id.startsWith('rag')) && workflow.id !== 'rag8_optimized_router_hybrid'), [workflows]);

  useEffect(() => {
    void pipelineApi.getWorkflows().then(({ workflows: items }) => {
      const ragItems = items.filter((item) => (item.id === 'default' || item.id.startsWith('rag')) && item.id !== 'rag8_optimized_router_hybrid');
      setWorkflows(ragItems);
      const fairPair = ragItems.filter((item) => ['rag3_llm_router_dense', 'rag6_semantic_router_dense'].includes(item.id));
      setSelected((fairPair.length === 2 ? fairPair : ragItems).map((item) => item.id));
    }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : '워크플로우를 불러오지 못했습니다.'));
  }, []);

  const toggle = (workflowId: string) => setSelected((current) => current.includes(workflowId) ? current.filter((id) => id !== workflowId) : [...current, workflowId]);
  const run = async () => {
    try {
      const cases = mode === 'scored' ? DEFAULT_CASES : casesFromLines(questionsText);
      if (selected.length < 2) throw new Error('비교할 RAG를 두 개 이상 선택해 주세요.');
      if (!cases.length) throw new Error('질문을 한 줄에 하나씩 입력해 주세요.');
      setRunning(true); setError(''); setResult(await pipelineApi.compareBenchmarks(selected, cases));
    } catch (cause) { setError(cause instanceof Error ? cause.message : '벤치마크 실행에 실패했습니다.'); } finally { setRunning(false); }
  };

  if (!isOpen) return null;
  return <div className="benchmark-overlay" role="presentation" onMouseDown={onClose}>
    <aside className="benchmark-panel" role="dialog" aria-modal="true" aria-label="RAG 성능 비교" onMouseDown={(event) => event.stopPropagation()}>
      <header className="benchmark-panel__header"><span><BarChart3 size={18} /> RAG 성능 비교</span><button type="button" onClick={onClose} aria-label="성능 비교 닫기"><X size={18} /></button></header>
      <p className="benchmark-panel__intro">동일 질문을 순차 실행해 정확도, 응답 시간, 토큰, 비용을 비교합니다. 실행 결과는 서버의 <code>data/benchmarks</code>에 자동 저장됩니다.</p>
      <section className="benchmark-section"><div className="benchmark-section__title"><span>비교 대상</span><small>{selected.length}개 선택</small></div><p className="benchmark-panel__intro">라우터만 비교: RAG3 ↔ RAG6. 기존 전체 기준선 비교: default ↔ RAG7. RAG8은 현재 RAG7과 동일합니다.</p><div className="benchmark-workflow-grid">{ragWorkflows.map((workflow) => { const active = selected.includes(workflow.id); return <button type="button" key={workflow.id} className="benchmark-workflow-card" data-selected={active} onClick={() => toggle(workflow.id)}><i>{active && <Check size={13} strokeWidth={3} />}</i><strong>{workflow.name}</strong><small>{WORKFLOW_HINTS[workflow.id] ?? workflow.id}</small></button>; })}</div></section>
      <section className="benchmark-section benchmark-cases"><div className="benchmark-section__title"><span>질문 세트</span><small>{mode === 'scored' ? '정답 포함 24문항' : '한 줄당 1문항'}</small></div><div className="benchmark-mode"><button type="button" data-selected={mode === 'scored'} onClick={() => setMode('scored')}>정답 포함 24문항</button><button type="button" data-selected={mode === 'lines'} onClick={() => setMode('lines')}>내 질문 직접 입력</button></div>{mode === 'scored' ? <ol>{DEFAULT_CASES.map((item) => <li key={item.id}>{item.question}</li>)}</ol> : <textarea className="benchmark-json" value={questionsText} onChange={(event) => setQuestionsText(event.target.value)} rows={14} placeholder={'질문 하나\n질문 둘\n질문 셋'} aria-label="한 줄당 하나의 질문" />}<p className="benchmark-panel__intro">직접 입력은 한 줄씩 순차 실행하며 시간·토큰·비용만 비교합니다. 정확도는 정답이 있는 24문항 세트에서만 계산됩니다.</p></section>
      <button type="button" className="benchmark-run-button" onClick={() => void run()} disabled={running || selected.length < 2}><Play size={16} fill="currentColor" /> {running ? '전체 비교 실행 중…' : `${selected.length}개 RAG 비교 실행`}</button>{error && <div className="benchmark-error">{error}</div>}
      {result && <section className="benchmark-section benchmark-results"><div className="benchmark-section__title"><span>비교 결과</span><small>순차 실행 · 자동 저장</small></div>{result.id && <p className="benchmark-saved">저장됨: <code>{result.id}</code></p>}{result.summary.map((item) => <article key={item.workflow_id} className="benchmark-result-card"><strong>{ragWorkflows.find((flow) => flow.id === item.workflow_id)?.name ?? item.workflow_id}</strong><div className="benchmark-result-metrics"><span><b>{item.accuracy === null ? '—' : `${(item.accuracy * 100).toFixed(1)}%`}</b> 정답률 {item.scored_cases ? `(${item.scored_cases})` : ''}</span><span><b>{item.average_latency_seconds.toFixed(2)}s</b> 평균 시간</span><span><b>{item.average_tokens.toFixed(0)}</b> tokens</span><span><b>${item.average_cost_usd.toFixed(4)}</b> 비용</span></div>{item.router_kind && <div className="benchmark-router-metrics">{item.router_kind} router · {item.route_accuracy === null ? '라우팅 정답 없음' : `라우팅 정확도 ${(item.route_accuracy * 100).toFixed(1)}%`} · {item.average_router_latency_seconds?.toFixed(3)}s · {item.average_router_tokens?.toFixed(0)} tokens</div>}</article>)}</section>}
    </aside>
  </div>;
}
