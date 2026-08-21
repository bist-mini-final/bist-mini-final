import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SpreadsheetResultModal } from './SpreadsheetResultModal';

describe('SpreadsheetResultModal', () => {
  it('keeps the selected sheet when polling replaces result object identities', () => {
    const input = { file_name: 'sample.xlsx', sheet_names: ['First', 'Second'] };
    const output = {
      file_name: 'sample.xlsx',
      workbook_hash: 'a'.repeat(64),
      tables: [],
    };
    const { rerender } = render(
      <SpreadsheetResultModal
        kind="luna_vlm"
        input={input}
        output={output}
        onClose={vi.fn()}
      />
    );
    const sheetSelect = screen.getByLabelText('시트') as HTMLSelectElement;
    fireEvent.change(sheetSelect, { target: { value: 'Second' } });
    expect(sheetSelect.value).toBe('Second');

    rerender(
      <SpreadsheetResultModal
        kind="luna_vlm"
        input={{ ...input, sheet_names: [...input.sheet_names] }}
        output={{ ...output, worker_active: true }}
        onClose={vi.fn()}
      />
    );

    expect((screen.getByLabelText('시트') as HTMLSelectElement).value).toBe('Second');
  });
});
