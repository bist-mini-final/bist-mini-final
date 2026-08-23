function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

/**
 * Resolves a named backend output port while retaining compatibility with
 * legacy payloads that exposed the port value directly.
 */
export function unwrapModuleOutput<T extends Record<string, unknown>>(
  output: unknown,
  port: string,
): T | null {
  if (!isRecord(output)) return null;
  const portValue = output[port];
  return isRecord(portValue) ? portValue as T : output as T;
}
