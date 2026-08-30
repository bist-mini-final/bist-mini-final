import { beforeEach, describe, expect, it, vi } from 'vitest';

const httpMocks = vi.hoisted(() => ({
  requestJson: vi.fn(),
  requestResponse: vi.fn(),
}));

vi.mock('../../../shared/api/httpClient', () => httpMocks);

import { dataSourceApi } from './dataSourceApi';

describe('dataSourceApi.updateIndexCompany', () => {
  beforeEach(() => {
    httpMocks.requestJson.mockReset();
  });

  it('uses the backend company update contract', async () => {
    httpMocks.requestJson.mockResolvedValue({
      status: 'success',
      index_id: 'index/a',
      company_name: 'Renamed Company',
    });

    await dataSourceApi.updateIndexCompany('index/a', 'Renamed Company');

    expect(httpMocks.requestJson).toHaveBeenCalledWith(
      '/api/data-sources/indexes/index%2Fa/company',
      {
        method: 'PUT',
        json: { company_name: 'Renamed Company' },
        signal: undefined,
      },
    );
  });
});
