import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  buildBiPlaygroundHandoffUrl,
  parseBiPlaygroundHandoff,
  useBiPlaygroundHandoff,
} from '../playgroundHandoffAdapter';

const mocks = vi.hoisted(() => ({
  listIndexes: vi.fn(),
}));

vi.mock('../../../data-sources/services/dataSourceApi', () => ({
  dataSourceApi: {
    listIndexes: mocks.listIndexes,
  },
}));

const context = {
  companyId: 'acme',
  fileName: 'acme.xlsx',
  workbookHash: 'a'.repeat(64),
  indexId: 'index-acme',
  metricId: 'revenue',
  periodId: 'fy-2025',
  question: 'ACME의 매출을 FY2025 기준으로 설명해줘.',
};

const search = new URL(
  buildBiPlaygroundHandoffUrl(context),
  'http://localhost',
).search;

describe('BI Playground handoff adapter', () => {
  beforeEach(() => {
    mocks.listIndexes.mockReset();
  });

  it('round-trips validated dashboard context through search parameters', () => {
    expect(parseBiPlaygroundHandoff(search)).toEqual(context);
  });

  it('rejects incomplete or malformed handoff parameters', () => {
    expect(parseBiPlaygroundHandoff('?company_id=acme&workbook_hash=not-a-hash')).toBeNull();
  });

  it('applies the question and verified file and index only after the workflow is ready', async () => {
    const setQueryText = vi.fn();
    const updateFile = vi.fn();
    const updateIndex = vi.fn();
    mocks.listIndexes.mockResolvedValue([{ index_id: context.indexId }]);

    const options = {
      modules: [{
        type: 'processed_file_selector',
        input_schema: {
          properties: {
            file_name: { enum: ['other.xlsx', context.fileName] },
          },
        },
      }],
      nodes: [
        {
          data: {
            moduleType: 'processed_file_selector',
            onValuesChange: updateFile,
          },
        },
        {
          data: {
            moduleType: 'pgvector_collection_loader',
            onValuesChange: updateIndex,
          },
        },
      ],
      search,
      setQueryText,
    };

    const { rerender } = renderHook(
      ({ ready }) => useBiPlaygroundHandoff({ ...options, ready }),
      { initialProps: { ready: false } },
    );

    expect(setQueryText).not.toHaveBeenCalled();
    expect(updateFile).not.toHaveBeenCalled();
    expect(updateIndex).not.toHaveBeenCalled();

    rerender({ ready: true });

    expect(setQueryText).toHaveBeenCalledWith(context.question);
    expect(updateFile).toHaveBeenCalledWith({ file_name: context.fileName });
    await waitFor(() => {
      expect(updateIndex).toHaveBeenCalledWith({
        collection_name: context.indexId,
        collection_names: [context.indexId],
      });
    });
  });

  it('keeps existing node selections when the file and index are unavailable', async () => {
    const setQueryText = vi.fn();
    const updateFile = vi.fn();
    const updateIndex = vi.fn();
    mocks.listIndexes.mockResolvedValue([{ index_id: 'another-index' }]);

    renderHook(() => useBiPlaygroundHandoff({
      modules: [{
        type: 'processed_file_selector',
        input_schema: {
          properties: {
            file_name: { enum: ['other.xlsx'] },
          },
        },
      }],
      nodes: [
        {
          data: {
            moduleType: 'processed_file_selector',
            onValuesChange: updateFile,
          },
        },
        {
          data: {
            moduleType: 'pgvector_collection_loader',
            onValuesChange: updateIndex,
          },
        },
      ],
      ready: true,
      search,
      setQueryText,
    }));

    expect(setQueryText).toHaveBeenCalledWith(context.question);
    expect(updateFile).not.toHaveBeenCalled();
    await waitFor(() => expect(mocks.listIndexes).toHaveBeenCalledOnce());
    expect(updateIndex).not.toHaveBeenCalled();
  });
});
