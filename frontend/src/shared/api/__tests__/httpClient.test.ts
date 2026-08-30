import { describe, expect, it } from 'vitest';
import { API_V1_PREFIX, versionedApiEndpoint } from '../httpClient';

describe('versionedApiEndpoint', () => {
  it('moves legacy API paths to the canonical v1 namespace', () => {
    expect(versionedApiEndpoint('/api/workflows?limit=10'))
      .toBe('/api/v1/workflows?limit=10');
    expect(versionedApiEndpoint('/api')).toBe(API_V1_PREFIX);
  });

  it('does not double-version or rewrite non-API resources', () => {
    expect(versionedApiEndpoint('/api/v1/bi/companies'))
      .toBe('/api/v1/bi/companies');
    expect(versionedApiEndpoint('/healthz')).toBe('/healthz');
  });
});
