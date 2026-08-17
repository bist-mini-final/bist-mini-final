import { Search } from 'lucide-react';


interface SpreadsheetInspectActionProps {
  available: boolean;
  label: string;
  onInspect: () => void;
}

export function SpreadsheetInspectAction({
  available,
  label,
  onInspect,
}: SpreadsheetInspectActionProps) {
  const unavailableLabel = `${label} — 먼저 모듈을 실행하세요`;

  return (
    <button
      type="button"
      className="nodrag nopan flow-node__action flow-node__inspect"
      disabled={!available}
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
        if (available) onInspect();
      }}
      aria-label={available ? label : unavailableLabel}
      title={available ? label : unavailableLabel}
    >
      <Search className="h-3.5 w-3.5" />
    </button>
  );
}
