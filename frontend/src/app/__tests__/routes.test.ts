import { describe, it, expect } from 'vitest';
import { APP_ROUTES, findRoute } from '../routes';

describe('APP_ROUTES registry', () => {
  it('registers all required routes with valid metadata', () => {
    const paths = APP_ROUTES.map((r) => r.path);
    expect(paths).toContain('/');
    expect(paths).toContain('/playground');
    expect(paths).toContain('/data-sources');
    expect(paths).toContain('/dashboard');
    expect(paths).toContain('/company-comparison');
    expect(paths).toContain('/company-comparison-v2');
    expect(paths).toContain('/jobs');
    expect(paths).toContain('/settings');
    expect(paths).not.toContain('/evaluations');
  });

  it('has ready status for core pages', () => {
    const home = APP_ROUTES.find((r) => r.path === '/');
    const playground = APP_ROUTES.find((r) => r.path === '/playground');
    const dataSources = APP_ROUTES.find((r) => r.path === '/data-sources');
    const dashboard = APP_ROUTES.find((r) => r.path === '/dashboard');

    expect(home?.status).toBe('ready');
    expect(playground?.status).toBe('ready');
    expect(dataSources?.status).toBe('ready');
    expect(dashboard?.status).toBe('ready');
  });

  it('resolves the documented BI compatibility path without duplicating navigation', () => {
    expect(findRoute('/bi')?.path).toBe('/dashboard');
    expect(APP_ROUTES.filter((route) => route.path === '/dashboard')).toHaveLength(1);
  });
});
