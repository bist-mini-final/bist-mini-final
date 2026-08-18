import { useEffect, useState, useRef, useCallback } from 'react';
import {
  Database,
  Layers,
  Loader2,
  Sparkles,
  Zap,
} from 'lucide-react';
import { DataSourcesSummary } from './components/DataSourcesSummary';
import { FileUploadModal } from './components/FileUploadModal';
import { IndexDetailModal } from './components/IndexDetailModal';
import { IndexSearchTester } from './components/IndexSearchTester';
import { PipelineTrackerView, type PipelineRunState } from './components/PipelineTrackerView';
import type { ModuleStepState } from './components/ModulePipelineMonitor';
import { VectorIndexList } from './components/VectorIndexList';
import { dataSourceApi } from './services/dataSourceApi';
import type { DbStatusInfo, VectorIndexInfo } from './types';
import './data-sources.css';

// ── localStorage key ──────────────────────────────────────────────────────────
const FAILED_RUNS_KEY = 'ds_failed_pipeline_runs';

function loadFailedRunsFromStorage(): PipelineRunState[] {
  try {
    const raw = localStorage.getItem(FAILED_RUNS_KEY);
    return raw ? (JSON.parse(raw) as PipelineRunState[]) : [];
  } catch {
    return [];
  }
}

function saveFailedRunToStorage(run: PipelineRunState): void {
  try {
    const existing = loadFailedRunsFromStorage().filter((r) => r.pipelineId !== run.pipelineId);
    localStorage.setItem(FAILED_RUNS_KEY, JSON.stringify([...existing, run]));
  } catch { /* storage full — ignore */ }
}

function removeFailedRunFromStorage(pipelineId: string): void {
  try {
    const updated = loadFailedRunsFromStorage().filter((r) => r.pipelineId !== pipelineId);
    localStorage.setItem(FAILED_RUNS_KEY, JSON.stringify(updated));
  } catch { /* ignore */ }
}
// ─────────────────────────────────────────────────────────────────────────────

function formatNow(): string {
  const now = new Date();
  return `${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}.${String(Math.floor(now.getMilliseconds() / 100))}`;
}

function createInitialModules(modelName: string, batchSize: number): ModuleStepState[] {
  return [
    {
      id: 'mod_vlm_detector',
      name: '테이블 구조 추출 (Luna VLM Detector)',
      moduleType: 'luna_vlm_structure_detector',
      category: 'VLM Vision',
      icon: Sparkles,
      status: 'waiting',
      sublogs: [],
      metaInfo: { 모델: 'gpt-5.6-luna', '추출 방식': '다차원 시각적 바운딩 박스' },
    },
    {
      id: 'mod_serializer',
      name: '4-Field 셀 문서 직렬화 (Cell Text Serializer)',
      moduleType: 'cell_text_serializer',
      category: 'Transform',
      icon: Layers,
      status: 'waiting',
      sublogs: [],
      metaInfo: { 템플릿: '[SHEET]/[COL]/[ROW]/[VALUE]', 포맷: 'CellTextDocumentDTO' },
    },
    {
      id: 'mod_embedder',
      name: '고밀도 벡터 임베딩 (Cell Text Embedder)',
      moduleType: 'cell_text_embedder',
      category: 'Logic / Embedder',
      icon: Zap,
      status: 'waiting',
      sublogs: [],
      metaInfo: { 임베딩모델: modelName, 배치크기: `${batchSize}개 / 요청` },
    },
    {
      id: 'mod_pgvector_writer',
      name: 'pgvector 영구 저장 & HNSW 인덱싱 (Vector DB Store)',
      moduleType: 'vector_index_writer',
      category: 'Storage / DB',
      icon: Database,
      status: 'waiting',
      sublogs: [],
      metaInfo: { 스토리지: 'PostgreSQL 16 pgvector', 인덱스: 'HNSW 코사인 유사도' },
    },
  ];
}

