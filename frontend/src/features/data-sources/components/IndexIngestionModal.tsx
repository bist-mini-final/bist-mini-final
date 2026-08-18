import { useState, useRef, useEffect } from 'react';
import {
  Database,
  Layers,
  Play,
  Settings2,
  Sparkles,
  X,
  Zap,
} from 'lucide-react';
import { dataSourceApi } from '../services/dataSourceApi';
import type { DataSourceFile, VectorIndexInfo } from '../types';
import { ModulePipelineMonitor, type ModuleStepState } from './ModulePipelineMonitor';

interface IngestModalProps {
  files: DataSourceFile[];
  initialFileName?: string;
  onClose: () => void;
  onSuccess: (index: VectorIndexInfo) => void;
}

const EMBEDDING_MODELS = [
  {
    id: 'text-embedding-3-large',
    name: 'OpenAI text-embedding-3-large',
    dimension: 3072,
    badge: '추천 (고정밀)',
    description: '3072차원 고정밀 임베딩. 질의-테이블 복합 검색 성능 우수',
  },
  {
    id: 'text-embedding-3-small',
    name: 'OpenAI text-embedding-3-small',
    dimension: 1536,
    badge: '경량 모델',
    description: '1536차원 경량 임베딩. 경제적인 API 비용',
  },
  {
    id: 'BAAI/bge-m3',
    name: 'BAAI/bge-m3 (로컬 모델)',
    dimension: 1024,
    badge: '오픈소스',
    description: '1024차원 로컬 임베딩. API 비용 없음',
  },
];

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

