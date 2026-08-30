import { EyeOff, GripVertical, Search } from 'lucide-react';
import { Button, IconButton, StatusBadge } from '../../../shared/ui';
import type { BiCardDefinition } from '../config/cardRegistry';
import type { BiCardViewModel } from '../selectors/cardViewModel';
import type { BiDashboardSnapshot, CardMoveDirection, CardSize, PeriodRange } from '../types';
import { BiCardChart } from './charts/BiCardChart';

interface BiCardShellProps {
  readonly definition: BiCardDefinition;
  readonly dashboard: BiDashboardSnapshot;
  readonly viewModel: BiCardViewModel;
  readonly size: CardSize;
  readonly layoutLabel: string;
  readonly periodLabel: PeriodRange;
  readonly isEditing: boolean;
  readonly canMove: (direction: CardMoveDirection) => boolean;
  readonly onMove: (direction: CardMoveDirection) => void;
  readonly onHide: () => void;
  readonly onShowEvidence: () => void;
}

export function BiCardShell(props: BiCardShellProps) {
  const Icon = props.definition.icon;
  const showChart = props.viewModel.state === 'ready' || props.viewModel.state === 'partial';
  const chartOwnsSummary = props.definition.id === 'cash_flow'
    || props.definition.id === 'stability'
    || props.definition.id === 'financial_scale'
    || props.definition.id === 'financial_health_heatmap';

  return (
    <article
      className="bi-card"
      data-size={props.size}
      data-card-id={props.definition.id}
      data-editing={props.isEditing}
      data-state={props.viewModel.state}
    >
      <header className="bi-card__header">
        {props.isEditing ? (
          <button
            className="bi-card__drag-handle"
            type="button"
            aria-label={`${props.definition.title} 카드 위치 변경. 방향키로 이동`}
            onKeyDown={(event) => {
              const direction = event.key === 'ArrowUp'
                ? 'up'
                : event.key === 'ArrowDown'
                  ? 'down'
                  : event.key === 'ArrowLeft'
                    ? 'left'
                    : event.key === 'ArrowRight'
                      ? 'right'
                      : null;
              if (!direction) return;
              event.preventDefault();
              if (props.canMove(direction)) props.onMove(direction);
            }}
          >
            <GripVertical size={17} aria-hidden="true" />
          </button>
        ) : null}
        <span className="bi-card__icon"><Icon size={18} aria-hidden="true" /></span>
        <div className="bi-card__heading">
          <div className="bi-card__title-row">
            <h3>{props.definition.title}</h3>
            <StatusBadge
              className="bi-card__state"
              tone={props.viewModel.state === 'ready' ? 'success' : 'warning'}
            >
              {props.viewModel.stateLabel}
            </StatusBadge>
            {props.isEditing ? (
              <IconButton
                className="bi-card__hide-button"
                variant="danger"
                size="sm"
                type="button"
                aria-label={`${props.definition.title} 카드 숨기기`}
                title="카드 숨기기"
                onClick={props.onHide}
              >
                <EyeOff size={15} aria-hidden="true" />
              </IconButton>
            ) : null}
          </div>
          <p>{props.definition.description}</p>
        </div>
      </header>

      {!chartOwnsSummary ? (
        <div className="bi-card__metric">
          <span>{props.viewModel.primaryLabel}</span>
          <strong>{props.viewModel.primaryValue}</strong>
          {props.viewModel.secondaryLabel && props.viewModel.secondaryValue ? (
            <small>{props.viewModel.secondaryLabel} {props.viewModel.secondaryValue}</small>
          ) : null}
        </div>
      ) : null}

      {showChart ? (
        <BiCardChart
          cardId={props.definition.id}
          dashboard={props.dashboard}
          range={props.periodLabel}
          size={props.size}
        />
      ) : (
        <div className="bi-card__state-panel" data-state={props.viewModel.state}>
          <strong>{props.viewModel.stateLabel}</strong>
          <span>
            {props.viewModel.state === 'ambiguous'
              ? `${props.viewModel.primaryLabel}: ${props.viewModel.primaryValue}`
              : '원본 값과 단위를 확인한 뒤 차트를 표시합니다.'}
          </span>
        </div>
      )}

      <footer className="bi-card__footer">
        <div className="bi-card__meta">
          <span>{props.periodLabel}</span><span>{props.viewModel.unitLabel}</span><span>{props.layoutLabel}</span>
        </div>
        <div className="bi-card__actions">
          <Button size="sm" type="button" disabled={props.viewModel.evidence.length === 0} onClick={props.onShowEvidence}>
            <Search size={14} aria-hidden="true" />근거 보기
          </Button>
        </div>
      </footer>
    </article>
  );
}
