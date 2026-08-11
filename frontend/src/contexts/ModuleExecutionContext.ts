import { createContext, useContext } from 'react';

export interface ModuleExecutionContextValue {
  onExecuteNode: (nodeId: string) => void;
  onStopExecution: () => void;
  onClearNodeResult: (nodeId: string) => void;
  isExecuting: boolean;
}

export const ModuleExecutionContext = createContext<ModuleExecutionContextValue>({
  onExecuteNode: () => {},
  onStopExecution: () => {},
  onClearNodeResult: () => {},
  isExecuting: false,
});

export function useModuleExecution() {
  return useContext(ModuleExecutionContext);
}
