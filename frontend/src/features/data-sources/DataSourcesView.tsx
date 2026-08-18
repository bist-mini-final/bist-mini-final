import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { DataSourcesSummary } from './components/DataSourcesSummary';
import { DbConnectionModal } from './components/DbConnectionModal';
import { FileUploadModal } from './components/FileUploadModal';
import { IndexDetailModal } from './components/IndexDetailModal';
import { IndexSearchTester } from './components/IndexSearchTester';
import { VectorIndexList } from './components/VectorIndexList';
import { dataSourceApi } from './services/dataSourceApi';
import type { DbStatusInfo, VectorIndexInfo } from './types';
import './data-sources.css';

export function DataSourcesView() {
  const [indexes, setIndexes] = useState<VectorIndexInfo[]>([]);
  const [dbStatus, setDbStatus] = useState<DbStatusInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modals state
  const [isDbModalOpen, setIsDbModalOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [detailIndexId, setDetailIndexId] = useState<string | null>(null);
  const [searchTargetIndex, setSearchTargetIndex] = useState<VectorIndexInfo | null>(null);

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
            dbStatus={dbStatus}
            isLoading={isLoading}
            onRefresh={fetchData}
            onDbModalClick={() => setIsDbModalOpen(true)}
            onDetailClick={(id) => setDetailIndexId(id)}
            onSearchClick={(idx) => setSearchTargetIndex(idx)}
            onDeleteClick={handleDeleteIndex}
            onCreateClick={() => setIsUploadOpen(true)}
          />
        </div>
      )}

      {/* Modals */}
      {isDbModalOpen && (
        <DbConnectionModal
          status={dbStatus}
          onClose={() => setIsDbModalOpen(false)}
          onRefresh={fetchData}
        />
      )}

      {isUploadOpen && (
        <FileUploadModal
          onClose={() => setIsUploadOpen(false)}
          onSuccess={() => {
            fetchData();
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
