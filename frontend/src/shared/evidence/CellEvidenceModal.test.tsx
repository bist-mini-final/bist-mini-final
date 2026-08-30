import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CellEvidenceModal } from './CellEvidenceModal';
import { cellEvidenceApi, type CellEvidence } from './cellEvidenceApi';

vi.mock('./cellEvidenceApi', () => ({
  cellEvidenceApi: {
    resolve: vi.fn(),
    imageUrl: vi.fn(() => '/evidence/sheet.png'),
  },
}));

const evidence: CellEvidence = {
  company_name: 'IBM',
  index_id: 'idx-1',
  file_name: 'ibm.xlsx',
  workbook_hash: 'hash-1',
  sheet_name: 'Income Statement',
  cell_coord: 'E16',
  cell_value: '$62,753M',
  row_header: ['Revenue'],
  column_header: ['FY2024'],
  source_text: 'Revenue FY2024',
  image: {
    rendered_available: false,
    typed_available: true,
    image_width: null,
    image_height: null,
    cell_bbox_px: null,
    unavailable_reason: '테스트에서는 이미지를 생략합니다.',
  },
};

describe('CellEvidenceModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(cellEvidenceApi.resolve).mockReset().mockResolvedValue(evidence);
    vi.mocked(cellEvidenceApi.imageUrl).mockReset().mockReturnValue('/evidence/sheet.png');
  });

  it('uses the shared accessible dialog and resolves citation metadata', async () => {
    const onClose = vi.fn();
    render(
      <CellEvidenceModal
        citation={{ sheet: 'Income Statement', cell: 'E16', company: 'IBM' }}
        onClose={onClose}
      />,
    );

    expect(screen.getByRole('dialog', { name: /셀 원본 근거 검증/ }))
      .toHaveAttribute('aria-modal', 'true');
    expect(await screen.findByText('$62,753M')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: '근거 검증 닫기' })).toHaveFocus());

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('shows a terminal error state and can retry resolution', async () => {
    vi.mocked(cellEvidenceApi.resolve)
      .mockRejectedValueOnce(new Error('인덱스에서 셀을 찾지 못했습니다.'))
      .mockResolvedValueOnce(evidence);

    render(
      <CellEvidenceModal
        citation={{ sheet: 'Income Statement', cell: 'E16', company: 'Coldplay' }}
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('인덱스에서 셀을 찾지 못했습니다.');
    expect(screen.queryByText('원본 시트를 준비하는 중입니다.')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));

    expect(await screen.findByText('$62,753M')).toBeInTheDocument();
    expect(cellEvidenceApi.resolve).toHaveBeenCalledTimes(2);
  });

  it('pans a rendered source sheet by dragging the viewport', async () => {
    vi.mocked(cellEvidenceApi.resolve).mockResolvedValue({
      ...evidence,
      image: {
        rendered_available: true,
        typed_available: true,
        image_width: 1600,
        image_height: 1000,
        cell_bbox_px: [400, 180, 510, 205],
        unavailable_reason: null,
      },
    });

    render(
      <CellEvidenceModal
        citation={{ sheet: 'Income Statement', cell: 'E16', company: 'IBM' }}
        onClose={vi.fn()}
      />,
    );
    await screen.findByAltText('Income Statement 원본 시트');
    const viewport = screen.getByRole('region', { name: '원본 시트 캔버스 · 드래그하여 이동' });
    viewport.scrollLeft = 200;
    viewport.scrollTop = 150;

    fireEvent.pointerDown(viewport, { button: 0, pointerId: 7, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(viewport, { pointerId: 7, clientX: 60, clientY: 70 });

    expect(viewport).toHaveClass('is-dragging');
    expect(viewport.scrollLeft).toBe(240);
    expect(viewport.scrollTop).toBe(180);

    fireEvent.pointerUp(viewport, { pointerId: 7, clientX: 60, clientY: 70 });
    expect(viewport).not.toHaveClass('is-dragging');
  });
});
