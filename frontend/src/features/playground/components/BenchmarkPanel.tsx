import { useCallback, useEffect, useMemo, useState } from 'react';
import { BarChart3, Check, Pause, Play, Square, X } from 'lucide-react';
import { pipelineApi } from '../services/api';
import type { BenchmarkCase, BenchmarkComparison, BenchmarkJob, BenchmarkRunSnapshot, BenchmarkSet, WorkflowDocument } from '../types';

// Fast, repeatable core set: exactly one held-out question for each of the
// six query types. Keep semantic-decomposition-core-6.json in sync.
const DEFAULT_CASES: BenchmarkCase[] = [
  { id: 't1-revenue', question: 'IBM LTM 매출 숫자 뭐예요?', expected_numbers: [67535], expected_target: 'get_ibm_key_financials', expected_sheets: ['Income_Statement'], expected_plan: { metrics: ['revenue'], periods: [2025] } },
  { id: 't2-revenue-trend', question: 'IBM 매출, 2021년부터 2025년까지 연도별로 보여줘.', expected_numbers: [57351, 60530, 61860, 62753, 67535], expected_target: 'get_ibm_key_financials', expected_sheets: ['Income_Statement'], expected_plan: { metrics: ['revenue'], periods: [2021, 2022, 2023, 2024, 2025] } },
  { id: 't3-cashflow', question: 'IBM 영업현금흐름과 투자지출(CapEx) 각각 얼마야?', expected_numbers: [13193, -1617], expected_target: 'get_ibm_key_financials', expected_sheets: ['Cash_Flow'], expected_plan: { metrics: ['operating_cash_flow', 'capex'], periods: [2025] } },
  { id: 't4-fcf', question: 'IBM 2025년 FCF를 영업현금흐름과 CapEx로 계산해줘.', expected_numbers: [11576], expected_target: 'get_ibm_key_financials', expected_sheets: ['Cash_Flow'], expected_plan: { metrics: ['operating_cash_flow', 'capex'], periods: [2025] } },
  { id: 't5-margin-reason', question: 'IBM의 2025년 매출 성장과 EBITDA 마진 개선을 수치 근거로 설명해줘.', expected_numbers: [7.62, 24.84], expected_terms: ['EBITDA'], expected_target: 'get_ibm_key_financials', expected_sheets: ['Income_Statement'], expected_plan: { metrics: ['revenue', 'ebitda'], periods: [2025] } },
  { id: 't6-revenue-2026', question: 'IBM의 2026년 예상 매출은 얼마로 잡혀 있나요?', expected_numbers: [71183.3116], expected_target: 'get_ibm_key_financials', expected_sheets: ['Income_Statement'], expected_plan: { metrics: ['revenue'], periods: [2026] } },
];

const isBenchmarkWorkflow = (workflow: WorkflowDocument) => {
  const moduleTypes = new Set(workflow.graph.nodes.map((node) => node.module_type));
  return moduleTypes.has('query_input') && moduleTypes.has('decomposer');
};
const DEFAULT_QUESTIONS_TEXT = DEFAULT_CASES.map((item) => item.question).join('\n');
const normalizeQuestion = (question: string) => question.trim().replace(/\s+/g, ' ');
const DEFAULT_CASE_BY_QUESTION = new Map(DEFAULT_CASES.map((item) => [normalizeQuestion(item.question), item]));

interface BenchmarkPanelProps { isOpen: boolean; onClose: () => void; }

function casesFromLines(value: string, knownCases: Map<string, BenchmarkCase> = DEFAULT_CASE_BY_QUESTION): BenchmarkCase[] {
    return value.split(/\r?\n/).map((question) => question.trim()).filter(Boolean)
    .map((question, index) => {
      const knownCase = knownCases.get(normalizeQuestion(question));
      return knownCase
        ? { ...knownCase, id: `${knownCase.id}-${index + 1}`, question }
        : { id: `free-${String(index + 1).padStart(3, '0')}`, question };
    });
}

