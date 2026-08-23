import { mkdtempSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import path from 'path';
import { afterEach, describe, expect, it } from 'vitest';

import { loadCommunityDirectorySummary, loadCommunityFacilityDetail } from '../community-directory';

const ORIGINAL_ROOT = process.env.OSEKKAI_COMMUNITY_DATA_ROOT;

const HEADER = [
  'community_id', 'ward_code', 'ward_name', 'name', 'name_kana', 'category', 'activity_status',
  'description', 'source_comment', 'target_audience', 'target_audience_notes', 'venue_name',
  'venue_notes', 'venue_address', 'official_url', 'online_participation', 'foreign_language_support',
  'area_name', 'map_location_id', 'latitude', 'longitude', 'geocoded_address',
  'location_precision', 'location_source', 'location_source_url',
  'supported_languages', 'inbound_program', 'notes', 'source_updated_at', 'fetched_at',
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

function writeCommunitiesCsv(rows: string[][], addressFixture: Record<string, unknown> = VENUE_ADDRESS_DIRECTORY_FIXTURE): void {
  const dir = mkdtempSync(path.join(tmpdir(), 'osekkai-community-'));
  const lines = [HEADER, ...rows].map((row) => row.map((value) => `"${value.replace(/"/g, '""')}"`).join(','));
  writeFileSync(path.join(dir, 'communities.csv'), `﻿${lines.join('\n')}\n`, 'utf-8');
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
    writeCommunitiesCsv([
      row({ community_id: 'community_1', ward_name: '千代田区', name: '読書会さくら', description: '読書', venue_name: '九段;スポーツセンター' }),
      row({ community_id: 'community_2', ward_name: '千代田区', name: '卓球クラブ', description: 'スポーツ', venue_name: 'スポーツセンター' }),
      row({ community_id: 'community_3', ward_name: '千代田区', name: '未知施設の会', description: '謎', venue_name: '未知の施設' }),
      row({ community_id: 'community_4', ward_name: '新宿区', name: '新宿の会', description: 'その他', venue_name: '公民館' }),
      row({ community_id: 'community_5', ward_name: '福岡県', name: '対象外の会', description: 'その他', venue_name: '九段' }),
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

  it('prefers a geocoded venue_address over the ward office fallback', async () => {
    writeCommunitiesCsv([
      row({
        community_id: 'community_1', ward_name: '渋谷区', name: 'あみもの教室', description: '手芸',
        venue_name: '本町区民会館', venue_address: '東京都渋谷区本町3-46-1',
      }),
      row({ community_id: 'community_2', ward_name: '渋谷区', name: '住所なしの会', description: 'その他', venue_name: '未登録施設' }),
    ]);

    const result = await loadCommunityDirectorySummary();

    expect(result.counts.withVenueAddress).toBe(1);
    const addressFacility = result.facilities.find((facility) => facility.key === 'addr:東京都渋谷区本町3-46-1');
    expect(addressFacility).toMatchObject({ ward: '渋谷区', count: 1, latitude: 35.687641, longitude: 139.682785 });
    // 渋谷区 has no ward-geocoding-directory entry in this fixture, so the second
    // (address-less) row cannot resolve anywhere and is simply excluded.
    expect(result.facilities.some((facility) => facility.ward === '渋谷区' && facility.key !== addressFacility?.key)).toBe(false);
  });

  it('ignores a venue_address entry recorded under a different ward', async () => {
    writeCommunitiesCsv([
      row({
        community_id: 'community_1', ward_name: '千代田区', name: '間違った区の会', description: '謎',
        venue_name: '未知の施設', venue_address: '東京都渋谷区本町3-46-1',
      }),
    ]);

    const result = await loadCommunityDirectorySummary();

    // The address is geocoded for 渋谷区, not 千代田区, so it must not be trusted
    // here — the row falls back to the Chiyoda ward office instead.
    expect(result.counts).toEqual({ total: 1, withVenueAddress: 0, withKnownFacility: 0, withAreaLocation: 0, withWardOfficeFallback: 1 });
    expect(result.facilities[0].key).toBe('chiyoda-office');
  });

  it('uses a CSV activity-area point before the ward office and labels it approximate', async () => {
    writeCommunitiesCsv([
      row({
        community_id: 'community_area', ward_name: '新宿区', name: '西新宿一丁目町会', description: '町会・自治会',
        area_name: '西新宿一丁目', map_location_id: 'map_nishishinjuku', latitude: '35.6912', longitude: '139.6996',
        geocoded_address: '東京都新宿区西新宿一丁目', location_precision: 'name_chome',
        location_source: 'community_name', location_source_url: 'https://maps.gsi.go.jp/',
      }),
    ]);

    const result = await loadCommunityDirectorySummary();

    expect(result.counts).toEqual({ total: 1, withVenueAddress: 0, withKnownFacility: 0, withAreaLocation: 1, withWardOfficeFallback: 0 });
    expect(result.facilities[0]).toMatchObject({
      key: 'map_nishishinjuku', locationKind: 'activity_area', locationPrecision: 'name_chome',
      name: '西新宿一丁目（活動区域の目安）',
    });
  });

  it('labels the first point of an explicit multi-venue record as representative', async () => {
    writeCommunitiesCsv([
      row({
        community_id: 'community_multi', ward_name: '千代田区', name: '二会場の会', description: '文化',
        venue_address: '東京都千代田区九段南1-5-10 | 東京都千代田区内神田2-1-8',
        map_location_id: 'map_multi', latitude: '35.6953', longitude: '139.7520',
        geocoded_address: '東京都千代田区九段南一丁目5番10号',
        location_precision: 'multiple_addresses_representative', location_source: 'venue_address',
      }),
    ]);

    const result = await loadCommunityDirectorySummary();

    expect(result.counts.withVenueAddress).toBe(1);
    expect(result.facilities[0]).toMatchObject({
      key: 'map_multi', locationKind: 'multiple_addresses',
      name: '千代田区九段南一丁目5番10号（複数会場の代表）',
    });
  });
});

describe('loadCommunityFacilityDetail', () => {
  it('returns only the communities resolved to the requested facility', async () => {
    writeCommunitiesCsv([
      row({ community_id: 'community_1', ward_name: '千代田区', name: '読書会さくら', description: '読書', venue_name: '九段' }),
      row({ community_id: 'community_2', ward_name: '千代田区', name: '卓球クラブ', description: 'スポーツ', venue_name: 'スポーツセンター' }),
    ]);

    const detail = await loadCommunityFacilityDetail('kudan');

    expect(detail).not.toBeNull();
    expect(detail?.communities.map((community) => community.name)).toEqual(['読書会さくら']);
    expect(detail?.latitude).toBeCloseTo(35.695339, 5);
  });

  it('returns null for a facility key with no matching communities', async () => {
    writeCommunitiesCsv([
      row({ community_id: 'community_1', ward_name: '千代田区', name: '読書会さくら', description: '読書', venue_name: '九段' }),
    ]);

    expect(await loadCommunityFacilityDetail('sports-center')).toBeNull();
  });
});
