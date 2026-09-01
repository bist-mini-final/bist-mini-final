import type { FC, ReactNode } from 'react';

interface CompanyLogoBadgeProps {
  readonly companyId: string;
  readonly companyName: string;
  readonly size?: number;
  readonly className?: string;
}

interface BrandPalette {
  readonly primary: string;
  readonly secondary: string;
  readonly surface: string;
  readonly border: string;
}

export interface CompanyLogoDesign {
  readonly family: number;
  readonly palette: number;
  readonly variant: number;
  readonly initials: string;
}

const BRAND_PALETTES: readonly BrandPalette[] = [
  { primary: '#075985', secondary: '#0ea5e9', surface: '#f0f9ff', border: '#bae6fd' },
  { primary: '#166534', secondary: '#22c55e', surface: '#f0fdf4', border: '#bbf7d0' },
  { primary: '#3730a3', secondary: '#6366f1', surface: '#eef2ff', border: '#c7d2fe' },
  { primary: '#9f1239', secondary: '#f43f5e', surface: '#fff1f2', border: '#fecdd3' },
  { primary: '#115e59', secondary: '#14b8a6', surface: '#f0fdfa', border: '#99f6e4' },
  { primary: '#92400e', secondary: '#f59e0b', surface: '#fffbeb', border: '#fde68a' },
  { primary: '#6b21a8', secondary: '#a855f7', surface: '#faf5ff', border: '#e9d5ff' },
  { primary: '#334155', secondary: '#64748b', surface: '#f8fafc', border: '#cbd5e1' },
  { primary: '#9a3412', secondary: '#f97316', surface: '#fff7ed', border: '#fed7aa' },
  { primary: '#1e40af', secondary: '#3b82f6', surface: '#eff6ff', border: '#bfdbfe' },
];

function hashString(value: string): number {
  let hash = 0x811c9dc5;
  for (const character of value) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 0x01000193);
  }
  hash ^= hash >>> 16;
  hash = Math.imul(hash, 0x7feb352d);
  hash ^= hash >>> 15;
  hash = Math.imul(hash, 0x846ca68b);
  return (hash ^ (hash >>> 16)) >>> 0;
}

function companyInitials(companyName: string): string {
  const words = companyName
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean);

  if (words.length > 1) {
    return words
      .slice(0, 2)
      .map((word) => Array.from(word)[0])
      .join('')
      .toUpperCase();
  }

  return Array.from(words[0] ?? '?').slice(0, 2).join('').toUpperCase();
}

export function companyLogoDesign(
  companyId: string,
  companyName: string,
): CompanyLogoDesign {
  const seed = hashString(`${companyId.trim().toLowerCase()}::${companyName.trim().toLowerCase()}`);
  return {
    palette: seed % BRAND_PALETTES.length,
    family: (seed >>> 7) % 6,
    variant: (seed >>> 15) % 4,
    initials: companyInitials(companyName),
  };
}

function BrandAccent({ variant, color }: { readonly variant: number; readonly color: string }) {
  if (variant === 0) {
    return <rect x="7" y="5" width="7" height="2" rx="1" fill={color} />;
  }
  if (variant === 1) {
    return <rect x="18" y="25" width="7" height="2" rx="1" fill={color} />;
  }
  if (variant === 2) {
    return <rect x="25" y="6" width="2" height="7" rx="1" fill={color} />;
  }
  return <rect x="5" y="19" width="2" height="7" rx="1" fill={color} />;
}

function BrandSymbol({
  family,
  initials,
  primary,
  secondary,
}: {
  readonly family: number;
  readonly initials: string;
  readonly primary: string;
  readonly secondary: string;
}): ReactNode {
  if (family === 0) {
    return (
      <g>
        <path d="M8 22V10.5c0-1.38 1.12-2.5 2.5-2.5H14v3h-2.5a.5.5 0 0 0-.5.5V22H8Z" fill={secondary} />
        <path d="M14 8h3.5A6.5 6.5 0 0 1 24 14.5V22h-3v-7.5a3.5 3.5 0 0 0-3.5-3.5H14V8Z" fill={primary} />
      </g>
    );
  }

  if (family === 1) {
    return (
      <g fill="none">
        <circle cx="16" cy="16" r="7" stroke={primary} strokeWidth="3" />
        <path d="M9.8 17.2c3.7-4.5 8.3-5.5 13-2.7" stroke={secondary} strokeWidth="2.5" strokeLinecap="round" />
        <circle cx="23" cy="12" r="2.1" fill={primary} />
      </g>
    );
  }

  if (family === 2) {
    return (
      <g>
        <path d="m9 20 7-9 7 9" fill="none" stroke={primary} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="9" cy="20" r="2.6" fill={secondary} />
        <circle cx="16" cy="11" r="2.6" fill={primary} />
        <circle cx="23" cy="20" r="2.6" fill={secondary} />
      </g>
    );
  }

  if (family === 3) {
    return (
      <g>
        <rect x="8" y="17" width="3.6" height="6" rx="1.2" fill={secondary} />
        <rect x="14.2" y="12.5" width="3.6" height="10.5" rx="1.2" fill={primary} />
        <rect x="20.4" y="8" width="3.6" height="15" rx="1.2" fill={secondary} />
        <path d="m8.7 12.8 5.2-4.2 4 1.4 5.2-4" fill="none" stroke={primary} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    );
  }

  if (family === 4) {
    return (
      <g>
        <path d="M8 9.5 15.8 6v16L8 18.5v-9Z" fill={primary} />
        <path d="M16.8 10 24 7.3v9.2L16.8 21v-11Z" fill={secondary} />
        <path d="m10.5 11.3 2.8-1.1v7.6l-2.8-1.1v-5.4Z" fill="#fff" opacity=".9" />
      </g>
    );
  }

  return (
    <g>
      <rect x="7" y="8" width="18" height="16" rx="5" fill={primary} />
      <text
        x="16"
        y="19.1"
        fill="#fff"
        fontSize={initials.length > 1 ? '7.4' : '9'}
        fontWeight="750"
        letterSpacing="-.25"
        textAnchor="middle"
      >
        {initials}
      </text>
      <rect x="21.5" y="8" width="3.5" height="5" rx="1.75" fill={secondary} />
    </g>
  );
}

/** Stable, generated brand mark shared by every company-comparison surface. */
export const CompanyLogoBadge: FC<CompanyLogoBadgeProps> = ({
  companyId,
  companyName,
  size = 22,
  className = '',
}) => {
  const design = companyLogoDesign(companyId, companyName);
  const palette = BRAND_PALETTES[design.palette];

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={`company-custom-logo-svg company-brand-mark ${className}`.trim()}
      data-logo-family={design.family}
      data-logo-palette={design.palette}
      data-logo-variant={design.variant}
      aria-hidden="true"
      focusable="false"
    >
      <rect x="1" y="1" width="30" height="30" rx="8" fill={palette.surface} stroke={palette.border} />
      <BrandSymbol
        family={design.family}
        initials={design.initials}
        primary={palette.primary}
        secondary={palette.secondary}
      />
      <BrandAccent variant={design.variant} color={palette.secondary} />
    </svg>
  );
};
