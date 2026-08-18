import { useEffect, useRef, useState } from 'react';
import { DEFAULT_CARD_LAYOUT, getCardDefinition, isBiCardId } from '../config/cardRegistry';
import type { BiCardId, BiCardLayoutItem, CardSize } from '../types';

const STORAGE_KEY = 'rag-flow:bi-layout:v1';

interface StoredLayout {
  readonly schemaVersion: 1;
  readonly cards: readonly BiCardLayoutItem[];
  readonly hiddenCardIds: readonly BiCardId[];
}

interface BiLayoutController extends StoredLayout {
  readonly moveCard: (cardId: BiCardId, direction: -1 | 1) => void;
  readonly resizeCard: (cardId: BiCardId, size: CardSize) => void;
  readonly hideCard: (cardId: BiCardId) => void;
  readonly restoreCard: (cardId: BiCardId) => void;
  readonly resetLayout: () => void;
}

const DEFAULT_LAYOUT: StoredLayout = {
  schemaVersion: 1,
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

function normalizeLayout(value: unknown): StoredLayout {
  if (!isUnknownRecord(value)) return DEFAULT_LAYOUT;
  const candidate = value;
  if (candidate.schemaVersion !== 1 || !Array.isArray(candidate.cards)) return DEFAULT_LAYOUT;

  const seen = new Set<BiCardId>();
  const cards = candidate.cards.flatMap((item) => {
    if (!isUnknownRecord(item)) return [];
    const card = item;
    if (!isBiCardId(card.cardId) || seen.has(card.cardId)) return [];
    seen.add(card.cardId);
    const definition = getCardDefinition(card.cardId);
    return [{ cardId: card.cardId, size: isAllowedSize(card.cardId, card.size) ? card.size : definition.defaultSize }];
  });
  const hiddenCardIds = Array.isArray(candidate.hiddenCardIds)
    ? candidate.hiddenCardIds.filter((cardId): cardId is BiCardId => isBiCardId(cardId) && !seen.has(cardId))
    : [];
  const uniqueHidden = [...new Set(hiddenCardIds)];
  const accountedFor = new Set([...cards.map((card) => card.cardId), ...uniqueHidden]);
  const appended = DEFAULT_CARD_LAYOUT.filter((card) => !accountedFor.has(card.cardId));
  return { schemaVersion: 1, cards: [...cards, ...appended], hiddenCardIds: uniqueHidden };
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

  const moveCard = (cardId: BiCardId, direction: -1 | 1) => {
    setLayout((current) => {
      const index = current.cards.findIndex((card) => card.cardId === cardId);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= current.cards.length) return current;
      const cards = [...current.cards];
      const currentCard = cards[index];
      const nextCard = cards[nextIndex];
      if (!currentCard || !nextCard) return current;
      cards[index] = nextCard;
      cards[nextIndex] = currentCard;
      return { ...current, cards };
    });
  };

  const resizeCard = (cardId: BiCardId, size: CardSize) => {
    if (!isAllowedSize(cardId, size)) return;
    setLayout((current) => ({
      ...current,
      cards: current.cards.map((card) => card.cardId === cardId ? { ...card, size } : card),
    }));
  };

  const hideCard = (cardId: BiCardId) => {
    setLayout((current) => ({
      ...current,
      cards: current.cards.filter((card) => card.cardId !== cardId),
      hiddenCardIds: current.hiddenCardIds.includes(cardId)
        ? current.hiddenCardIds
        : [...current.hiddenCardIds, cardId],
    }));
  };

  const restoreCard = (cardId: BiCardId) => {
    setLayout((current) => ({
      ...current,
      cards: current.cards.some((card) => card.cardId === cardId)
        ? current.cards
        : [...current.cards, { cardId, size: getCardDefinition(cardId).defaultSize }],
      hiddenCardIds: current.hiddenCardIds.filter((hiddenId) => hiddenId !== cardId),
    }));
  };

  const resetLayout = () => {
    window.localStorage.removeItem(STORAGE_KEY);
    skipNextPersist.current = true;
    setLayout({ schemaVersion: 1, cards: [...DEFAULT_CARD_LAYOUT], hiddenCardIds: [] });
  };

  return { ...layout, moveCard, resizeCard, hideCard, restoreCard, resetLayout };
}
