import type { BiCardId } from '../bi/types';
import type { WorkflowRun } from '../playground/types';
import type { StructuredCellEvidence } from '../../shared/markdown/cellCitations';

export interface ChatVisualization {
  readonly company_id: string;
  readonly card_id: BiCardId;
}

export interface ChatAttachment {
  readonly id: string;
  readonly name: string;
  readonly content_type: string | null;
  readonly size: number;
  readonly created_at?: string;
}

export interface ChatMessage {
  readonly id: string;
  readonly role: 'user' | 'assistant';
  readonly content: string;
  readonly status: 'processing' | 'completed' | 'failed';
  readonly run_id: string | null;
  readonly visualization: ChatVisualization | null;
  readonly evidence: readonly StructuredCellEvidence[];
  readonly attachments: ChatAttachment[];
  readonly created_at: string;
}

export interface ChatSession {
  readonly id: string;
  readonly title: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly messages?: ChatMessage[];
}

export interface ChatTurn {
  readonly run: WorkflowRun;
  readonly message: ChatMessage | null;
}

export interface ChatProgressStep {
  readonly id: string;
  readonly label: string;
  readonly state: 'active' | 'completed';
}

export type ChatDialogState =
  | { readonly type: 'rename'; readonly session: ChatSession }
  | { readonly type: 'delete'; readonly session: ChatSession }
  | null;
