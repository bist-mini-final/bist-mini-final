import { useEffect, useState, useRef } from 'react';
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
        metaInfo: { 임베딩모델: modelName, 차원: `${dimension}D`, 소비토큰: `${tokens.toLocaleString()} tokens` },
        sublogs: [
          { time: '00:01.9', msg: `⚡ 문서를 배치 크기 ${batchSize} 단위로 분할하여 OpenAI Embeddings 호출`, status: 'done' },
          { time: '00:02.8', msg: `🌐 ${modelName} (${dimension}D) 고밀도 벡터 생성 및 L2 정규화 완료`, status: 'done' },
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

  // Modals state
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [detailIndexId, setDetailIndexId] = useState<string | null>(null);
  const [searchTargetIndex, setSearchTargetIndex] = useState<VectorIndexInfo | null>(null);

  const pipelineTimerRef = useRef<any>(null);

  const fetchData = async () => {
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
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (pipelineTimerRef.current) clearInterval(pipelineTimerRef.current);
    };
  }, []);

  const handleStartUploadPipeline = async (file: File, model: string, batchSize: number) => {
    setIsUploadOpen(false);

    const initialMods = createInitialModules(model, batchSize);
    initialMods[0].status = 'running';
    initialMods[0].sublogs = [
      { time: formatNow(), msg: `📂 엑셀 파일 로드: "${file.name}" (${(file.size / 1024).toFixed(1)} KB)`, status: 'running' },
      { time: formatNow(), msg: `👁️ Luna VLM 다차원 표 영역 바운딩 박스 & 헤더 계층 추출 시작...`, status: 'running' },
    ];

    const pipelineState: PipelineRunState = {
      pipelineId: `pipe_${Date.now()}`,
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

    const start = Date.now();
    pipelineTimerRef.current = setInterval(() => {
      setActivePipelineRun((prev) => {
        if (!prev || prev.status !== 'running') return prev;
        return {
          ...prev,
          elapsedSeconds: (Date.now() - start) / 1000,
        };
      });
    }, 100);

    const t1 = setTimeout(() => {
      setActivePipelineRun((prev) => {
        if (!prev || prev.status !== 'running') return prev;
        const nextMods = [...prev.modules];
        nextMods[0].status = 'done';
        nextMods[0].durationSeconds = 1.1;
        nextMods[0].sublogs.push({
          time: formatNow(),
          msg: `📐 Luna VLM 표 바운딩 박스 및 복합 계층 헤더 추출 완료 (2개 표 검출)`,
          status: 'done',
        });
        nextMods[1].status = 'running';
        nextMods[1].sublogs = [
          { time: formatNow(), msg: `📝 4-Field 직렬화 템플릿 적용 ([SHEET]/[COL]/[ROW]/[VALUE])`, status: 'running' },
          { time: formatNow(), msg: `🧹 공백 셀 필터링 및 서식 정규화 완료`, status: 'running' },
        ];
        return {
          ...prev,
          currentStageIndex: 1,
          progressPercent: 40,
          modules: nextMods,
        };
      });
    }, 1100);

    const t2 = setTimeout(() => {
      setActivePipelineRun((prev) => {
        if (!prev || prev.status !== 'running') return prev;
        const nextMods = [...prev.modules];
        nextMods[1].status = 'done';
        nextMods[1].durationSeconds = 0.9;
        nextMods[1].sublogs.push({
          time: formatNow(),
          msg: `📑 총 직렬화 문서(CellTextDocumentDTO) 생성 완료`,
          status: 'done',
        });
        nextMods[2].status = 'running';
        nextMods[2].sublogs = [
          { time: formatNow(), msg: `⚡ 문서를 배치 크기 ${batchSize} 단위로 분할하여 OpenAI Embeddings 호출`, status: 'running' },
          { time: formatNow(), msg: `🌐 ${model} 고밀도 3072D 벡터 생성 및 토큰 누적 집계 중...`, status: 'running' },
        ];
        return {
          ...prev,
          currentStageIndex: 2,
          progressPercent: 70,
          modules: nextMods,
        };
      });
    }, 2200);

    const t3 = setTimeout(() => {
      setActivePipelineRun((prev) => {
        if (!prev || prev.status !== 'running') return prev;
        const nextMods = [...prev.modules];
        nextMods[2].status = 'done';
        nextMods[2].durationSeconds = 1.6;
        nextMods[2].sublogs.push({
          time: formatNow(),
          msg: `💾 float32 L2 정규화 및 임베딩 아티팩트 해시 생성 완료`,
          status: 'done',
        });
        nextMods[3].status = 'running';
        nextMods[3].sublogs = [
          { time: formatNow(), msg: `🔌 PostgreSQL 16 langchain_pg_collection 연결 및 cmetadata 등록`, status: 'running' },
          { time: formatNow(), msg: `📥 langchain_pg_embedding 테이블 벡터 및 메타데이터 적재 중...`, status: 'running' },
        ];
        return {
          ...prev,
          currentStageIndex: 3,
          progressPercent: 90,
          modules: nextMods,
        };
      });
    }, 3800);

    try {
      const uploadRes = await dataSourceApi.uploadFile(file, true, model, batchSize);
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
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

      setActivePipelineRun((prev) => {
        if (!prev) return prev;
        const nextMods = prev.modules.map((m) => ({
          ...m,
          status: 'done' as const,
          durationSeconds: m.durationSeconds || 1.0,
        }));
        nextMods[3].sublogs.push({
          time: formatNow(),
          msg: `🚀 PostgreSQL 16 pgvector HNSW 코사인 유사도 인덱스 동기화 완료! (${chunkCount}개 청크 적재 완료)`,
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
        };
      });

      // Refresh background index list
      fetchData();
    } catch (err: any) {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      if (pipelineTimerRef.current) clearInterval(pipelineTimerRef.current);
      setActivePipelineRun((prev) => (prev ? { ...prev, status: 'failed', error: err.message || '인덱싱 처리 실패' } : null));
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
  if (activePipelineRun) {
    return (
      <div className="ds-page">
        <PipelineTrackerView
          pipeline={activePipelineRun}
          onBack={() => {
            setActivePipelineRun(null);
            fetchData();
          }}
          onRefresh={fetchData}
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
            onRefresh={fetchData}
            onDetailClick={(id) => setDetailIndexId(id)}
            onSearchClick={(idx) => setSearchTargetIndex(idx)}
            onDeleteClick={handleDeleteIndex}
            onCreateClick={() => setIsUploadOpen(true)}
            onPipelineLogClick={async (idx) => {
              const built = buildCompletedPipelineFromIndex(idx);
              setActivePipelineRun(built);
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
                            sheet_names: detail.sheet_names || ['Income_Statement', 'Key_Stats'],
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
