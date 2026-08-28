import { useCallback, useEffect, useMemo, useState } from 'react';
import type { BiCompanySummary } from '../types';

const SELECTED_COMPANY_KEY = 'rag-flow:bi-selected-company:v1';
const NAVIGATION_EVENT = 'rag-flow:navigation';

function readPreferredCompanyId(): string {
  try {
    const companyIdFromUrl = new URLSearchParams(window.location.search).get('companyId');
    if (companyIdFromUrl) {
      window.localStorage.setItem(SELECTED_COMPANY_KEY, companyIdFromUrl);
      return companyIdFromUrl;
    }
    return window.localStorage.getItem(SELECTED_COMPANY_KEY) ?? '';
  } catch (error) {
    if (error instanceof DOMException) return '';
    throw error;
  }
}

function storeCompanyId(companyId: string): void {
  try {
    window.localStorage.setItem(SELECTED_COMPANY_KEY, companyId);
  } catch (error) {
    if (!(error instanceof DOMException)) throw error;
  }
}

export interface SelectedBiCompany {
  readonly selectedCompanyId: string;
  readonly selectedCompany: BiCompanySummary | null;
  readonly selectCompany: (companyId: string) => void;
}

/** Resolves a persisted preference against the companies currently available to BI. */
export function useSelectedBiCompany(
  companies: readonly BiCompanySummary[],
): SelectedBiCompany {
  const [preferredCompanyId, setPreferredCompanyId] = useState(readPreferredCompanyId);
  useEffect(() => {
    const syncCompanyFromUrl = () => {
      const companyId = new URLSearchParams(window.location.search).get('companyId');
      if (!companyId) return;
      setPreferredCompanyId(companyId);
      storeCompanyId(companyId);
    };
    window.addEventListener('popstate', syncCompanyFromUrl);
    window.addEventListener(NAVIGATION_EVENT, syncCompanyFromUrl);
    return () => {
      window.removeEventListener('popstate', syncCompanyFromUrl);
      window.removeEventListener(NAVIGATION_EVENT, syncCompanyFromUrl);
    };
  }, []);
  const selectedCompany = useMemo(
    () => companies.find((company) => company.companyId === preferredCompanyId)
      ?? companies[0]
      ?? null,
    [companies, preferredCompanyId],
  );
  const selectCompany = useCallback((companyId: string) => {
    setPreferredCompanyId(companyId);
    storeCompanyId(companyId);
  }, []);

  return {
    selectedCompanyId: selectedCompany?.companyId ?? '',
    selectedCompany,
    selectCompany,
  };
}
