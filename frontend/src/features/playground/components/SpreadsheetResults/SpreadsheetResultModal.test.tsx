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

  it('supports keyboard dismissal and restores an explicit close action', () => {
    const onClose = vi.fn();
    render(
      <SpreadsheetResultModal
        kind="luna_vlm"
        input={{ file_name: 'sample.xlsx', sheet_names: ['Sheet1'] }}
        output={{ file_name: 'sample.xlsx', workbook_hash: 'b'.repeat(64), tables: [] }}
        onClose={onClose}
      />
    );

    expect(screen.getByRole('button', { name: '결과 검사 창 닫기' })).toHaveFocus();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('updates zoom and lets the sidebar separator resize with the keyboard', () => {
    render(
      <SpreadsheetResultModal
        kind="luna_vlm"
        input={{ file_name: 'sample.xlsx', sheet_names: ['Sheet1'] }}
        output={{ file_name: 'sample.xlsx', workbook_hash: 'c'.repeat(64), tables: [] }}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText('60%')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '확대' }));
    expect(screen.getByText('70%')).toBeInTheDocument();

    const separator = screen.getByRole('slider', { name: '결과 정보 패널 너비 조절' });
    expect(separator).toHaveAttribute('aria-valuenow', '400');
    fireEvent.keyDown(separator, { key: 'ArrowRight' });
    expect(separator).toHaveAttribute('aria-valuenow', '424');
  });

  it('switches between typed and rendered artifact layers', () => {
    render(
      <SpreadsheetResultModal
        kind="luna_vlm"
        input={{ file_name: 'sample.xlsx', sheet_names: ['Sheet1'] }}
        output={{ file_name: 'sample.xlsx', workbook_hash: 'd'.repeat(64), tables: [] }}
        onClose={vi.fn()}
      />
    );

    const image = screen.getByRole('img', { name: 'Sheet1 Excel 렌더링' });
    expect(image).toHaveAttribute('src', expect.stringContaining('layer=typed'));
    fireEvent.click(screen.getByRole('checkbox', { name: '셀 타입 색상' }));
    expect(image).toHaveAttribute('src', expect.stringContaining('layer=rendered'));
  });
});