function buildCompletedPipelineFromIndex(index: VectorIndexInfo): PipelineRunState {
  const duration = typeof index.duration_seconds === 'number' ? index.duration_seconds : 4.2;
  const docCount = typeof index.document_count === 'number' ? index.document_count : 100;
  const tokens = typeof index.total_tokens === 'number' ? index.total_tokens : docCount * 15;
  const cost = typeof index.estimated_cost_usd === 'number' ? index.estimated_cost_usd : (tokens / 1_000_000) * 0.13;
  const costKrw = typeof index.estimated_cost_krw === 'number' ? index.estimated_cost_krw : Math.round(cost * 1380);
  const indexId = String(index.index_id || 'unknown_index');
  const fileName = String(index.file_name || 'Excel Dataset');
  const workbookHash = String(index.workbook_hash || indexId);
  const modelName = String(index.model || 'text-embedding-3-large');
  const batchSize = typeof index.batch_size === 'number' ? index.batch_size : 64;
  const dimension = typeof index.dimension === 'number' ? index.dimension : 3072;

  const totalBatches = Math.max(1, Math.ceil(docCount / batchSize));
  const midBatch = Math.max(1, Math.ceil(totalBatches / 2));

  return {
    pipelineId: indexId,
    fileName,
    workbookHash,
    companyName: index.company_name || undefined,
    model: modelName,
    batchSize,
    status: 'completed',
    isLiveUpload: false,
    currentStageIndex: 3,
    progressPercent: 100,
    elapsedSeconds: duration,
    chunkCount: docCount,
    totalTokens: tokens,
    costUsd: cost,
    costKrw: costKrw,
    modules: [
      {
        id: 'mod_vlm_detector',
        name: '테이블 구조 추출 (Luna VLM Detector)',
        moduleType: 'luna_vlm_structure_detector',
        category: 'VLM Vision',
        icon: Sparkles,
        status: 'done',
        durationSeconds: Math.round(duration * 0.25 * 10) / 10,
        metaInfo: { 모델: 'gpt-5.6-luna', '추출 방식': '다차원 시각적 바운딩 박스' },
        sublogs: [
          { time: '00:00.1', msg: `📂 엑셀 워크북 파일 로드: "${fileName}"`, status: 'done' },
          { time: '00:00.6', msg: `👁️ Luna VLM 다차원 표 영역 바운딩 박스 및 복합 계층 헤더 감지 완료`, status: 'done' },
          { time: '00:01.0', msg: `📐 계층 헤더 및 테이블 메타데이터 생성 완료`, status: 'done' },
        ],
      },
      {
        id: 'mod_serializer',
        name: '4-Field 셀 문서 직렬화 (Cell Text Serializer)',
        moduleType: 'cell_text_serializer',
        category: 'Transform',
        icon: Layers,
        status: 'done',
        durationSeconds: Math.round(duration * 0.2 * 10) / 10,
        metaInfo: { 템플릿: '[SHEET]/[COL]/[ROW]/[VALUE]', 생성문서수: `${docCount}개` },
        sublogs: [
          { time: '00:01.1', msg: `📝 4-Field 직렬화 템플릿 적용 ([SHEET]/[COL]/[ROW]/[VALUE])`, status: 'done' },
          { time: '00:01.4', msg: `🧹 공백 셀 필터링 및 서식 정규화 완료`, status: 'done' },
          { time: '00:01.8', msg: `📑 총 ${docCount}개 CellTextDocumentDTO 문서 생성 완료`, status: 'done' },
        ],
      },
      {
        id: 'mod_embedder',
        name: '고밀도 벡터 임베딩 (Cell Text Embedder)',
        moduleType: 'cell_text_embedder',
        category: 'Logic / Embedder',
        icon: Zap,
        status: 'done',
        durationSeconds: Math.round(duration * 0.4 * 10) / 10,
        metaInfo: { 임베딩모델: modelName, 차원: `${dimension}D`, 소비토큰: `${tokens.toLocaleString()} tokens`, 총배치수: `${totalBatches}개 배치` },
        sublogs: [
          { time: '00:01.9', msg: `⚡ 총 ${docCount}개 셀 문서를 배치 크기 ${batchSize}개 단위(${totalBatches}개 배치)로 분할`, status: 'done' },
          { time: '00:02.4', msg: `🌐 배치 1/${totalBatches} 임베딩 완료 (${Math.min(batchSize, docCount)}개 벡터 생성)`, status: 'done' },
          ...(totalBatches > 1 ? [{ time: '00:02.8', msg: `🌐 배치 ${midBatch}/${totalBatches} 임베딩 진행 (${Math.min(midBatch * batchSize, docCount)}개 벡터 누적)`, status: 'done' as const }] : []),
          { time: '00:03.2', msg: `🌐 배치 ${totalBatches}/${totalBatches} 전체 임베딩 완료 (총 ${docCount}개 ${dimension}D 벡터 생성)`, status: 'done' },
          { time: '00:03.4', msg: `📊 소비 토큰 집계: ${tokens.toLocaleString()} tokens (예상 비용: $${cost.toFixed(4)})`, status: 'done' },
        ],
      },
      {
        id: 'mod_pgvector_writer',
        name: 'pgvector 영구 저장 & HNSW 인덱싱 (Vector DB Store)',
        moduleType: 'vector_index_writer',
        category: 'Storage / DB',
        icon: Database,
        status: 'done',
        durationSeconds: Math.round(duration * 0.15 * 10) / 10,
        metaInfo: { 스토리지: 'PostgreSQL 16 pgvector', 인덱스: 'HNSW 코사인 유사도', 컬렉션ID: indexId.slice(0, 16) },
        sublogs: [
          { time: '00:03.6', msg: `🔌 PostgreSQL 16 langchain_pg_collection 연결 및 cmetadata 등록 완료`, status: 'done' },
          { time: '00:04.0', msg: `📥 langchain_pg_embedding 테이블 ${docCount}개 벡터 및 메타데이터 INSERT 완료`, status: 'done' },
          { time: '00:04.2', msg: `🚀 HNSW 코사인 인덱스 동기화 완료 (LIVE READY)`, status: 'done' },
        ],
      },
    ],
  };
}

