export interface JsonPreview {
  text: string;
  truncated: boolean;
}

export interface JsonPreviewLimits {
  maxArrayItems: number;
  maxDepth: number;
  maxLines: number;
  maxNodes: number;
  maxObjectFields: number;
  maxStringCharacters: number;
  maxTextCharacters: number;
}

export const DEFAULT_JSON_PREVIEW_LIMITS: JsonPreviewLimits = {
  maxArrayItems: 12,
  maxDepth: 6,
  maxLines: 120,
  maxNodes: 300,
  maxObjectFields: 20,
  maxStringCharacters: 600,
  maxTextCharacters: 24_000,
};

function serializablePrimitive(value: unknown): unknown {
  if (value === undefined) return '[undefined]';
  if (typeof value === 'bigint') return `${value.toString()}n`;
  if (typeof value === 'number' && !Number.isFinite(value)) return String(value);
  if (typeof value === 'function') return '[function]';
  if (typeof value === 'symbol') return value.toString();
  return value;
}

/**
 * Build a bounded JSON representation without stringifying or cloning the full value.
 * This function is intentionally a UI preview only; workflow state remains untouched.
 */
export function formatJsonPreview(
  value: unknown,
  limits: JsonPreviewLimits = DEFAULT_JSON_PREVIEW_LIMITS,
): JsonPreview {
  let truncated = false;
  let visitedNodes = 0;
  const seen = new WeakSet<object>();

  const compact = (current: unknown, depth: number): unknown => {
    visitedNodes += 1;
    if (visitedNodes > limits.maxNodes) {
      truncated = true;
      return '[preview node limit reached]';
    }
    if (typeof current === 'string') {
      if (current.length <= limits.maxStringCharacters) return current;
      truncated = true;
      const remainingCharacters = current.length - limits.maxStringCharacters;
      return `${current.slice(0, limits.maxStringCharacters)}… (${remainingCharacters} more characters)`;
    }
    if (current === null || typeof current !== 'object') {
      return serializablePrimitive(current);
    }
    if (depth >= limits.maxDepth) {
      truncated = true;
      return '[maximum preview depth reached]';
    }
    if (seen.has(current)) {
      truncated = true;
      return '[circular reference]';
    }
    seen.add(current);

    if (Array.isArray(current)) {
      const visibleCount = Math.min(current.length, limits.maxArrayItems);
      const result = current
        .slice(0, visibleCount)
        .map((item) => compact(item, depth + 1));
      if (current.length > visibleCount) {
        truncated = true;
        result.push(`… ${current.length - visibleCount} more items`);
      }
      return result;
    }

    const result: Record<string, unknown> = {};
    let fieldCount = 0;
    for (const key in current) {
      if (!Object.prototype.hasOwnProperty.call(current, key)) continue;
      if (fieldCount >= limits.maxObjectFields) {
        truncated = true;
        result['…'] = 'additional fields omitted';
        break;
      }
      result[key] = compact((current as Record<string, unknown>)[key], depth + 1);
      fieldCount += 1;
    }
    return result;
  };

  const compacted = compact(value, 0);
  const serialized = JSON.stringify(compacted, null, 2) ?? String(compacted);
  const lines = serialized.split('\n');
  let text = serialized;
  if (lines.length > limits.maxLines) {
    truncated = true;
    const remainingLines = lines.length - limits.maxLines;
    text = `${lines.slice(0, limits.maxLines).join('\n')}\n… (${remainingLines} more lines)`;
  }
  if (text.length > limits.maxTextCharacters) {
    truncated = true;
    text = `${text.slice(0, limits.maxTextCharacters)}\n… (preview character limit reached)`;
  }
  return { text, truncated };
}
