import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ConnectionEvidence, LiveEvent, Opportunity, RankedOpportunity } from '@/lib/osekkai/types.generated';
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

const event = (id: string, title: string, status: LiveEvent['status'] = 'scheduled'): LiveEvent => ({
  schemaVersion: '1.0', id, provider: 'tokyo', sourceRecordId: id, title, description: '公開説明',
  startsAt: '2026-09-05T14:00:00+09:00', endsAt: '2026-09-05T16:00:00+09:00', timezone: 'Asia/Tokyo',
  venueName: '東京会場', address: '東京都', latitude: null, longitude: null, communityId: null, seriesId: null,
  status, registrationStatus: status === 'scheduled' ? 'open' : 'closed', registrationDeadline: null,
  capacity: null, participants: null, priceYen: null, categories: [], sourceUrl: `https://example.com/${id}`,
  sourceDataset: '東京都Open Data', license: 'CC BY', sourceClassification: 'raw_open_data',
  sourceUpdatedAt: '2026-08-23T09:00:00+09:00', fetchedAt: '2026-08-23T09:00:00+09:00',
  revalidatedAt: '2026-08-23T09:00:00+09:00', checksum: 'b'.repeat(64), fieldProvenance: {
    title: { classification: 'source_verified', sourceUrl: `https://example.com/${id}`, capturedAt: '2026-08-23T09:00:00+09:00' },
  },
});

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
    const evidence: ConnectionEvidence[] = [];
    render(<EventMap events={[event('exhibition', '大規模展示'), event('canceled', '中止になった交流会', 'canceled')]} opportunities={[]} evidence={evidence} ranking={[]} />);
    expect(screen.getByText('大規模展示')).toBeInTheDocument();
    expect(screen.getByText('中止になった交流会')).toBeInTheDocument();
    expect(screen.getByText(/2件中/)).toBeInTheDocument();
  });

  it('falls back to region search when browser geolocation is denied', () => {
    const getCurrentPosition = vi.fn((_: PositionCallback, error: PositionErrorCallback) => {
      error({ code: 1, message: 'denied', PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 });
    });
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition },
    });

    render(<EventMap events={[event('community', '地域の交流会')]} opportunities={[]} evidence={[]} ranking={[]} />);
    fireEvent.click(screen.getByRole('button', { name: /現在地から探す/ }));

    expect(getCurrentPosition).toHaveBeenCalledOnce();
    expect(screen.getByText('現在地を使わず、地域名で探せます')).toBeInTheDocument();
    expect(screen.getByLabelText('駅名または地域名')).toBeInTheDocument();
  });
});
