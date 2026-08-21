import type { LayoutItem } from 'react-grid-layout';

export interface BiGridGeometry {
  readonly columns: number;
  readonly containerWidth: number;
  readonly margin: readonly [number, number];
  readonly rowHeight: number;
}

export interface BiGridRect {
  readonly blockSize: number;
  readonly inlineSize: number;
  readonly x: number;
  readonly y: number;
}

export function getBiGridRect(item: LayoutItem, geometry: BiGridGeometry): BiGridRect {
  const [marginX, marginY] = geometry.margin;
  const columnWidth = (
    geometry.containerWidth - marginX * (geometry.columns - 1)
  ) / geometry.columns;
  return {
    blockSize: item.h * geometry.rowHeight + Math.max(0, item.h - 1) * marginY,
    inlineSize: item.w * columnWidth + Math.max(0, item.w - 1) * marginX,
    x: item.x * (columnWidth + marginX),
    y: item.y * (geometry.rowHeight + marginY),
  };
}
