import { useEffect, useState } from 'react';
import { FileSpreadsheet, Loader2, Table, X } from 'lucide-react';
import { dataSourceApi } from '../services/dataSourceApi';
import type { SheetPreviewData } from '../types';

interface PreviewProps {
  fileName: string;
  onClose: () => void;
}

export function FilePreviewModal({ fileName, onClose }: PreviewProps) {
  const [data, setData] = useState<SheetPreviewData | null>(null);
  const [selectedSheet, setSelectedSheet] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCancelled = false;
    setIsLoading(true);
    setError(null);

    dataSourceApi
      .previewSheet(fileName, selectedSheet || undefined, 20)
      .then((res) => {
        if (!isCancelled) {
          setData(res);
          if (!selectedSheet && res.sheet_name) {
            setSelectedSheet(res.sheet_name);
          }
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!isCancelled) {
          setError(err.message || '시트를 불러오지 못했습니다.');
          setIsLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [fileName, selectedSheet]);

  return (
    <div className="ds-modal-backdrop" onClick={onClose}>
      <div
        className="ds-modal ds-modal--large"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="preview-title"
      >
        <header className="ds-modal__header">
          <div className="ds-modal__title-wrap">
            <span className="ds-modal__icon ds-modal__icon--blue">
              <FileSpreadsheet size={19} />
            </span>
            <div>
              <h3 id="preview-title">{fileName}</h3>
              <small>Excel 시트 데이터 미리보기</small>
            </div>
          </div>
          <button className="ds-modal__close" onClick={onClose} aria-label="닫기">
            <X size={18} />
          </button>
        </header>

        {data && data.available_sheets.length > 0 && (
          <div className="ds-sheet-tabs">
            {data.available_sheets.map((sheet) => (
              <button
                key={sheet}
                type="button"
                className={`ds-sheet-tab ${sheet === (selectedSheet || data.sheet_name) ? 'is-active' : ''}`}
                onClick={() => setSelectedSheet(sheet)}
              >
                <Table size={14} />
                <span>{sheet}</span>
              </button>
            ))}
          </div>
        )}

        <div className="ds-modal__body">
          {isLoading && (
            <div className="ds-loading-state">
              <Loader2 className="ds-spin" size={24} />
              <span>시트 데이터를 로드하는 중...</span>
            </div>
          )}

          {error && <div className="ds-error-alert">{error}</div>}

          {!isLoading && !error && data && (
            <div className="ds-table-scroll">
              <table className="ds-preview-table">
                <tbody>
                  {data.preview_rows.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="ds-empty-cell">
                        시트에 표시할 데이터가 없습니다.
                      </td>
                    </tr>
                  ) : (
                    data.preview_rows.map((row, rIdx) => (
                      <tr key={rIdx} className={rIdx === 0 ? 'ds-row-header' : ''}>
                        <td className="ds-row-num">{rIdx + 1}</td>
                        {row.map((cell, cIdx) => (
                          <td key={cIdx}>{cell || <span className="ds-null">-</span>}</td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <footer className="ds-modal__footer">
          <small>상위 20개 행만 미리 표시됩니다.</small>
          <button type="button" className="secondary-button" onClick={onClose}>
            닫기
          </button>
        </footer>
      </div>
    </div>
  );
}
