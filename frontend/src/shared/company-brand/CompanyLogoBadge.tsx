import type { CSSProperties, FC } from 'react';
import type { SimpleIcon } from 'simple-icons';
import {
  si3m,
  siAbbvie,
  siAirbnb,
  siAmd,
  siAmericanairlines,
  siApple,
  siArm,
  siAtandt,
  siAtlassian,
  siAutodesk,
  siBoeing,
  siBookingdotcom,
  siBroadcom,
  siCaterpillar,
  siCisco,
  siCloudflare,
  siCocacola,
  siCoinbase,
  siDatadog,
  siDell,
  siDelta,
  siDigitalocean,
  siDoordash,
  siDropbox,
  siDuolingo,
  siEbay,
  siElastic,
  siEtsy,
  siExpedia,
  siFastly,
  siFedex,
  siFerrari,
  siFiverr,
  siFord,
  siFortinet,
  siGeneralmotors,
  siGithub,
  siGitlab,
  siGoogle,
  siHilton,
  siHonda,
  siHp,
  siHubspot,
  siInstacart,
  siIntel,
  siIntuit,
  siJetblue,
  siJohndeere,
  siKfc,
  siLucid,
  siLyft,
  siMarriott,
  siMastercard,
  siMcdonalds,
  siMerck,
  siMeta,
  siMongodb,
  siMotorola,
  siNetflix,
  siNike,
  siNubank,
  siNvidia,
  siOkta,
  siPalantir,
  siPaloaltonetworks,
  siParamountplus,
  siPaypal,
  siPinterest,
  siQualcomm,
  siReddit,
  siRobinhood,
  siRoblox,
  siRoku,
  siShopify,
  siSnapchat,
  siSnowflake,
  siSouthwestairlines,
  siSpotify,
  siStarbucks,
  siTacobell,
  siTaketwointeractivesoftware,
  siTarget,
  siTesla,
  siTinder,
  siToyota,
  siTripadvisor,
  siTwitch,
  siUber,
  siUnderarmour,
  siUnitedairlines,
  siUnity,
  siUps,
  siUpwork,
  siVerizon,
  siVisa,
  siWhatsapp,
  siWix,
  siYelp,
  siZillow,
  siZoom,
} from 'simple-icons';
import {
  COMPANY_BRAND_CATALOG_VERSION,
  type CompanyBrandMark,
} from './contract';
import './company-brand.css';

interface CompanyLogoBadgeProps {
  readonly companyId: string;
  readonly companyName: string;
  readonly brandMark?: CompanyBrandMark | null;
  readonly size?: number;
  readonly className?: string;
}

interface BrandPalette {
  readonly foreground: string;
  readonly surface: string;
  readonly border: string;
  readonly accent: string;
}

export interface CompanyLogoDesign extends CompanyBrandMark {
  readonly sourceBrand: string;
}

const BRAND_ICONS: readonly SimpleIcon[] = [
  si3m,
  siAbbvie,
  siAirbnb,
  siAmd,
  siAmericanairlines,
  siApple,
  siArm,
  siAtandt,
  siAtlassian,
  siAutodesk,
  siBoeing,
  siBookingdotcom,
  siBroadcom,
  siCaterpillar,
  siCisco,
  siCloudflare,
  siCocacola,
  siCoinbase,
  siDatadog,
  siDell,
  siDelta,
  siDigitalocean,
  siDoordash,
  siDropbox,
  siDuolingo,
  siEbay,
  siElastic,
  siEtsy,
  siExpedia,
  siFastly,
  siFedex,
  siFerrari,
  siFiverr,
  siFord,
  siFortinet,
  siGeneralmotors,
  siGitlab,
  siGoogle,
  siHilton,
  siHonda,
  siHp,
  siHubspot,
  siInstacart,
  siIntel,
  siIntuit,
  siJetblue,
  siJohndeere,
  siKfc,
  siLucid,
  siLyft,
  siMarriott,
  siMastercard,
  siMcdonalds,
  siMerck,
  siMeta,
  siMongodb,
  siMotorola,
  siNetflix,
  siNike,
  siNubank,
  siNvidia,
  siOkta,
  siPalantir,
  siPaloaltonetworks,
  siParamountplus,
  siPaypal,
  siPinterest,
  siQualcomm,
  siReddit,
  siRobinhood,
  siRoblox,
  siRoku,
  siShopify,
  siSnapchat,
  siSnowflake,
  siSouthwestairlines,
  siSpotify,
  siStarbucks,
  siTacobell,
  siTaketwointeractivesoftware,
  siTarget,
  siTesla,
  siTinder,
  siToyota,
  siTripadvisor,
  siTwitch,
  siUber,
  siUnderarmour,
  siUnitedairlines,
  siUnity,
  siUps,
  siUpwork,
  siVerizon,
  siVisa,
  siWhatsapp,
  siWix,
  siYelp,
  siZillow,
  siZoom,
  siGithub,
];

