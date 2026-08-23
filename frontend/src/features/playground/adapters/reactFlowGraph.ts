import type { Node } from '@xyflow/react';
import { NODE_MODULE_TYPES } from '../config/pipeline';
import type { ModuleType } from '../types';

export function nodeModuleType(
  node: Pick<Node, 'type' | 'data'> | undefined,
): ModuleType | undefined {
  const explicitType = node?.data.moduleType;
  return typeof explicitType === 'string'
    ? explicitType as ModuleType
    : NODE_MODULE_TYPES[node?.type ?? ''];
}
