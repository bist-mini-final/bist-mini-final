import { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Copy,
  Database,
  Layers,
  Loader2,
  RefreshCw,
  Server,
  ShieldAlert,
  Sparkles,
  Zap,
} from 'lucide-react';
import { dataSourceApi } from '../data-sources/services/dataSourceApi';
import type { DbStatusInfo } from '../data-sources/types';
import './settings.css';

export function SettingsView() {
  const [dbStatus, setDbStatus] = useState<DbStatusInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isTesting, setIsTesting] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState(false);

  const fetchStatus = async () => {
    setIsLoading(true);
    try {
      const res = await dataSourceApi.getDbStatus();
      setDbStatus(res);
    } catch {
      setDbStatus(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleTestConnection = async () => {
    setIsTesting(true);
    try {
      const res = await dataSourceApi.getDbStatus();
      setDbStatus(res);
    } catch {
      setDbStatus(null);
    } finally {
      setIsTesting(false);
    }
  };

  const dbHost = dbStatus?.host || 'localhost';
  const dbPort = dbStatus?.port || 5432;
  const dbName = dbStatus?.database || 'rag_flow';
  const dbUrl = `postgresql://<user>:<password>@${dbHost}:${dbPort}/${dbName}`;
  const dockerCmd = 'docker compose -f docker-compose.db.yml up -d';

  const copyToClipboard = (text: string, type: 'url' | 'cmd') => {
    navigator.clipboard.writeText(text);
    if (type === 'url') {
      setCopiedUrl(true);
      setTimeout(() => setCopiedUrl(false), 2000);
    } else {
      setCopiedCmd(true);
      setTimeout(() => setCopiedCmd(false), 2000);
    }
  };

  return (
    <div className="settings-page">
      <header className="settings-header">
        <div>
          <h1>시스템 환경 & 인프라 설정</h1>
          <p>PostgreSQL pgvector 데이터베이스 연결, 임베딩 파이프라인, 유사도 캐시 임계값을 관리합니다.</p>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={fetchStatus}
          disabled={isLoading}
        >
          <RefreshCw size={15} className={isLoading ? 'ds-spin' : ''} />
          <span>새로고침</span>
        </button>
      </header>

      {/* 1. Database & pgvector Infrastructure */}
      <section className="settings-section">
        <div className="settings-section__header">
          <div className="settings-section__title">
            <Server size={19} className="text-emerald-600" />
            <div>
              <h3>PostgreSQL 16 + pgvector 데이터베이스</h3>
              <span>LangChain 공식 표준 벡터 스키마 연동</span>
            </div>
          </div>
          <button
            type="button"
            className="primary-button"
            onClick={handleTestConnection}
            disabled={isTesting}
          >
            {isTesting ? <Loader2 size={14} className="ds-spin" /> : <RefreshCw size={14} />}
            <span>연결 테스트</span>
          </button>
        </div>

        {/* Status Banner */}
        <div
          className={`settings-status-banner ${
            dbStatus?.connected ? 'is-connected' : 'is-disconnected'
          }`}
        >
          {dbStatus?.connected ? (
            <>
              <CheckCircle2 size={20} />
              <div>
                <strong>PostgreSQL pgvector 정상 연결됨</strong>
                <p style={{ margin: 0, fontSize: '0.82rem' }}>
                  PostgreSQL {dbStatus.postgres_version || '16'} (pgvector v{dbStatus.pgvector_version || '0.8.6'} · HNSW 인덱싱 가동 중)
                </p>
              </div>
            </>
          ) : (
            <>
              <ShieldAlert size={20} />
              <div>
                <strong>pgvector 데이터베이스에 연결할 수 없습니다</strong>
                <p style={{ margin: 0, fontSize: '0.82rem' }}>
                  터미널에서 <code>{dockerCmd}</code> 명령어를 실행해 컨테이너를 시작하세요.
                </p>
              </div>
            </>
          )}
        </div>

        {/* Metric Cards Grid */}
        <div className="settings-grid-cards">
          <div className="settings-card">
            <span className="settings-card__label">
              <Server size={14} /> 호스트 / 포트
            </span>
            <span className="settings-card__val">
              {dbHost}:{dbPort}
            </span>
          </div>

          <div className="settings-card">
            <span className="settings-card__label">
              <Database size={14} /> 데이터베이스명
            </span>
            <span className="settings-card__val">
              {dbName}
            </span>
          </div>

          <div className="settings-card">
            <span className="settings-card__label">
              <Layers size={14} /> 등록된 컬렉션 수
            </span>
            <span className="settings-card__val">
              {dbStatus?.total_indexes ?? 0}개
            </span>
          </div>

          <div className="settings-card">
            <span className="settings-card__label">
              <Zap size={14} /> 적재된 벡터 청크
            </span>
            <span className="settings-card__val">
              {(dbStatus?.total_chunks ?? 0).toLocaleString()}청크
            </span>
          </div>
        </div>

        {/* PostgreSQL URL & Docker Command Box */}
        <div className="settings-url-box">
          <label>PostgreSQL 연결 접속 URL (SQLAlchemy / psycopg)</label>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <code style={{ flex: 1 }}>{dbUrl}</code>
            <button
              type="button"
              className="secondary-button"
              onClick={() => copyToClipboard(dbUrl, 'url')}
            >
              <Copy size={14} />
              <span>{copiedUrl ? '복사됨!' : 'URL 복사'}</span>
            </button>
          </div>
        </div>

        <div className="settings-url-box">
          <label>Docker 컨테이너 가동 명령어</label>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <code style={{ flex: 1 }}>{dockerCmd}</code>
            <button
              type="button"
              className="secondary-button"
              onClick={() => copyToClipboard(dockerCmd, 'cmd')}
            >
              <Copy size={14} />
              <span>{copiedCmd ? '복사됨!' : '명령어 복사'}</span>
            </button>
          </div>
        </div>
      </section>

      {/* 2. RAG Pipeline & Similarity Cache Configuration */}
      <section className="settings-section">
        <div className="settings-section__header">
          <div className="settings-section__title">
            <Sparkles size={19} className="text-amber-500" />
            <div>
              <h3>RAG 파이프라인 & 캐시 임계값 설정</h3>
              <span>질문 유사도 캐시 및 임베딩 모델 표준</span>
            </div>
          </div>
        </div>

        <div className="settings-grid-cards">
          <div className="settings-card">
            <span className="settings-card__label">
              <Zap size={14} /> 질문 캐시 유사도 임계값
            </span>
            <span className="settings-card__val" style={{ color: '#16a34a' }}>
              0.95 (보수적 임계값)
            </span>
            <small style={{ fontSize: '0.75rem', color: '#64748b' }}>
              완전 유사한 질의에 대해서만 캐시 히트 적용
            </small>
          </div>

          <div className="settings-card">
            <span className="settings-card__label">
              <Sparkles size={14} /> 표준 임베딩 모델
            </span>
            <span className="settings-card__val">
              text-embedding-3-large
            </span>
            <small style={{ fontSize: '0.75rem', color: '#64748b' }}>
              3072차원 Cosine Distance 인덱싱
            </small>
          </div>

          <div className="settings-card">
            <span className="settings-card__label">
              <Layers size={14} /> 표 구조화 파이프라인
            </span>
            <span className="settings-card__val">
              Luna VLM
            </span>
            <small style={{ fontSize: '0.75rem', color: '#64748b' }}>
              LunaVlmStructureDetectorModule 자동 파싱
            </small>
          </div>
        </div>
      </section>
    </div>
  );
}

export default SettingsView;
