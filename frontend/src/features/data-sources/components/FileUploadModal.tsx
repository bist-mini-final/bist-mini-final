import { useState, useRef, useEffect, type DragEvent, type ChangeEvent } from 'react';
import {
  CheckCircle2,
  CloudUpload,
  Database,
  FileCheck2,
  Layers,
  Loader2,
  Sparkles,
  UploadCloud,
  X,
  Zap,
} from 'lucide-react';
import { dataSourceApi } from '../services/dataSourceApi';
import type { DataSourceFile } from '../types';
import { ModulePipelineMonitor, type ModuleStepState } from './ModulePipelineMonitor';

interface UploadProps {
  onClose: () => void;
  onSuccess: (uploaded: DataSourceFile) => void;
  onStartPipeline?: (file: File, model: string, batchSize: number) => void;
}

type IngestionPhase = 'idle' | 'ingesting' | 'success';

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

export function FileUploadModal({ onClose, onSuccess, onStartPipeline }: UploadProps) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<IngestionPhase>('idle');
  const [currentStageIndex, setCurrentStageIndex] = useState(0);
  const [progressPercent, setProgressPercent] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [resultData, setResultData] = useState<any>(null);
  const [selectedModel, setSelectedModel] = useState('text-embedding-3-large');
  const [batchSize, setBatchSize] = useState(64);

  const [modules, setModules] = useState<ModuleStepState[]>(() =>
    createInitialModules('text-embedding-3-large', 64)
  );

  const fileInputRef = useRef<HTMLInputElement>(null);
  const timerRef = useRef<any>(null);

  // Timer loop during ingesting
  useEffect(() => {
    if (phase === 'ingesting') {
      const start = Date.now();
      timerRef.current = setInterval(() => {
        setElapsedSeconds((Date.now() - start) / 1000);
      }, 100);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [phase]);

  const handleDrag = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setSelectedFile(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const formatNow = () => {
    const now = new Date();
    return `${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}.${String(Math.floor(now.getMilliseconds() / 100))}`;
  };

  const handleStartIngest = async () => {
    if (!selectedFile) return;

    if (onStartPipeline) {
      onStartPipeline(selectedFile, selectedModel, batchSize);
      return;
    }

    setPhase('ingesting');
    setError(null);
    setCurrentStageIndex(0);
    setProgressPercent(15);

    const initialMods = createInitialModules(selectedModel, batchSize);
    initialMods[0].status = 'running';
    initialMods[0].sublogs = [
      { time: formatNow(), msg: `📂 엑셀 워크북 파일 로드: "${selectedFile.name}" (${(selectedFile.size / 1024).toFixed(1)} KB)`, status: 'running' },
      { time: formatNow(), msg: `👁️ Luna VLM: 다차원 표 영역 바운딩 박스 및 복합 계층 헤더 감지 시작...`, status: 'running' },
    ];
    setModules(initialMods);

    // Heartbeat: adds a "still working" log every 15s without touching stage state.
    // Stage transitions happen ONLY when the real API response arrives.
    let pulseCount = 0;
    const elapsedRef = { current: 0 };
    const elapsedTick = setInterval(() => { elapsedRef.current += 0.1; }, 100);
    const pulseTimer = setInterval(() => {
      pulseCount += 1;
      setModules((prev) => {
        const next = prev.map((m) => ({ ...m }));
        const activeIdx = currentStageIndex;
        if (next[activeIdx] && next[activeIdx].status === 'running') {
          next[activeIdx] = {
            ...next[activeIdx],
            sublogs: [
              ...next[activeIdx].sublogs,
              {
                time: formatNow(),
                msg: `⏳ 백엔드 처리 중... (${Math.round(elapsedRef.current)}초 경과, 대기 ${pulseCount * 15}s)`,
                status: 'running' as const,
              },
            ],
          };
        }
        return next;
      });
    }, 15000);

    try {
      const uploadRes = await dataSourceApi.uploadFile(selectedFile, true, selectedModel, batchSize);
      clearInterval(pulseTimer);
      clearInterval(elapsedTick);

      if (uploadRes.error) {
        throw new Error(uploadRes.error);
      }

      const idxData = uploadRes.ingested_index || {};
      const chunkCount = idxData.document_count || 0;
      const usedPipeline: string = idxData.used_pipeline || 'exhaustive';
      const lunaWasUsed = usedPipeline === 'luna_vlm_structured';
      const sheetCount = idxData.sheet_names?.length || idxData.sheets?.length || 1;

      setCurrentStageIndex(3);
      setProgressPercent(100);

      setModules((prev) => {
        const next = prev.map((m) => ({
          ...m,
          status: 'done' as const,
          durationSeconds: m.durationSeconds || 1.0,
        }));
        next[0].sublogs.push({
          time: formatNow(),
          msg: `📐 Luna VLM ${lunaWasUsed ? '✅ 성공 — 표 바운딩 박스 및 헤더 계층 추출 완료' : '⚠️ 폴백 — Exhaustive 직렬화로 처리'}`,
          status: 'done',
        });
        next[2].sublogs.push({
          time: formatNow(),
          msg: `💾 전체 임베딩 완료 — 총 ${chunkCount}개 3072D 벡터 생성`,
          status: 'done',
        });
        next[3].sublogs.push({
          time: formatNow(),
          msg: `🚀 PostgreSQL 16 pgvector HNSW 인덱스 동기화 완료! (${chunkCount}개 청크, ${sheetCount}개 시트)`,
          status: 'done',
        });
        return next;
      });

      setResultData(uploadRes.file);
      setPhase('success');
      onSuccess(uploadRes.file);
    } catch (err: any) {
      clearInterval(pulseTimer);
      clearInterval(elapsedTick);
      setError(err.message || '인덱싱 파이프라인 처리 중 오류가 발생했습니다.');
      setPhase('idle');
    }
  };

  return (
    <div className="ds-modal-backdrop" onClick={phase === 'ingesting' ? undefined : onClose}>
      <div
        className="ds-modal ds-modal--large"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="upload-title"
      >
        <header className="ds-modal__header">
          <div className="ds-modal__title-wrap">
            <span className="ds-modal__icon ds-modal__icon--green">
              <CloudUpload size={19} />
            </span>
            <div>
              <h3 id="upload-title">새 엑셀 파일 인덱싱 (pgvector 적재)</h3>
              <small>Luna VLM 표 구조 분석 & 4필드 직렬화 후 PostgreSQL pgvector로 고밀도 임베딩을 즉시 적재합니다</small>
            </div>
          </div>
          {phase !== 'ingesting' && (
            <button className="ds-modal__close" onClick={onClose} aria-label="닫기">
              <X size={18} />
            </button>
          )}
        </header>

        <div className="ds-modal__body">
          {/* Phase 1: Idle (Dropzone + Parameters) */}
          {phase === 'idle' && (
            <div className="ds-upload-config-stack">
              <div
                className={`ds-dropzone ${dragActive ? 'is-active' : ''}`}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xlsx,.xlsm"
                  style={{ display: 'none' }}
                  onChange={handleChange}
                />
                {selectedFile ? (
                  <div className="ds-dropzone__selected">
                    <FileCheck2 size={36} className="ds-icon-success" />
                    <strong>{selectedFile.name}</strong>
                    <small>{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</small>
                    <span>다른 엑셀 파일을 선택하려면 클릭하거나 드래그하세요</span>
                  </div>
                ) : (
                  <div className="ds-dropzone__prompt">
                    <UploadCloud size={38} />
                    <strong>클릭하거나 엑셀 파일을 여기로 끌어다 놓으세요</strong>
                    <small>지원 형식: .xlsx, .xlsm (최대 500MB)</small>
                  </div>
                )}
              </div>

              {/* Ingestion Parameters */}
              <div
                style={{
                  marginTop: '1rem',
                  display: 'grid',
                  gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                  gap: '0.85rem',
                  background: '#f8fafc',
                  padding: '0.85rem',
                  borderRadius: '8px',
                  border: '1px solid #e2e8f0',
                }}
              >
                <div>
                  <label style={{ display: 'block', fontSize: '0.72rem', fontWeight: 650, color: '#475569', marginBottom: '0.3rem' }}>
                    임베딩 모델
                  </label>
                  <select
                    className="ds-select"
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                    style={{ width: '100%', fontSize: '0.8rem', padding: '0.4rem 0.6rem' }}
                  >
                    <option value="text-embedding-3-large">OpenAI text-embedding-3-large (3072D)</option>
                    <option value="text-embedding-3-small">OpenAI text-embedding-3-small (1536D)</option>
                    <option value="BAAI/bge-m3">BAAI/bge-m3 (1024D · Local OpenSource)</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.72rem', fontWeight: 650, color: '#475569', marginBottom: '0.3rem' }}>
                    임베딩 배치 크기 (Batch Size)
                  </label>
                  <select
                    className="ds-select"
                    value={batchSize}
                    onChange={(e) => setBatchSize(Number(e.target.value))}
                    style={{ width: '100%', fontSize: '0.8rem', padding: '0.4rem 0.6rem' }}
                  >
                    <option value={64}>64개 / 요청 (표준)</option>
                    <option value={128}>128개 / 요청 (빠름)</option>
                    <option value={256}>256개 / 요청 (대용량 최적화)</option>
                  </select>
                </div>
              </div>

              {error && <div className="ds-error-alert" style={{ marginTop: '0.85rem' }}>{error}</div>}
            </div>
          )}

          {/* Phase 2: Module-Centric Live Pipeline Monitor */}
          {phase === 'ingesting' && (
            <ModulePipelineMonitor
              fileName={selectedFile?.name || 'Excel File'}
              model={selectedModel}
              batchSize={batchSize}
              elapsedSeconds={elapsedSeconds}
              currentStageIndex={currentStageIndex}
              progressPercent={progressPercent}
              modules={modules}
            />
          )}

          {/* Phase 3: Success Result Summary */}
          {phase === 'success' && (
            <div className="ds-success-card">
              <span className="ds-success-badge">
                <CheckCircle2 size={32} />
              </span>
              <div>
                <h4 style={{ margin: 0, fontSize: '1.2rem', color: '#0f172a', fontWeight: 750 }}>
                  모듈 파이프라인 pgvector 인덱싱 적재 완료!
                </h4>
                <p style={{ margin: '0.35rem 0 0', color: '#64748b', fontSize: '0.82rem' }}>
                  <strong>{resultData?.file_name || selectedFile?.name}</strong>의 표 구조화 및 고밀도 임베딩이 PostgreSQL 16 pgvector에 영구 적재되었습니다.
                </p>
              </div>

              <div className="ds-success-metrics-grid">
                <div className="ds-success-metric-box">
                  <small>인덱싱 소요 시간</small>
                  <strong>{elapsedSeconds.toFixed(1)}초</strong>
                </div>
                <div className="ds-success-metric-box">
                  <small>적재 스토리지</small>
                  <strong style={{ color: '#15803d' }}>pgvector</strong>
                </div>
                <div className="ds-success-metric-box">
                  <small>임베딩 모델</small>
                  <strong style={{ fontSize: '0.8rem', color: '#1e40af' }}>{selectedModel.replace('text-embedding-', '')}</strong>
                </div>
                <div className="ds-success-metric-box">
                  <small>인덱스 상태</small>
                  <strong style={{ color: '#2563eb' }}>LIVE READY</strong>
                </div>
              </div>
            </div>
          )}
        </div>

        <footer className="ds-modal__footer">
          {phase === 'idle' && (
            <>
              <button type="button" className="secondary-button" onClick={onClose}>
                취소
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={handleStartIngest}
                disabled={!selectedFile}
              >
                <Zap size={15} />
                <span>인덱싱 시작</span>
              </button>
            </>
          )}

          {phase === 'ingesting' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#0f766e', fontSize: '0.8rem', fontWeight: 600 }}>
              <Loader2 size={16} className="ds-spin" />
              <span>각 파이프라인 모듈 카드를 클릭하면 세부 실행 로그를 확인할 수 있습니다.</span>
            </div>
          )}

          {phase === 'success' && (
            <button
              type="button"
              className="primary-button"
              style={{ width: '100%' }}
              onClick={onClose}
            >
              <span>데이터 소스 목록 확인</span>
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
