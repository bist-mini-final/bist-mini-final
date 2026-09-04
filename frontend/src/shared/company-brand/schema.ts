import { z } from 'zod';
import {
  COMPANY_BRAND_CATALOG_VERSION,
  type CompanyBrandMark,
} from './contract';

export const CompanyBrandMarkApiSchema = z.object({
  catalog_version: z.literal(COMPANY_BRAND_CATALOG_VERSION),
  source_icon: z.string().min(1),
  color_index: z.number().int().min(0).max(11),
  rotation_degrees: z.number().int().min(-12).max(12),
  flip_vertical: z.boolean(),
}).strict().transform((value): CompanyBrandMark => ({
  catalogVersion: value.catalog_version,
  sourceIcon: value.source_icon,
  colorIndex: value.color_index,
  rotationDegrees: value.rotation_degrees,
  flipVertical: value.flip_vertical,
}));
