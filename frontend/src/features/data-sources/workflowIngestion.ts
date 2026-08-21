import {
  Binary,
  Building2,
  CloudCog,
  Database,
  FileSpreadsheet,
  Rows3,
  Shuffle,
  Sparkles,
} from 'lucide-react';
import type { WorkflowRun } from '../playground/types';
import type { IngestionJobResponse } from './types';
import type { ModuleStepState, PipelineRunState } from './pipelineTypes';

const MODULE_VIEW: Record<
  string,
  { name: string; category: string; icon: typeof Sparkles }
> = {
  processed_file_selector: {
    name: '처리 파일 선택 (Processed File Selector)',
    category: 'Source',
    icon: FileSpreadsheet,
  },
  luna_vlm_structure_detector: {
    name: '테이블 구조 추출 (Luna VLM Detector)',
    category: 'Logic / Vision',
    icon: CloudCog,
  },
  cell_text_serializer: {
    name: '셀 문서 직렬화 (Cell Text Serializer)',
    category: 'Transform',
    icon: Rows3,
  },
  exhaustive_cell_text_serializer: {
    name: '전수 셀 직렬화 (Exhaustive Serializer)',
    category: 'Transform',
    icon: Shuffle,
  },
  cell_text_embedder: {
    name: '셀 문서 임베딩 (Cell Text Embedder)',
    category: 'Logic / Embedder',
    icon: Binary,
  },
  pgvector_index_writer: {
    name: 'pgvector 영구 적재 (PgVector Index Writer)',
    category: 'Storage / DB',
    icon: Database,
  },
  company_entity_extractor: {
    name: '기업 엔티티 추출 (Company Entity Extractor)',
    category: 'Logic / Vision',
    icon: Building2,
  },
  sheet_metadata_persistence: {
    name: '시트 메타데이터 저장 (Sheet Metadata Persistence)',
    category: 'Storage / DB',
    icon: Rows3,
  },
  index_company_persistence: {
    name: '인덱스 기업명 저장 (Index Company Persistence)',
    category: 'Storage / DB',
    icon: Database,
  },
};

/**
 * Formats a timestamp as minutes, seconds, and tenths of a second.
 *
 * @param value - The timestamp value to format
 * @returns The formatted timestamp, or `--:--.-` when no value is provided
 */
function timestamp(value: string | null | undefined): string {
  if (!value) return '--:--.-';
  const date = new Date(value);
  return `${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}.${Math.floor(date.getMilliseconds() / 100)}`;
}

/**
 * Calculates the elapsed runtime of a workflow run.
 *
 * @param run - The workflow run whose duration is measured
 * @returns The elapsed time in seconds, or `0` when either timestamp is invalid
 */
function elapsedSeconds(run: WorkflowRun): number {
  const start = new Date(run.created_at).getTime();
  const end = run.status === 'queued' || run.status === 'running'
    ? Date.now()
    : new Date(run.updated_at).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end)) return 0;
  return Math.max(0, (end - start) / 1000);
}

const PHASE_LABELS: Record<string, string> = {
  workbook_scan: '워크북 시트 스캔',
  sheet_analysis: 'Luna VLM 시트 분석',
  serialization_tables: '셀 문서 직렬화',
  document_generation: '전수 셀 문서 생성',
  embedding_batches: '임베딩 생성',
  storage_batches: 'pgvector 적재',
};

