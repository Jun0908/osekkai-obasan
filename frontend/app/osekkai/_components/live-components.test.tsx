import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { MapEventSummary, Opportunity, RankedOpportunity } from '@/lib/osekkai/types.generated';
import EventMap from './event-map';
import LiveSourceStrip from './live-source-strip';
import RecommendationShortlist from './recommendation-shortlist';

afterEach(cleanup);

const opportunity = (id: string, title: string): Opportunity => ({
  schemaVersion: '1.0', id, eventId: `event-${id}`, communityId: null, seriesId: null,
  title, startsAt: '2026-09-05T14:00:00+09:00', endsAt: '2026-09-05T16:00:00+09:00',
  address: '東京都江東区', priceYen: 500, socialIntensity: 2, conversationRequired: 'medium',
  soloFriendly: true, provider: 'doorkeeper', sourceType: 'live_provider', sourceClassification: 'live_provider',
  sourceUrl: `https://example.com/${id}`, sourceDataset: 'Official API', license: 'terms',
  capturedAt: '2026-08-23T09:00:00+09:00', sourceUpdatedAt: '2026-08-23T09:00:00+09:00',
  fetchedAt: '2026-08-23T09:00:00+09:00', revalidatedAt: '2026-08-23T09:00:00+09:00',
  checksum: 'a'.repeat(64), dataMode: 'live', verificationStatus: 'source_verified', fieldProvenance: {
    title: { classification: 'source_verified', sourceUrl: `https://example.com/${id}`, capturedAt: '2026-08-23T09:00:00+09:00' },
  }, travelEstimate: { mode: 'walk', minutes: 8, source: 'maps_verified' }, status: 'scheduled',
  registrationStatus: 'open', registrationDeadline: null, capacity: 20, participants: 8,
});

const ranking: RankedOpportunity[] = ['one', 'two'].map((id, index) => ({
  rank: index + 1, score: 0.9 - index * 0.1, opportunityId: id,
  recommendationReasons: [{ code: 'connection', text: `交流根拠 ${index + 1}`, evidenceUrl: `https://example.com/${id}`, classification: 'live_provider' }],
  exclusionReasons: [],
}));

const event = (id: string, title: string, status: MapEventSummary['status'] = 'scheduled'): MapEventSummary => ({
  id, provider: 'tokyo', title,
  startsAt: '2026-09-05T14:00:00+09:00', endsAt: '2026-09-05T16:00:00+09:00',
  venueName: '麹町会場', address: '東京都千代田区麹町1丁目', latitude: 35.684, longitude: 139.7373, seriesId: null,
  status, registrationStatus: status === 'scheduled' ? 'open' : 'closed',
  capacity: null, participants: null, priceYen: null, categories: [], sourceUrl: `https://example.com/${id}`,
  sourceClassification: 'raw_open_data', revalidatedAt: '2026-08-23T09:00:00+09:00',
  opportunityId: null, travelMinutes: null, connectionEvidence: null,
});

const mapProps = {
  ranking: [] as RankedOpportunity[],
  counts: { totalInMesh: 2, inWard: 2, withCoordinates: 2, missingCoordinates: 0, returned: 2 },
  loading: false,
  loadingMore: false,
};

describe('Live judge components', () => {
  it('shows multiple ranked recommendations with source facts', () => {
    const unknownPrice = opportunity('two', '月例ごはん会');
    unknownPrice.priceYen = null;
    render(<RecommendationShortlist opportunities={[unknownPrice, opportunity('one', '初心者ボードゲーム')]} ranking={ranking} />);
    expect(screen.getByText('初心者ボードゲーム')).toBeInTheDocument();
    expect(screen.getByText('月例ごはん会')).toBeInTheDocument();
    expect(screen.getByText(/#1/)).toBeInTheDocument();
    expect(screen.getAllByText(/Google Routes 8分/)).toHaveLength(2);
    expect(screen.getByText('料金未確認')).toBeInTheDocument();
  });

  it('shows required provider health and counts', () => {
    render(<LiveSourceStrip status={{ schemaVersion: '1.0', dataMode: 'live', generatedAt: '2026-08-23T09:00:00+09:00', counts: { events: 12, eligibleEvents: 5, opportunities: 3, providerErrors: 0 }, sources: [{ id: 'tokyo', displayName: '東京都Open Data', requiredForDemo: true, readiness: 'ready', health: 'healthy', lastAttemptAt: '2026-08-23T09:00:00+09:00', lastSuccessAt: '2026-08-23T09:00:00+09:00', eventCount: 12, datasetCount: 2, error: null, stale: false, refreshMinutes: 60 }] }} />);
    expect(screen.getByText('東京都Open Data')).toBeInTheDocument();
    expect(screen.getByText(/12件を取得・3件を推薦候補化/)).toBeInTheDocument();
  });

  it('keeps non-recommended and canceled events in the complete fallback list', () => {
    render(<EventMap {...mapProps} events={[event('exhibition', '大規模展示'), event('canceled', '中止になった交流会', 'canceled')]} />);
    expect(screen.getByText('大規模展示')).toBeInTheDocument();
    expect(screen.getByText('中止になった交流会')).toBeInTheDocument();
    expect(screen.getByText(/千代田区2件/)).toBeInTheDocument();
  });

  it('falls back to region search when browser geolocation is denied', () => {
    const getCurrentPosition = vi.fn((_: PositionCallback, error: PositionErrorCallback) => {
      error({ code: 1, message: 'denied', PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 });
    });
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition },
    });

    render(<EventMap {...mapProps} events={[event('community', '地域の交流会')]} />);
    fireEvent.click(screen.getByRole('button', { name: /現在地を移動時間に使う/ }));

    expect(getCurrentPosition).toHaveBeenCalledOnce();
    expect(screen.getByText('現在地を使わず、地図のEventを見られます')).toBeInTheDocument();
  });
});
