import { useEffect, useMemo, useState } from 'react';
import { BarChart3, Check, Play, X } from 'lucide-react';
import { pipelineApi } from '../services/api';
import type { BenchmarkCase, BenchmarkComparison, WorkflowDocument } from '../types';

const DEFAULT_CASES: BenchmarkCase[] = [
  { id: 'revenue', question: 'IBM의 LTM 매출은 얼마인가요?', expected_numbers: [67535], expected_target: 'get_ibm_key_financials', expected_sheets: ['Key_Stats'] },
  { id: 'eps-dps', question: '2024-12-31 기준 희석 EPS와 DPS는 얼마인가요?', expected_numbers: [6.429, 6.67], expected_target: 'get_ibm_key_financials', expected_sheets: ['Key_Stats'] },
  { id: 'cashflow', question: '2025년 영업현금흐름과 CAPEX는 얼마인가요?', expected_numbers: [13193, -1617], expected_target: 'get_ibm_key_financials', expected_sheets: ['Key_Stats'] },
];

const WORKFLOW_HINTS: Record<string, string> = {
  rag1_dense_baseline: 'Dense 검색 기준선',
  rag3_llm_router_dense: 'LLM 라우터 + Dense',
  rag4_hybrid_rrf: 'BM25 + Dense + RRF',
  rag5_decomposition_hybrid: 'LLM 분해 + Hybrid',
  rag6_semantic_router_dense: 'Semantic 라우터 + Dense',
  rag7_adaptive_semantic_hybrid: 'Adaptive Semantic + Hybrid',
  rag8_optimized_router_hybrid: 'Optimized Semantic + Hybrid',
};

interface BenchmarkPanelProps { isOpen: boolean; onClose: () => void; }

export function BenchmarkPanel({ isOpen, onClose }: BenchmarkPanelProps) {
  const [workflows, setWorkflows] = useState<WorkflowDocument[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [casesText, setCasesText] = useState(() => JSON.stringify(DEFAULT_CASES, null, 2));
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [result, setResult] = useState<BenchmarkComparison | null>(null);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(false);

  const ragWorkflows = useMemo(() => workflows.filter((workflow) => workflow.id.startsWith('rag')), [workflows]);

  useEffect(() => {
    void pipelineApi.getWorkflows().then(({ workflows: items }) => {
      const ragItems = items.filter((item) => item.id.startsWith('rag'));
      setWorkflows(ragItems);
      setSelected(ragItems.map((item) => item.id));
    }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : '워크플로우를 불러오지 못했습니다.'));
  }, []);

  const toggle = (workflowId: string) => setSelected((current) =>
    current.includes(workflowId) ? current.filter((id) => id !== workflowId) : [...current, workflowId]
  );

  const run = async () => {
    try {
      const cases = JSON.parse(casesText) as BenchmarkCase[];
      if (selected.length < 2) throw new Error('비교할 RAG를 두 개 이상 선택해 주세요.');
      if (!Array.isArray(cases) || !cases.length) throw new Error('평가 질문이 비어 있습니다.');
      setRunning(true); setError(''); setResult(await pipelineApi.compareBenchmarks(selected, cases));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '벤치마크 실행에 실패했습니다.');
    } finally { setRunning(false); }
  };

  if (!isOpen) return null;
  return (
    <div className="benchmark-overlay" role="presentation" onMouseDown={onClose}>
      <aside className="benchmark-panel" role="dialog" aria-modal="true" aria-label="RAG 성능 비교" onMouseDown={(event) => event.stopPropagation()}>
        <header className="benchmark-panel__header"><span><BarChart3 size={18} /> RAG 성능 비교</span><button type="button" onClick={onClose} aria-label="성능 비교 닫기"><X size={18} /></button></header>
        <p className="benchmark-panel__intro">동일한 질문 세트를 순차 실행해 정확도, 응답 시간, 토큰·비용과 라우터 성능을 비교합니다.</p>

        <section className="benchmark-section">
          <div className="benchmark-section__title"><span>비교 대상</span><small>{selected.length}개 선택</small></div>
          <div className="benchmark-workflow-grid">
            {ragWorkflows.map((workflow) => {
              const active = selected.includes(workflow.id);
              return <button type="button" key={workflow.id} className="benchmark-workflow-card" data-selected={active} onClick={() => toggle(workflow.id)}>
                <i>{active && <Check size={13} strokeWidth={3} />}</i><strong>{workflow.name}</strong><small>{WORKFLOW_HINTS[workflow.id] ?? workflow.id}</small>
              </button>;
            })}
          </div>
        </section>

        <section className="benchmark-section benchmark-cases">
          <div className="benchmark-section__title"><span>평가 세트</span><small>기본 3문항</small></div>
          <ol>{DEFAULT_CASES.map((item) => <li key={item.id}>{item.question}</li>)}</ol>
          <button type="button" className="benchmark-advanced-toggle" onClick={() => setShowAdvanced((open) => !open)}>{showAdvanced ? 'JSON 편집 닫기' : '평가 질문 직접 편집'}</button>
          {showAdvanced && <textarea className="benchmark-json" value={casesText} onChange={(event) => setCasesText(event.target.value)} rows={10} aria-label="평가 질문 JSON" />}
        </section>

        <button type="button" className="benchmark-run-button" onClick={() => void run()} disabled={running || selected.length < 2}><Play size={16} fill="currentColor" /> {running ? '전체 비교 실행 중…' : `${selected.length}개 RAG 비교 실행`}</button>
        {error && <div className="benchmark-error">{error}</div>}

        {result && <section className="benchmark-section benchmark-results"><div className="benchmark-section__title"><span>비교 결과</span><small>{result.execution_mode === 'sequential_isolated' ? '순차 실행' : ''}</small></div>
          {result.id && <p className="benchmark-saved">저장됨 · <code>{result.id}</code></p>}
          {result.summary.map((item) => <article key={item.workflow_id} className="benchmark-result-card">
            <strong>{ragWorkflows.find((flow) => flow.id === item.workflow_id)?.name ?? item.workflow_id}</strong>
            <div className="benchmark-result-metrics"><span><b>{(item.accuracy * 100).toFixed(1)}%</b> 답변 정확도</span><span><b>{item.average_latency_seconds.toFixed(2)}s</b> 평균 시간</span><span><b>{item.average_tokens.toFixed(0)}</b> tokens</span><span><b>${item.average_cost_usd.toFixed(4)}</b> 비용</span></div>
            {item.router_kind && <div className="benchmark-router-metrics">{item.router_kind} router · {item.route_accuracy === null ? '라우팅 정답셋 없음' : `라우팅 정확도 ${(item.route_accuracy * 100).toFixed(1)}%`} · {item.average_router_latency_seconds?.toFixed(3)}s · {item.average_router_tokens?.toFixed(0)} tokens</div>}
          </article>)}
        </section>}
      </aside>
    </div>
  );
}
