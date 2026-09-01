import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CompanyLogoBadge, companyLogoDesign } from './CompanyLogoBadge';

describe('CompanyLogoBadge', () => {
  it('keeps one company mark stable while varying the generated brand identity', () => {
    const companies = [
      ['company-amesoft', 'AmeSoft'],
      ['company-nexora', 'Nexora Labs'],
      ['company-veltrix', 'Veltrix Systems'],
      ['company-lumena', 'Lumena AI'],
      ['company-corevia', 'Corevia Technology'],
      ['company-altiven', 'Altiven'],
    ] as const;
    const first = companyLogoDesign(...companies[0]);
    expect(companyLogoDesign(...companies[0])).toEqual(first);

    const visualSignatures = new Set(
      companies.map(([id, name]) => {
        const design = companyLogoDesign(id, name);
        return `${design.palette}:${design.family}:${design.variant}`;
      }),
    );
    expect(visualSignatures.size).toBe(companies.length);
  });

  it('renders reusable flat marks without gradient identifiers or crest metadata', () => {
    const { container } = render(
      <>
        <CompanyLogoBadge companyId="company-nexora" companyName="Nexora Labs" />
        <CompanyLogoBadge companyId="company-nexora" companyName="Nexora Labs" />
      </>,
    );
    expect(container.querySelectorAll('linearGradient')).toHaveLength(0);
    expect(container.querySelectorAll('[data-logo-family]')).toHaveLength(2);
    expect(container.querySelectorAll('[data-crest-sigil]')).toHaveLength(0);
  });
});
