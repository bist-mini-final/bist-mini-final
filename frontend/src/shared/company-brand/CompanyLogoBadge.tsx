import type { FC } from 'react';
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

export interface CompanyLogoDesign extends CompanyBrandMark {
  readonly sourceBrand: string;
  readonly brandColor: string;
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
    // Retained as neutral values for backward-compatible snapshot DTOs.
    colorIndex: 0,
    rotationDegrees: 0,
    flipVertical: false,
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
    sourceBrand: icon.title,
    brandColor: `#${icon.hex}`,
  };
}

/** A stable, unmodified mark sourced from the bundled 100-company SVG catalog. */
export const CompanyLogoBadge: FC<CompanyLogoBadgeProps> = ({
  companyId,
  companyName,
  brandMark,
  size = 22,
  className = '',
}) => {
  const design = companyLogoDesign(companyId, companyName, brandMark);
  const icon = BRAND_ICON_BY_SLUG.get(design.sourceIcon) ?? BRAND_ICONS[0];

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className={`company-custom-logo-svg company-brand-mark ${className}`.trim()}
      data-catalog-version={design.catalogVersion}
      data-source-icon={design.sourceIcon}
      data-source-brand={design.sourceBrand}
      data-brand-color={design.brandColor}
      aria-hidden="true"
      focusable="false"
    >
      <path d={icon.path} fill={design.brandColor} />
    </svg>
  );
};

export const COMPANY_BRAND_ICON_COUNT = BRAND_ICONS.length;

export { COMPANY_BRAND_CATALOG_VERSION } from './contract';
export type { CompanyBrandMark } from './contract';
