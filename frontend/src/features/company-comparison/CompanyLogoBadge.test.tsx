import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  COMPANY_BRAND_ICON_COUNT,
  CompanyLogoBadge,
  companyLogoDesign,
} from './CompanyLogoBadge';

describe('CompanyLogoBadge', () => {
  it('keeps one company mark stable while varying the source company logo', () => {
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
        return design.sourceIcon;
      }),
    );
    expect(visualSignatures.size).toBe(companies.length);
    expect(COMPANY_BRAND_ICON_COUNT).toBe(100);
  });

  it('renders only the original source mark without a background container', () => {
    const { container } = render(
      <>
        <CompanyLogoBadge companyId="company-nexora" companyName="Nexora Labs" />
        <CompanyLogoBadge companyId="company-nexora" companyName="Nexora Labs" />
      </>,
    );
    expect(container.querySelectorAll('linearGradient')).toHaveLength(0);
    expect(container.querySelectorAll('rect')).toHaveLength(0);
    expect(container.querySelectorAll('[data-source-icon]')).toHaveLength(2);
    expect(container.querySelectorAll('[data-brand-color]')).toHaveLength(2);
    expect(container.querySelectorAll('[data-catalog-version="simple-icons-v16-us-listed-1"]')).toHaveLength(2);
  });

  it('honors the brand mark persisted in a BI snapshot', () => {
    const { container } = render(
      <CompanyLogoBadge
        companyId="company-nexora"
        companyName="Nexora Labs"
        brandMark={{
          catalogVersion: 'simple-icons-v16-us-listed-1',
          sourceIcon: 'nvidia',
          colorIndex: 4,
          rotationDegrees: -8,
          flipVertical: true,
        }}
      />,
    );
    const mark = container.querySelector('[data-source-icon="nvidia"]');
    expect(mark).toHaveAttribute('data-brand-color', '#76B900');
    expect(mark).not.toHaveAttribute('data-color-index');
    expect(mark).not.toHaveAttribute('data-rotation');
    expect(mark).not.toHaveAttribute('data-flip-vertical');
    expect(mark?.querySelector('path')).toHaveAttribute('fill', '#76B900');
  });
});
