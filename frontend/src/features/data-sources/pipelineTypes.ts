import type { LucideIcon } from 'lucide-react';
import type { LunaInspectionOutput } from './types';

export interface ModuleStepState {
  id: string;
  name: string;
  moduleType: string;
  category: string;
  icon: LucideIcon;
  status: 'waiting' | 'running' | 'done' | 'failed';
  durationSeconds?: number;
  sublogs: Array<{
    time: string;
    msg: string;
    status?: 'info' | 'running' | 'done' | 'warn' | 'failed';
  }>;
  metaInfo?: Record<string, string | number>;
  batchProgress?: {
    completed: number;
    total: number;
    completedItems?: number;
    totalItems?: number;
  };
}

export interface PipelineRunState {
  pipelineId: string;
  fileName: string;
  workbookHash?: string;
  targetIndexId?: string;
  companyName?: string;
  model: string;
  batchSize: number;
  status: 'queued' | 'running' | 'paused' | 'completed' | 'failed';
  currentStageIndex: number;
  progressPercent: number;
  elapsedSeconds: number;
  modules: ModuleStepState[];
  chunkCount?: number;
  totalTokens?: number;
  costUsd?: number;
  costKrw?: number;
  error?: string | null;
  isLiveUpload?: boolean;
  lunaOutput?: LunaInspectionOutput;
}
