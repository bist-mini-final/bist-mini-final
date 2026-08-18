import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, EyeOff, SlidersHorizontal } from 'lucide-react';
import type { CardSize } from '../types';

interface CardEditMenuProps {
  readonly size: CardSize;
  readonly allowedSizes: readonly CardSize[];
  readonly isFirst: boolean;
  readonly isLast: boolean;
  readonly onMove: (direction: -1 | 1) => void;
  readonly onResize: (size: CardSize) => void;
  readonly onHide: () => void;
}

export function CardEditMenu(props: CardEditMenuProps) {
  return (
    <details className="bi-card-menu">
      <summary aria-label="카드 편집 메뉴"><SlidersHorizontal size={17} aria-hidden="true" /></summary>
      <div className="bi-card-menu__popover">
        <div className="bi-card-menu__row" aria-label="카드 순서 변경">
          <button type="button" disabled={props.isFirst} onClick={() => props.onMove(-1)}>
            <ArrowUp size={15} aria-hidden="true" />위로
          </button>
          <button type="button" disabled={props.isLast} onClick={() => props.onMove(1)}>
            <ArrowDown size={15} aria-hidden="true" />아래로
          </button>
          <button type="button" disabled={props.isFirst} onClick={() => props.onMove(-1)}>
            <ArrowLeft size={15} aria-hidden="true" />왼쪽
          </button>
          <button type="button" disabled={props.isLast} onClick={() => props.onMove(1)}>
            <ArrowRight size={15} aria-hidden="true" />오른쪽
          </button>
        </div>
        <fieldset>
          <legend>카드 크기</legend>
          <div className="bi-card-menu__sizes">
            {props.allowedSizes.map((size) => (
              <button
                key={size}
                type="button"
                aria-pressed={size === props.size}
                onClick={() => props.onResize(size)}
              >
                {size}
              </button>
            ))}
          </div>
        </fieldset>
        <button className="bi-card-menu__hide" type="button" onClick={props.onHide}>
          <EyeOff size={15} aria-hidden="true" />카드 숨기기
        </button>
      </div>
    </details>
  );
}
