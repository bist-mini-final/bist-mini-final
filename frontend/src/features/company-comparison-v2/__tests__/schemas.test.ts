import { describe, expect, it } from 'vitest';
import { parseCompanyComparisonV2 } from '../schemas';

function payload() {
  const section = {
    title: '성장',
    body: '선택한 두 기업의 검증된 성장 지표와 원본 근거를 동일 기간 기준으로 비교했습니다.',
    evidence_ids: ['E1'],
  };
  return {
    schema_version: 2,
    analysis_id: 'comparison-1',
    analysis_mode: 'rag',
    brief_status: 'ready',
    start_year: 2021,
    end_year: 2025,
    query_analysis: null,
    companies: [
      {
        company_id: 'company-a', display_name: 'A', currency: 'USD', scale: 'millions',
        points: [
          { year: 2021, revenue: 100, operating_income: 10 },
          { year: 2025, revenue: 200, operating_income: 30 },
        ],
        revenue_cagr: 18.9, operating_margin: 15, liabilities_to_assets: 40, net_debt: -20,
        stability_basis_year: 2025,
      },
      {
        company_id: 'company-b', display_name: 'B', currency: 'USD', scale: 'millions',
        points: [
          { year: 2021, revenue: 200, operating_income: 20 },
          { year: 2025, revenue: 220, operating_income: 25 },
        ],
        revenue_cagr: 2.4, operating_margin: 11.4, liabilities_to_assets: 60, net_debt: 50,
        stability_basis_year: 2025,
      },
    ],
    brief: {
      compared_company_ids: ['company-a', 'company-b'],
      growth: section,
      profitability: { ...section, title: '수익성' },
      risk: { ...section, title: '재무 안정성' },
      caveats: [],
    },
    evidence: [{
      evidence_id: 'E1', company_id: 'company-a', file_name: 'a.xlsm',
      sheet_name: 'Financials', cell_coord: 'B2', source_text: 'Revenue 100', origin: 'rag',
    }],
    warnings: [],
    meta: {
      generated_at: '2026-08-26T00:00:00Z', snapshot_ids: ['snapshot-a', 'snapshot-b'],
      evidence_count: 1, prompt_version: 'comparison-v2.1', model: 'gpt-5.6-luna',
      latency_ms: 1234, cache_hit: false,
    },
  };
}

describe('company comparison V2 response schema', () => {
  it('maps the strict API response to UI types', () => {
    const result = parseCompanyComparisonV2(payload());
    expect(result.companies[0].points[1].operatingIncome).toBe(30);
    expect(result.companies[0].netDebt).toBe(-20);
    expect(result.companies[0].stabilityBasisYear).toBe(2025);
    expect(result.brief?.comparedCompanyIds).toEqual(['company-a', 'company-b']);
    expect(result.evidence[0].origin).toBe('rag');
    expect(result.queryAnalysis).toBeNull();
  });

  it('maps a question analysis that controls the focused charts', () => {
    const result = parseCompanyComparisonV2({
      ...payload(),
      query_analysis: {
        question: '두 기업 중 재무적으로 더 안정적인 기업은 어디야?',
        evaluation_type: 'stability',
        evaluation_label: '재무 안정성 평가',
        rationale: '부채 비중과 순현금 수준을 중심으로 묻는 질문입니다.',
        required_metrics: ['total_liabilities', 'total_assets', 'net_debt'],
        chart_ids: ['stability'],
      },
    });
    expect(result.queryAnalysis?.evaluationType).toBe('stability');
    expect(result.queryAnalysis?.chartIds).toEqual(['stability']);
  });

  it('rejects an unexpected API field', () => {
    expect(() => parseCompanyComparisonV2({ ...payload(), fixed_answer: true })).toThrow();
  });
});
