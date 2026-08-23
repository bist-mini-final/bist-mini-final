import { useEffect, useRef, useState } from 'react';
import { DEFAULT_CARD_LAYOUT, getCardDefinition, isBiCardId } from '../config/cardRegistry';
import {
  applyBiCardRows,
  constrainBiCardGridSize,
  getCardPresetGridSize,
  normalizeWideCardLayout,
} from '../layout/biGridLayout';
import { getBiCardRows, moveBiCardInRows } from '../layout/biRowLayout';
import type {
  BiCardGridSize,
  BiCardId,
  BiCardLayoutItem,
  BiResizableGridBreakpoint,
  CardMoveDirection,
  CardSize,
} from '../types';

const STORAGE_KEY = 'rag-flow:bi-layout:v3';

interface StoredLayout {
  readonly schemaVersion: 3;
  readonly cards: readonly BiCardLayoutItem[];
  readonly hiddenCardIds: readonly BiCardId[];
}

interface BiLayoutController extends StoredLayout {
  readonly canMoveCard: (cardId: BiCardId, direction: CardMoveDirection) => boolean;
  readonly moveCard: (cardId: BiCardId, direction: CardMoveDirection) => void;
  readonly replaceCards: (cards: readonly BiCardLayoutItem[]) => void;
  readonly hideCard: (cardId: BiCardId) => void;
  readonly restoreCard: (cardId: BiCardId) => void;
  readonly resetLayout: () => void;
}

const DEFAULT_LAYOUT: StoredLayout = {
  schemaVersion: 3,
  cards: DEFAULT_CARD_LAYOUT,
  hiddenCardIds: [],
};

function isAllowedSize(cardId: BiCardId, value: unknown): value is CardSize {
  return typeof value === 'string'
    && getCardDefinition(cardId).allowedSizes.some((size) => size === value);
}

function isUnknownRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readGridCoordinate(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : fallback;
}

function readGridSize(
  cardId: BiCardId,
  breakpoint: BiResizableGridBreakpoint,
  value: unknown,
  fallback: BiCardGridSize,
): BiCardGridSize {
  if (!isUnknownRecord(value)) return fallback;
  const w = readGridCoordinate(value.w, fallback.w);
  const h = readGridCoordinate(value.h, fallback.h);
  return constrainBiCardGridSize(cardId, breakpoint, { w, h });
}

function normalizeLayout(value: unknown): StoredLayout {
  if (!isUnknownRecord(value)) return DEFAULT_LAYOUT;
  const candidate = value;
  if (candidate.schemaVersion !== 3 || !Array.isArray(candidate.cards)) {
    return DEFAULT_LAYOUT;
  }

  const seen = new Set<BiCardId>();
  const cards = candidate.cards.flatMap((item) => {
    if (!isUnknownRecord(item)) return [];
    const card = item;
    if (!isBiCardId(card.cardId) || seen.has(card.cardId)) return [];
    if (typeof card.rowId !== 'string' || !card.rowId.trim()) return [];
    seen.add(card.cardId);
    const definition = getCardDefinition(card.cardId);
    const fallback = DEFAULT_CARD_LAYOUT.find((item) => item.cardId === card.cardId);
    const size = isAllowedSize(card.cardId, card.size) ? card.size : definition.defaultSize;
    const gridSizes = isUnknownRecord(card.gridSizes) ? card.gridSizes : {};
    const x = readGridCoordinate(card.x, fallback?.x ?? 0);
    const y = readGridCoordinate(card.y, fallback?.y ?? 0);
    return [{
      cardId: card.cardId,
      rowId: card.rowId,
      size,
      x,
      y,
      gridSizes: {
        wide: readGridSize(card.cardId, 'wide', gridSizes.wide, getCardPresetGridSize(card.cardId, size, 'wide')),
        medium: readGridSize(card.cardId, 'medium', gridSizes.medium, getCardPresetGridSize(card.cardId, size, 'medium')),
      },
    }];
  });
  const hiddenCardIds = Array.isArray(candidate.hiddenCardIds)
    ? candidate.hiddenCardIds.filter((cardId): cardId is BiCardId => isBiCardId(cardId) && !seen.has(cardId))
    : [];
  const uniqueHidden = [...new Set(hiddenCardIds)];
  const accountedFor = new Set([...cards.map((card) => card.cardId), ...uniqueHidden]);
  if (accountedFor.size === 0) return DEFAULT_LAYOUT;
  const newCardIds = DEFAULT_CARD_LAYOUT
    .map((card) => card.cardId)
    .filter((cardId) => !accountedFor.has(cardId));
  return {
    schemaVersion: 3,
    cards: normalizeWideCardLayout(cards),
    hiddenCardIds: [...uniqueHidden, ...newCardIds],
  };
}

