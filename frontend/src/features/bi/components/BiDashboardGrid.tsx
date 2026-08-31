import { useEffect, useRef, useState } from 'react';
import { createUuid } from '../../../shared/lib/uuid';
import {
  ResponsiveGridLayout,
  verticalCompactor,
  type EventCallback,
  type LayoutItem,
  type ResponsiveLayouts,
} from 'react-grid-layout';
import { getCardDefinition, isBiCardId } from '../config/cardRegistry';
import {
  BI_GRID_BREAKPOINTS,
  BI_GRID_COLUMNS,
  createBiGridLayout,
  findNearestCardSize,
  getBiGridBreakpoint,
  type BiGridBreakpoint,
} from '../layout/biGridLayout';
import { projectBiGridDrop } from '../layout/biGridDropTarget';
import { buildCardViewModel } from '../selectors/cardViewModel';
import type { BiCardId, BiCardLayoutItem, BiDashboardSnapshot, CardMoveDirection, PeriodRange } from '../types';
import { BiCardShell } from './BiCardShell';
import { BiGridDragPreview } from './BiGridDragPreview';

interface BiDashboardGridProps {
  readonly dashboard: BiDashboardSnapshot;
  readonly cards: readonly BiCardLayoutItem[];
  readonly periodRange: PeriodRange;
  readonly isEditing: boolean;
  readonly canMoveCard: (cardId: BiCardId, direction: CardMoveDirection) => boolean;
  readonly onMoveCard: (cardId: BiCardId, direction: CardMoveDirection) => void;
  readonly onReplaceCards: (cards: readonly BiCardLayoutItem[]) => void;
  readonly onHideCard: (cardId: BiCardId) => void;
  readonly onShowEvidence: (cardId: BiCardId) => void;
}

function useGridWidth() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return undefined;
    const updateWidth = () => setWidth(element.getBoundingClientRect().width);
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return { containerRef, width };
}

function getPointerPosition(event: Event) {
  if (event instanceof MouseEvent) return { x: event.clientX, y: event.clientY };
  if (event instanceof TouchEvent) {
    const touch = event.touches[0] ?? event.changedTouches[0];
    return touch ? { x: touch.clientX, y: touch.clientY } : null;
  }
  return null;
}

interface DragPreviewState {
  readonly activeCardId: BiCardId;
  readonly cards: readonly BiCardLayoutItem[];
  readonly invalidCardIds: readonly BiCardId[];
  readonly targetKind: 'new-row' | 'row' | null;
}

function getPreviewKey(preview: DragPreviewState): string {
  return [
    preview.activeCardId,
    preview.targetKind ?? 'invalid',
    ...preview.cards.map((card) => `${card.rowId}/${card.cardId}`),
    ...preview.invalidCardIds,
  ].join(':');
}