function numericProgress(progress: Record<string, unknown> | undefined): ModuleStepState['liveProgress'] {
  if (!progress) return undefined;
  const phase = typeof progress.phase === 'string' ? progress.phase : 'processing';
  const candidates = [
    ['completed_batches', 'total_batches', '배치'],
    ['finished_sheets', 'total_sheets', '시트'],
    ['completed_sheets', 'total_sheets', '시트'],
    ['completed_tables', 'total_tables', '테이블'],
    ['completed_items', 'total_items', '건'],
  ] as const;
  const candidate = candidates.find(([completedKey, totalKey]) => {
    const completed = Number(progress[completedKey]);
    const total = Number(progress[totalKey]);
    return Number.isFinite(completed) && Number.isFinite(total) && total > 0;
  });
  if (!candidate) return undefined;
  const [completedKey, totalKey, unit] = candidate;
  const completed = Number(progress[completedKey]);
  const total = Number(progress[totalKey]);
  const completedItems = Number(progress.completed_items);
  const totalItems = Number(progress.total_items);
  const currentItem = typeof progress.current_sheet === 'string'
    ? progress.current_sheet
    : undefined;
  return {
    phase,
    label: PHASE_LABELS[phase] || '모듈 처리',
    completed,
    total,
    unit,
    percent: Math.min(100, Math.max(0, (completed / total) * 100)),
    completedItems: Number.isFinite(completedItems) ? completedItems : undefined,
    totalItems: Number.isFinite(totalItems) ? totalItems : undefined,
    currentItem,
  };
}

/**
 * Builds the display state for a workflow module, including its status, progress, metadata, and activity log.
 *
 * @param run - The workflow execution containing the module node and runtime state
 * @param nodeId - The identifier of the module node
 * @returns The module's display state, or `null` when the node or its runtime state is unavailable
 */
function moduleState(run: WorkflowRun, nodeId: string): ModuleStepState | null {
  const node = run.graph.nodes.find((candidate) => candidate.id === nodeId);
  const state = run.nodes[nodeId];
  if (!node || !state) return null;
  const view = MODULE_VIEW[node.module_type] ?? {
    name: node.module_type,
    category: 'Module',
    icon: Sparkles,
  };

  const status: ModuleStepState['status'] = state.status === 'running'
    ? 'running'
    : state.status === 'succeeded' || state.status === 'skipped'
      ? 'done'
      : state.status === 'failed'
        ? 'failed'
        : 'waiting';
  const config = state.config_payload && Object.keys(state.config_payload).length > 0
    ? state.config_payload
    : node.config;
  const metaInfo: Record<string, string | number> = {};
  if (typeof config.model === 'string') metaInfo['모델'] = config.model;
  if (typeof config.batch_size === 'number') metaInfo['배치 크기'] = config.batch_size;
  if (typeof config.variant_mode === 'string') metaInfo['직렬화 방식'] = config.variant_mode;
  if (state.cache_hit) metaInfo['캐시'] = 'hit';

  const completedBatches = Number(state.progress?.completed_batches);
  const totalBatches = Number(state.progress?.total_batches);
  const completedItems = Number(state.progress?.completed_items);
  const totalItems = Number(state.progress?.total_items);
  const hasBatchProgress = Number.isFinite(completedBatches)
    && Number.isFinite(totalBatches)
    && totalBatches > 0;
  const batchProgress = hasBatchProgress
    ? {
        completed: completedBatches,
        total: totalBatches,
        completedItems: Number.isFinite(completedItems) ? completedItems : undefined,
        totalItems: Number.isFinite(totalItems) ? totalItems : undefined,
      }
    : undefined;
  const liveProgress = numericProgress(state.progress);
  if (batchProgress) {
    metaInfo['배치 진행'] = `${batchProgress.completed}/${batchProgress.total}`;
    if (batchProgress.totalItems !== undefined) {
      metaInfo['문서 진행'] = `${batchProgress.completedItems ?? 0}/${batchProgress.totalItems}`;
    }
  }
  if (liveProgress) {
    metaInfo['현재 단계'] = liveProgress.label;
    if (liveProgress.currentItem) metaInfo['처리 대상'] = liveProgress.currentItem;
  }
  const failedSheets = Number(state.progress?.failed_sheets);
  if (Number.isFinite(failedSheets) && failedSheets > 0) {
    metaInfo['실패 시트'] = failedSheets;
  }

  let message = '실행 대기 중';
  let logStatus: NonNullable<ModuleStepState['sublogs'][number]['status']> = 'info';
  if (state.status === 'running') {
    message = liveProgress
      ? `${liveProgress.label} 중 · ${liveProgress.completed}/${liveProgress.total} ${liveProgress.unit} 완료`
      : `${view.name} 실행 중`;
    logStatus = 'running';
  } else if (state.status === 'succeeded') {
    message = `${view.name} 완료${state.cache_hit ? ' (캐시 사용)' : ''}`;
    logStatus = 'done';
  } else if (state.status === 'skipped') {
    message = state.skip_reason || `${view.name} 건너뜀`;
    logStatus = 'warn';
  } else if (state.status === 'failed') {
    message = state.error || `${view.name} 실행 실패`;
    logStatus = 'failed';
  }

  return {
    id: node.id,
    name: view.name,
    moduleType: node.module_type,
    category: view.category,
    icon: view.icon,
    status,
    durationSeconds: typeof state.elapsed_ms === 'number' ? state.elapsed_ms / 1000 : undefined,
    sublogs: [{
      time: timestamp(state.completed_at || state.started_at || run.created_at),
      msg: message,
      status: logStatus,
    }],
    metaInfo,
    batchProgress,
    liveProgress,
  };
}