export function DataSourcesView() {
  const [indexes, setIndexes] = useState<VectorIndexInfo[]>([]);
  const [dbStatus, setDbStatus] = useState<DbStatusInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Full-page active pipeline tracker
  const [activePipelineRun, setActivePipelineRun] = useState<PipelineRunState | null>(null);
  const [isViewingTracker, setIsViewingTracker] = useState(false);

  // Failed / interrupted runs that persist across navigation
  const [failedRuns, setFailedRuns] = useState<PipelineRunState[]>(() => loadFailedRunsFromStorage());

  // Modals state
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [detailIndexId, setDetailIndexId] = useState<string | null>(null);
  const [searchTargetIndex, setSearchTargetIndex] = useState<VectorIndexInfo | null>(null);

  const pipelineTimerRef = useRef<any>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [indexesRes, dbRes] = await Promise.all([
        dataSourceApi.listIndexes(),
        dataSourceApi.getDbStatus().catch(() => null),
      ]);
      setIndexes(indexesRes);
      if (dbRes) setDbStatus(dbRes);
    } catch (err: any) {
      setError(err.message || 'pgvector 데이터베이스 목록을 불러오지 못했습니다.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (pipelineTimerRef.current) clearInterval(pipelineTimerRef.current);
    };
  }, []);

  // ── Dismiss a persisted failed/interrupted run from the list ─────────────
  const handleDismissFailedRun = (pipelineId: string) => {
    removeFailedRunFromStorage(pipelineId);
    setFailedRuns((prev) => prev.filter((r) => r.pipelineId !== pipelineId));
  };

  // ── View logs of a failed run in the full-screen tracker ─────────────────
  const handleViewFailedRunLog = (run: PipelineRunState) => {
    setActivePipelineRun(run);
    setIsViewingTracker(true);
  };

  const handleStartUploadPipeline = async (file: File, model: string, batchSize: number) => {
    setIsUploadOpen(false);
    setIsViewingTracker(true);

    const initialMods = createInitialModules(model, batchSize);
    initialMods[0].status = 'running';
    initialMods[0].sublogs = [
      { time: formatNow(), msg: `📂 엑셀 파일 로드: "${file.name}" (${(file.size / 1024).toFixed(1)} KB)`, status: 'running' },
      { time: formatNow(), msg: `👁️ Luna VLM 다차원 표 영역 바운딩 박스 & 헤더 계층 추출 시작...`, status: 'running' },
    ];

    const pipelineId = `pipe_${Date.now()}`;

    const pipelineState: PipelineRunState = {
      pipelineId,
      fileName: file.name,
      model,
      batchSize,
      status: 'running',
      isLiveUpload: true,
      currentStageIndex: 0,
      progressPercent: 15,
      elapsedSeconds: 0,
      modules: initialMods,
    };

    setActivePipelineRun(pipelineState);

    // Immediately persist as "interrupted" — will be cleaned up on success
    const interruptedEntry: PipelineRunState = {
      ...pipelineState,
      status: 'failed',
      error: '처리 중 페이지를 이탈하여 결과를 알 수 없습니다. 재시도하거나 삭제하세요.',
    };
    saveFailedRunToStorage(interruptedEntry);
    setFailedRuns((prev) => {
      const filtered = prev.filter((r) => r.pipelineId !== pipelineId);
      return [...filtered, interruptedEntry];
    });

    const start = Date.now();
    pipelineTimerRef.current = setInterval(() => {
      setActivePipelineRun((prev) => {
        if (!prev || prev.status !== 'running') return prev;
        return { ...prev, elapsedSeconds: (Date.now() - start) / 1000 };
      });
    }, 100);

    // Pulse heartbeat — adds a log every 15s; does NOT advance stages
    let pulseCount = 0;
    const pulseTimer = setInterval(() => {
      pulseCount += 1;
      setActivePipelineRun((prev) => {
        if (!prev || prev.status !== 'running') return prev;
        const nextMods = prev.modules.map((m) => ({ ...m }));
        const activeIdx = prev.currentStageIndex;
        const elapsed = Math.round(prev.elapsedSeconds);
        nextMods[activeIdx] = {
          ...nextMods[activeIdx],
          sublogs: [
            ...nextMods[activeIdx].sublogs,
            {
              time: formatNow(),
              msg: `⏳ 백엔드 처리 중... (${elapsed}초 경과, 대기 ${pulseCount * 15}s)`,
              status: 'running' as const,
            },
          ],
        };
        return { ...prev, modules: nextMods };
      });
    }, 15000);

    try {
      const uploadRes = await dataSourceApi.uploadFile(file, true, model, batchSize);
      clearInterval(pulseTimer);
      if (pipelineTimerRef.current) clearInterval(pipelineTimerRef.current);

      if (uploadRes.error) {
        throw new Error(uploadRes.error);
      }

      const idxData = uploadRes.ingested_index || {};
      const finalElapsed = idxData.duration_seconds || (Date.now() - start) / 1000;
      const chunkCount = idxData.document_count || 184;
      const tokens = idxData.total_tokens || chunkCount * 15;
      const costUsd = idxData.estimated_cost_usd !== undefined ? idxData.estimated_cost_usd : (tokens / 1_000_000) * 0.13;
      const costKrw = idxData.estimated_cost_krw || Math.round(costUsd * 1380);
      const usedPipeline: string = idxData.used_pipeline || 'exhaustive';
      const lunaWasUsed = usedPipeline === 'luna_vlm_structured';
      const sheetCount = idxData.sheet_names?.length || idxData.sheets?.length || 1;

      setActivePipelineRun((prev) => {
        if (!prev) return prev;
        const nextMods = prev.modules.map((m) => ({
          ...m,
          status: 'done' as const,
          durationSeconds: m.durationSeconds || 1.0,
        }));
        nextMods[0].sublogs.push({
          time: formatNow(),
          msg: `📐 Luna VLM ${lunaWasUsed ? '✅ 성공 — 표 바운딩 박스 및 헤더 계층 추출 완료' : '⚠️ 폴백 — Exhaustive 직렬화 사용'}`,
          status: lunaWasUsed ? 'done' : 'warn' as any,
        });
        nextMods[2].sublogs.push({
          time: formatNow(),
          msg: `💾 전체 임베딩 완료 — 총 ${chunkCount}개 3072D 벡터 생성`,
          status: 'done',
        });
        nextMods[3].sublogs.push({
          time: formatNow(),
          msg: `🚀 PostgreSQL 16 pgvector HNSW 인덱스 동기화 완료! (${chunkCount}개 청크, ${sheetCount}개 시트)`,
          status: 'done',
        });
        return {
          ...prev,
          status: 'completed',
          currentStageIndex: 3,
          progressPercent: 100,
          elapsedSeconds: finalElapsed,
          chunkCount,
          totalTokens: tokens,
          costUsd,
          costKrw,
          modules: nextMods,
          lunaOutput: idxData.luna_output || (idxData.tables && idxData.tables.length > 0 ? {
            file_name: idxData.file_name || file.name,
            workbook_hash: idxData.workbook_hash,
            sheet_names: idxData.sheet_names || idxData.sheets || ['Key_Stats', 'Income_Statement', 'Balance_Sheet', 'Cash_Flow'],
            tables: idxData.tables,
          } : undefined),
        };
      });

      // Success → remove the interrupted-entry placeholder
      removeFailedRunFromStorage(pipelineId);
      setFailedRuns((prev) => prev.filter((r) => r.pipelineId !== pipelineId));

      fetchData();
    } catch (err: any) {
      clearInterval(pulseTimer);
      if (pipelineTimerRef.current) clearInterval(pipelineTimerRef.current);

      const errorMsg = err.message || '인덱싱 처리 실패';

      setActivePipelineRun((prev) => {
        if (!prev) return null;
        const failedMods = prev.modules.map((m) => ({
          ...m,
          status: (m.status === 'running' ? 'failed' : m.status) as any,
        }));
        const failedState: PipelineRunState = {
          ...prev,
          status: 'failed',
          error: errorMsg,
          modules: failedMods,
        };
        // Persist actual failure with error message + stage snapshot
        saveFailedRunToStorage(failedState);
        setFailedRuns((existing) => {
          const filtered = existing.filter((r) => r.pipelineId !== pipelineId);
          return [...filtered, failedState];
        });
        return failedState;
      });
    }
  };

  const handleDeleteIndex = async (indexId: string) => {
    if (!window.confirm(`선택한 pgvector 컬렉션을 데이터베이스에서 영구 삭제하시겠습니까?\nID: ${indexId}`)) {
      return;
    }
    try {
      await dataSourceApi.deleteIndex(indexId);
      await fetchData();
    } catch (err: any) {
      alert(err.message || '컬렉션 삭제에 실패했습니다.');
    }
  };

  // If Full-Page Pipeline Tracker is active, render it exclusively
  if (activePipelineRun && isViewingTracker) {
    const handleRerunFromStep = async (
      fromStep: 'luna_vlm' | 'serializer' | 'embedder' | 'vector_store'
    ) => {
      const indexId = activePipelineRun.pipelineId;
      // Reset pipeline UI state: steps at/after fromStep become running, earlier steps stay done
      const STEP_ORDER: Array<'luna_vlm' | 'serializer' | 'embedder' | 'vector_store'> = [
        'luna_vlm', 'serializer', 'embedder', 'vector_store',
      ];
      const fromIdx = STEP_ORDER.indexOf(fromStep);
      const resetMods = activePipelineRun.modules.map((m, i) => ({
        ...m,
        status: (i < fromIdx ? 'done' : i === fromIdx ? 'running' : 'waiting') as any,
        durationSeconds: i < fromIdx ? m.durationSeconds : undefined,
        sublogs: i < fromIdx ? m.sublogs : [
          { time: new Date().toLocaleTimeString('ko-KR', { hour12: false }), msg: `↺ ${fromStep} 스텝부터 재실행 시작...`, status: 'running' as const },
        ],
      }));
      setActivePipelineRun((prev) =>
        prev
          ? {
              ...prev,
              status: 'running',
              currentStageIndex: fromIdx,
              progressPercent: Math.round((fromIdx / prev.modules.length) * 100),
              error: null,
              modules: resetMods,
            }
          : prev
      );

      const start = Date.now();
      if (pipelineTimerRef.current) clearInterval(pipelineTimerRef.current);
      pipelineTimerRef.current = setInterval(() => {
        setActivePipelineRun((prev) => {
          if (!prev || prev.status !== 'running') return prev;
          return { ...prev, elapsedSeconds: (Date.now() - start) / 1000 };
        });
      }, 100);

      try {
        const res = await dataSourceApi.rerunFromStep(
          indexId,
          fromStep,
          activePipelineRun.model,
          activePipelineRun.batchSize
        );
        if (pipelineTimerRef.current) clearInterval(pipelineTimerRef.current);

        const idxData = res.index || {};
        const finalElapsed = idxData.duration_seconds || (Date.now() - start) / 1000;
        const chunkCount = idxData.document_count || activePipelineRun.chunkCount || 0;

        setActivePipelineRun((prev) => {
          if (!prev) return prev;
          const doneMods = prev.modules.map((m) => ({
            ...m,
            status: 'done' as const,
            durationSeconds: m.durationSeconds || 1.0,
          }));
          doneMods[doneMods.length - 1].sublogs.push({
            time: new Date().toLocaleTimeString('ko-KR', { hour12: false }),
            msg: `🚀 재실행 완료 — ${chunkCount}개 청크 pgvector 저장 완료`,
            status: 'done',
          });
          return {
            ...prev,
            status: 'completed',
            currentStageIndex: prev.modules.length - 1,
            progressPercent: 100,
            elapsedSeconds: finalElapsed,
            chunkCount,
            modules: doneMods,
          };
        });
        fetchData();
      } catch (err: any) {
        if (pipelineTimerRef.current) clearInterval(pipelineTimerRef.current);
        setActivePipelineRun((prev) => {
          if (!prev) return prev;
          const failedMods = prev.modules.map((m) => ({
            ...m,
            status: (m.status === 'running' ? 'failed' : m.status) as any,
          }));
          return { ...prev, status: 'failed', error: err.message || '재실행 실패', modules: failedMods };
        });
      }
    };

    return (
      <div className="ds-page">
        <PipelineTrackerView
          pipeline={activePipelineRun}
          onBack={() => {
            setIsViewingTracker(false);
            fetchData();
          }}
          onRefresh={fetchData}
          onRerunFromStep={handleRerunFromStep}
        />
      </div>
    );
  }

  return (
    <div className="ds-page">
      {/* Summary KPI Cards */}
      <DataSourcesSummary indexes={indexes} dbStatus={dbStatus} />

      {error && <div className="ds-error-alert">{error}</div>}

      {/* Main Content Pane */}
      {isLoading ? (
        <div className="ds-loading-pane">
          <Loader2 className="ds-spin" size={32} />
          <span>pgvector 데이터베이스 동기화 중...</span>
        </div>
      ) : (
        <div className="ds-tab-content">
          <VectorIndexList
            indexes={indexes}
            isLoading={isLoading}
            activeRunningPipeline={activePipelineRun}
            failedRuns={failedRuns}
            onResumePipeline={() => setIsViewingTracker(true)}
            onViewFailedLog={handleViewFailedRunLog}
            onDismissFailedRun={handleDismissFailedRun}
            onRefresh={fetchData}
            onDetailClick={(id) => setDetailIndexId(id)}
            onSearchClick={(idx) => setSearchTargetIndex(idx)}
            onDeleteClick={handleDeleteIndex}
            onCreateClick={() => setIsUploadOpen(true)}
            onPipelineLogClick={async (idx) => {
              const built = buildCompletedPipelineFromIndex(idx);
              setActivePipelineRun(built);
              setIsViewingTracker(true);
              try {
                const detail = await dataSourceApi.getIndexDetail(idx.index_id);
                if (detail.luna_output || (detail.tables && detail.tables.length > 0)) {
                  setActivePipelineRun((prev) =>
                    prev
                      ? {
                          ...prev,
                          lunaOutput: detail.luna_output || {
                            file_name: detail.file_name,
                            workbook_hash: detail.workbook_hash,
                            sheet_names: detail.sheet_names || ['Key_Stats', 'Income_Statement', 'Balance_Sheet', 'Cash_Flow'],
                            tables: detail.tables || [],
                          },
                        }
                      : null
                  );
                }
              } catch (err) {
                console.warn('Failed to load real luna_output from DB:', err);
              }
            }}
          />
        </div>
      )}

      {/* Modals */}
      {isUploadOpen && (
        <FileUploadModal
          onClose={() => setIsUploadOpen(false)}
          onSuccess={() => {
            fetchData();
          }}
          onStartPipeline={(file, model, batchSize) => {
            handleStartUploadPipeline(file, model, batchSize);
          }}
        />
      )}

      {detailIndexId && (
        <IndexDetailModal
          indexId={detailIndexId}
          onClose={() => setDetailIndexId(null)}
        />
      )}

      {searchTargetIndex && (
        <IndexSearchTester
          indexId={searchTargetIndex.index_id}
          fileName={searchTargetIndex.file_name}
          model={searchTargetIndex.model}
          onClose={() => setSearchTargetIndex(null)}
        />
      )}
    </div>
  );
}
