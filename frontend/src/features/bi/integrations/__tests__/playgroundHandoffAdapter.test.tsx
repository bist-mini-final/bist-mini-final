import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  buildBiPlaygroundHandoffUrl,
  parseBiPlaygroundHandoff,
  useBiPlaygroundHandoff,
} from '../playgroundHandoffAdapter';

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
  it('round-trips validated dashboard context through search parameters', () => {
    expect(parseBiPlaygroundHandoff(search)).toEqual(context);
  });

  it('rejects incomplete or malformed handoff parameters', () => {
    expect(parseBiPlaygroundHandoff('?company_id=acme&workbook_hash=not-a-hash')).toBeNull();
  });

  it('applies the question and verified file only after the workflow is ready', () => {
    const setQueryText = vi.fn();
    const updateFile = vi.fn();

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

    rerender({ ready: true });

    expect(setQueryText).toHaveBeenCalledWith(context.question);
    expect(updateFile).toHaveBeenCalledWith({ file_name: context.fileName });
  });

  it('does not change the file node when the handed-off file is unavailable', () => {
    const setQueryText = vi.fn();
    const updateFile = vi.fn();

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
      ],
      ready: true,
      search,
      setQueryText,
    }));

    expect(setQueryText).toHaveBeenCalledWith(context.question);
    expect(updateFile).not.toHaveBeenCalled();
  });
});
