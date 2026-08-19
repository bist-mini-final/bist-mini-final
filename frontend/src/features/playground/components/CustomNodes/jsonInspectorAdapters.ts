import type { ModuleType } from '../../types';

export type JsonRow = Record<string, unknown>;

export interface TableInspectorContent {
  kind: 'table';
  label: string;
  preferredColumns: string[];
  rows: JsonRow[];
  totalRows: number;
}

export interface MarkdownInspectorContent {
  kind: 'markdown';
  label: string;
  markdown: string;
  sourceCharacters?: number;
  truncated: boolean;
}

export type JsonInspectorContent = TableInspectorContent | MarkdownInspectorContent;

interface InspectorAdapter {
  accepts: (moduleType: ModuleType | undefined, value: unknown) => boolean;
  adapt: (value: unknown) => JsonInspectorContent | null;
}

const ADAPTER_SAMPLE_SIZE = 24;

export function isJsonRow(value: unknown): value is JsonRow {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function collectionItems(value: unknown): { items: unknown[]; total: number } | null {
  if (Array.isArray(value)) return { items: value, total: value.length };
  if (!isJsonRow(value) || !Array.isArray(value.items)) return null;
  const total = typeof value.count === 'number' ? value.count : value.items.length;
  return { items: value.items, total };
}

function sampleCollection(items: unknown[], count = ADAPTER_SAMPLE_SIZE): unknown[] {
  if (items.length <= count) return items;
  const sampledIndices = new Set<number>();
  while (sampledIndices.size < count) {
    sampledIndices.add(Math.floor(Math.random() * items.length));
  }
  return [...sampledIndices].map((index) => items[index]);
}

function hasSerializedTexts(value: unknown): boolean {
  if (!isJsonRow(value)) return false;
  const collection = collectionItems(value.items);
  if (!collection) return false;
  const candidate = collection.items.find((item) => isJsonRow(item));
  return isJsonRow(candidate) && typeof candidate.text === 'string';
}

function hasAnswer(value: unknown): boolean {
  if (!isJsonRow(value)) return false;
  const answerJson = isJsonRow(value.answer_json) ? value.answer_json : value;
  return typeof answerJson.answer === 'string' || isJsonRow(answerJson.answer);
}

function refinedAnswerJson(value: unknown): JsonRow | null {
  if (!isJsonRow(value)) return null;
  return isJsonRow(value.refined_answer_json)
    ? value.refined_answer_json
    : value;
}

function hasRefinedAnswer(value: unknown): boolean {
  const refined = refinedAnswerJson(value);
  if (!refined) return false;
  return typeof refined.refined_answer === 'string'
    || isJsonRow(refined.refined_answer);
}

function hasSubqueries(value: unknown): boolean {
  return isJsonRow(value) && collectionItems(value.subqueries) !== null;
}

function hasItems(value: unknown): boolean {
  return isJsonRow(value)
    && (collectionItems(value.items) !== null || isJsonRow(value.items));
}

function serializedTextContent(value: unknown): TableInspectorContent | null {
  if (!isJsonRow(value)) return null;
  const collection = collectionItems(value.items);
  if (!collection) return null;
  const rows = sampleCollection(collection.items).flatMap((item) =>
    isJsonRow(item) && typeof item.text === 'string'
      ? [{ text: item.text }]
      : []
  );
  if (rows.length === 0 && collection.total > 0) return null;
  return {
    kind: 'table',
    label: '직렬화 텍스트',
    preferredColumns: ['text'],
    rows,
    totalRows: collection.total,
  };
}

function answerMarkdown(value: unknown): MarkdownInspectorContent | null {
  if (!isJsonRow(value)) return null;
  const answerJson = isJsonRow(value.answer_json) ? value.answer_json : value;
  const answer = answerJson.answer;
  if (typeof answer === 'string') {
    return {
      kind: 'markdown',
      label: 'Reader 답변',
      markdown: answer,
      truncated: false,
    };
  }
  if (!isJsonRow(answer) || typeof answer.preview !== 'string') return null;
  return {
    kind: 'markdown',
    label: 'Reader 답변',
    markdown: answer.preview,
    sourceCharacters: typeof answer.characters === 'number' ? answer.characters : undefined,
    truncated: true,
  };
}

function refinedAnswerMarkdown(value: unknown): MarkdownInspectorContent | null {
  const refined = refinedAnswerJson(value);
  if (!refined) return null;
  const answer = refined.refined_answer;
  if (typeof answer === 'string') {
    return {
      kind: 'markdown',
      label: 'Refiner 개선 답변',
      markdown: answer,
      truncated: false,
    };
  }
  if (!isJsonRow(answer) || typeof answer.preview !== 'string') return null;
  return {
    kind: 'markdown',
    label: 'Refiner 개선 답변',
    markdown: answer.preview,
    sourceCharacters: typeof answer.characters === 'number' ? answer.characters : undefined,
    truncated: true,
  };
}

function subqueryContent(value: unknown): TableInspectorContent | null {
  if (!isJsonRow(value)) return null;
  const collection = collectionItems(value.subqueries);
  if (!collection) return null;
  return {
    kind: 'table',
    label: '서브쿼리',
    preferredColumns: ['query'],
    rows: sampleCollection(collection.items).map((query) => ({ query })),
    totalRows: collection.total,
  };
}

function genericItemsContent(value: unknown): TableInspectorContent | null {
  if (!isJsonRow(value)) return null;
  const collection = collectionItems(value.items);
  if (collection) {
    return {
      kind: 'table',
      label: '행 미리보기',
      preferredColumns: ['text', 'serialized_text', 'cell_id', 'variant'],
      rows: sampleCollection(collection.items).map(
        (item) => isJsonRow(item) ? item : { value: item }
      ),
      totalRows: collection.total,
    };
  }
  if (!isJsonRow(value.items)) return null;
  const rows = Object.entries(value.items).map(([subquery, embedding]) => ({
    subquery,
    embedding,
  }));
  return {
    kind: 'table',
    label: '행 미리보기',
    preferredColumns: ['subquery', 'embedding'],
    rows,
    totalRows: rows.length,
  };
}

function genericContent(value: unknown): TableInspectorContent {
  if (Array.isArray(value)) {
    return {
      kind: 'table',
      label: '행 미리보기',
      preferredColumns: [],
      rows: sampleCollection(value).map(
        (item) => isJsonRow(item) ? item : { value: item }
      ),
      totalRows: value.length,
    };
  }
  return {
    kind: 'table',
    label: 'JSON 미리보기',
    preferredColumns: [],
    rows: [isJsonRow(value) ? value : { value }],
    totalRows: 1,
  };
}

const SERIALIZER_TYPES = new Set<ModuleType>([
  'cell_text_serializer',
  'exhaustive_cell_text_serializer',
]);

const INSPECTOR_ADAPTERS: InspectorAdapter[] = [
  {
    accepts: (moduleType) => moduleType !== undefined && SERIALIZER_TYPES.has(moduleType),
    adapt: serializedTextContent,
  },
  {
    accepts: (moduleType) => moduleType === 'reader',
    adapt: answerMarkdown,
  },
  {
    accepts: (moduleType) => moduleType === 'answer_refiner',
    adapt: refinedAnswerMarkdown,
  },
  {
    accepts: (_moduleType, value) => hasSerializedTexts(value),
    adapt: serializedTextContent,
  },
  {
    accepts: (_moduleType, value) => hasRefinedAnswer(value),
    adapt: refinedAnswerMarkdown,
  },
  {
    accepts: (_moduleType, value) => hasAnswer(value),
    adapt: answerMarkdown,
  },
  {
    accepts: (_moduleType, value) => hasSubqueries(value),
    adapt: subqueryContent,
  },
  {
    accepts: (_moduleType, value) => hasItems(value),
    adapt: genericItemsContent,
  },
];

export function adaptJsonInspectorContent(
  moduleType: ModuleType | undefined,
  value: unknown,
): JsonInspectorContent {
  const adapter = INSPECTOR_ADAPTERS.find(({ accepts }) => accepts(moduleType, value));
  return adapter?.adapt(value) ?? genericContent(value);
}
