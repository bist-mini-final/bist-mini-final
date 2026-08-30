import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { pipelineApi, type SpreadsheetArtifactLayer } from '../../services/api';
import {
  spreadsheetTableKey,
  type SpreadsheetResult,
  type SpreadsheetResultTable,
} from './spreadsheetResultModel';

export const SIDEBAR_MIN_WIDTH = 320;
export const SIDEBAR_MAX_WIDTH = 680;

type InspectorBodyStyle = CSSProperties & {
  '--spreadsheet-sidebar-width': string;
};

/** Owns viewport, selection, zoom, and resize state for the spreadsheet inspector. */
export function useSpreadsheetResultInspector({
  parsed,
  defaultLayer,
  onClose,
}: {
  readonly parsed: SpreadsheetResult;
  readonly defaultLayer: SpreadsheetArtifactLayer;
  readonly onClose: () => void;
}) {
  const workbookIdentity = `${parsed.workbookHash}\u0000${parsed.fileName}\u0000${parsed.sheetNames.join('\u0000')}`;
  const firstSheet = parsed.sheetNames[0] ?? '';
  const [selectedSheet, setSelectedSheet] = useState(firstSheet);
  const [selectedTableKey, setSelectedTableKey] = useState<string | null>(null);
  const [zoom, setZoom] = useState(0.6);
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });
  const [imageError, setImageError] = useState(false);
  const [imageLayer, setImageLayer] = useState<SpreadsheetArtifactLayer>(defaultLayer);
  const [showClassificationBoxes, setShowClassificationBoxes] = useState(true);
  const [showCellTypeColors, setShowCellTypeColors] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(400);
  const viewportRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const sidebarResizeCleanupRef = useRef<(() => void) | null>(null);

  const sheetTables = useMemo(
    () => parsed.tables.filter((table) => table.sheet_name === selectedSheet),
    [parsed.tables, selectedSheet],
  );
  const selectedTable: SpreadsheetResultTable | null = sheetTables.find(
    (table) => spreadsheetTableKey(table) === selectedTableKey,
  ) ?? sheetTables[0] ?? null;
  const firstTableKey = sheetTables[0] ? spreadsheetTableKey(sheetTables[0]) : null;
  const totalRegions = parsed.tables.reduce((count, table) => count + table.regions.length, 0);
  const imageUrl = selectedSheet
    ? pipelineApi.spreadsheetArtifactUrl(parsed.workbookHash, selectedSheet, imageLayer)
    : '';

  useEffect(() => {
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  useEffect(() => () => sidebarResizeCleanupRef.current?.(), []);

  useEffect(() => {
    setSelectedSheet(firstSheet);
    setSelectedTableKey(null);
  }, [firstSheet, workbookIdentity]);

  useEffect(() => {
    setSelectedTableKey(firstTableKey);
    setImageSize({ width: 0, height: 0 });
    setImageError(false);
  }, [firstTableKey, selectedSheet]);

  useEffect(() => {
    setImageLayer(defaultLayer);
    setShowClassificationBoxes(true);
    setShowCellTypeColors(true);
  }, [defaultLayer]);

  useEffect(() => {
    setImageSize({ width: 0, height: 0 });
    setImageError(false);
  }, [imageLayer]);

  const fitImage = (naturalWidth: number, naturalHeight: number) => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const availableWidth = Math.max(240, viewport.clientWidth - 48);
    const availableHeight = Math.max(240, viewport.clientHeight - 48);
    const nextZoom = Math.min(1, availableWidth / naturalWidth, availableHeight / naturalHeight);
    setZoom(Math.max(0.2, Math.round(nextZoom * 20) / 20));
  };

  const changeZoom = (delta: number) => {
    setZoom((current) => Math.min(1.5, Math.max(0.2, Number((current + delta).toFixed(2)))));
  };

  const clampSidebarWidth = (width: number) => {
    const viewportMaximum = typeof window === 'undefined'
      ? SIDEBAR_MAX_WIDTH
      : Math.max(SIDEBAR_MIN_WIDTH, window.innerWidth - 440);
    return Math.min(
      Math.max(SIDEBAR_MIN_WIDTH, Math.round(width)),
      Math.min(SIDEBAR_MAX_WIDTH, viewportMaximum),
    );
  };

  const resizeSidebarBy = (delta: number) => {
    setSidebarWidth((current) => clampSidebarWidth(current + delta));
  };

  const beginSidebarResize = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    sidebarResizeCleanupRef.current?.();
    const startX = event.clientX;
    const startWidth = sidebarWidth;
    const handlePointerMove = (moveEvent: globalThis.PointerEvent) => {
      setSidebarWidth(clampSidebarWidth(startWidth + moveEvent.clientX - startX));
    };
    const cleanup = () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
      window.removeEventListener('pointercancel', handlePointerUp);
      document.body.classList.remove('spreadsheet-result-is-resizing');
      sidebarResizeCleanupRef.current = null;
    };
    const handlePointerUp = () => cleanup();
    sidebarResizeCleanupRef.current = cleanup;
    document.body.classList.add('spreadsheet-result-is-resizing');
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    window.addEventListener('pointercancel', handlePointerUp);
  };

  const handleSidebarResizeKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    resizeSidebarBy(event.key === 'ArrowLeft' ? -24 : 24);
  };

  const toggleCellTypeColors = () => {
    setShowCellTypeColors((current) => {
      const next = !current;
      setImageLayer(next ? 'typed' : 'rendered');
      return next;
    });
  };

  const bodyStyle: InspectorBodyStyle = {
    '--spreadsheet-sidebar-width': `${sidebarWidth}px`,
  };

  return {
    selectedSheet,
    setSelectedSheet,
    selectedTableKey,
    setSelectedTableKey,
    zoom,
    imageSize,
    setImageSize,
    imageError,
    setImageError,
    showClassificationBoxes,
    setShowClassificationBoxes,
    showCellTypeColors,
    toggleCellTypeColors,
    sidebarWidth,
    sheetTables,
    selectedTable,
    totalRegions,
    imageUrl,
    viewportRef,
    closeButtonRef,
    bodyStyle,
    fitImage,
    changeZoom,
    beginSidebarResize,
    handleSidebarResizeKeyDown,
  };
}
