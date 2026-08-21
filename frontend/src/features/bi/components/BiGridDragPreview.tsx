import type { Layout } from 'react-grid-layout';
import { getCardDefinition, isBiCardId } from '../config/cardRegistry';
import { getBiGridRect } from '../layout/biGridGeometry';
import type { BiCardId } from '../types';

interface BiGridDragPreviewProps {
  readonly activeCardId: BiCardId;
  readonly columns: number;
  readonly containerWidth: number;
  readonly layout: Layout;
  readonly margin: readonly [number, number];
  readonly rowHeight: number;
  readonly invalidCardIds: readonly BiCardId[];
  readonly targetKind: 'new-row' | 'row' | null;
}

export function BiGridDragPreview(props: BiGridDragPreviewProps) {
  return (
    <div className="bi-grid-preview" data-bi-grid-preview aria-hidden="true">
      {props.layout.map((item) => {
        const rect = getBiGridRect(item, props);
        const isActive = item.i === props.activeCardId;
        const isInvalid = isBiCardId(item.i) && props.invalidCardIds.includes(item.i);
        const isFirstInvalid = item.i === props.invalidCardIds[0];
        return (
          <div
            key={item.i}
            className="bi-grid-preview__item"
            data-active={isActive && props.invalidCardIds.length === 0}
            data-invalid={isInvalid}
            data-preview-card-id={item.i}
            style={{
              blockSize: rect.blockSize,
              inlineSize: rect.inlineSize,
              transform: `translate(${rect.x}px, ${rect.y}px)`,
            }}
          >
            {isActive && props.targetKind ? (
              <span>{props.targetKind === 'new-row' ? '새 행으로 놓기' : `${getCardDefinition(props.activeCardId).title} 놓을 위치`}</span>
            ) : null}
            {isFirstInvalid ? <span>행당 최대 3개</span> : null}
          </div>
        );
      })}
    </div>
  );
}
