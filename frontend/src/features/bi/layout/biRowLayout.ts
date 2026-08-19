import type {
  BiCardDropTarget,
  BiCardId,
  BiCardLayoutItem,
  BiCardRow,
  CardMoveDirection,
} from '../types';

export const BI_MAX_CARDS_PER_ROW = 3;

function getAvailableRowId(baseId: string, usedRowIds: ReadonlySet<string>): string {
  if (!usedRowIds.has(baseId)) return baseId;
  let suffix = 2;
  while (usedRowIds.has(`${baseId}-${suffix}`)) suffix += 1;
  return `${baseId}-${suffix}`;
}

export function normalizeBiCardRows(
  rows: readonly BiCardRow[],
  visibleCardIds: readonly BiCardId[],
): readonly BiCardRow[] {
  const visibleIds = new Set(visibleCardIds);
  const seenCardIds = new Set<BiCardId>();
  const usedRowIds = new Set<string>();
  const normalizedRows: BiCardRow[] = [];

  rows.forEach((row, rowIndex) => {
    const cardIds = row.cardIds.filter((cardId) => {
      if (!visibleIds.has(cardId) || seenCardIds.has(cardId)) return false;
      seenCardIds.add(cardId);
      return true;
    });
    for (let start = 0; start < cardIds.length; start += BI_MAX_CARDS_PER_ROW) {
      const baseId = row.rowId.trim() || `row-${rowIndex + 1}`;
      const preferredId = start === 0 ? baseId : `${baseId}-${start / BI_MAX_CARDS_PER_ROW + 1}`;
      const rowId = getAvailableRowId(preferredId, usedRowIds);
      usedRowIds.add(rowId);
      normalizedRows.push({ rowId, cardIds: cardIds.slice(start, start + BI_MAX_CARDS_PER_ROW) });
    }
  });

  visibleCardIds.forEach((cardId) => {
    if (seenCardIds.has(cardId)) return;
    const rowId = getAvailableRowId(`row-${cardId}`, usedRowIds);
    usedRowIds.add(rowId);
    normalizedRows.push({ rowId, cardIds: [cardId] });
  });
  return normalizedRows;
}

export function getBiCardRows(cards: readonly BiCardLayoutItem[]): readonly BiCardRow[] {
  const rows: Array<{ rowId: string; cardIds: BiCardId[] }> = [];
  const rowIndexes = new Map<string, number>();
  cards.forEach((card) => {
    const rowIndex = rowIndexes.get(card.rowId);
    if (rowIndex !== undefined) {
      rows[rowIndex]?.cardIds.push(card.cardId);
      return;
    }
    rowIndexes.set(card.rowId, rows.length);
    rows.push({ rowId: card.rowId, cardIds: [card.cardId] });
  });
  return rows;
}

export function getResponsiveBiCardRows(
  rows: readonly BiCardRow[],
  cardsPerRow: number,
): readonly BiCardRow[] {
  return rows.flatMap((row) => {
    const segments: BiCardRow[] = [];
    for (let start = 0; start < row.cardIds.length; start += cardsPerRow) {
      segments.push({ rowId: row.rowId, cardIds: row.cardIds.slice(start, start + cardsPerRow) });
    }
    return segments;
  });
}

export function projectBiCardRows(
  rows: readonly BiCardRow[],
  cardId: BiCardId,
  target: BiCardDropTarget,
): readonly BiCardRow[] | null {
  const remainingRows = rows.flatMap((row) => {
    const cardIds = row.cardIds.filter((candidate) => candidate !== cardId);
    return cardIds.length > 0 ? [{ ...row, cardIds }] : [];
  });

  if (target.kind === 'new-row') {
    if (remainingRows.some((row) => row.rowId === target.rowId)) return null;
    const insertionIndex = target.beforeRowId === null
      ? remainingRows.length
      : remainingRows.findIndex((row) => row.rowId === target.beforeRowId);
    const nextRows = [...remainingRows];
    nextRows.splice(insertionIndex < 0 ? nextRows.length : insertionIndex, 0, {
      rowId: target.rowId,
      cardIds: [cardId],
    });
    return nextRows;
  }

  const targetIndex = remainingRows.findIndex((row) => row.rowId === target.rowId);
  const targetRow = remainingRows[targetIndex];
  if (!targetRow || targetRow.cardIds.length >= BI_MAX_CARDS_PER_ROW) return null;
  const cardIds = [...targetRow.cardIds];
  cardIds.splice(Math.min(Math.max(target.cardIndex, 0), cardIds.length), 0, cardId);
  return remainingRows.map((row, index) => index === targetIndex ? { ...row, cardIds } : row);
}

export function moveBiCardInRows(
  rows: readonly BiCardRow[],
  cardId: BiCardId,
  direction: CardMoveDirection,
): readonly BiCardRow[] | null {
  const sourceRowIndex = rows.findIndex((row) => row.cardIds.includes(cardId));
  const sourceRow = rows[sourceRowIndex];
  if (!sourceRow) return null;
  const cardIndex = sourceRow.cardIds.indexOf(cardId);

  if (direction === 'left' || direction === 'right') {
    const targetIndex = direction === 'left' ? cardIndex - 1 : cardIndex + 1;
    if (targetIndex < 0 || targetIndex >= sourceRow.cardIds.length) return null;
    const cardIds = [...sourceRow.cardIds];
    const targetCard = cardIds[targetIndex];
    if (!targetCard) return null;
    cardIds[targetIndex] = cardId;
    cardIds[cardIndex] = targetCard;
    return rows.map((row, index) => index === sourceRowIndex ? { ...row, cardIds } : row);
  }

  const targetRowIndex = direction === 'up' ? sourceRowIndex - 1 : sourceRowIndex + 1;
  const targetRow = rows[targetRowIndex];
  if (targetRow && targetRow.cardIds.length < BI_MAX_CARDS_PER_ROW) {
    return projectBiCardRows(rows, cardId, {
      kind: 'row',
      rowId: targetRow.rowId,
      cardIndex: Math.min(cardIndex, targetRow.cardIds.length),
    });
  }
  if (!targetRow && sourceRow.cardIds.length === 1) return null;

  const usedRowIds = new Set(rows.map((row) => row.rowId));
  const beforeRowId = direction === 'up' ? sourceRow.rowId : targetRow?.rowId ?? null;
  return projectBiCardRows(rows, cardId, {
    kind: 'new-row',
    beforeRowId,
    rowId: getAvailableRowId(`row-${cardId}`, usedRowIds),
  });
}