function readStoredLayout(): StoredLayout {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored ? normalizeLayout(JSON.parse(stored)) : DEFAULT_LAYOUT;
  } catch (error) {
    if (error instanceof SyntaxError || error instanceof DOMException) return DEFAULT_LAYOUT;
    throw error;
  }
}

export function useBiLayout(): BiLayoutController {
  const [layout, setLayout] = useState<StoredLayout>(readStoredLayout);
  const skipNextPersist = useRef(false);

  useEffect(() => {
    if (skipNextPersist.current) {
      skipNextPersist.current = false;
      return;
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
    } catch (error) {
      if (!(error instanceof DOMException)) throw error;
    }
  }, [layout]);

  const canMoveCard = (cardId: BiCardId, direction: CardMoveDirection) => (
    moveBiCardInRows(getBiCardRows(layout.cards), cardId, direction) !== null
  );

  const moveCard = (cardId: BiCardId, direction: CardMoveDirection) => {
    setLayout((current) => {
      const rows = moveBiCardInRows(getBiCardRows(current.cards), cardId, direction);
      return rows ? { ...current, cards: applyBiCardRows(current.cards, rows) } : current;
    });
  };

  const replaceCards = (cards: readonly BiCardLayoutItem[]) => {
    setLayout((current) => ({ ...current, cards: normalizeWideCardLayout(cards) }));
  };

  const hideCard = (cardId: BiCardId) => {
    setLayout((current) => ({
      ...current,
      cards: normalizeWideCardLayout(current.cards.filter((card) => card.cardId !== cardId)),
      hiddenCardIds: current.hiddenCardIds.includes(cardId)
        ? current.hiddenCardIds
        : [...current.hiddenCardIds, cardId],
    }));
  };

  const restoreCard = (cardId: BiCardId) => {
    setLayout((current) => {
      if (current.cards.some((card) => card.cardId === cardId)) return current;
      const definition = getCardDefinition(cardId);
      const fallback = DEFAULT_CARD_LAYOUT.find((card) => card.cardId === cardId);
      const restoredCard: BiCardLayoutItem = {
        cardId,
        rowId: `row-${crypto.randomUUID()}`,
        size: fallback?.size ?? definition.defaultSize,
        x: 0,
        y: current.cards.reduce((maximum, card) => Math.max(maximum, card.y), 0) + 10,
        gridSizes: fallback?.gridSizes ?? {
          wide: getCardPresetGridSize(cardId, definition.defaultSize, 'wide'),
          medium: getCardPresetGridSize(cardId, definition.defaultSize, 'medium'),
        },
      };
      return {
        ...current,
        cards: normalizeWideCardLayout([...current.cards, restoredCard]),
        hiddenCardIds: current.hiddenCardIds.filter((hiddenId) => hiddenId !== cardId),
      };
    });
  };

  const resetLayout = () => {
    window.localStorage.removeItem(STORAGE_KEY);
    skipNextPersist.current = true;
    setLayout({ schemaVersion: 3, cards: [...DEFAULT_CARD_LAYOUT], hiddenCardIds: [] });
  };

  return { ...layout, canMoveCard, moveCard, replaceCards, hideCard, restoreCard, resetLayout };
}
