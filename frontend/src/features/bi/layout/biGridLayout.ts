import type { Layout, LayoutItem } from 'react-grid-layout';
import { getCardDefinition } from '../config/cardRegistry';
import type {
  BiCardGridSize,
  BiCardId,
  BiCardLayoutItem,
  BiCardRow,
  BiResizableGridBreakpoint,
  CardSize,
} from '../types';
import {
  BI_MAX_CARDS_PER_ROW,
  getBiCardRows,
  getResponsiveBiCardRows,
  normalizeBiCardRows,
} from './biRowLayout';

export const BI_GRID_BREAKPOINTS = { wide: 1100, medium: 680, compact: 0 } as const;
export const BI_GRID_COLUMNS = { wide: 17, medium: 8, compact: 1 } as const;
export const BI_GRID_CARDS_PER_ROW = { wide: BI_MAX_CARDS_PER_ROW, medium: 2, compact: 1 } as const;
export type BiGridBreakpoint = keyof typeof BI_GRID_BREAKPOINTS;

function getCardWidth(cardId: BiCardId, size: CardSize, columns: number): number {
  if (columns === BI_GRID_COLUMNS.compact) return 1;
  if (columns === BI_GRID_COLUMNS.medium) return size === 'L' ? 8 : 4;
  const definition = getCardDefinition(cardId);
  if (size === definition.defaultSize) return definition.defaultWideSpan;
  if (size === 'S') return 5;
  if (size === 'M') return 8;
  return 17;
}

function getCardHeight(cardId: BiCardId, size: CardSize, columns: number): number {
  if (columns === BI_GRID_COLUMNS.compact) return 14;
  if (columns === BI_GRID_COLUMNS.medium) return size === 'L' ? 14 : 12;
  const definition = getCardDefinition(cardId);
  if (size === definition.defaultSize) return definition.defaultWideHeight;
  if (size === 'S') return 12;
  if (size === 'M') return 11;
  return 14;
}

export function getCardPresetGridSize(
  cardId: BiCardId,
  size: CardSize,
  breakpoint: BiResizableGridBreakpoint,
): BiCardGridSize {
  const columns = BI_GRID_COLUMNS[breakpoint];
  return {
    w: getCardWidth(cardId, size, columns),
    h: getCardHeight(cardId, size, columns),
  };
}

function getCardSizeLimits(cardId: BiCardId, breakpoint: BiResizableGridBreakpoint) {
  const definition = getCardDefinition(cardId);
  const presetSizes = definition.allowedSizes.map((size) => getCardPresetGridSize(cardId, size, breakpoint));
  return {
    minW: Math.min(...presetSizes.map((size) => size.w)),
    maxW: BI_GRID_COLUMNS[breakpoint],
    minH: Math.floor(Math.min(...presetSizes.map((size) => size.h))),
    maxH: 20,
  };
}

export function constrainBiCardGridSize(
  cardId: BiCardId,
  breakpoint: BiResizableGridBreakpoint,
  size: BiCardGridSize,
): BiCardGridSize {
  const limits = getCardSizeLimits(cardId, breakpoint);
  return {
    w: Math.min(limits.maxW, Math.max(limits.minW, size.w)),
    h: Math.min(limits.maxH, Math.max(limits.minH, size.h)),
  };
}

function getCardGridSize(card: BiCardLayoutItem, breakpoint: BiGridBreakpoint): BiCardGridSize {
  if (breakpoint === 'compact') return { w: 1, h: 14 };
  return constrainBiCardGridSize(card.cardId, breakpoint, card.gridSizes[breakpoint]);
}

function packCards(cards: readonly BiCardLayoutItem[], breakpoint: BiGridBreakpoint) {
  const columns = BI_GRID_COLUMNS[breakpoint];
  const cardsPerRow = BI_GRID_CARDS_PER_ROW[breakpoint];
  const cardsById = new Map(cards.map((card) => [card.cardId, card]));
  const rows = getResponsiveBiCardRows(getBiCardRows(cards), cardsPerRow).map((row) => (
    row.cardIds.flatMap((cardId) => {
      const card = cardsById.get(cardId);
      return card ? [card] : [];
    })
  ));

  let cursorY = 0;
  return rows.flatMap((row) => {
    const height = Math.max(...row.map((card) => getCardGridSize(card, breakpoint).h));
    const equalWidth = columns / row.length;
    let cursorX = 0;
    const positions = row.map((card, index) => {
      const width = index === row.length - 1 ? columns - cursorX : equalWidth;
      const position = { card, x: cursorX, y: cursorY, width, height };
      cursorX += width;
      return position;
    });
    cursorY += height;
    return positions;
  });
}

export function getBiGridBreakpoint(containerWidth: number): BiGridBreakpoint {
  if (containerWidth >= BI_GRID_BREAKPOINTS.wide) return 'wide';
  if (containerWidth >= BI_GRID_BREAKPOINTS.medium) return 'medium';
  return 'compact';
}

export function normalizeWideCardLayout(cards: readonly BiCardLayoutItem[]): BiCardLayoutItem[] {
  const cardsById = new Map(cards.map((card) => [card.cardId, card]));
  const rows = normalizeBiCardRows(getBiCardRows(cards), cards.map((card) => card.cardId));
  const orderedCards = rows.flatMap((row) => row.cardIds.flatMap((cardId) => {
    const card = cardsById.get(cardId);
    return card ? [{ ...card, rowId: row.rowId }] : [];
  }));
  return packCards(orderedCards, 'wide').map(({ card, x, y }) => ({ ...card, x, y }));
}

export function applyBiCardRows(
  cards: readonly BiCardLayoutItem[],
  rows: readonly BiCardRow[],
): BiCardLayoutItem[] {
  const cardsById = new Map(cards.map((card) => [card.cardId, card]));
  return normalizeWideCardLayout(rows.flatMap((row) => row.cardIds.flatMap((cardId) => {
    const card = cardsById.get(cardId);
    return card ? [{ ...card, rowId: row.rowId }] : [];
  })));
}

export function createBiGridLayout(
  cards: readonly BiCardLayoutItem[],
  breakpoint: BiGridBreakpoint,
  isEditing: boolean,
): Layout {
  return packCards(cards, breakpoint).map(({ card, x, y, width, height }) => {
    return {
      i: card.cardId,
      x,
      y,
      w: width,
      h: height,
      minW: width,
      maxW: width,
      minH: height,
      maxH: height,
      isDraggable: isEditing,
      isResizable: false,
    } satisfies LayoutItem;
  });
}

export function findNearestCardSize(cardId: BiCardId, width: number, columns: number): CardSize {
  const definition = getCardDefinition(cardId);
  return definition.allowedSizes.reduce((nearest, size) => {
    const nearestDistance = Math.abs(getCardWidth(cardId, nearest, columns) - width);
    const candidateDistance = Math.abs(getCardWidth(cardId, size, columns) - width);
    return candidateDistance < nearestDistance ? size : nearest;
  }, definition.defaultSize);
}
