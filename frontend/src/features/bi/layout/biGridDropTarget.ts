import type { BiCardId, BiCardLayoutItem, BiCardRow } from '../types';
import {
  applyBiCardRows,
  BI_GRID_CARDS_PER_ROW,
  BI_GRID_COLUMNS,
  createBiGridLayout,
  type BiGridBreakpoint,
} from './biGridLayout';
import { getBiGridRect, type BiGridGeometry } from './biGridGeometry';
import {
  BI_MAX_CARDS_PER_ROW,
  getBiCardRows,
  getResponsiveBiCardRows,
  projectBiCardRows,
} from './biRowLayout';

interface BiGridDropProjectionInput extends Omit<BiGridGeometry, 'columns'> {
  readonly activeCardId: BiCardId;
  readonly breakpoint: BiGridBreakpoint;
  readonly cards: readonly BiCardLayoutItem[];
  readonly newRowId: string;
  readonly pointerX: number;
  readonly pointerY: number;
}

export type BiGridDropProjection =
  | {
    readonly cards: readonly BiCardLayoutItem[];
    readonly kind: 'valid';
    readonly targetKind: 'new-row' | 'row';
  }
  | {
    readonly cards: readonly BiCardLayoutItem[];
    readonly invalidCardIds: readonly BiCardId[];
    readonly kind: 'invalid';
  };

interface VisibleRowSegment {
  readonly bottom: number;
  readonly cardIds: readonly BiCardId[];
  readonly rowId: string;
  readonly top: number;
}

function withoutCard(rows: readonly BiCardRow[], cardId: BiCardId): readonly BiCardRow[] {
  return rows.flatMap((row) => {
    const cardIds = row.cardIds.filter((candidate) => candidate !== cardId);
    return cardIds.length > 0 ? [{ ...row, cardIds }] : [];
  });
}

function getVisibleSegments(
  cards: readonly BiCardLayoutItem[],
  rows: readonly BiCardRow[],
  breakpoint: BiGridBreakpoint,
  geometry: BiGridGeometry,
): readonly VisibleRowSegment[] {
  const layoutById = new Map(createBiGridLayout(cards, breakpoint, false).map((item) => [item.i, item]));
  return getResponsiveBiCardRows(rows, BI_GRID_CARDS_PER_ROW[breakpoint]).flatMap((row) => {
    const rects = row.cardIds.flatMap((cardId) => {
      const item = layoutById.get(cardId);
      return item ? [{ cardId, ...getBiGridRect(item, geometry) }] : [];
    });
    if (rects.length === 0) return [];
    return [{
      bottom: Math.max(...rects.map((rect) => rect.y + rect.blockSize)),
      cardIds: rects.map((rect) => rect.cardId),
      rowId: row.rowId,
      top: Math.min(...rects.map((rect) => rect.y)),
    }];
  });
}

function getNewRowTarget(
  rows: readonly BiCardRow[],
  segments: readonly VisibleRowSegment[],
  pointerY: number,
  marginY: number,
): string | null | undefined {
  const rowBounds = rows.flatMap((row) => {
    const matching = segments.filter((segment) => segment.rowId === row.rowId);
    if (matching.length === 0) return [];
    return [{
      bottom: Math.max(...matching.map((segment) => segment.bottom)),
      rowId: row.rowId,
      top: Math.min(...matching.map((segment) => segment.top)),
    }];
  });
  if (rowBounds.length === 0) return null;
  const lastRow = rowBounds[rowBounds.length - 1];

  const candidates = [
    { beforeRowId: rowBounds[0]?.rowId ?? null, distance: Math.abs(pointerY - (rowBounds[0]?.top ?? 0)), threshold: 12 },
    ...rowBounds.slice(1).map((row, index) => ({
      beforeRowId: row.rowId,
      distance: Math.abs(pointerY - ((rowBounds[index]?.bottom ?? row.top) + row.top) / 2),
      threshold: Math.max(12, marginY * 1.5),
    })),
    {
      beforeRowId: null,
      distance: Math.abs(pointerY - (lastRow?.bottom ?? 0)),
      threshold: 12,
    },
  ].sort((left, right) => left.distance - right.distance);
  const nearest = candidates[0];
  return nearest && nearest.distance <= nearest.threshold ? nearest.beforeRowId : undefined;
}

function distanceToSegment(pointerY: number, segment: VisibleRowSegment): number {
  if (pointerY < segment.top) return segment.top - pointerY;
  if (pointerY > segment.bottom) return pointerY - segment.bottom;
  return 0;
}

export function projectBiGridDrop(input: BiGridDropProjectionInput): BiGridDropProjection {
  const sourceRows = getBiCardRows(input.cards);
  const remainingRows = withoutCard(sourceRows, input.activeCardId);
  const remainingCards = applyBiCardRows(input.cards, remainingRows);
  const geometry: BiGridGeometry = {
    columns: BI_GRID_COLUMNS[input.breakpoint],
    containerWidth: input.containerWidth,
    margin: input.margin,
    rowHeight: input.rowHeight,
  };
  const segments = getVisibleSegments(remainingCards, remainingRows, input.breakpoint, geometry);
  const beforeRowId = getNewRowTarget(remainingRows, segments, input.pointerY, input.margin[1]);
  if (beforeRowId !== undefined) {
    const rows = projectBiCardRows(sourceRows, input.activeCardId, {
      beforeRowId,
      kind: 'new-row',
      rowId: input.newRowId,
    });
    return rows
      ? { cards: applyBiCardRows(input.cards, rows), kind: 'valid', targetKind: 'new-row' }
      : { cards: input.cards, invalidCardIds: [], kind: 'invalid' };
  }

  const segment = [...segments].sort((left, right) => (
    distanceToSegment(input.pointerY, left) - distanceToSegment(input.pointerY, right)
  ))[0];
  const targetRow = segment ? remainingRows.find((row) => row.rowId === segment.rowId) : undefined;
  if (!segment || !targetRow) {
    return { cards: input.cards, invalidCardIds: [], kind: 'invalid' };
  }
  if (targetRow.cardIds.length >= BI_MAX_CARDS_PER_ROW) {
    return { cards: input.cards, invalidCardIds: targetRow.cardIds, kind: 'invalid' };
  }

  const layoutById = new Map(createBiGridLayout(remainingCards, input.breakpoint, false).map((item) => [item.i, item]));
  const localIndex = segment.cardIds.filter((cardId) => {
    const item = layoutById.get(cardId);
    if (!item) return false;
    const rect = getBiGridRect(item, geometry);
    return rect.x + rect.inlineSize / 2 < input.pointerX;
  }).length;
  const firstSegmentCard = segment.cardIds[0];
  const segmentStart = firstSegmentCard ? targetRow.cardIds.indexOf(firstSegmentCard) : 0;
  const rows = projectBiCardRows(sourceRows, input.activeCardId, {
    cardIndex: Math.max(0, segmentStart) + localIndex,
    kind: 'row',
    rowId: targetRow.rowId,
  });
  return rows
    ? { cards: applyBiCardRows(input.cards, rows), kind: 'valid', targetKind: 'row' }
    : { cards: input.cards, invalidCardIds: targetRow.cardIds, kind: 'invalid' };
}
