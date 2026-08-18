import { MessageCircleQuestion, Search } from 'lucide-react';
import type { BiCardDefinition } from '../config/cardRegistry';
import type { BiCardViewModel } from '../selectors/cardViewModel';
import type { CardSize, PeriodRange } from '../types';
import { CardEditMenu } from './CardEditMenu';

interface BiCardShellProps {
  readonly definition: BiCardDefinition;
  readonly viewModel: BiCardViewModel;
  readonly size: CardSize;
  readonly periodLabel: PeriodRange;
  readonly isEditing: boolean;
  readonly isFirst: boolean;
  readonly isLast: boolean;
  readonly onMove: (direction: -1 | 1) => void;
  readonly onResize: (size: CardSize) => void;
  readonly onHide: () => void;
  readonly onShowEvidence: () => void;
}

export function BiCardShell(props: BiCardShellProps) {
  const Icon = props.definition.icon;
  const showPeriodValues = props.size !== 'S';

  return (
    <article
      className="bi-card"
      data-size={props.size}
      data-editing={props.isEditing}
      data-state={props.viewModel.state}
    >
      <header className="bi-card__header">
        <span className="bi-card__icon"><Icon size={18} aria-hidden="true" /></span>
        <div className="bi-card__heading">
          <div className="bi-card__title-row">
            <h3>{props.definition.title}</h3>
            <span className="bi-card__state">{props.viewModel.stateLabel}</span>
          </div>
          <p>{props.definition.description}</p>
        </div>
        {props.isEditing ? (
          <CardEditMenu
            size={props.size}
            allowedSizes={props.definition.allowedSizes}
            isFirst={props.isFirst}
            isLast={props.isLast}
            onMove={props.onMove}
            onResize={props.onResize}
            onHide={props.onHide}
          />
        ) : null}
      </header>

      <div className="bi-card__metric">
        <span>{props.viewModel.primaryLabel}</span>
        <strong>{props.viewModel.primaryValue}</strong>
        {props.viewModel.secondaryLabel && props.viewModel.secondaryValue ? (
          <small>{props.viewModel.secondaryLabel} {props.viewModel.secondaryValue}</small>
        ) : null}
      </div>

      {showPeriodValues ? (
        <div className="bi-card__period-values">
          <div className="bi-card__period-values-heading">
            <span>기간별 수치</span><small>차트 연결 전 값 검증</small>
          </div>
          <div className="bi-card__value-grid">
            {props.viewModel.rows.map((row) => (
              <div key={row.periodLabel} data-status={row.status}>
                <span>{row.periodLabel}</span><strong>{row.value}</strong>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="bi-card__compact-note">소형 카드는 대표값만 표시합니다.</p>
      )}

      <footer className="bi-card__footer">
        <div className="bi-card__meta">
          <span>{props.periodLabel}</span><span>{props.viewModel.unitLabel}</span><span>{props.size} 카드</span>
        </div>
        <div className="bi-card__actions">
          <button type="button" disabled={props.viewModel.evidence.length === 0} onClick={props.onShowEvidence}>
            <Search size={14} aria-hidden="true" />근거 보기
          </button>
          <button type="button" disabled aria-describedby={`${props.definition.id}-chatbot-note`}>
            <MessageCircleQuestion size={14} aria-hidden="true" />챗봇 질문
          </button>
        </div>
        <span className="bi-card__deferred-note" id={`${props.definition.id}-chatbot-note`}>챗봇 연결은 다음 단계입니다.</span>
      </footer>
    </article>
  );
}