const BRAND_ICON_BY_SLUG = new Map(BRAND_ICONS.map((icon) => [icon.slug, icon]));
const BRAND_PALETTES: readonly BrandPalette[] = [
  { foreground: '#b91c1c', surface: '#fff1f2', border: '#fecdd3', accent: '#ef4444' },
  { foreground: '#1d4ed8', surface: '#eff6ff', border: '#bfdbfe', accent: '#60a5fa' },
  { foreground: '#6d28d9', surface: '#f5f3ff', border: '#ddd6fe', accent: '#a78bfa' },
  { foreground: '#0f766e', surface: '#f0fdfa', border: '#99f6e4', accent: '#2dd4bf' },
  { foreground: '#c2410c', surface: '#fff7ed', border: '#fed7aa', accent: '#fb923c' },
  { foreground: '#0369a1', surface: '#f0f9ff', border: '#bae6fd', accent: '#38bdf8' },
  { foreground: '#a21caf', surface: '#fdf4ff', border: '#f5d0fe', accent: '#e879f9' },
  { foreground: '#166534', surface: '#f0fdf4', border: '#bbf7d0', accent: '#4ade80' },
  { foreground: '#9f1239', surface: '#fff1f2', border: '#fecdd3', accent: '#fb7185' },
  { foreground: '#4338ca', surface: '#eef2ff', border: '#c7d2fe', accent: '#818cf8' },
  { foreground: '#a16207', surface: '#fefce8', border: '#fef08a', accent: '#facc15' },
  { foreground: '#334155', surface: '#f8fafc', border: '#cbd5e1', accent: '#94a3b8' },
];
const BRAND_ROTATIONS = [-12, -8, -4, 0, 4, 8, 12] as const;

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

function fallbackBrandMark(companyId: string, companyName: string): CompanyBrandMark {
  const seed = hashString(`${companyId.trim().toLowerCase()}::${companyName.trim().toLowerCase()}`);
  return {
    catalogVersion: COMPANY_BRAND_CATALOG_VERSION,
    sourceIcon: BRAND_ICONS[seed % BRAND_ICONS.length].slug,
    colorIndex: (seed >>> 7) % BRAND_PALETTES.length,
    rotationDegrees: BRAND_ROTATIONS[(seed >>> 15) % BRAND_ROTATIONS.length],
    flipVertical: Boolean((seed >>> 22) & 1),
  };
}

export function companyLogoDesign(
  companyId: string,
  companyName: string,
  brandMark?: CompanyBrandMark | null,
): CompanyLogoDesign {
  const fallback = fallbackBrandMark(companyId, companyName);
  const resolved = brandMark?.catalogVersion === COMPANY_BRAND_CATALOG_VERSION
    && BRAND_ICON_BY_SLUG.has(brandMark.sourceIcon)
    ? brandMark
    : fallback;
  const icon = BRAND_ICON_BY_SLUG.get(resolved.sourceIcon) ?? BRAND_ICONS[0];
  return {
    ...resolved,
    colorIndex: Math.abs(resolved.colorIndex) % BRAND_PALETTES.length,
    rotationDegrees: Math.max(-12, Math.min(12, resolved.rotationDegrees)),
    sourceBrand: icon.title,
  };
}

/** A stable augmented mark sourced from the bundled 100-brand SVG catalog. */
export const CompanyLogoBadge: FC<CompanyLogoBadgeProps> = ({
  companyId,
  companyName,
  brandMark,
  size = 22,
  className = '',
}) => {
  const design = companyLogoDesign(companyId, companyName, brandMark);
  const icon = BRAND_ICON_BY_SLUG.get(design.sourceIcon) ?? BRAND_ICONS[0];
  const palette = BRAND_PALETTES[design.colorIndex];
  const iconTransform = `rotate(${design.rotationDegrees}deg) scaleY(${design.flipVertical ? -1 : 1})`;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={`company-custom-logo-svg company-brand-mark ${className}`.trim()}
      data-catalog-version={design.catalogVersion}
      data-source-icon={design.sourceIcon}
      data-source-brand={design.sourceBrand}
      data-color-index={design.colorIndex}
      data-rotation={design.rotationDegrees}
      data-flip-vertical={design.flipVertical}
      aria-hidden="true"
      focusable="false"
    >
      <rect x="1" y="1" width="30" height="30" rx="8" fill={palette.surface} stroke={palette.border} />
      <path d="M5 26.5h8" stroke={palette.accent} strokeWidth="1.5" strokeLinecap="round" opacity=".7" />
      <g transform="translate(4 4)">
        <path
          d={icon.path}
          fill={palette.foreground}
          style={{ transform: iconTransform, transformOrigin: '12px 12px' } as CSSProperties}
        />
      </g>
    </svg>
  );
};

export const COMPANY_BRAND_ICON_COUNT = BRAND_ICONS.length;

export { COMPANY_BRAND_CATALOG_VERSION } from './contract';
export type { CompanyBrandMark } from './contract';
