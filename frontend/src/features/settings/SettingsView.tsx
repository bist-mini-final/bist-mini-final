import { useEffect, useRef, useState } from 'react';
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

/**
 * PostgreSQL/pgvector 인프라와 RAG 파이프라인 설정을 표시하고 관리하는 설정 화면을 렌더링합니다.
 *
 * @returns 데이터베이스 상태, 연결 정보, RAG 설정을 포함하는 설정 화면
 */
export function SettingsView() {
  const [dbStatus, setDbStatus] = useState<DbStatusInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isTesting, setIsTesting] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState<'idle' | 'success' | 'error'>('idle');
  const [copiedCmd, setCopiedCmd] = useState<'idle' | 'success' | 'error'>('idle');

  const copyResetTimers = useRef<
    Partial<Record<'url' | 'cmd', ReturnType<typeof setTimeout>>>
  >({});
  const copyRequestIds = useRef<Partial<Record<'url' | 'cmd', number>>>({});

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
    return () => {
      if (copyResetTimers.current.url) {
        clearTimeout(copyResetTimers.current.url);
      }
      if (copyResetTimers.current.cmd) {
        clearTimeout(copyResetTimers.current.cmd);
      }
    };
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
  const dockerCmd = 'docker compose -f deploy/db/docker-compose.yml up -d';

  const copyToClipboard = async (text: string, type: 'url' | 'cmd') => {
    const setStatus = type === 'url' ? setCopiedUrl : setCopiedCmd;
    const requestId = (copyRequestIds.current[type] ?? 0) + 1;
    copyRequestIds.current[type] = requestId;

    if (copyResetTimers.current[type]) {
      clearTimeout(copyResetTimers.current[type]);
    }
    try {
      if (!navigator.clipboard?.writeText) {
        if (copyRequestIds.current[type] === requestId) {
          setStatus('error');
          copyResetTimers.current[type] = setTimeout(() => {
            if (copyRequestIds.current[type] === requestId) {
              setStatus('idle');
              delete copyResetTimers.current[type];
            }
          }, 2000);
        }
        return;
      }
      await navigator.clipboard.writeText(text);
      if (copyRequestIds.current[type] === requestId) {
        setStatus('success');
        copyResetTimers.current[type] = setTimeout(() => {
          if (copyRequestIds.current[type] === requestId) {
            setStatus('idle');
            delete copyResetTimers.current[type];
          }
        }, 2000);
      }
    } catch {
      if (copyRequestIds.current[type] === requestId) {
        setStatus('error');
        copyResetTimers.current[type] = setTimeout(() => {
          if (copyRequestIds.current[type] === requestId) {
            setStatus('idle');
            delete copyResetTimers.current[type];
          }
        }, 2000);
      }
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
              <span>PostgreSQL/pgvector native 저장 계층</span>
            </div>
          </div>
          <button
            type="button"
            className="primary-button"
            onClick={handleTestConnection}
            disabled={isTesting}
          >
            {isTesting ? (
              <Loader2 size={15} className="ds-spin" />
            ) : (
              <RefreshCw size={15} />
            )}
            <span>{isTesting ? '연결 테스트 중...' : '연결 다시 테스트'}</span>
          </button>
        </div>

        {/* Status Banner */}
        {dbStatus?.connected ? (
          <div className="settings-status-banner settings-status-banner--success">
            <CheckCircle2 size={18} className="text-emerald-600" />
            <div>
              <p className="font-semibold text-emerald-900">PostgreSQL pgvector 정상 연결됨</p>
              <p className="text-xs text-emerald-700">
                PostgreSQL {dbStatus.postgres_version || '16'} (pgvector v{dbStatus.pgvector_version || '0.8.0'}) 연동 활성화 상태입니다.
              </p>
            </div>
          </div>
        ) : (
          <div className="settings-status-banner settings-status-banner--danger">
            <ShieldAlert size={18} className="text-rose-600" />
            <div>
              <p className="font-semibold text-rose-900">pgvector 데이터베이스에 연결할 수 없습니다</p>
              <p className="text-xs text-rose-700">
                Docker 컨테이너가 실행 중인지 확인하거나 <code>docker compose -f deploy/db/docker-compose.yml up -d</code>로 데이터베이스를 시작하세요.
              </p>
            </div>
          </div>
        )}

        {/* Database Metric Cards */}
        <div className="settings-grid">
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
          <label>PostgreSQL 연결 접속 URL (psycopg)</label>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <code style={{ flex: 1 }}>{dbUrl}</code>
            <button
              type="button"
              className="secondary-button"
              onClick={() => copyToClipboard(dbUrl, 'url')}
            >
              <Copy size={14} />
              <span>{copiedUrl === 'success' ? '복사됨!' : copiedUrl === 'error' ? '복사 실패' : 'URL 복사'}</span>
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
              <span>{copiedCmd === 'success' ? '복사됨!' : copiedCmd === 'error' ? '복사 실패' : '명령어 복사'}</span>
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
              <span>스프레드시트 쿼리 분해 및 벡터 유사도 정책</span>
            </div>
          </div>
        </div>

        <div className="settings-config-table">
          <div className="settings-config-row">
            <div>
              <p className="font-semibold text-slate-800">질의 임베딩 계약</p>
              <p className="text-xs text-slate-500">
                선택한 pgvector 인덱스와 동일한 모델·차원으로 질의 벡터를 생성합니다.
              </p>
            </div>
            <span className="settings-badge font-mono">INDEX-BOUND</span>
          </div>

          <div className="settings-config-row">
            <div>
              <p className="font-semibold text-slate-800">RAG 벡터 검색 유사도 캐시 임계값 (Threshold)</p>
              <p className="text-xs text-slate-500">
                높을수록 동일하거나 매우 유사한 질의에만 캐시를 재사용합니다.
              </p>
            </div>
            <span className="settings-badge">0.95 (보수적 임계값)</span>
          </div>

          <div className="settings-config-row">
            <div>
              <p className="font-semibold text-slate-800">Reciprocal Rank Fusion (RRF) 파라미터 (k)</p>
              <p className="text-xs text-slate-500">
                복수 컬렉션 검색 결과 순위 통합 시 사용하는 가중 상수 (기본값: 60)
              </p>
            </div>
            <span className="settings-badge font-mono">k = 60</span>
          </div>

          <div className="settings-config-row">
            <div>
              <p className="font-semibold text-slate-800">LLM 추론 모델 (Structure Detector / Answer Refiner)</p>
              <p className="text-xs text-slate-500">
                BFS 영역 감지 및 셀 좌표 기반 응답 정제에 사용하는 모델
              </p>
            </div>
            <span className="settings-badge font-mono">gpt-4o-mini</span>
          </div>
        </div>
      </section>
    </div>
  );
}