export function IndexIngestionModal({
  files,
  initialFileName,
  onClose,
  onSuccess,
}: IngestModalProps) {
  const excelFiles = files.filter((f) => f.file_type === 'excel');
  const [selectedFile, setSelectedFile] = useState<string>(
    initialFileName || (excelFiles[0]?.file_name ?? '')
  );
  const currentFileObj = excelFiles.find((f) => f.file_name === selectedFile);

  const [selectedSheets, setSelectedSheets] = useState<string[]>(
    () => currentFileObj?.sheet_names || []
  );
  const [model, setModel] = useState<string>('text-embedding-3-large');
  const [variantMode, setVariantMode] = useState<'header_only' | 'header_with_value' | 'both'>(
    'header_only'
  );
  const [structureMode, setStructureMode] = useState<'auto' | 'luna_vlm' | 'exhaustive'>('auto');
  const [batchSize, setBatchSize] = useState<number>(64);

  const [isIngesting, setIsIngesting] = useState(false);
  const [currentStageIndex, setCurrentStageIndex] = useState(0);
  const [progressPercent, setProgressPercent] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const [modules, setModules] = useState<ModuleStepState[]>(() =>
    createInitialModules('text-embedding-3-large', 64)
  );

  const timerRef = useRef<any>(null);

  useEffect(() => {
    if (isIngesting) {
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
  }, [isIngesting]);

  useEffect(() => {
    if (initialFileName) {
      setSelectedFile(initialFileName);
      const found = excelFiles.find((f) => f.file_name === initialFileName);
      if (found) {
        setSelectedSheets([...found.sheet_names]);
      }
    }
  }, [initialFileName]);

  const handleFileChange = (newFileName: string) => {
    setSelectedFile(newFileName);
    const found = excelFiles.find((f) => f.file_name === newFileName);
    setSelectedSheets(found?.sheet_names || []);
  };

  const toggleSheet = (sheetName: string) => {
    setSelectedSheets((prev) =>
      prev.includes(sheetName) ? prev.filter((s) => s !== sheetName) : [...prev, sheetName]
    );
  };

  const handleSelectAllSheets = () => {
    if (currentFileObj) {
      setSelectedSheets([...currentFileObj.sheet_names]);
    }
  };

  const formatNow = () => {
    const now = new Date();
    return `${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}.${String(Math.floor(now.getMilliseconds() / 100))}`;
  };

  const handleStartIngest = async () => {
    if (!selectedFile) {
      setError('인덱싱할 대상 엑셀 파일을 선택하세요.');
      return;
    }
    if (selectedSheets.length === 0) {
      setError('최소 1개 이상의 시트를 선택해야 합니다.');
      return;
    }

    setIsIngesting(true);
    setError(null);
    setCurrentStageIndex(0);
    setProgressPercent(15);

    const initialMods = createInitialModules(model, batchSize);
    initialMods[0].status = 'running';
    initialMods[0].sublogs = [
      { time: formatNow(), msg: `📂 엑셀 파일 로드: "${selectedFile}" (${selectedSheets.length}개 시트 선택)`, status: 'running' },
      { time: formatNow(), msg: `👁️ Luna VLM: [${selectedSheets.join(', ')}] 시트 표 바운딩 박스 & 헤더 계층 추출 시작...`, status: 'running' },
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
        const runningIdx = next.findIndex((m) => m.status === 'running');
        const activeIdx = runningIdx >= 0 ? runningIdx : next.length - 1;
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
        return next;
      });
    }, 15000);

    try {
      const newIndex = await dataSourceApi.ingestWorkbook({
        file_name: selectedFile,
        model,
        variant_mode: variantMode,
        structure_mode: structureMode,
        sheet_names: selectedSheets,
        batch_size: batchSize,
      });

      clearInterval(pulseTimer);
      clearInterval(elapsedTick);

      const chunkCount = newIndex.document_count || 0;
      const usedPipeline: string = (newIndex as any).used_pipeline || 'exhaustive';
      const lunaWasUsed = usedPipeline === 'luna_vlm_structured';
      const sheetCount = selectedSheets.length;

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

      setTimeout(() => {
        onSuccess(newIndex);
        onClose();
      }, 700);
    } catch (err: any) {
      clearInterval(pulseTimer);
      clearInterval(elapsedTick);
      setError(err.message || '벡터 인덱싱에 실패했습니다.');
      setIsIngesting(false);
    }
  };

  return (
    <div className="ds-modal-backdrop" onClick={isIngesting ? undefined : onClose}>
      <div
        className="ds-modal ds-modal--large"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="ingest-title"
      >
        <header className="ds-modal__header">
          <div className="ds-modal__title-wrap">
            <span className="ds-modal__icon ds-modal__icon--green">
              <Database size={19} />
            </span>
            <div>
              <h3 id="ingest-title">엑셀 → 벡터 DB 원클릭 인덱싱</h3>
              <small>표 구조 분석부터 임베딩과 영속 벡터 인덱스 적재까지 자동 수행</small>
            </div>
          </div>
          {!isIngesting && (
            <button className="ds-modal__close" onClick={onClose} aria-label="닫기">
              <X size={18} />
            </button>
          )}
        </header>

        <div className="ds-modal__body">
          {error && <div className="ds-error-alert">{error}</div>}

          {isIngesting ? (
            <ModulePipelineMonitor
              fileName={selectedFile}
              model={model}
              batchSize={batchSize}
              elapsedSeconds={elapsedSeconds}
              currentStageIndex={currentStageIndex}
              progressPercent={progressPercent}
              modules={modules}
            />
          ) : (
            <div className="ds-form-stack">
              {/* 1. File Selection */}
              <div className="ds-form-group">
                <label className="ds-form-label">
                  <span>대상 엑셀 파일</span>
                </label>
                <select
                  className="ds-select"
                  value={selectedFile}
                  onChange={(e) => handleFileChange(e.target.value)}
                >
                  {excelFiles.map((f) => (
                    <option key={f.file_name} value={f.file_name}>
                      {f.file_name} ({f.sheet_names.length}개 시트)
                    </option>
                  ))}
                </select>
              </div>

              {/* 2. Sheet Selection */}
              {currentFileObj && currentFileObj.sheet_names.length > 0 && (
                <div className="ds-form-group">
                  <div className="ds-form-label-row">
                    <label className="ds-form-label">
                      <span>인덱싱 대상 시트 ({selectedSheets.length}/{currentFileObj.sheet_names.length} 선택)</span>
                    </label>
                    <button
                      type="button"
                      className="ds-text-btn"
                      onClick={handleSelectAllSheets}
                    >
                      전체 선택
                    </button>
                  </div>
                  <div className="ds-chip-group">
                    {currentFileObj.sheet_names.map((sheet) => {
                      const isChecked = selectedSheets.includes(sheet);
                      return (
                        <button
                          key={sheet}
                          type="button"
                          className={`ds-chip ${isChecked ? 'is-selected' : ''}`}
                          onClick={() => toggleSheet(sheet)}
                        >
                          <span className="ds-chip__dot" />
                          <span>{sheet}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* 3. Embedding Model Selection */}
              <div className="ds-form-group">
                <label className="ds-form-label">
                  <Sparkles size={15} /> <span>임베딩 모델 선택</span>
                </label>
                <div className="ds-model-selector">
                  {EMBEDDING_MODELS.map((m) => (
                    <label
                      key={m.id}
                      className={`ds-model-option ${model === m.id ? 'is-selected' : ''}`}
                    >
                      <input
                        type="radio"
                        name="embedding-model"
                        value={m.id}
                        checked={model === m.id}
                        onChange={(e) => setModel(e.target.value)}
                      />
                      <div className="ds-model-option__body">
                        <div className="ds-model-option__header">
                          <strong>{m.name}</strong>
                          <span className="ds-badge ds-badge--green">{m.badge}</span>
                        </div>
                        <p>{m.description}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              {/* 4. Advanced Ingestion Options */}
              <details className="ds-advanced-details" open>
                <summary className="ds-advanced-summary">
                  <Settings2 size={15} /> 구조화 및 직렬화 설정
                </summary>
                <div className="ds-advanced-body">
                  <div className="ds-form-row">
                    <div className="ds-form-group">
                      <label className="ds-form-label">구조화 모드</label>
                      <select
                        className="ds-select"
                        value={structureMode}
                        onChange={(e) => setStructureMode(e.target.value as any)}
                      >
                        <option value="auto">Luna VLM 자동 구조화 (권장 / indexing_prebuilt)</option>
                        <option value="exhaustive">전수 셀 직렬화 (빠른 모드)</option>
                      </select>
                    </div>
                    <div className="ds-form-group">
                      <label className="ds-form-label">직렬화 형태</label>
                      <select
                        className="ds-select"
                        value={variantMode}
                        onChange={(e) => setVariantMode(e.target.value as any)}
                      >
                        <option value="header_only">Header Only (질의 검색 표준 - 추천)</option>
                        <option value="header_with_value">Header with Value (값 포함)</option>
                        <option value="both">Both (헤더 및 값 조합 생성)</option>
                      </select>
                    </div>
                  </div>
                  <div className="ds-form-row" style={{ marginTop: '0.6rem' }}>
                    <div className="ds-form-group">
                      <label className="ds-form-label">배치 크기</label>
                      <select
                        className="ds-select"
                        value={batchSize}
                        onChange={(e) => setBatchSize(Number(e.target.value))}
                      >
                        <option value={32}>32개 / 요청</option>
                        <option value={64}>64개 / 요청 (표준)</option>
                        <option value={128}>128개 / 요청 (빠름)</option>
                        <option value={256}>256개 / 요청 (대용량)</option>
                      </select>
                    </div>
                  </div>
                </div>
              </details>
            </div>
          )}
        </div>

        <footer className="ds-modal__footer">
          {isIngesting ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#0f766e', fontSize: '0.8rem', fontWeight: 600 }}>
              <span>각 파이프라인 모듈 카드를 클릭하면 세부 실행 로그를 확인할 수 있습니다.</span>
            </div>
          ) : (
            <>
              <button
                type="button"
                className="secondary-button"
                onClick={onClose}
              >
                취소
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={handleStartIngest}
                disabled={!selectedFile || selectedSheets.length === 0}
              >
                <Play size={15} fill="currentColor" /> 인덱싱 시작
              </button>
            </>
          )}
        </footer>
      </div>
    </div>
  );
}
