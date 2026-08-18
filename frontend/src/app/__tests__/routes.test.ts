import { describe, it, expect } from 'vitest';
import { APP_ROUTES } from '../routes';

describe('APP_ROUTES registry', () => {
  it('registers all required routes with valid metadata', () => {
    const paths = APP_ROUTES.map((r) => r.path);
    expect(paths).toContain('/');
    expect(paths).toContain('/playground');
    expect(paths).toContain('/data-sources');
    expect(paths).toContain('/evaluations');
    expect(paths).toContain('/bi');
    expect(paths).toContain('/settings');
  });

  it('has ready status for core pages', () => {
    const home = APP_ROUTES.find((r) => r.path === '/');
    const playground = APP_ROUTES.find((r) => r.path === '/playground');
    const dataSources = APP_ROUTES.find((r) => r.path === '/data-sources');
    const bi = APP_ROUTES.find((r) => r.path === '/bi');

    expect(home?.status).toBe('ready');
    expect(playground?.status).toBe('ready');
    expect(dataSources?.status).toBe('ready');
    expect(bi?.status).toBe('ready');
  });
});
