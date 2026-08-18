import { getCardDefinition } from '../config/cardRegistry';
import { buildCardViewModel } from '../selectors/cardViewModel';
import type { BiCardId, BiCardLayoutItem, BiDashboardSnapshot, CardSize, PeriodRange } from '../types';
import { BiCardShell } from './BiCardShell';

interface BiDashboardGridProps {
  readonly dashboard: BiDashboardSnapshot;
  readonly cards: readonly BiCardLayoutItem[];
  readonly periodRange: PeriodRange;
  readonly isEditing: boolean;
  readonly onMoveCard: (cardId: BiCardId, direction: -1 | 1) => void;
  readonly onResizeCard: (cardId: BiCardId, size: CardSize) => void;
  readonly onHideCard: (cardId: BiCardId) => void;
  readonly onShowEvidence: (cardId: BiCardId) => void;
}

export function BiDashboardGrid(props: BiDashboardGridProps) {
  return (
    <section id="bi-dashboard" className="bi-dashboard" aria-label="기업 재무 카드" aria-live="polite">
      {props.cards.map((layoutItem, index) => {
        const definition = getCardDefinition(layoutItem.cardId);
        const viewModel = buildCardViewModel({
          definition,
          dashboard: props.dashboard,
          range: props.periodRange,
          size: layoutItem.size,
        });
        return (
          <BiCardShell
            key={layoutItem.cardId}
            definition={definition}
            viewModel={viewModel}
            size={layoutItem.size}
            periodLabel={props.periodRange}
            isEditing={props.isEditing}
            isFirst={index === 0}
            isLast={index === props.cards.length - 1}
            onMove={(direction) => props.onMoveCard(layoutItem.cardId, direction)}
            onResize={(size) => props.onResizeCard(layoutItem.cardId, size)}
            onHide={() => props.onHideCard(layoutItem.cardId)}
            onShowEvidence={() => props.onShowEvidence(layoutItem.cardId)}
          />
        );
      })}
    </section>
  );
}
