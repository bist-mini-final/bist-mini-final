import {
  createContext,
  lazy,
  Suspense,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type { SheetCitationGroup } from '../markdown/cellCitations';

const LazyCellEvidenceModal = lazy(async () => {
  const module = await import('./CellEvidenceModal');
  return { default: module.CellEvidenceModal };
});

type OpenCellEvidence = (group: SheetCitationGroup) => void;

const CellEvidenceContext = createContext<OpenCellEvidence | null>(null);

/** Keeps evidence dialogs outside volatile canvases and page-level render lifecycles. */
export function CellEvidenceProvider({ children }: { readonly children: ReactNode }) {
  const [group, setGroup] = useState<SheetCitationGroup | null>(null);
  const openEvidence = useMemo<OpenCellEvidence>(() => setGroup, []);

  return (
    <CellEvidenceContext.Provider value={openEvidence}>
      {children}
      {group ? (
        <Suspense fallback={null}>
          <LazyCellEvidenceModal group={group} onClose={() => setGroup(null)} />
        </Suspense>
      ) : null}
    </CellEvidenceContext.Provider>
  );
}

export function useCellEvidenceLauncher(): OpenCellEvidence | null {
  return useContext(CellEvidenceContext);
}
