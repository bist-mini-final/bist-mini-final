import { useEffect, useRef, useState } from 'react';
import type { PipelineRunState } from '../pipelineTypes';
import { SpreadsheetResultModal } from '../../playground/components/SpreadsheetResults/SpreadsheetResultModal';
import {
  AutoReturnBanner,
  PipelineHud,
  PipelineModuleList,
  PipelineStateNotice,
  PipelineTrackerHeader,
} from './PipelineTrackerSections';

interface TrackerProps {
  pipeline: PipelineRunState;
  onBack: () => void;
  onResume?: () => void;
  onCancel?: () => void;
  onDelete?: () => void;
  isCancelling?: boolean;
  isDeleting?: boolean;
}

/** Coordinates tracker-only UI state while presentation stays in focused sections. */
export function PipelineTrackerView({
  pipeline,
  onBack,
  onResume,
  onCancel,
  onDelete,
  isCancelling = false,
  isDeleting = false,
}: TrackerProps) {
  const [openModuleIds, setOpenModuleIds] = useState<Record<string, boolean>>({
    [pipeline.modules[pipeline.currentStageIndex]?.id || '']: true,
  });
  const [autoReturnSeconds, setAutoReturnSeconds] = useState<number | null>(null);
  const [isAutoReturnPaused, setIsAutoReturnPaused] = useState(false);
  const [isLunaInspectorOpen, setIsLunaInspectorOpen] = useState(false);
  const autoReturnTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const activeModule = pipeline.modules[pipeline.currentStageIndex];
    if (!activeModule) return;
    setOpenModuleIds((current) => ({ ...current, [activeModule.id]: true }));
  }, [pipeline.currentStageIndex, pipeline.modules]);

  useEffect(() => {
    if (pipeline.isLiveUpload && pipeline.status === 'completed' && autoReturnSeconds === null) {
      setAutoReturnSeconds(4);
    }
  }, [pipeline.isLiveUpload, pipeline.status, autoReturnSeconds]);

  useEffect(() => {
    if (
      autoReturnSeconds !== null
      && autoReturnSeconds > 0
      && !isAutoReturnPaused
      && !isLunaInspectorOpen
    ) {
      autoReturnTimerRef.current = setTimeout(() => {
        setAutoReturnSeconds((current) => current !== null ? current - 1 : null);
      }, 1000);
    } else if (autoReturnSeconds === 0) {
      onBack();
    }

    return () => {
      if (autoReturnTimerRef.current) clearTimeout(autoReturnTimerRef.current);
    };
  }, [autoReturnSeconds, isAutoReturnPaused, isLunaInspectorOpen, onBack]);

  const toggleModule = (moduleId: string) => {
    setOpenModuleIds((current) => ({ ...current, [moduleId]: !current[moduleId] }));
  };

  return (
    <div className="ds-pipeline-tracker">
      <PipelineTrackerHeader
        pipeline={pipeline}
        isCancelling={isCancelling}
        isDeleting={isDeleting}
        onBack={onBack}
        onCancel={onCancel}
        onDelete={onDelete}
      />

      <PipelineStateNotice pipeline={pipeline} onResume={onResume} />

      {pipeline.isLiveUpload
        && pipeline.status === 'completed'
        && autoReturnSeconds !== null
        && (
          <AutoReturnBanner
            seconds={autoReturnSeconds}
            paused={isAutoReturnPaused}
            onTogglePaused={() => setIsAutoReturnPaused((current) => !current)}
            onBack={onBack}
          />
        )}

      <div className="ds-pipeline-grid">
        <PipelineModuleList
          pipeline={pipeline}
          openModuleIds={openModuleIds}
          onToggleModule={toggleModule}
          onInspectLuna={() => setIsLunaInspectorOpen(true)}
        />
        <PipelineHud pipeline={pipeline} />
      </div>

      {isLunaInspectorOpen && pipeline.lunaOutput && (
        <SpreadsheetResultModal
          kind="luna_vlm"
          input={{
            file_name: pipeline.fileName,
            sheet_names: pipeline.lunaOutput.sheet_names || [],
          }}
          output={pipeline.lunaOutput}
          onClose={() => setIsLunaInspectorOpen(false)}
        />
      )}
    </div>
  );
}
