import { useState } from 'react';
import {
  CheckCircle2,
  Database,
  Layers,
  Loader2,
  Play,
  Settings2,
  Sparkles,
  X,
} from 'lucide-react';
import { dataSourceApi } from '../services/dataSourceApi';
import type { DataSourceFile, VectorIndexInfo } from '../types';

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
    id: 'BAAI/bge-large-en-v1.5',
    name: 'BAAI/bge-large-en-v1.5',
    dimension: 1024,
    badge: '로컬 모델',
    description: '1024차원 오픈소스 로컬 임베딩. API 비용 없음',
  },
];

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
  const [error, setError] = useState<string | null>(null);
  const [stepMessage, setStepMessage] = useState<string>('');

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
    setStepMessage('엑셀 표 구조를 분석하고 셀 텍스트를 직렬화하는 중...');

    try {
      // Small simulated step feedback
      setTimeout(() => {
        setStepMessage('고차원 벡터 임베딩 생성 및 배치 연산 수행 중...');
      }, 1200);

      const newIndex = await dataSourceApi.ingestWorkbook({
        file_name: selectedFile,
        model,
        variant_mode: variantMode,
        structure_mode: structureMode,
        sheet_names: selectedSheets,
        batch_size: batchSize,
      });

      onSuccess(newIndex);
      onClose();
    } catch (err: any) {
      setError(err.message || '벡터 인덱싱에 실패했습니다.');
      setIsIngesting(false);
    }
  };

  return (
    <div className="ds-modal-backdrop" onClick={onClose}>
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
          <button className="ds-modal__close" onClick={onClose} aria-label="닫기" disabled={isIngesting}>
            <X size={18} />
          </button>
        </header>

        <div className="ds-modal__body">
          {error && <div className="ds-error-alert">{error}</div>}

          {isIngesting ? (
            <div className="ds-ingesting-state">
              <div className="ds-ingesting-spinner">
                <Loader2 className="ds-spin" size={44} />
              </div>
              <h4>인덱싱 파이프라인이 실행 중입니다</h4>
              <p>{stepMessage}</p>
              <div className="ds-ingesting-steps">
                <div className="ds-step is-done">
                  <CheckCircle2 size={16} /> <span>엑셀 데이터 로드</span>
                </div>
                <div className="ds-step is-active">
                  <Loader2 size={16} className="ds-spin" /> <span>Luna VLM / 4필드 직렬화</span>
                </div>
                <div className="ds-step">
                  <Layers size={16} /> <span>배치 임베딩 생성</span>
                </div>
                <div className="ds-step">
                  <Database size={16} /> <span>Vector DB 적재</span>
                </div>
              </div>
            </div>
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
                        <option value={32}>32</option>
                        <option value={64}>64 (기본값)</option>
                        <option value={128}>128</option>
                        <option value={256}>256</option>
                      </select>
                    </div>
                  </div>
                </div>
              </details>
            </div>
          )}
        </div>

        <footer className="ds-modal__footer">
          <button
            type="button"
            className="secondary-button"
            onClick={onClose}
            disabled={isIngesting}
          >
            취소
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={handleStartIngest}
            disabled={isIngesting || !selectedFile || selectedSheets.length === 0}
          >
            <Play size={15} fill="currentColor" /> 인덱싱 시작
          </button>
        </footer>
      </div>
    </div>
  );
}
