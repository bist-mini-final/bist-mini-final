import { useChatWorkspace } from './ChatWorkspaceProvider';
import { ChatComposer } from './ChatComposer';
import { ChatMessages } from './ChatMessages';
import './chatbot.css';

export function ChatbotView() {
  const chat = useChatWorkspace();

  return (
    <div className="chatbot-page">
      <h1 className="page-visually-hidden">AI 금융 챗봇</h1>

      <div className="chatbot-layout">
        <section className="chatbot-panel">
          <ChatMessages
            messages={chat.messages}
            progress={chat.progress}
            pendingTurn={chat.pendingTurn}
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
    </div>
  );
}
