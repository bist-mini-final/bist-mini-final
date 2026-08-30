import { CloudCog, type LucideIcon } from 'lucide-react';
import type { SpreadsheetArtifactLayer } from '../../services/api';
import type { SpreadsheetInspectorKind, SpreadsheetRegionKind } from './spreadsheetResultModel';

export const REGION_META: Record<SpreadsheetRegionKind, { label: string; className: string }> = {
  title: { label: '제목', className: 'spreadsheet-result-region--title' },
  column_header: { label: '열 헤더', className: 'spreadsheet-result-region--column' },
  row_header: { label: '행 헤더', className: 'spreadsheet-result-region--row' },
  data: { label: '데이터', className: 'spreadsheet-result-region--data' },
};

interface InspectorMeta {
  readonly title: string;
  readonly description: string;
  readonly icon: LucideIcon;
  readonly layers: readonly { value: SpreadsheetArtifactLayer; label: string }[];
  readonly defaultLayer: SpreadsheetArtifactLayer;
}

export const INSPECTOR_META: Record<SpreadsheetInspectorKind, InspectorMeta> = {
  luna_vlm: {
    title: 'Luna 전체 시트 구조 식별 결과',
    description: '후보 영역 없이 전체 시트를 분석한 결과를 셀 타입 오버레이와 원본 좌표에서 확인합니다.',
    icon: CloudCog,
    layers: [
      { value: 'typed', label: '셀 타입 오버레이' },
      { value: 'rendered', label: '원본 시트' },
    ],
    defaultLayer: 'typed',
  },
};

export function readableHeaderName(value: string): string {
  return value.replace(/\b(\d{4}-\d{2}-\d{2}) 00:00:00\b/g, '$1');
}

export function compactExcelRange(value: string): string {
  const [start, end] = value.split(':');
  return end && start === end ? start : value;
}
