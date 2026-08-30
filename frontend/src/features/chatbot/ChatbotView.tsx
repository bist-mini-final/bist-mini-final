import { ConfirmDialog, PromptDialog } from '../../shared/ui';
import { ChatComposer } from './ChatComposer';
import { ChatMessages } from './ChatMessages';
import { ChatSessionSidebar } from './ChatSessionSidebar';
import { useChatController } from './useChatController';
import './chatbot.css';

export function ChatbotView() {
  const chat = useChatController();

  return (
    <div className="chatbot-page">
      <h1 className="page-visually-hidden">AI 금융 챗봇</h1>

      <ChatSessionSidebar
        sessions={chat.sessions}
        activeSessionId={chat.active?.id}
        disabled={chat.isRunning}
        onNewSession={chat.newSession}
        onSelectSession={(sessionId) => { void chat.selectSession(sessionId); }}
        onRenameSession={chat.requestRename}
        onDeleteSession={chat.requestDelete}
      />

      <div className="chatbot-layout">
        <section className="chatbot-panel">
          <ChatMessages
            messages={chat.messages}
            progress={chat.progress}
            examples={chat.examples}
            isRunning={chat.isRunning}
            isRefreshingSuggestions={chat.isRefreshingSuggestions}
            requestError={chat.requestError}
            onAskExample={(example) => { void chat.ask(example); }}
            onRefreshSuggestions={() => { void chat.refreshSuggestions(); }}
          />
          <ChatComposer
            draft={chat.draft}
            attachment={chat.attachment}
            isRunning={chat.isRunning}
            onDraftChange={chat.setDraft}
            onAttachmentChange={chat.setAttachment}
            onAsk={() => { void chat.ask(); }}
            onStop={chat.stop}
          />
        </section>
      </div>

      <ConfirmDialog
        open={chat.dialog?.type === 'delete'}
        tone="danger"
        title="대화를 삭제하시겠습니까?"
        description="대화와 포함된 모든 메시지가 영구 삭제됩니다."
        detail={chat.dialog?.type === 'delete' ? chat.dialog.session.title : undefined}
        confirmLabel="대화 삭제"
        busy={chat.isDialogBusy}
        error={chat.dialogError}
        onClose={chat.closeDialog}
        onConfirm={() => { void chat.deleteSession(); }}
      />
      <PromptDialog
        open={chat.dialog?.type === 'rename'}
        title="대화 이름 변경"
        description="사이드바에서 구분하기 쉬운 이름을 입력하세요."
        label="대화 이름"
        initialValue={chat.dialog?.type === 'rename' ? chat.dialog.session.title : ''}
        confirmLabel="이름 변경"
        busy={chat.isDialogBusy}
        error={chat.dialogError}
        onClose={chat.closeDialog}
        onConfirm={(title) => { void chat.renameSession(title); }}
      />
    </div>
  );
}
