import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { CloudUpload, FileCheck2, UploadCloud, X, Zap } from 'lucide-react';

interface UploadProps {
  onClose: () => void;
  onStartPipeline: (
    file: File,
    model: string,
    batchSize: number,
  ) => void | Promise<void>;
}

const MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024;
const SUPPORTED_EXTENSIONS = ['.xlsx', '.xlsm'];

/**
 * Validates a workbook's file format and size.
 *
 * @param file - The workbook file to validate
 * @returns An error message for an unsupported format or oversized file, or `null` when the file is valid
 */
function validateWorkbook(file: File): string | null {
  const lowerName = file.name.toLowerCase();
  if (!SUPPORTED_EXTENSIONS.some((extension) => lowerName.endsWith(extension))) {
    return '지원 형식은 .xlsx와 .xlsm입니다.';
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return '파일 크기는 500MB를 초과할 수 없습니다.';
  }
  return null;
}

/**
 * Displays a modal for selecting and configuring an Excel workbook for indexing.
 *
 * @param onClose - Called when the modal is closed or cancelled
 * @param onStartPipeline - Called with the selected workbook and indexing configuration
 */
export function FileUploadModal({ onClose, onStartPipeline }: UploadProps) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedModel, setSelectedModel] = useState('text-embedding-3-large');
  const [batchSize, setBatchSize] = useState(2048);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectFile = (file: File) => {
    const validationError = validateWorkbook(file);
    setError(validationError);
    setSelectedFile(validationError ? null : file);
  };

  const handleDrag = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setDragActive(event.type === 'dragenter' || event.type === 'dragover');
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setDragActive(false);
    const file = event.dataTransfer.files[0];
    if (file) selectFile(file);
  };

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) selectFile(file);
  };

  const handleStart = () => {
    if (!selectedFile) return;
    void onStartPipeline(selectedFile, selectedModel, batchSize);
  };

  return (
    <div className="ds-modal-backdrop" onClick={onClose}>
      <div
        className="ds-modal ds-modal--large"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-labelledby="upload-title"
      >
        <header className="ds-modal__header">
          <div className="ds-modal__title-wrap">
            <span className="ds-modal__icon ds-modal__icon--green">
              <CloudUpload size={19} />
            </span>
            <div>
              <h3 id="upload-title">새 엑셀 파일 인덱싱</h3>
              <small>업로드 후 서버 워크플로 큐에서 모듈 조합을 실행합니다.</small>
            </div>
          </div>
          <button className="ds-modal__close" onClick={onClose} aria-label="닫기">
            <X size={18} />
          </button>
        </header>

        <div className="ds-modal__body">
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
                hidden
                onChange={handleChange}
              />
              {selectedFile ? (
                <div className="ds-dropzone__selected">
                  <FileCheck2 size={36} className="ds-icon-success" />
                  <strong>{selectedFile.name}</strong>
                  <small>{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</small>
                  <span>다른 파일을 선택하려면 클릭하거나 드래그하세요.</span>
                </div>
              ) : (
                <div className="ds-dropzone__prompt">
                  <UploadCloud size={38} />
                  <strong>엑셀 파일을 선택하거나 여기로 끌어다 놓으세요.</strong>
                  <small>.xlsx, .xlsm · 최대 500MB</small>
                </div>
              )}
            </div>

            <div className="ds-upload-options">
              <label>
                <span>임베딩 모델</span>
                <select
                  className="ds-select"
                  value={selectedModel}
                  onChange={(event) => setSelectedModel(event.target.value)}
                >
                  <option value="text-embedding-3-large">OpenAI text-embedding-3-large (3072D)</option>
                  <option value="text-embedding-3-small">OpenAI text-embedding-3-small (1536D)</option>
                  <option value="BAAI/bge-m3">BAAI/bge-m3 (1024D · Local)</option>
                </select>
              </label>
              <label>
                <span>임베딩 배치 크기</span>
                <select
                  className="ds-select"
                  value={batchSize}
                  onChange={(event) => setBatchSize(Number(event.target.value))}
                >
                  {[128, 256, 512, 1024, 2048].map((size) => (
                    <option key={size} value={size}>{size}개 / 요청</option>
                  ))}
                </select>
              </label>
            </div>

            {error && <div className="ds-error-alert">{error}</div>}
          </div>
        </div>

        <footer className="ds-modal__footer">
          <button type="button" className="secondary-button" onClick={onClose}>
            취소
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={handleStart}
            disabled={!selectedFile}
          >
            <Zap size={15} /> 인덱싱 시작
          </button>
        </footer>
      </div>
    </div>
  );
}
