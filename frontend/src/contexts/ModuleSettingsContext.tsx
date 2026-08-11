import { createContext, useContext } from 'react';

type OpenModuleSettings = (nodeId: string) => void;

export const ModuleSettingsContext = createContext<OpenModuleSettings | null>(null);

export function useOpenModuleSettings() {
  return useContext(ModuleSettingsContext);
}
