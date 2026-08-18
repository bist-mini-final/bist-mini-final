import {
  Clock,
  Database,
  Eye,
  FileSpreadsheet,
  Play,
  Trash2,
  Upload,
} from 'lucide-react';
import type { DataSourceFile } from '../types';

interface FileListProps {
  files: DataSourceFile[];
  onUploadClick: () => void;
  onPreviewClick: (fileName: string) => void;
  onIngestClick: (fileName: string) => void;
  onDeleteClick: (fileName: string) => void;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function FileList({
  files,
  onUploadClick,
  onPreviewClick,
  onIngestClick,
  onDeleteClick,
}: FileListProps) {
  return (
    <div className="ds-panel">
      <div className="ds-panel__header">
        <div>
          <h3>원시 데이터 파일 목록</h3>
          <small>data/processed/ 디렉터리에 보관된 분석 대상 원본 파일</small>
        </div>
        <button type="button" className="primary-button" onClick={onUploadClick}>
          <Upload size={15} /> 파일 업로드
        </button>
      </div>

      {files.length === 0 ? (
        <div className="ds-empty-state">
          <FileSpreadsheet size={40} />
          <h4>등록된 데이터 파일이 없습니다</h4>
          <p>분석할 Excel(.xlsx, .xlsm)이나 사전 인덱스(.parquet) 파일을 업로드하세요.</p>
          <button type="button" className="primary-button" onClick={onUploadClick}>
            <Upload size={15} /> 첫 번째 파일 업로드
          </button>
        </div>
      ) : (
        <div className="ds-table-container">
          <table className="ds-table">
            <thead>
              <tr>
                <th>파일명</th>
                <th>형식</th>
                <th>크기</th>
                <th>시트 목록</th>
                <th>수정일시</th>
                <th>인덱스 상태</th>
                <th className="ds-text-right">작업</th>
              </tr>
            </thead>
            <tbody>
              {files.map((file) => {
                const isExcel = file.file_type === 'excel';
                const hasIndexes = file.associated_index_ids.length > 0;

                return (
                  <tr key={file.file_name}>
                    <td className="ds-file-name-cell">
                      <FileSpreadsheet size={18} className="ds-icon-file" />
                      <div>
                        <strong>{file.file_name}</strong>
                        {file.workbook_hash && (
                          <small className="ds-font-mono">{file.workbook_hash.slice(0, 10)}...</small>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className={`ds-badge ds-badge--${file.file_type}`}>
                        {file.file_type.toUpperCase()}
                      </span>
                    </td>
                    <td>{formatBytes(file.size_bytes)}</td>
                    <td>
                      {isExcel && file.sheet_names.length > 0 ? (
                        <div className="ds-sheet-chips">
                          {file.sheet_names.slice(0, 3).map((s) => (
                            <span key={s} className="ds-mini-chip">
                              {s}
                            </span>
                          ))}
                          {file.sheet_names.length > 3 && (
                            <span className="ds-mini-chip ds-mini-chip--more">
                              +{file.sheet_names.length - 3}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="ds-text-muted">-</span>
                      )}
                    </td>
                    <td>
                      <span className="ds-time-text">
                        <Clock size={12} /> {formatDate(file.updated_at)}
                      </span>
                    </td>
                    <td>
                      {hasIndexes ? (
                        <span className="ds-status-badge is-ready">
                          <Database size={13} /> {file.associated_index_ids.length}개 인덱스 연결됨
                        </span>
                      ) : (
                        <span className="ds-status-badge is-unindexed">미인덱싱</span>
                      )}
                    </td>
                    <td className="ds-text-right">
                      <div className="ds-actions-row">
                        {isExcel && (
                          <>
                            <button
                              type="button"
                              className="ds-action-btn ds-action-btn--primary"
                              title="엑셀을 벡터 DB로 인덱싱"
                              onClick={() => onIngestClick(file.file_name)}
                            >
                              <Play size={14} fill="currentColor" />
                              <span>인덱싱</span>
                            </button>
                            <button
                              type="button"
                              className="ds-action-btn"
                              title="시트 데이터 미리보기"
                              onClick={() => onPreviewClick(file.file_name)}
                            >
                              <Eye size={14} />
                              <span>미리보기</span>
                            </button>
                          </>
                        )}
                        <button
                          type="button"
                          className="ds-action-btn ds-action-btn--danger"
                          title="파일 삭제"
                          onClick={() => onDeleteClick(file.file_name)}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
