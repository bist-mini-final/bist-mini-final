import { FormEvent, useEffect, useRef, useState } from 'react';
import { Bot, CircleStop, FileText, MessageSquarePlus, Paperclip, Pencil, RefreshCw, Send, Trash2, X } from 'lucide-react';
import { MarkdownAnswer } from '../playground/components/MarkdownAnswer';
import { pipelineApi } from '../playground/services/api';
import { requestJson } from '../../shared/api/httpClient';
import type { WorkflowRun } from '../playground/types';
import { BiCardChart } from '../bi/components/charts/BiCardChart';
import { fetchBiDashboard } from '../bi/services/api';
import type { BiCardId, BiDashboardSnapshot } from '../bi/types';
import '../bi/bi.css';
import '../bi/bi-reference.css';
import './chatbot.css';

type Visualization = { company_id: string; card_id: BiCardId };
type Attachment = { id: string; name: string; content_type: string | null; size: number; created_at?: string };
type Message = { id: string; role: 'user' | 'assistant'; content: string; status: 'processing' | 'completed' | 'failed'; run_id: string | null; visualization: Visualization | null; attachments: Attachment[]; created_at: string };
type Session = { id: string; title: string; created_at: string; updated_at: string; messages?: Message[] };
type Turn = { run: WorkflowRun; message: Message | null };
type ProgressStep = { id: string; label: string; state: 'active' | 'completed' };
const EXAMPLES = ['IBM의 2024년과 2025년 매출을 비교해줘.', '2025년 IBM 총자산과 총부채는 각각 얼마인가?', 'IBM의 현금흐름 추이를 차트로 보여줘.'];
const CLIENT_KEY = 'rag-flow:chat-client-id';
const clientId = () => { let id = localStorage.getItem(CLIENT_KEY); if (!id) { id = crypto.randomUUID(); localStorage.setItem(CLIENT_KEY, id); } return id; };
const chatApi = {
  list: (id: string) => requestJson<{ sessions: Session[] }>(`/api/chat/sessions?client_id=${encodeURIComponent(id)}`),
  suggestions: () => requestJson<{ questions: string[] }>('/api/chat/suggestions'),
  refreshSuggestions: () => requestJson<{ questions: string[] }>('/api/chat/suggestions/refresh', { method: 'POST' }),
  create: (id: string) => requestJson<Session>('/api/chat/sessions', { method: 'POST', json: { client_id: id } }),
  get: (sessionId: string, id: string) => requestJson<Session>(`/api/chat/sessions/${encodeURIComponent(sessionId)}?client_id=${encodeURIComponent(id)}`),
  rename: (sessionId: string, id: string, title: string) => requestJson<Session>(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'PATCH', json: { client_id: id, title } }),
  remove: (sessionId: string, id: string) => requestJson<{ deleted: string }>(`/api/chat/sessions/${encodeURIComponent(sessionId)}?client_id=${encodeURIComponent(id)}`, { method: 'DELETE' }),
  upload: (sessionId: string, id: string, file: File) => { const body = new FormData(); body.set('client_id', id); body.set('file', file); return requestJson<Attachment>(`/api/chat/sessions/${encodeURIComponent(sessionId)}/attachments`, { method: 'POST', body, timeout: 60_000 }); },
  send: (sessionId: string, id: string, content: string, attachmentId?: string) => requestJson<{ assistant_message: Message; run_id: string | null; mode: 'direct' | 'rag' }>(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`, { method: 'POST', json: { client_id: id, content, attachment_id: attachmentId }, timeout: 45_000 }),
  sync: (runId: string, id: string) => requestJson<Turn>(`/api/chat/runs/${encodeURIComponent(runId)}?client_id=${encodeURIComponent(id)}`),
};

function ChatVisualization({ visualization }: { visualization: Visualization }) {
  const [dashboard, setDashboard] = useState<BiDashboardSnapshot | null>(null);
  useEffect(() => { const controller = new AbortController(); void fetchBiDashboard(visualization.company_id, controller.signal).then((result) => { if (result.kind === 'snapshot') setDashboard(result.dashboard); }).catch(() => undefined); return () => controller.abort(); }, [visualization.company_id]);
  return dashboard ? <div className="chatbot-visualization bi-card" data-card-id={visualization.card_id}><BiCardChart cardId={visualization.card_id} dashboard={dashboard} range="최근 5개" size="M" /></div> : null;
}

function progressForEvent(event: { event: string; data: unknown }): ProgressStep[] {
  if (event.event === 'run_started') return [{ id: 'analysis', label: '질문을 분석하고 있습니다', state: 'active' }];
  if (!event.event.startsWith('node_') || !event.data || typeof event.data !== 'object') return [];
  const node = event.data as { node_id?: string; module_type?: string; status?: string };
  if (node.status !== 'running') return [];
  const name = `${node.node_id ?? ''} ${node.module_type ?? ''}`.toLowerCase();
  const label = name.includes('embed') ? '질문을 벡터로 변환하고 있습니다'
    : name.includes('retriev') || name.includes('search') || name.includes('query') ? '관련 재무 문서를 검색하고 있습니다'
      : name.includes('rerank') || name.includes('fusion') ? '검색 결과의 관련도를 검토하고 있습니다'
        : name.includes('read') || name.includes('llm') ? '근거를 바탕으로 답변을 작성하고 있습니다'
          : '답변에 필요한 데이터를 처리하고 있습니다';
  return [{ id: node.node_id ?? name, label, state: 'active' }];
}

function formatDate(date: string) {
  return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(date));
}

function repairInlineTable(markdown: string) {
  const normalized = markdown.replace(/\\+\|/g, '|');
  return normalized.split('\n').map((line) => repairInlineTableLine(line)).join('\n');
}

function repairInlineTableLine(line: string) {
  if (!line.includes('|---')) return line;

  const separatorStart = line.indexOf('|---');
  const tableStart = line.indexOf('|');
  if (tableStart < 0 || tableStart >= separatorStart) return line;
  const headerCells = line.slice(tableStart, separatorStart).split('|').map((cell) => cell.trim()).filter(Boolean);
  const cellsAfterHeader = line.slice(separatorStart).split('|').map((cell) => cell.trim()).filter(Boolean);
  if (headerCells.length < 3 || cellsAfterHeader.length < headerCells.length) return line;

  const separatorCells = cellsAfterHeader.slice(0, headerCells.length);
  if (!separatorCells.every((cell) => /^:?-{3,}:?$/.test(cell))) return line;
  const dataCells = cellsAfterHeader.slice(headerCells.length);
  const rowCount = Math.floor(dataCells.length / headerCells.length);
  if (!rowCount) return line;

  const rows = Array.from({ length: rowCount }, (_, row) =>
    dataCells.slice(row * headerCells.length, (row + 1) * headerCells.length),
  );
  const table = [
    `| ${headerCells.join(' | ')} |`,
    `| ${separatorCells.join(' | ')} |`,
    ...rows.map((row) => `| ${row.join(' | ')} |`),
  ].join('\n');
  const remainder = dataCells.slice(rowCount * headerCells.length).join(' | ').trim();
  return `${line.slice(0, tableStart)}${table}${remainder ? `\n${remainder}` : ''}`;
}

function repairCollapsedDateTableHeaders(markdown: string) {
  const lines = markdown.split('\n');
  return lines.map((line, index) => {
    const separator = lines[index + 1] ?? '';
    if (!line.trimStart().startsWith('|') || !separator.trimStart().startsWith('|')) return line;

    const dates = line.match(/20\d{2}-\d{2}-\d{2}/g) ?? [];
    const separatorCells = separator.split('|').filter((cell) => cell.trim());
    if (dates.length < 2 || separatorCells.length !== dates.length + 1) return line;

    const firstDate = dates[0];
    if (!firstDate) return line;
    const firstDateIndex = line.indexOf(firstDate);
    const title = line.slice(0, firstDateIndex).replace(/^\s*\|\s*/, '').trim();
    if (!title) return line;
    return `| ${[title, ...dates].join(' | ')} |`;
  }).join('\n');
}

export function normalizeChatMarkdown(markdown: string) {
  return repairCollapsedDateTableHeaders(repairInlineTable(markdown)).replace(/(?<![A-Za-z])NA(?![A-Za-z])\s*로?\s*근거가 부족(?:합니다|해요)?/gi, '확인 가능한 근거가 부족해 요약에서 제외했습니다').replace(/(?<![A-Za-z])NA(?![A-Za-z])\s*로 표시되어 있어/gi, '확인 가능한 값이 없어').replace(/\s*[;；]\s*(?=(?:\*\*)?[^\n]*확인 가능한 근거가 부족)/g, '\n\n').replace(/(\d{4})~~(\d{4})/g, '$1–$2').replace(/\\([*_`\[\].])/g, '$1').replace(/\[([^\]]+:[^\]]+)\]/g, (_match, source: string) => {
    const [sheet, detail = ''] = source.split(':', 2);
    const [field, period] = detail.split('|').map((item) => item.trim());
    const label = `${sheet.replace(/_/g, ' ')}${field ? ` · ${field}` : ''}${period ? ` · ${period}` : ''}`;
    return `[${label}](https://citation.local/${encodeURIComponent(label)})`;
  });
}