function RunDetails({ run, title }: { run: BenchmarkRunSnapshot; title: string }) {
  return <details className="benchmark-run-details" open>
    <summary>{title} <small>{run.status} · {run.nodes.length}개 노드</small></summary>
    <div className="benchmark-node-list">
      {run.nodes.map((node) => <details key={node.node_id} className="benchmark-node" open={node.status === 'running' || node.status === 'failed'}>
        <summary><span data-status={node.status}>{node.status}</span><b>{node.module_type}</b><small>{node.elapsed_ms === null ? '대기 중' : `${(node.elapsed_ms / 1000).toFixed(2)}s`}{node.cache_hit ? ' · cache' : ''}</small></summary>
        {node.error && <pre className="benchmark-node__error">{node.error}</pre>}
        {node.output_preview && <pre className="benchmark-node__output">{node.output_preview}</pre>}
        {!node.error && !node.output_preview && <p>아직 결과가 없습니다.</p>}
      </details>)}
    </div>
  </details>;
}

export function BenchmarkPanel({ isOpen, onClose }: BenchmarkPanelProps) {
  const [workflows, setWorkflows] = useState<WorkflowDocument[]>([]);
  const [benchmarkSets, setBenchmarkSets] = useState<BenchmarkSet[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [mode, setMode] = useState<string>('semantic-decomposition-core-6');
  const [questionsText, setQuestionsText] = useState(DEFAULT_QUESTIONS_TEXT);
  const [cacheMode, setCacheMode] = useState<'off' | 'index_only' | 'all'>('index_only');
  const [executionScope, setExecutionScope] = useState<'full' | 'pre_retrieval'>('pre_retrieval');
  const [result, setResult] = useState<BenchmarkComparison | null>(null);
  const [error, setError] = useState('');
  const [isLoadingWorkflows, setIsLoadingWorkflows] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<BenchmarkJob | null>(null);
  const running = jobId !== null;
  const ragWorkflows = useMemo(() => workflows.filter(isBenchmarkWorkflow), [workflows]);
  const knownCases = useMemo(() => new Map(
    [...DEFAULT_CASES, ...benchmarkSets.flatMap((item) => item.cases)]
      .map((item) => [normalizeQuestion(item.question), item] as const),
  ), [benchmarkSets]);

  const loadWorkflows = useCallback(async () => {
    setIsLoadingWorkflows(true);
    try {
      const [{ workflows: items }, { benchmark_sets: sets }] = await Promise.all([
        pipelineApi.getWorkflows(),
        pipelineApi.getBenchmarkSets(),
      ]);
      const ragItems = items.filter(isBenchmarkWorkflow);
      setWorkflows(ragItems);
      setSelected(ragItems.map((item) => item.id));
      setBenchmarkSets(sets);
      setError('');
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : '워크플로우를 불러오지 못했습니다.');
    } finally {
      setIsLoadingWorkflows(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) void loadWorkflows();
  }, [isOpen, loadWorkflows]);

  const toggle = (workflowId: string) => setSelected((current) => current.includes(workflowId) ? current.filter((id) => id !== workflowId) : [...current, workflowId]);

  useEffect(() => {
    if (!jobId) return;
    let disposed = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const next = await pipelineApi.getBenchmarkJob(jobId);
        if (disposed) return;
        setJob(next);
        if (next.status === 'completed') {
          setResult(next.result);
          setJobId(null);
        } else if (next.status === 'failed') {
          setError(next.error || '벤치마크 실행에 실패했습니다.');
          setJobId(null);
        } else if (next.status === 'cancelled') {
          setJobId(null);
        } else {
          timer = window.setTimeout(() => void poll(), 700);
        }
      } catch (cause) {
        if (!disposed) {
          setError(cause instanceof Error ? cause.message : '벤치마크 진행 상황을 불러오지 못했습니다.');
          setJobId(null);
        }
      }
    };
    void poll();
    return () => { disposed = true; if (timer) window.clearTimeout(timer); };
  }, [jobId]);

  const run = async () => {
    try {
      const cases = casesFromLines(questionsText, knownCases);
      if (selected.length < 2) throw new Error('비교할 RAG를 두 개 이상 선택해 주세요.');
      if (!cases.length) throw new Error('질문을 한 줄에 하나씩 입력해 주세요.');
      setError(''); setResult(null); setJob(null);
      const started = await pipelineApi.startBenchmarkJob(selected, cases, cacheMode, executionScope);
      setJobId(started.id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '벤치마크 실행을 시작하지 못했습니다.'); }
  };

  const stop = () => {
    if (!job?.id || job.status === 'cancelling') return;
    setJob((current) => current ? { ...current, status: 'cancelling' } : current);
    void pipelineApi.cancelBenchmarkJob(job.id)
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : '벤치마크 중지를 요청하지 못했습니다.'));
  };

  const pauseOrResume = () => {
    if (!job?.id) return;
    const paused = job.status === 'paused' || job.status === 'pausing';
    setJob((current) => current ? { ...current, status: paused ? 'running' : 'pausing' } : current);
    const request = paused
      ? pipelineApi.resumeBenchmarkJob(job.id)
      : pipelineApi.pauseBenchmarkJob(job.id);
    void request.catch((cause: unknown) => setError(
      cause instanceof Error ? cause.message : '벤치마크 일시 중지 상태를 변경하지 못했습니다.',
    ));
  };

  const selectBenchmarkSet = (set: BenchmarkSet) => {
    setMode(set.id);
    setQuestionsText(set.cases.map((item) => item.question).join('\n'));
  };

  if (!isOpen) return null;
  return <div className="benchmark-overlay" role="presentation" onMouseDown={onClose}>
    <aside className="benchmark-panel" role="dialog" aria-modal="true" aria-label="RAG 성능 비교" onMouseDown={(event) => event.stopPropagation()}>
      <header className="benchmark-panel__header"><span><BarChart3 size={18} /> RAG 성능 비교</span><button type="button" onClick={onClose} aria-label="성능 비교 닫기"><X size={18} /></button></header>
      <p className="benchmark-panel__intro">동일 질문을 순차 실행해 정확도, <b>백엔드 노드 실행 시간</b>, 토큰, 비용을 비교합니다. 대기열·브라우저 통신 시간은 시간 지표에서 제외됩니다.</p>
      <section className="benchmark-section"><div className="benchmark-section__title"><span>비교 대상</span><small>{selected.length}개 선택</small></div><p className="benchmark-panel__intro">서버가 제공한 현재 워크플로 중 Query Input과 Decomposer가 연결된 RAG만 표시합니다. 비교하려면 기준 워크플로를 복제해 변형을 만드세요.</p><div className="benchmark-workflow-grid">{ragWorkflows.map((workflow) => { const active = selected.includes(workflow.id); return <button type="button" key={workflow.id} className="benchmark-workflow-card" data-selected={active} onClick={() => toggle(workflow.id)}><i>{active && <Check size={13} strokeWidth={3} />}</i><strong>{workflow.name}</strong><small>{workflow.id}</small></button>; })}</div>{isLoadingWorkflows && <p className="benchmark-workflow-state">워크플로를 불러오는 중…</p>}{!isLoadingWorkflows && !ragWorkflows.length && <div className="benchmark-workflow-state">비교 가능한 워크플로가 없습니다. <button type="button" onClick={() => void loadWorkflows()}>다시 불러오기</button></div>}</section>
      <section className="benchmark-section benchmark-cases"><div className="benchmark-section__title"><span>질문 세트</span><small>{casesFromLines(questionsText, knownCases).length}문항 · 한 줄당 하나</small></div><div className="benchmark-mode">{benchmarkSets.filter((set) => set.id === 'semantic-decomposition-core-6' || set.id === 'semantic-safety-holdout-30').map((set) => <button type="button" key={set.id} data-selected={mode === set.id} onClick={() => selectBenchmarkSet(set)}>{set.name}</button>)}<button type="button" data-selected={mode === 'lines'} onClick={() => setMode('lines')}>직접 편집</button><button type="button" className="benchmark-reset-questions" onClick={() => { setMode('semantic-decomposition-core-6'); setQuestionsText(DEFAULT_QUESTIONS_TEXT); }}>기본값 복원</button></div><label className="benchmark-question-editor"><span>비교할 질문 <small>각 줄이 하나의 실행입니다</small></span><textarea className="benchmark-json" value={questionsText} onChange={(event) => { setQuestionsText(event.target.value); setMode('lines'); }} rows={8} placeholder={'질문 하나\n질문 둘\n질문 셋'} aria-label="한 줄당 하나의 질문" spellCheck={false} /></label><p className="benchmark-panel__intro">안전성 홀드아웃은 카탈로그 비중복 질문으로 route precision·coverage·기권 정확도와 plan precision·unsafe reuse를 측정합니다.</p></section>
      {job && <section className="benchmark-progress" aria-live="polite"><div className="benchmark-section__title"><span>{job.status === 'cancelling' ? '중지 요청 중…' : job.status === 'cancelled' ? '실행 중지됨' : job.status === 'pausing' ? '현재 문항 완료 후 일시 중지…' : job.status === 'paused' ? '일시 중지됨' : '실행 진행 상황'}</span><small>{job.completed} / {job.total}</small></div><div className="benchmark-progress__bar"><i style={{ width: `${job.total ? (job.completed / job.total) * 100 : 0}%` }} /></div>{job.current && <p className="benchmark-progress__current"><b>{job.current.workflow_id}</b> · {job.current.question || '다음 작업 준비 중'}</p>}{job.active_run && <RunDetails run={job.active_run} title="현재 실행 중인 노드" />}{!job.active_run && job.last_run && <RunDetails run={job.last_run} title="직전 실행 결과" />}<ol className="benchmark-progress__logs">{job.logs.slice().reverse().map((log, index) => <li key={`${log.at}-${index}`} data-event={log.event}><time>{new Date(log.at).toLocaleTimeString()}</time><span>{log.event === 'started' ? '실행 준비' : log.event === 'running' ? '실행 중' : log.event === 'completed' ? (log.error ? `실패: ${log.error}` : '완료') : log.event === 'paused' ? '일시 중지됨' : log.event === 'resumed' ? '다시 시작됨' : log.event === 'pausing' ? '일시 중지 요청' : '중지 요청'}</span><b>{log.workflow_id ?? '비교기'}</b><em>{log.question ?? ''}</em></li>)}</ol></section>}
      <label className="benchmark-cache-option"><span><b>실행 범위</b><small>검색 전 모드는 라우팅·분해까지만 실행하고 시트·지표·기간 정확도를 채점합니다.</small></span><select value={executionScope} onChange={(event) => setExecutionScope(event.target.value as typeof executionScope)} disabled={running}><option value="pre_retrieval">검색 전까지만 (빠른 중간 평가)</option><option value="full">전체 RAG (최종 답변 평가)</option></select></label>
      <label className="benchmark-cache-option"><span><b>벤치마크 캐시 모드</b><small>정확도·질의 성능 비교에는 ‘pgvector 데이터 소스만 재사용’을 권장합니다.</small></span><select value={cacheMode} onChange={(event) => setCacheMode(event.target.value as typeof cacheMode)} disabled={running}><option value="index_only">pgvector 데이터 소스만 재사용 (권장)</option><option value="off">캐시 미사용 (콜드 스타트)</option><option value="all">전체 결과 캐시 사용</option></select></label><div className="benchmark-run-actions"><button type="button" className="benchmark-run-button" onClick={() => void run()} disabled={running || selected.length < 2}><Play size={16} fill="currentColor" /> {running ? (job?.status === 'paused' ? '비교 일시 중지됨' : '비교 실행 중…') : `${selected.length}개 RAG 비교 실행`}</button>{running && job?.status !== 'cancelling' && <button type="button" className="benchmark-pause-button" onClick={pauseOrResume}><Pause size={15} fill="currentColor" /> {job?.status === 'paused' || job?.status === 'pausing' ? '계속 실행' : '일시 중지'}</button>}{running && <button type="button" className="benchmark-stop-button" onClick={stop} disabled={job?.status === 'cancelling'}><Square size={15} fill="currentColor" /> {job?.status === 'cancelling' ? '중지 요청 중' : '실행 중지'}</button>}</div>{error && <div className="benchmark-error">{error}</div>}
      {result && <section className="benchmark-section benchmark-results"><div className="benchmark-section__title"><span>비교 결과</span><small>순차 실행 · {result.execution_scope === 'pre_retrieval' ? '검색 전 중간 평가' : '전체 RAG 평가'} · {result.cache_mode === 'index_only' ? 'pgvector 데이터 소스만 재사용' : result.use_cache ? '전체 결과 캐시' : '캐시 미사용'} · 자동 저장</small></div>{result.id && <p className="benchmark-saved">저장됨: <code>{result.id}</code></p>}{result.summary.map((item) => <article key={item.workflow_id} className="benchmark-result-card"><strong>{ragWorkflows.find((flow) => flow.id === item.workflow_id)?.name ?? item.workflow_id}</strong><div className="benchmark-result-metrics">{result.execution_scope === 'pre_retrieval' && item.intermediate_accuracy != null && <span><b>{`${(item.intermediate_accuracy * 100).toFixed(1)}%`}</b> 라우팅·계획 종합</span>}<span><b>{result.execution_scope === 'pre_retrieval' ? (item.plan_accuracy == null ? '—' : `${(item.plan_accuracy * 100).toFixed(1)}%`) : (item.accuracy === null ? '—' : `${(item.accuracy * 100).toFixed(1)}%`)}</b> {result.execution_scope === 'pre_retrieval' ? '계획 정확도' : '최종 정답률'}</span>{item.sheet_exact_accuracy != null && <><span><b>{`${(item.sheet_exact_accuracy * 100).toFixed(1)}%`}</b> 시트 exact</span><span><b>{item.average_sheet_precision == null ? '—' : `${(item.average_sheet_precision * 100).toFixed(1)}%`}</b> 시트 precision</span><span><b>{item.average_sheet_recall == null ? '—' : `${(item.average_sheet_recall * 100).toFixed(1)}%`}</b> 시트 recall</span></>}<span><b>{item.average_latency_seconds.toFixed(2)}s</b> 평균 처리 시간</span><span><b>{item.average_tokens.toFixed(0)}</b> 이번 API tokens</span><span><b>${item.average_cost_usd.toFixed(4)}</b> 이번 API 비용</span><span><b>{item.llm_fallback_calls}</b> LLM fallback</span><span><b>{item.plan_reuse_coverage == null ? '—' : `${(item.plan_reuse_coverage * 100).toFixed(1)}%`}</b> 계획 재사용</span><span><b>{item.plan_reuse_precision == null ? '—' : `${(item.plan_reuse_precision * 100).toFixed(1)}%`}</b> 재사용 계획 정밀도</span><span><b>{item.unsafe_plan_reuse_count ?? 0}</b> 위험 계획 재사용</span></div>{result.use_cache && <p className="benchmark-cache-summary">캐시 hit <b>{item.cache_hits} / {item.node_runs}</b> · 재사용 결과의 과거 사용량: 평균 {item.average_reused_tokens.toFixed(0)} tokens / ${item.average_reused_cost_usd.toFixed(4)} <small>(이번 실행에는 과금되지 않음)</small></p>}{item.router_kind && <div className="benchmark-router-metrics">{item.router_kind} router · coverage {item.route_coverage == null ? '—' : `${(item.route_coverage * 100).toFixed(1)}%`} · precision {item.route_precision == null ? '—' : `${(item.route_precision * 100).toFixed(1)}%`} · 기권 정확도 {item.abstention_accuracy == null ? '—' : `${(item.abstention_accuracy * 100).toFixed(1)}%`} · {item.average_router_latency_seconds?.toFixed(3)}s · {item.average_router_tokens?.toFixed(0)} tokens</div>}</article>)}</section>}
    </aside>
  </div>;
}
