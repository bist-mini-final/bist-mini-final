import { useState, useRef, type DragEvent, type ChangeEvent } from 'react';
import { CloudUpload, FileCheck2, Loader2, UploadCloud, X } from 'lucide-react';
import { dataSourceApi } from '../services/dataSourceApi';
import type { DataSourceFile } from '../types';

interface UploadProps {
  onClose: () => void;
  onSuccess: (uploaded: DataSourceFile) => void;
}

export function FileUploadModal({ onClose, onSuccess }: UploadProps) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const handleUpload = async () => {
    if (!selectedFile) return;
    setIsUploading(true);
    setError(null);
    try {
      const uploaded = await dataSourceApi.uploadFile(selectedFile);
      onSuccess(uploaded);
      onClose();
    } catch (err: any) {
      setError(err.message || '파일 업로드에 실패했습니다.');
      setIsUploading(false);
    }
  };

  return (
    <div className="ds-modal-backdrop" onClick={onClose}>
      <div
        className="ds-modal ds-modal--medium"
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
              <h3 id="upload-title">새 데이터 파일 업로드</h3>
              <small>Excel(.xlsx, .xlsm), Parquet(.parquet), JSON(.json)</small>
            </div>
          </div>
          <button className="ds-modal__close" onClick={onClose} aria-label="닫기">
            <X size={18} />
          </button>
        </header>

        <div className="ds-modal__body">
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
              accept=".xlsx,.xlsm,.parquet,.json"
              style={{ display: 'none' }}
              onChange={handleChange}
            />
            {selectedFile ? (
              <div className="ds-dropzone__selected">
                <FileCheck2 size={36} className="ds-icon-success" />
                <strong>{selectedFile.name}</strong>
                <small>{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</small>
                <span>다른 파일을 선택하려면 클릭하거나 드래그하세요</span>
              </div>
            ) : (
              <div className="ds-dropzone__prompt">
                <UploadCloud size={38} />
                <strong>클릭하거나 파일을 여기로 끌어다 놓으세요</strong>
                <small>지원 형식: .xlsx, .xlsm, .parquet, .json (최대 500MB)</small>
              </div>
            )}
          </div>

          {error && <div className="ds-error-alert">{error}</div>}
        </div>

        <footer className="ds-modal__footer">
          <button type="button" className="secondary-button" onClick={onClose} disabled={isUploading}>
            취소
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={handleUpload}
            disabled={!selectedFile || isUploading}
          >
            {isUploading ? (
              <>
                <Loader2 className="ds-spin" size={16} /> 업로드 중...
              </>
            ) : (
              '업로드 시작'
            )}
          </button>
        </footer>
      </div>
    </div>
  );
}
