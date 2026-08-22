import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  getOsekkaiSession: vi.fn(),
  osekkaiRequest: vi.fn(),
}));

vi.mock('./api-client', () => ({
  friendlyApiError: (error: unknown) => error instanceof Error ? error.message : String(error),
  getOsekkaiSession: apiMocks.getOsekkaiSession,
  osekkaiRequest: apiMocks.osekkaiRequest,
}));

import ImpactClient from './impact-client';

const unverifiedLabels = [
  'Third Place Acquisition Rate',
  'Role Acquisition Rate',
  'OSEKKAI Graduation Rate',
  'UCLA-3 baseline',
  'UCLA-3 week 4',
  'UCLA-3 week 8',
  'Loneliness Point-Weeks Avoided',
];

describe('Impact canonical metrics contract', () => {
  beforeEach(() => {
    apiMocks.getOsekkaiSession.mockResolvedValue({
      csrfToken: 'csrf-test-token',
      dataMode: 'demo',
      expiresAt: '2026-08-22T12:00:00+09:00',
    });
    apiMocks.osekkaiRequest.mockImplementation(async (path: string) => {
      if (path === '/profile') return {};
      if (path === '/interventions') {
        return {
          interventions: [{
            id: '11111111-1111-4111-8111-111111111111',
            sequence: 1,
            decidedAt: '2026-08-22T10:00:00+09:00',
            decision: 'do_not_push',
            shouldPush: false,
            reasonCodes: ['NO_PUSH_CONSENT'],
            metricClassification: 'demo',
          }],
        };
      }
      if (path === '/metrics') {
        return {
          schemaVersion: '1.0',
          generatedAt: '2026-08-22T10:00:00+09:00',
          dataMode: 'demo',
          metrics: [],
          unverifiedMetrics: unverifiedLabels.map((label, index) => ({
            key: `unverified-${index}`,
            label,
            value: null,
            classification: 'unverified',
            note: `canonical note ${index}`,
          })),
        };
      }
      throw new Error(`unexpected path: ${path}`);
    });
  });

  it('renders every canonical unverified metric without replacing or merging entries', async () => {
    render(<ImpactClient />);

    expect(await screen.findByRole('heading', { name: unverifiedLabels[0] })).toBeInTheDocument();
    for (const label of unverifiedLabels) {
      expect(screen.getByRole('heading', { name: label })).toBeInTheDocument();
    }
    expect(screen.getAllByText(/canonical note/)).toHaveLength(7);
  });
});
