import { useEffect, useState } from 'react';
import { BarChart3, Boxes, ChevronRight, Play } from 'lucide-react';
import { pipelineApi } from '../services/api';
import type { BenchmarkCase, BenchmarkComparison, WorkflowDocument } from '../types';

const example = JSON.stringify([
  { id: 'q1', question: 'IBM의 LTM 매출은?', expected_numbers: [67535] },
], null, 2);

export function BenchmarkPanel() {
  const [workflows, setWorkflows] = useState<WorkflowDocument[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [casesText, setCasesText] = useState(example);
  const [result, setResult] = useState<BenchmarkComparison | null>(null);
  const [error, setError] = useState('');
  const [running, setRunning] = useState(false);

  useEffect(() => {
    void pipelineApi.getWorkflows()
      .then(({ workflows: items }) => {
        setWorkflows(items);
        setSelected(items.slice(0, 2).map((item) => item.id));
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : '워크플로를 불러오지 못했습니다.'));
  }, []);

  const toggle = (workflowId: string) => setSelected((current) =>
    current.includes(workflowId) ? current.filter((id) => id !== workflowId) : [...current, workflowId]
  );

  const run = async () => {
    try {
      const cases = JSON.parse(casesText) as BenchmarkCase[];
      if (selected.length < 2) throw new Error('비교할 프레임을 두 개 이상 선택하세요.');
      if (!Array.isArray(cases) || !cases.length) throw new Error('질문셋 JSON이 비어 있습니다.');
      setRunning(true);
      setError('');
      setResult(await pipelineApi.compareBenchmarks(selected, cases));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '벤치마크 실행에 실패했습니다.');
    } finally {
      setRunning(false);
    }
  };

  return (
    <details className="benchmark-panel">
      <summary><BarChart3 size={16} /> RAG 성능 비교</summary>
      <p>비교할 <strong>프레임(워크플로)</strong>을 이름으로 선택하세요. 각 프레임은 펼치면 내부 레이어(노드)를 볼 수 있습니다.</p>
      <div className="workflow-picker">
        {workflows.map((workflow) => <article key={workflow.id} className="workflow-frame">
          <label className="workflow-frame__title"><input type="checkbox" checked={selected.includes(workflow.id)} onChange={() => toggle(workflow.id)} /> <Boxes size={15} /> {workflow.name}</label>
          <small>{workflow.id === 'workflow' ? '현재 캔버스' : '저장된 템플릿'} · {workflow.graph.nodes.length}개 레이어</small>
          <details><summary><ChevronRight size={14} /> 레이어 보기</summary><ol>{workflow.graph.nodes.map((node) => <li key={node.id}><code>{node.module_type}</code></li>)}</ol></details>
        </article>)}
      </div>
      <label>질문셋 JSON<textarea value={casesText} onChange={(event) => setCasesText(event.target.value)} rows={7} /></label>
      <button type="button" onClick={() => void run()} disabled={running}><Play size={15} /> {running ? '실행 중…' : '선택한 프레임 비교'}</button>
      {error && <div className="benchmark-error">{error}</div>}
      {result && <div className="benchmark-results">
        {result.summary.map((item) => <article key={item.workflow_id}>
          <h4>{workflows.find((flow) => flow.id === item.workflow_id)?.name ?? item.workflow_id}</h4>
          <div className="benchmark-bar"><span style={{ width: `${item.accuracy * 100}%` }} /></div>
          <strong>{(item.accuracy * 100).toFixed(1)}%</strong> 정확도 · {item.average_latency_seconds.toFixed(2)}초 · {item.average_tokens.toFixed(0)} tokens · ${item.average_cost_usd.toFixed(6)}
        </article>)}
      </div>}
    </details>
  );
}
