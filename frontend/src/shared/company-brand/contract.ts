export const COMPANY_BRAND_CATALOG_VERSION = 'simple-icons-v16-us-listed-1' as const;

export interface CompanyBrandMark {
  readonly catalogVersion: typeof COMPANY_BRAND_CATALOG_VERSION;
  readonly sourceIcon: string;
  readonly colorIndex: number;
  readonly rotationDegrees: number;
  readonly flipVertical: boolean;
}
