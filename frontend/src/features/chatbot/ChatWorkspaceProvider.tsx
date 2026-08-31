import { createContext, useContext, type ReactNode } from 'react';
import { useChatController } from './useChatController';

type ChatWorkspace = ReturnType<typeof useChatController>;

const ChatWorkspaceContext = createContext<ChatWorkspace | null>(null);

interface ChatWorkspaceProviderProps {
  readonly children: ReactNode;
}

/** Keeps chat state and session history available while users move between app features. */
export function ChatWorkspaceProvider({ children }: ChatWorkspaceProviderProps) {
  const chat = useChatController();
  return (
    <ChatWorkspaceContext.Provider value={chat}>
      {children}
    </ChatWorkspaceContext.Provider>
  );
}

export function useChatWorkspace(): ChatWorkspace {
  const value = useContext(ChatWorkspaceContext);
  if (!value) {
    throw new Error('useChatWorkspace must be used inside ChatWorkspaceProvider.');
  }
  return value;
}