/**
 * Converts an ingestion job response into the pipeline run state used by the interface.
 *
 * @param job - Ingestion job response containing workflow, index, and output data
 * @returns Pipeline state with module statuses, progress, runtime metadata, and costs
 */
export function pipelineFromIngestionJob(job: IngestionJobResponse): PipelineRunState {
  const run = job.run;
  const orderedNodeIds = run.batches.flatMap((batch) => batch.node_ids);
  const modules = orderedNodeIds
    .map((nodeId) => moduleState(run, nodeId))
    .filter((module): module is ModuleStepState => module !== null);
  const currentStageIndex = Math.max(
    0,
    modules.findIndex((module) => module.status === 'running') >= 0
      ? modules.findIndex((module) => module.status === 'running')
      : modules.findIndex((module) => module.status === 'failed') >= 0
        ? modules.findIndex((module) => module.status === 'failed')
        : modules.reduce((last, module, index) => module.status === 'done' ? index : last, 0)
  );
  const completedModuleUnits = modules.reduce((total, module) => {
    if (module.status === 'done' || module.status === 'failed') return total + 1;
    if (module.status === 'running') {
      return total + Math.max(0.03, (module.liveProgress?.percent || 0) / 100);
    }
    return total;
  }, 0);
  const selectorNode = run.graph.nodes.find((node) => node.module_type === 'processed_file_selector');
  const selectorInput = selectorNode ? run.runtime_inputs[selectorNode.id] : undefined;
  const embedderNode = run.graph.nodes.find((node) => node.module_type === 'cell_text_embedder');
  const model = String(embedderNode?.config.model || job.index?.model || 'text-embedding-3-large');
  const batchSize = Number(embedderNode?.config.batch_size || job.index?.batch_size || 2048);
  const lunaOutput = job.luna_output || job.index?.luna_output;

  return {
    pipelineId: run.id,
    fileName: String(selectorInput?.file_name || job.index?.file_name || 'Excel Dataset'),
    workbookHash: lunaOutput?.workbook_hash || job.index?.workbook_hash,
    targetIndexId: job.target_index_id || undefined,
    companyName: job.index?.company_name,
    model,
    batchSize,
    status: run.status === 'completed'
      ? 'completed'
      : run.status === 'failed'
        ? 'failed'
        : run.status,
    isLiveUpload: true,
    currentStageIndex,
    progressPercent: run.status === 'completed'
      ? 100
      : Math.round((completedModuleUnits / Math.max(1, modules.length)) * 100),
    elapsedSeconds: elapsedSeconds(run),
    chunkCount: job.index?.document_count,
    totalTokens: job.index?.total_tokens,
    costUsd: job.index?.estimated_cost_usd,
    costKrw: job.index?.estimated_cost_krw,
    error: job.error,
    modules,
    lunaOutput: lunaOutput || undefined,
    scheduler: {
      backend: run.orchestration?.backend || 'direct',
      deploymentName: run.orchestration?.deployment_name || undefined,
      externalRunId: run.orchestration?.external_run_id || undefined,
      workerActive: job.worker_active,
    },
  };
}
