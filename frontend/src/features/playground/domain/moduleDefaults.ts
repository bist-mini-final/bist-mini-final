import type { ModuleDefinition } from '../types';

export function objectConfig(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export function numericRecord(value: unknown): Record<string, number> {
  return Object.fromEntries(
    Object.entries(objectConfig(value)).filter(
      (entry): entry is [string, number] => typeof entry[1] === 'number',
    ),
  );
}

export function moduleConfigDefaults(
  definition: ModuleDefinition | undefined,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(definition?.config_schema.properties ?? {}).flatMap(([field, schema]) =>
      schema.default === undefined ? [] : [[field, schema.default]],
    ),
  );
}

export function moduleInputDefaults(
  definition: ModuleDefinition | undefined,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(definition?.input_schema.properties ?? {}).flatMap(([field, schema]) =>
      schema.default === undefined ? [] : [[field, schema.default]],
    ),
  );
}

export function resolveTargetInput(
  definition: ModuleDefinition | undefined,
  declaredInput: unknown,
): string | undefined {
  if (typeof declaredInput === 'string' && definition?.inputs.includes(declaredInput)) {
    return declaredInput;
  }
  return definition?.inputs.length === 1 ? definition.inputs[0] : undefined;
}