export function BiDashboardGrid(props: BiDashboardGridProps) {
  const { width, containerRef } = useGridWidth();
  const breakpoint = getBiGridBreakpoint(width);
  const columns = BI_GRID_COLUMNS[breakpoint];
  const [announcement, setAnnouncement] = useState('');
  const [dragPreview, setDragPreview] = useState<DragPreviewState | null>(null);
  const dragPreviewRef = useRef<DragPreviewState | null>(null);
  const dragRowIdRef = useRef<string | null>(null);
  const [layoutRevision, setLayoutRevision] = useState(0);
  const layouts: ResponsiveLayouts<BiGridBreakpoint> = {
    wide: createBiGridLayout(props.cards, 'wide', props.isEditing),
    medium: createBiGridLayout(props.cards, 'medium', props.isEditing),
    compact: createBiGridLayout(props.cards, 'compact', props.isEditing),
  };
  const layoutKey = `${props.cards.map((card) => `${card.rowId}/${card.cardId}`).join(':')}:${layoutRevision}`;
  const rowHeight = breakpoint === 'wide' ? 20 : breakpoint === 'medium' ? 22 : 24;
  const margin: [number, number] = breakpoint === 'wide' ? [10, 10] : [12, 12];

  const updateDragPreview = (activeItem: LayoutItem | null, event: Event) => {
    const pointer = getPointerPosition(event);
    const measure = containerRef.current;
    if (!activeItem || !isBiCardId(activeItem.i) || !pointer || !measure || width <= 0) return;
    const activeCardId = activeItem.i;
    dragRowIdRef.current ??= `row-${createUuid()}`;
    const bounds = measure.getBoundingClientRect();
    const projection = projectBiGridDrop({
      activeCardId,
      breakpoint,
      cards: props.cards,
      containerWidth: width,
      margin,
      newRowId: dragRowIdRef.current,
      pointerX: pointer.x - bounds.left,
      pointerY: pointer.y - bounds.top,
      rowHeight,
    });
    const nextPreview: DragPreviewState = projection.kind === 'valid'
      ? { activeCardId, cards: projection.cards, invalidCardIds: [], targetKind: projection.targetKind }
      : { activeCardId, cards: projection.cards, invalidCardIds: projection.invalidCardIds, targetKind: null };
    dragPreviewRef.current = nextPreview;
    setDragPreview((current) => {
      return current && getPreviewKey(current) === getPreviewKey(nextPreview) ? current : nextPreview;
    });
  };

  const handleDragStart: EventCallback = (_layout, _oldItem, newItem, _placeholder, event) => {
    dragRowIdRef.current = `row-${createUuid()}`;
    updateDragPreview(newItem, event);
  };

  const handleDrag: EventCallback = (_layout, _oldItem, newItem, _placeholder, event) => {
    updateDragPreview(newItem, event);
  };

  const handleDragStop: EventCallback = (_layout, _oldItem, newItem, _placeholder, event) => {
    updateDragPreview(newItem, event);
    const finalPreview = dragPreviewRef.current;
    if (finalPreview?.targetKind) props.onReplaceCards(finalPreview.cards);
    setLayoutRevision((current) => current + 1);
    setDragPreview(null);
    dragPreviewRef.current = null;
    dragRowIdRef.current = null;
    if (newItem && isBiCardId(newItem.i)) {
      setAnnouncement(finalPreview?.targetKind
        ? `${getCardDefinition(newItem.i).title} 카드 위치를 저장했습니다.`
        : '한 행에는 카드를 최대 3개까지 배치할 수 있습니다.');
    }
  };

  const orderedCards = (layouts[breakpoint] ?? []).flatMap((item) => {
    const card = props.cards.find((candidate) => candidate.cardId === item.i);
    return card ? [{ card, gridItem: item }] : [];
  });
  const cardElements = orderedCards.map(({ card: layoutItem, gridItem }) => {
    const definition = getCardDefinition(layoutItem.cardId);
    const displaySize = breakpoint === 'compact'
      ? layoutItem.size
      : findNearestCardSize(layoutItem.cardId, gridItem.w, columns);
    const viewModel = buildCardViewModel({
      definition,
      dashboard: props.dashboard,
      range: props.periodRange,
      size: displaySize,
    });
    return (
      <div key={layoutItem.cardId} className="bi-grid-item" data-card-grid-id={layoutItem.cardId}>
        <BiCardShell
          definition={definition}
          dashboard={props.dashboard}
          viewModel={viewModel}
          size={displaySize}
          layoutLabel={`${displaySize} 카드`}
          periodLabel={props.periodRange}
          isEditing={props.isEditing}
          canMove={(direction) => props.canMoveCard(layoutItem.cardId, direction)}
          onMove={(direction) => {
            props.onMoveCard(layoutItem.cardId, direction);
            const directionLabel = { up: '위', down: '아래', left: '왼쪽', right: '오른쪽' }[direction];
            setAnnouncement(`${definition.title} 카드를 ${directionLabel}으로 이동했습니다.`);
          }}
          onHide={() => props.onHideCard(layoutItem.cardId)}
          onShowEvidence={() => props.onShowEvidence(layoutItem.cardId)}
        />
      </div>
    );
  });

  return (
    <section
      id="bi-dashboard"
      className="bi-dashboard"
      aria-label="기업 재무 카드"
      data-editing={props.isEditing}
    >
      <span className="bi-visually-hidden" aria-live="polite">{announcement}</span>
      <div ref={containerRef} className="bi-dashboard__measure">
        {dragPreview && width > 0 ? (
          <BiGridDragPreview
            activeCardId={dragPreview.activeCardId}
            columns={columns}
            containerWidth={width}
            layout={createBiGridLayout(dragPreview.cards, breakpoint, false)}
            margin={margin}
            rowHeight={rowHeight}
            invalidCardIds={dragPreview.invalidCardIds}
            targetKind={dragPreview.targetKind}
          />
        ) : null}
        {width > 0 ? (
          <ResponsiveGridLayout<BiGridBreakpoint>
            key={layoutKey}
            width={width}
            breakpoint={breakpoint}
            breakpoints={BI_GRID_BREAKPOINTS}
            cols={BI_GRID_COLUMNS}
            layouts={layouts}
            rowHeight={rowHeight}
            margin={margin}
            containerPadding={[0, 0]}
            compactor={verticalCompactor}
            dragConfig={{
              enabled: props.isEditing,
              bounded: true,
              handle: '.bi-card__drag-handle',
              cancel: 'button:not(.bi-card__drag-handle), summary, details, a, [role="button"]',
            }}
            resizeConfig={{ enabled: false, handles: [] }}
            onDragStart={handleDragStart}
            onDrag={handleDrag}
            onDragStop={handleDragStop}
          >
            {cardElements}
          </ResponsiveGridLayout>
        ) : cardElements}
      </div>
    </section>
  );
}