function ChatAnswer({ markdown }: { markdown: string }) {
  const clean = normalizeChatMarkdown(markdown);
  return <MarkdownAnswer markdown={clean} />;
}

export function ChatbotView() {
  const [client] = useState(clientId); const [sessions, setSessions] = useState<Session[]>([]); const [examples, setExamples] = useState(EXAMPLES); const [isRefreshingSuggestions, setIsRefreshingSuggestions] = useState(false); const [active, setActive] = useState<Session | null>(null); const [draft, setDraft] = useState(''); const [attachment, setAttachment] = useState<File | null>(null); const [isRunning, setIsRunning] = useState(false); const [requestError, setRequestError] = useState(''); const [progress, setProgress] = useState<ProgressStep[]>([]); const [dialog, setDialog] = useState<{ type: 'rename' | 'delete'; session: Session } | null>(null); const [titleDraft, setTitleDraft] = useState(''); const aborter = useRef<AbortController | null>(null); const attachmentInput = useRef<HTMLInputElement>(null);
  const refresh = async () => { const loaded = await chatApi.list(client); setSessions(loaded.sessions); return loaded.sessions; };
  const select = async (id: string) => setActive(await chatApi.get(id, client));
  useEffect(() => { void refresh().catch(() => undefined); void chatApi.suggestions().then(({ questions }) => { if (questions.length) setExamples(questions); }).catch(() => undefined); }, [client]);
  const refreshSuggestions = async () => { if (isRefreshingSuggestions) return; setIsRefreshingSuggestions(true); try { const { questions } = await chatApi.refreshSuggestions(); if (questions.length) setExamples(questions); } finally { setIsRefreshingSuggestions(false); } };
  const newSession = () => { if (isRunning) return; setActive(null); setDraft(''); setAttachment(null); setRequestError(''); setProgress([]); };
  const renameSession = async () => {
    if (!dialog || dialog.type !== 'rename') return;
    const { session } = dialog; const title = titleDraft.trim();
    if (!title || title === session.title) return;
    const updated = await chatApi.rename(session.id, client, title);
    setSessions((items) => items.map((item) => item.id === updated.id ? updated : item));
    setActive((current) => current?.id === updated.id ? { ...current, title: updated.title, updated_at: updated.updated_at } : current);
    setDialog(null);
  };
  const deleteSession = async () => {
    if (!dialog || dialog.type !== 'delete') return;
    const { session } = dialog;
    await chatApi.remove(session.id, client);
    setSessions((items) => items.filter((item) => item.id !== session.id));
    if (active?.id === session.id) newSession();
    setDialog(null);
  };
  const streamAnswer = async (message: Message) => {
    const chunkSize = 12;
    for (let length = chunkSize; length < message.content.length; length += chunkSize) {
      const partial = message.content.slice(0, length);
      setActive((current) => current && ({ ...current, messages: (current.messages ?? []).map((item) => item.id === message.id ? { ...message, content: partial } : item) }));
      await new Promise<void>((resolve) => window.setTimeout(resolve, 14));
    }
    setActive((current) => current && ({ ...current, messages: (current.messages ?? []).map((item) => item.id === message.id ? message : item) }));
  };
  const ask = async (event?: FormEvent, value = draft) => {
    event?.preventDefault(); const content = value.trim(); if (!content || isRunning) return;
    setDraft(''); setRequestError(''); setIsRunning(true); setProgress([{ id: 'analysis', label: '질문을 분석하고 있습니다', state: 'active' }]); const controller = new AbortController(); aborter.current = controller;
    try {
      let session: Session;
      if (active) session = active;
      else { const created = await chatApi.create(client); session = { ...created, messages: [] }; setActive(session); }
      const uploadedAttachment = attachment ? await chatApi.upload(session.id, client, attachment) : null;
      if (uploadedAttachment) setAttachment(null);
      const localUser: Message = { id: `local-${crypto.randomUUID()}`, role: 'user', content, status: 'completed', run_id: null, visualization: null, attachments: uploadedAttachment ? [uploadedAttachment] : [], created_at: new Date().toISOString() };
      setActive((current) => current ? ({ ...current, messages: [...(current.messages ?? []), localUser] }) : ({ ...session, messages: [localUser] }));
      const started = await chatApi.send(session.id, client, content, uploadedAttachment?.id);
      setActive((current) => current && ({ ...current, messages: [...(current.messages ?? []).filter((item) => item.id !== localUser.id), { ...localUser, id: `user-${started.run_id}` }, started.assistant_message] }));
      if (!started.run_id) {
        setProgress([{ id: 'answer', label: '답변을 작성하고 있습니다', state: 'active' }]);
        await refresh();
        const completed = await chatApi.get(session.id, client);
        const answer = [...(completed.messages ?? [])].reverse().find((item) => item.role === 'assistant');
        setActive(answer ? { ...completed, messages: completed.messages?.map((item) => item.id === answer.id ? { ...answer, content: '' } : item) } : completed);
        if (answer) await streamAnswer(answer);
        return;
      }
      const run = await pipelineApi.streamRun(started.run_id, (event) => {
        const updates = progressForEvent(event);
        if (updates.length) setProgress(updates);
      }, controller.signal); const synced = await chatApi.sync(run.id, client);
      if (synced.message) {
        const answer = synced.message;
        setActive((current) => current && ({ ...current, messages: (current.messages ?? []).map((item) => item.id === answer.id ? { ...answer, content: '' } : item) }));
        await streamAnswer(answer);
      }
      await refresh();
    } catch (error) { if (!(error instanceof DOMException && error.name === 'AbortError')) { const message = error instanceof Error ? error.message : '질문 처리에 실패했습니다.'; setRequestError(message); setActive((current) => current && ({ ...current, messages: [...(current.messages ?? []), { id: `error-${crypto.randomUUID()}`, role: 'assistant', content: message, status: 'failed', run_id: null, visualization: null, attachments: [], created_at: new Date().toISOString() }] })); } }
    finally { aborter.current = null; setIsRunning(false); setProgress([]); }
  };
  const messages = active?.messages ?? [];
  return <div className="chatbot-page"><header className="chatbot-header"><span className="chatbot-header__icon"><Bot size={22} /></span><div><span className="chatbot-header__eyebrow">FINANCIAL RAG ASSISTANT</span><h1>AI 금융 챗봇</h1><p>내 대화에서 재무 문서 기반 답변을 확인하세요.</p></div></header><div className="chatbot-layout chatbot-layout--sessions"><aside className="chatbot-sessions"><button type="button" onClick={newSession}><MessageSquarePlus size={16} /> 새 대화</button><span>내 대화</span>{sessions.map((session) => <div key={session.id} className={`chatbot-session${active?.id === session.id ? ' is-active' : ''}`} title={`최근 대화: ${formatDate(session.updated_at)}`}><button type="button" className="chatbot-session__select" onClick={() => void select(session.id)}><strong>{session.title}</strong></button><span className="chatbot-session__actions"><button type="button" aria-label={`${session.title} 제목 편집`} onClick={() => { setTitleDraft(session.title); setDialog({ type: 'rename', session }); }}><Pencil size={13} /></button><button type="button" aria-label={`${session.title} 삭제`} onClick={() => setDialog({ type: 'delete', session })}><Trash2 size={13} /></button></span></div>)}</aside><section className="chatbot-panel"><div className="chatbot-messages" aria-live="polite">{messages.length === 0 && <div className="chatbot-empty"><Bot size={28} /><h2>새 재무 질문을 시작하세요</h2><p>첫 질문을 보내면 내 대화 목록에 저장됩니다.</p><div className="chatbot-examples__heading"><span>추천 질문</span><button type="button" className="chatbot-refresh-suggestions" aria-label="추천 질문 새로고침" title="추천 질문 새로고침" onClick={() => void refreshSuggestions()} disabled={isRefreshingSuggestions}><RefreshCw size={15} className={isRefreshingSuggestions ? 'chatbot-spin' : ''} /></button></div><div className="chatbot-examples">{examples.map((example) => <button key={example} type="button" onClick={() => void ask(undefined, example)}>{example}</button>)}</div>{requestError && <small className="chatbot-request-error">{requestError}</small>}</div>}{messages.map((message) => <article key={message.id} className={`chatbot-message chatbot-message--${message.role}`}><span className="chatbot-message__avatar">{message.role === 'assistant' ? <Bot size={16} /> : '나'}</span><div className="chatbot-message__body">{message.status === 'processing' ? <div className="chatbot-progress">{progress.length ? progress.map((step) => <span key={step.id} className={step.state === 'active' ? 'is-active' : ''}>{step.state === 'active' && <RefreshCw size={14} className="chatbot-spin" />}{step.label}</span>) : <span className="is-active"><RefreshCw size={14} className="chatbot-spin" />답변을 준비하고 있습니다</span>}</div> : message.role === 'assistant' ? <ChatAnswer markdown={message.content} /> : <><p>{message.content}</p>{message.attachments.map((item) => <span key={item.id} className="chatbot-message__attachment"><FileText size={13} />{item.name}</span>)}</>}{message.visualization && message.status === 'completed' && <ChatVisualization visualization={message.visualization} />}{message.status === 'failed' && <small>답변 생성에 실패했습니다.</small>}</div></article>)}</div><form className="chatbot-composer" onSubmit={(event) => void ask(event)}>{attachment && <div className="chatbot-attachment"><FileText size={14} /><span>{attachment.name}</span><button type="button" aria-label="첨부 파일 제거" onClick={() => setAttachment(null)}><X size={13} /></button></div>}<textarea value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void ask(); } }} placeholder="예: IBM의 2025년 총자산은 얼마인가요?" rows={2} disabled={isRunning} /><div><input ref={attachmentInput} type="file" accept=".txt,.md,.csv,.json,.xlsx,.xlsm" hidden onChange={(event) => { setAttachment(event.target.files?.[0] ?? null); event.target.value = ''; }} /><button type="button" className="chatbot-attach" aria-label="파일 첨부" title="파일 첨부" onClick={() => attachmentInput.current?.click()} disabled={isRunning}><Paperclip size={17} /></button>{isRunning ? <button type="button" className="chatbot-stop" onClick={() => aborter.current?.abort()}><CircleStop size={16} /> 중지</button> : <button type="submit" disabled={!draft.trim()}><Send size={16} /> 질문하기</button>}</div></form></section></div>{dialog && <div className="chatbot-dialog-backdrop" role="presentation" onMouseDown={() => setDialog(null)}><section className="chatbot-dialog" role="dialog" aria-modal="true" aria-labelledby="chatbot-dialog-title" onMouseDown={(event) => event.stopPropagation()}><header><h2 id="chatbot-dialog-title">{dialog.type === 'delete' ? '대화를 삭제하시겠습니까?' : '채팅 이름 변경'}</h2><button type="button" aria-label="닫기" onClick={() => setDialog(null)}><X size={18} /></button></header>{dialog.type === 'delete' ? <p><strong>{dialog.session.title}</strong> 대화와 모든 메시지가 삭제됩니다.</p> : <form onSubmit={(event) => { event.preventDefault(); void renameSession(); }}><label htmlFor="chatbot-title">채팅 이름</label><input id="chatbot-title" value={titleDraft} onChange={(event) => setTitleDraft(event.target.value)} maxLength={80} autoFocus /></form>}<footer><button type="button" className="chatbot-dialog__cancel" onClick={() => setDialog(null)}>취소</button><button type="button" className={dialog.type === 'delete' ? 'chatbot-dialog__danger' : ''} onClick={() => void (dialog.type === 'delete' ? deleteSession() : renameSession())}>{dialog.type === 'delete' ? '삭제' : '변경'}</button></footer></section></div>}</div>;
}
