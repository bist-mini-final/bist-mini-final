import {
  createContext,
  lazy,
  Suspense,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type { CellCitation } from '../markdown/cellCitations';

const LazyCellEvidenceModal = lazy(async () => {
  const module = await import('./CellEvidenceModal');
  return { default: module.CellEvidenceModal };
});

type OpenCellEvidence = (citation: CellCitation) => void;

const CellEvidenceContext = createContext<OpenCellEvidence | null>(null);

/** Keeps evidence dialogs outside volatile canvases and page-level render lifecycles. */
export function CellEvidenceProvider({ children }: { readonly children: ReactNode }) {
  const [citation, setCitation] = useState<CellCitation | null>(null);
  const openEvidence = useMemo<OpenCellEvidence>(() => setCitation, []);

  return (
    <CellEvidenceContext.Provider value={openEvidence}>
      {children}
      {citation ? (
        <Suspense fallback={null}>
          <LazyCellEvidenceModal citation={citation} onClose={() => setCitation(null)} />
        </Suspense>
      ) : null}
    </CellEvidenceContext.Provider>
  );
}

export function useCellEvidenceLauncher(): OpenCellEvidence | null {
  return useContext(CellEvidenceContext);
}
