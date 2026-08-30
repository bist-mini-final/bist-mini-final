import { useEffect, useMemo, useRef } from 'react';
import { z } from 'zod';

const PROCESSED_FILE_SELECTOR = 'processed_file_selector' as const;

const BiPlaygroundHandoffSchema = z.object({
  company_id: z.string().min(1),
  file_name: z.string().min(1),
  workbook_hash: z.string().regex(/^[a-f0-9]{64}$/),
  index_id: z.string().min(1),
  metric_id: z.string().min(1),
  period_id: z.string().min(1),
  question: z.string().min(1),
}).strict().transform((value): BiPlaygroundHandoff => ({
  companyId: value.company_id,
  fileName: value.file_name,
  workbookHash: value.workbook_hash,
  indexId: value.index_id,
  metricId: value.metric_id,
  periodId: value.period_id,
  question: value.question,
}));

export type BiPlaygroundHandoff = {
  readonly companyId: string;
  readonly fileName: string;
  readonly workbookHash: string;
  readonly indexId: string;
  readonly metricId: string;
  readonly periodId: string;
  readonly question: string;
};

export type PlaygroundHandoffModule = {
  readonly type: string;
  readonly input_schema: {
    readonly properties?: Record<string, {
      readonly enum?: readonly unknown[];
    }>;
  };
};

export type PlaygroundHandoffNode = {
  readonly data: Record<string, unknown>;
};

export type UsePlaygroundHandoffOptions = {
  readonly modules: readonly PlaygroundHandoffModule[];
  readonly nodes: readonly PlaygroundHandoffNode[];
  readonly ready: boolean;
  readonly search: string;
  readonly setQueryText: (text: string) => void;
};

type NodeValuesUpdater = (patch: Record<string, unknown>) => void;

function findNodeValuesUpdater(
  nodes: readonly PlaygroundHandoffNode[],
  moduleType: string,
): NodeValuesUpdater | null {
  const callback = nodes.find(
    (node) => node.data.moduleType === moduleType,
  )?.data.onValuesChange;
  if (typeof callback !== 'function') return null;
  return (patch) => callback(patch);
}

function availableProcessedFiles(
  modules: readonly PlaygroundHandoffModule[],
): readonly string[] {
  const candidates = modules.find(
    (module) => module.type === PROCESSED_FILE_SELECTOR,
  )?.input_schema.properties?.file_name?.enum ?? [];
  return candidates.filter(
    (candidate): candidate is string => typeof candidate === 'string',
  );
}

export function buildBiPlaygroundHandoffUrl(context: BiPlaygroundHandoff): string {
  const params = new URLSearchParams({
    company_id: context.companyId,
    file_name: context.fileName,
    workbook_hash: context.workbookHash,
    index_id: context.indexId,
    metric_id: context.metricId,
    period_id: context.periodId,
    question: context.question,
  });
  return `/playground?${params.toString()}`;
}

export function parseBiPlaygroundHandoff(search: string): BiPlaygroundHandoff | null {
  const result = BiPlaygroundHandoffSchema.safeParse(
    Object.fromEntries(new URLSearchParams(search)),
  );
  return result.success ? result.data : null;
}

export function useBiPlaygroundHandoff(options: UsePlaygroundHandoffOptions): void {
  const { modules, nodes, ready, search, setQueryText } = options;
  const handoff = useMemo(
    () => parseBiPlaygroundHandoff(search),
    [search],
  );
  const nodesRef = useRef(nodes);
  const modulesRef = useRef(modules);
  const appliedSearchRef = useRef<string | null>(null);
  nodesRef.current = nodes;
  modulesRef.current = modules;

  useEffect(() => {
    if (!ready || !handoff || appliedSearchRef.current === search) return;
    appliedSearchRef.current = search;
    setQueryText(handoff.question);

    const nodes = nodesRef.current;
    const fileUpdater = findNodeValuesUpdater(nodes, PROCESSED_FILE_SELECTOR);
    if (
      fileUpdater
      && availableProcessedFiles(modulesRef.current).includes(handoff.fileName)
    ) {
      fileUpdater({ file_name: handoff.fileName });
    }

  }, [handoff, ready, search, setQueryText]);
}
