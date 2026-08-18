import { useEffect, useState } from 'react';
import {
  Database,
  FileSpreadsheet,
  Loader2,
  Plus,
  RefreshCw,
  Server,
} from 'lucide-react';
import { DataSourcesSummary } from './components/DataSourcesSummary';
import { DbConnectionModal } from './components/DbConnectionModal';
import { FileList } from './components/FileList';
import { FilePreviewModal } from './components/FilePreviewModal';
import { FileUploadModal } from './components/FileUploadModal';
import { IndexDetailModal } from './components/IndexDetailModal';
import { IndexIngestionModal } from './components/IndexIngestionModal';
import { IndexSearchTester } from './components/IndexSearchTester';
import { VectorIndexList } from './components/VectorIndexList';
import { dataSourceApi } from './services/dataSourceApi';
import type { DataSourceFile, DbStatusInfo, VectorIndexInfo } from './types';
import './data-sources.css';

export function DataSourcesView() {
  const [activeTab, setActiveTab] = useState<'files' | 'indexes'>('files');
  const [files, setFiles] = useState<DataSourceFile[]>([]);
  const [indexes, setIndexes] = useState<VectorIndexInfo[]>([]);
  const [dbStatus, setDbStatus] = useState<DbStatusInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modals state
  const [isDbModalOpen, setIsDbModalOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [previewFileName, setPreviewFileName] = useState<string | null>(null);
  const [ingestFileName, setIngestFileName] = useState<string | null>(null);
  const [isIngestModalOpen, setIsIngestModalOpen] = useState(false);
  const [detailIndexId, setDetailIndexId] = useState<string | null>(null);
  const [searchTargetIndex, setSearchTargetIndex] = useState<VectorIndexInfo | null>(null);

  const fetchData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [filesRes, indexesRes, dbRes] = await Promise.all([
        dataSourceApi.listFiles(),
        dataSourceApi.listIndexes(),
        dataSourceApi.getDbStatus().catch(() => null),
      ]);
      setFiles(filesRes);
      setIndexes(indexesRes);
      if (dbRes) setDbStatus(dbRes);
    } catch (err: any) {
      setError(err.message || '데이터 소스 목록을 불러오지 못했습니다.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleStartIngestion = (fileName?: string) => {
    setIngestFileName(fileName || null);
    setIsIngestModalOpen(true);
  };

  const handleDeleteFile = async (fileName: string) => {
    if (!window.confirm(`'${fileName}' 파일을 정말 삭제하시겠습니까?`)) {
      return;
    }
    try {
      await dataSourceApi.deleteFile(fileName);
      await fetchData();
    } catch (err: any) {
      alert(err.message || '파일 삭제에 실패했습니다.');
    }
  };

  const handleDeleteIndex = async (indexId: string) => {
    if (!window.confirm(`선택한 벡터 인덱스를 정말 삭제하시겠습니까?\nID: ${indexId}`)) {
      return;
    }
    try {
      await dataSourceApi.deleteIndex(indexId);
      await fetchData();
    } catch (err: any) {
      alert(err.message || '인덱스 삭제에 실패했습니다.');
    }
  };

  return (
    <div className="ds-page">
      {/* Page Header */}
      <header className="ds-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <span className="ds-eyebrow">
              <Database size={14} /> DATA INFRASTRUCTURE
            </span>
            {dbStatus && (
              <button
                type="button"
                className={`ds-db-status-pill ${dbStatus.connected ? 'is-connected' : 'is-disconnected'}`}
                onClick={() => setIsDbModalOpen(true)}
                title="PostgreSQL pgvector 컨테이너 설정 확인"
              >
                <span className="ds-db-status-pill__dot" />
                <Server size={12} />
                <span>
                  {dbStatus.connected
                    ? `pgvector (localhost:${dbStatus.port} / ${dbStatus.database})`
                    : 'pgvector 연결 안 됨'}
                </span>
              </button>
            )}
          </div>
          <h1>데이터 소스 & pgvector 인덱스 관리</h1>
          <p>
            분석 대상 엑셀 문서를 관리하고, 표 구조를 분석해 Docker pgvector 데이터베이스로 인덱싱합니다.
          </p>
        </div>
        <div className="ds-header__actions">
          <button
            type="button"
            className="secondary-button"
            onClick={fetchData}
            title="새로고침"
            disabled={isLoading}
          >
            <RefreshCw size={15} className={isLoading ? 'ds-spin' : ''} />
            <span>새로고침</span>
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={() => handleStartIngestion()}
          >
            <Plus size={16} />
            <span>새 인덱스 생성</span>
          </button>
        </div>
      </header>

      {/* Summary KPI Cards */}
      <DataSourcesSummary files={files} indexes={indexes} />

      {error && <div className="ds-error-alert">{error}</div>}

      {/* Tab Navigation */}
      <div className="ds-tabs-nav">
        <button
          type="button"
          className={`ds-nav-tab ${activeTab === 'files' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('files')}
        >
          <FileSpreadsheet size={16} />
          <span>원시 데이터 파일 ({files.length})</span>
        </button>
        <button
          type="button"
          className={`ds-nav-tab ${activeTab === 'indexes' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('indexes')}
        >
          <Database size={16} />
          <span>벡터 DB 인덱스 ({indexes.length})</span>
        </button>
      </div>

      {/* Main Content Pane */}
      {isLoading ? (
        <div className="ds-loading-pane">
          <Loader2 className="ds-spin" size={32} />
          <span>데이터 소스를 동기화하는 중...</span>
        </div>
      ) : (
        <div className="ds-tab-content">
          {activeTab === 'files' ? (
            <FileList
              files={files}
              onUploadClick={() => setIsUploadOpen(true)}
              onPreviewClick={(name) => setPreviewFileName(name)}
              onIngestClick={(name) => handleStartIngestion(name)}
              onDeleteClick={handleDeleteFile}
            />
          ) : (
            <VectorIndexList
              indexes={indexes}
              onDetailClick={(id) => setDetailIndexId(id)}
              onSearchClick={(idx) => setSearchTargetIndex(idx)}
              onDeleteClick={handleDeleteIndex}
              onCreateClick={() => handleStartIngestion()}
            />
          )}
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

      {previewFileName && (
        <FilePreviewModal
          fileName={previewFileName}
          onClose={() => setPreviewFileName(null)}
        />
      )}

      {isIngestModalOpen && (
        <IndexIngestionModal
          files={files}
          initialFileName={ingestFileName || undefined}
          onClose={() => setIsIngestModalOpen(false)}
          onSuccess={() => {
            fetchData();
            setActiveTab('indexes');
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
