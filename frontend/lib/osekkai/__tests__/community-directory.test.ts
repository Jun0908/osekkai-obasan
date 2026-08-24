import { mkdtempSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import path from 'path';
import { afterEach, describe, expect, it } from 'vitest';

import { loadCommunityDirectorySummary, loadCommunityFacilityDetail } from '../community-directory';

const ORIGINAL_ROOT = process.env.OSEKKAI_COMMUNITY_DATA_ROOT;

const HEADER = [
  'opportunity_id', 'ward_code', 'ward_name', 'title', 'genres', 'opportunity_type', 'verification_status',
  'participation_mode', 'target_age_min', 'target_age_max', 'eligibility_evidence', 'description', 'venue_name',
  'venue_address', 'latitude', 'longitude', 'official_url', 'source_classification', 'source_updated_at',
  'fetched_at', 'venue_address_source_url', 'venue_address_match_status',
];

const WARD_DIRECTORY_FIXTURE = {
  schemaVersion: '1.0',
  wards: {
    千代田区: {
      wardOffice: { key: 'chiyoda-office', name: '千代田区役所', address: '東京都千代田区九段南1-6-11', latitude: 35.694138, longitude: 139.752228, sourceUrl: 'https://www.city.chiyoda.lg.jp/' },
      anchors: [
        { key: 'kudan', match: '九段', name: '九段生涯学習館', address: '東京都千代田区九段南1-5-10', latitude: 35.695339, longitude: 139.751984, sourceUrl: 'https://www.city.chiyoda.lg.jp/shisetsu/bunka/kudan-gakushu.html' },
        { key: 'sports-center', match: 'スポーツセンター', name: '千代田区立スポーツセンター', address: '東京都千代田区内神田2-1-8', latitude: 35.689342, longitude: 139.767685, sourceUrl: 'https://www.city.chiyoda.lg.jp/shisetsu/bunka/sportscenter.html' },
      ],
    },
    新宿区: {
      wardOffice: { key: 'shinjuku-office', name: '新宿区役所', address: '東京都新宿区歌舞伎町1-4-1', latitude: 35.693535, longitude: 139.703476, sourceUrl: 'https://www.city.shinjuku.lg.jp/' },
      anchors: [],
    },
  },
};

const VENUE_ADDRESS_DIRECTORY_FIXTURE = {
  schemaVersion: '1.0',
  addresses: {
    '東京都渋谷区本町3-46-1': { ward: '渋谷区', latitude: 35.687641, longitude: 139.682785 },
  },
};

function writeOpportunitiesCsv(rows: string[][], addressFixture: Record<string, unknown> = VENUE_ADDRESS_DIRECTORY_FIXTURE): void {
  const dir = mkdtempSync(path.join(tmpdir(), 'osekkai-community-'));
  const lines = [HEADER, ...rows].map((row) => row.map((value) => `"${value.replace(/"/g, '""')}"`).join(','));
  writeFileSync(path.join(dir, 'adult_official_opportunities.csv'), `﻿${lines.join('\n')}\n`, 'utf-8');
  writeFileSync(path.join(dir, 'ward-geocoding-directory.json'), JSON.stringify(WARD_DIRECTORY_FIXTURE, null, 2), 'utf-8');
  writeFileSync(path.join(dir, 'venue-address-directory.json'), JSON.stringify(addressFixture, null, 2), 'utf-8');
  process.env.OSEKKAI_COMMUNITY_DATA_ROOT = dir;
}

afterEach(() => {
  if (ORIGINAL_ROOT === undefined) delete process.env.OSEKKAI_COMMUNITY_DATA_ROOT;
  else process.env.OSEKKAI_COMMUNITY_DATA_ROOT = ORIGINAL_ROOT;
});

function row(overrides: Partial<Record<(typeof HEADER)[number], string>>): string[] {
  return HEADER.map((column) => overrides[column] ?? '');
}

describe('loadCommunityDirectorySummary', () => {
  it('resolves Chiyoda venues to their known facility and other wards to the ward office', async () => {
    writeOpportunitiesCsv([
      row({ opportunity_id: 'opp_1', ward_name: '千代田区', title: '読書会さくら', description: '読書', venue_name: '九段' }),
      row({ opportunity_id: 'opp_2', ward_name: '千代田区', title: '卓球クラブ', description: 'スポーツ', venue_name: 'スポーツセンター' }),
      row({ opportunity_id: 'opp_3', ward_name: '千代田区', title: '未知施設の会', description: '謎', venue_name: '未知の施設' }),
      row({ opportunity_id: 'opp_4', ward_name: '新宿区', title: '新宿の会', description: 'その他', venue_name: '公民館' }),
      row({ opportunity_id: 'opp_5', ward_name: '福岡県', title: '対象外の会', description: 'その他', venue_name: '九段' }),
    ]);

    const result = await loadCommunityDirectorySummary();

    expect(result.counts).toEqual({ total: 4, withVenueAddress: 0, withKnownFacility: 2, withAreaLocation: 0, withWardOfficeFallback: 2 });
    expect(result.facilities).toHaveLength(4);

    const kudan = result.facilities.find((facility) => facility.key === 'kudan');
    expect(kudan).toMatchObject({ ward: '千代田区', count: 1, name: '九段生涯学習館' });

    const sportsCenter = result.facilities.find((facility) => facility.key === 'sports-center');
    expect(sportsCenter).toMatchObject({ ward: '千代田区', count: 1, name: '千代田区立スポーツセンター' });

    const chiyodaOffice = result.facilities.find((facility) => facility.key === 'chiyoda-office');
    expect(chiyodaOffice).toMatchObject({ ward: '千代田区', count: 1 });

    const shinjukuOffice = result.facilities.find((facility) => facility.key === 'shinjuku-office');
    expect(shinjukuOffice).toMatchObject({ ward: '新宿区', count: 1, name: '新宿区役所' });
  });

  it('uses the row\'s own latitude/longitude when the source pipeline geocoded one', async () => {
    writeOpportunitiesCsv([
      row({
        opportunity_id: 'opp_1', ward_name: '渋谷区', title: 'ヨガサークル', description: 'ヨガ',
        venue_name: '渋谷区民会館', venue_address: '東京都渋谷区渋谷1-1-1',
        latitude: '35.6598', longitude: '139.7036', venue_address_match_status: 'official_facility_exact',
      }),
    ]);

    const result = await loadCommunityDirectorySummary();

    expect(result.counts).toEqual({ total: 1, withVenueAddress: 1, withKnownFacility: 0, withAreaLocation: 0, withWardOfficeFallback: 0 });
    expect(result.facilities[0]).toMatchObject({
      key: 'latlng:35.659800,139.703600', ward: '渋谷区', latitude: 35.6598, longitude: 139.7036,
      locationKind: 'exact_address', locationPrecision: 'official_facility_exact',
    });
  });

  it('prefers a geocoded venue_address over the ward office fallback when no own coordinates exist', async () => {
    writeOpportunitiesCsv([
      row({
        opportunity_id: 'opp_1', ward_name: '渋谷区', title: 'あみもの教室', description: '手芸',
        venue_name: '本町区民会館', venue_address: '東京都渋谷区本町3-46-1',
      }),
      row({ opportunity_id: 'opp_2', ward_name: '渋谷区', title: '住所なしの会', description: 'その他', venue_name: '未登録施設' }),
    ]);

    const result = await loadCommunityDirectorySummary();

    expect(result.counts.withVenueAddress).toBe(1);
    const addressFacility = result.facilities.find((facility) => facility.key === 'addr:東京都渋谷区本町3-46-1');
    expect(addressFacility).toMatchObject({ ward: '渋谷区', count: 1, latitude: 35.687641, longitude: 139.682785 });
    // 渋谷区 has no ward-geocoding-directory entry in this fixture, so the second
    // (address-less, coordinate-less) row cannot resolve anywhere and is excluded.
    expect(result.facilities.some((facility) => facility.ward === '渋谷区' && facility.key !== addressFacility?.key)).toBe(false);
  });

  it('ignores a venue_address entry recorded under a different ward', async () => {
    writeOpportunitiesCsv([
      row({
        opportunity_id: 'opp_1', ward_name: '千代田区', title: '間違った区の会', description: '謎',
        venue_name: '未知の施設', venue_address: '東京都渋谷区本町3-46-1',
      }),
    ]);

    const result = await loadCommunityDirectorySummary();

    // The address is geocoded for 渋谷区, not 千代田区, so it must not be trusted
    // here — the row falls back to the Chiyoda ward office instead.
    expect(result.counts).toEqual({ total: 1, withVenueAddress: 0, withKnownFacility: 0, withAreaLocation: 0, withWardOfficeFallback: 1 });
    expect(result.facilities[0].key).toBe('chiyoda-office');
  });

  it('excludes town-association and senior-club rows when excludeAgeUnrelated is set', async () => {
    writeOpportunitiesCsv([
      row({ opportunity_id: 'opp_1', ward_name: '千代田区', title: '九段町会', genres: 'community_exchange', description: '町会・自治会', venue_name: '九段' }),
      row({ opportunity_id: 'opp_2', ward_name: '千代田区', title: '卓球クラブ', genres: 'sports', description: 'スポーツ', venue_name: 'スポーツセンター' }),
    ]);

    const result = await loadCommunityDirectorySummary({ excludeAgeUnrelated: true });

    expect(result.counts).toEqual({ total: 1, withVenueAddress: 0, withKnownFacility: 1, withAreaLocation: 0, withWardOfficeFallback: 0 });
    expect(result.facilities.find((facility) => facility.key === 'kudan')).toBeUndefined();
    expect(result.facilities.find((facility) => facility.key === 'sports-center')).toMatchObject({ count: 1 });
  });

  it('keeps only sports/exercise rows when onlySports is set', async () => {
    writeOpportunitiesCsv([
      row({ opportunity_id: 'opp_1', ward_name: '千代田区', title: '卓球クラブ', genres: 'sports', description: 'スポーツ', venue_name: 'スポーツセンター' }),
      row({ opportunity_id: 'opp_2', ward_name: '千代田区', title: '読書会さくら', genres: 'learning', description: '読書', venue_name: '九段' }),
    ]);

    const result = await loadCommunityDirectorySummary({ onlySports: true });

    expect(result.counts).toEqual({ total: 1, withVenueAddress: 0, withKnownFacility: 1, withAreaLocation: 0, withWardOfficeFallback: 0 });
    expect(result.facilities.find((facility) => facility.key === 'sports-center')).toMatchObject({ count: 1 });
    expect(result.facilities.find((facility) => facility.key === 'kudan')).toBeUndefined();
  });
});

describe('loadCommunityFacilityDetail', () => {
  it('returns only the communities resolved to the requested facility', async () => {
    writeOpportunitiesCsv([
      row({ opportunity_id: 'opp_1', ward_name: '千代田区', title: '読書会さくら', description: '読書', venue_name: '九段' }),
      row({ opportunity_id: 'opp_2', ward_name: '千代田区', title: '卓球クラブ', description: 'スポーツ', venue_name: 'スポーツセンター' }),
    ]);

    const detail = await loadCommunityFacilityDetail('kudan');

    expect(detail).not.toBeNull();
    expect(detail?.communities.map((community) => community.name)).toEqual(['読書会さくら']);
    expect(detail?.latitude).toBeCloseTo(35.695339, 5);
  });

  it('returns null for a facility key with no matching communities', async () => {
    writeOpportunitiesCsv([
      row({ opportunity_id: 'opp_1', ward_name: '千代田区', title: '読書会さくら', description: '読書', venue_name: '九段' }),
    ]);

    expect(await loadCommunityFacilityDetail('sports-center')).toBeNull();
  });

  it('drops town-association communities from the list when excludeAgeUnrelated is set', async () => {
    writeOpportunitiesCsv([
      row({ opportunity_id: 'opp_1', ward_name: '千代田区', title: '読書会さくら', description: '読書', venue_name: 'スポーツセンター' }),
      row({ opportunity_id: 'opp_2', ward_name: '千代田区', title: '九段町会', description: '町会・自治会', venue_name: 'スポーツセンター' }),
    ]);

    const detail = await loadCommunityFacilityDetail('sports-center', { excludeAgeUnrelated: true });

    expect(detail?.communities.map((community) => community.name)).toEqual(['読書会さくら']);
  });
});
