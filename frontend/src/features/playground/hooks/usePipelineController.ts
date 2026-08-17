import { useCallback, useEffect, useState } from 'react';
import { INITIAL_QUERY } from '../config/pipeline';
import { pipelineApi } from '../services/api';
import type {
  ModuleDefinition,
  WorkflowRun,
} from '../types';

export function usePipelineController() {
  const [modules, setModules] = useState<ModuleDefinition[]>([]);
  const [queryText, setQueryText] = useState(INITIAL_QUERY);
  const [activeStep, setActiveStep] = useState(-1);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    pipelineApi
      .getModules(controller.signal)
      .then((response) => setModules(response.modules))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setErrorMessage('백엔드 모듈 정의를 불러오지 못했습니다.');
        }
      });
    return () => controller.abort();
  }, []);

  const reset = useCallback(() => {
    setActiveStep(-1);
    setQueryText('');
    setErrorMessage(null);
  }, []);

  const clearResults = useCallback(() => {
    setActiveStep(-1);
    setErrorMessage(null);
  }, []);

  const applyWorkflowRun = useCallback((run: WorkflowRun) => {
    const progressedBatches = run.batches.filter((batch) => batch.status !== 'pending');
    setActiveStep(
      progressedBatches.length
        ? progressedBatches[progressedBatches.length - 1].index
        : -1
    );
  }, []);

  return {
    modules,
    queryText,
    setQueryText,
    activeStep,
    errorMessage,
    dismissError: () => setErrorMessage(null),
    reportError: (message: string) => setErrorMessage(message),
    applyWorkflowRun,
    reset,
    clearResults,
  };
}
