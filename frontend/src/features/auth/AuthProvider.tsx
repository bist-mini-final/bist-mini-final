import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import { LockKeyhole, LogIn } from 'lucide-react';
import { ApiError, requestJson } from '../../shared/api/httpClient';
import { Button } from '../../shared/ui';
import './auth.css';

type AuthRole = 'viewer' | 'operator' | 'admin';

interface AuthPrincipal {
  readonly username: string;
  readonly role: AuthRole;
  readonly tenant_id: string;
  readonly client_id: string;
}

interface SessionResponse {
  readonly enabled: boolean;
  readonly authenticated: boolean;
  readonly principal: AuthPrincipal | null;
}

interface AuthContextValue {
  readonly enabled: boolean;
  readonly principal: AuthPrincipal | null;
  readonly logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  enabled: false,
  principal: null,
  logout: async () => undefined,
});

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}

interface AuthProviderProps {
  readonly children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [loadError, setLoadError] = useState('');

  const loadSession = useCallback(async () => {
    setLoadError('');
    try {
      setSession(await requestJson<SessionResponse>('/api/auth/session'));
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setSession({ enabled: true, authenticated: false, principal: null });
        return;
      }
      setLoadError(error instanceof Error ? error.message : '로그인 상태를 확인하지 못했습니다.');
    }
  }, []);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  const login = async (username: string, password: string) => {
    const next = await requestJson<SessionResponse>('/api/auth/login', {
      method: 'POST',
      json: { username, password },
    });
    setSession(next);
  };

  const logout = useCallback(async () => {
    const next = await requestJson<SessionResponse>('/api/auth/logout', { method: 'POST' });
    setSession(next);
  }, []);

  const context = useMemo<AuthContextValue>(() => ({
    enabled: Boolean(session?.enabled),
    principal: session?.principal ?? null,
    logout,
  }), [logout, session]);

  if (loadError) {
    return (
      <main className="auth-screen">
        <section className="auth-card" aria-live="polite">
          <div className="auth-card__mark"><LockKeyhole size={22} /></div>
          <h1>서비스 연결 실패</h1>
          <p>{loadError}</p>
          <Button variant="primary" onClick={() => { void loadSession(); }}>다시 시도</Button>
        </section>
      </main>
    );
  }

  if (session === null) {
    return <main className="auth-screen" aria-label="로그인 상태 확인 중"><div className="auth-loader" /></main>;
  }

  if (session.enabled && !session.authenticated) {
    return <LoginScreen onLogin={login} />;
  }

  return <AuthContext.Provider value={context}>{children}</AuthContext.Provider>;
}

function LoginScreen({
  onLogin,
}: {
  readonly onLogin: (username: string, password: string) => Promise<void>;
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await onLogin(username.trim(), password);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '로그인하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-screen">
      <section className="auth-card">
        <div className="auth-card__brand">
          <div className="auth-card__mark"><LockKeyhole size={22} aria-hidden="true" /></div>
          <div><strong>Excel RAG</strong><span>Financial Intelligence Workspace</span></div>
        </div>
        <div className="auth-card__heading">
          <h1>워크스페이스 로그인</h1>
          <p>승인된 계정으로 안전하게 접속하세요.</p>
        </div>
        <form className="auth-form" onSubmit={(event) => { void submit(event); }}>
          <label>
            <span>아이디</span>
            <input
              name="username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
              minLength={3}
            />
          </label>
          <label>
            <span>비밀번호</span>
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {error && <p className="auth-form__error" role="alert">{error}</p>}
          <Button type="submit" variant="primary" size="lg" busy={busy} disabled={busy}>
            <LogIn size={17} aria-hidden="true" />
            {busy ? '확인 중…' : '로그인'}
          </Button>
        </form>
      </section>
    </main>
  );
}
