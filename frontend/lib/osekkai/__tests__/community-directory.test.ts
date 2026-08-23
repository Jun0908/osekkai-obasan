import { mkdtempSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import path from 'path';
import { afterEach, describe, expect, it } from 'vitest';

import { loadCommunityDirectorySummary, loadCommunityFacilityDetail } from '../community-directory';

const ORIGINAL_ROOT = process.env.OSEKKAI_COMMUNITY_DATA_ROOT;

const HEADER = [
  'community_id', 'ward_code', 'ward_name', 'name', 'name_kana', 'category', 'activity_status',
  'description', 'source_comment', 'target_audience', 'target_audience_notes', 'venue_name',
  'venue_notes', 'venue_address', 'venue_address_source_url', 'venue_address_match_status',
  'area_name', 'map_query', 'map_location_id', 'latitude', 'longitude', 'geocoded_address',
  'location_precision', 'location_source', 'location_source_url', 'official_url',
  'online_participation', 'foreign_language_support', 'supported_languages', 'inbound_program',
  'notes', 'source_updated_at', 'fetched_at',
];

const WARD_DIRECTORY_FIXTURE = {
  schemaVersion: '1.0',
  wards: {
    千代田区: {
      wardOffice: { key: 'chiyoda-office', name: '千代田区役所', address: '東京都千代田区九段南1-6-11', latitude: 35.694138, longitude: 139.752228, sourceUrl: 'https://www.city.chiyoda.lg.jp/' },
    },
  },
};

function writeCommunitiesCsv(rows: string[][]): void {
  const dir = mkdtempSync(path.join(tmpdir(), 'osekkai-community-'));
  const lines = [HEADER, ...rows].map((row) => row.map((value) => `"${value.replace(/"/g, '""')}"`).join(','));
  writeFileSync(path.join(dir, 'communities.csv'), `﻿${lines.join('\n')}\n`, 'utf-8');
  writeFileSync(path.join(dir, 'ward-geocoding-directory.json'), JSON.stringify(WARD_DIRECTORY_FIXTURE, null, 2), 'utf-8');
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
  it('groups rows sharing a map_location_id under one precise point', async () => {
    writeCommunitiesCsv([
      row({
        community_id: 'community_1', ward_name: '渋谷区', name: 'あみもの教室', description: '手芸',
        venue_name: '本町区民会館', venue_address: '東京都渋谷区本町3-46-1',
        map_location_id: 'map_abc', latitude: '35.687641', longitude: '139.682785',
        geocoded_address: '東京都渋谷区本町三丁目46番1号',
      }),
      row({
        community_id: 'community_2', ward_name: '渋谷区', name: '茶道教室', description: '茶華道',
        venue_name: '本町区民会館', venue_address: '東京都渋谷区本町3-46-1',
        map_location_id: 'map_abc', latitude: '35.687641', longitude: '139.682785',
        geocoded_address: '東京都渋谷区本町三丁目46番1号',
      }),
      row({ community_id: 'community_3', ward_name: '千代田区', name: '未登録の会', description: '謎' }),
    ]);

    const result = await loadCommunityDirectorySummary();

    expect(result.counts).toEqual({ total: 3, withPreciseLocation: 2, withWardOfficeFallback: 1 });
    expect(result.facilities).toHaveLength(2);

    const precise = result.facilities.find((facility) => facility.key === 'loc:map_abc');
    expect(precise).toMatchObject({ ward: '渋谷区', count: 2, name: '本町区民会館', precise: true });
    expect(precise?.latitude).toBeCloseTo(35.687641, 5);

    const office = result.facilities.find((facility) => facility.key === 'chiyoda-office');
    expect(office).toMatchObject({ ward: '千代田区', count: 1, name: '千代田区役所', precise: false });
  });

  it('derives a facility name from the geocoded address when venue_name is blank', async () => {
    writeCommunitiesCsv([
      row({
        community_id: 'community_1', ward_name: '渋谷区', name: '無名施設の会', description: 'その他',
        map_location_id: 'map_xyz', latitude: '35.66', longitude: '139.7',
        geocoded_address: '東京都渋谷区代々木1-1-1',
      }),
    ]);

    const result = await loadCommunityDirectorySummary();

    expect(result.facilities[0].name).toBe('渋谷区代々木1-1-1');
  });

  it('excludes rows with an unparseable latitude/longitude and an unknown ward', async () => {
    writeCommunitiesCsv([
      row({ community_id: 'community_1', ward_name: '福岡県', name: '対象外の会', description: 'その他' }),
      row({
        community_id: 'community_2', ward_name: '渋谷区', name: '壊れた座標の会', description: 'その他',
        latitude: 'not-a-number', longitude: '139.7',
      }),
    ]);

    const result = await loadCommunityDirectorySummary();

    expect(result.counts).toEqual({ total: 0, withPreciseLocation: 0, withWardOfficeFallback: 0 });
    expect(result.facilities).toEqual([]);
  });
});

describe('loadCommunityFacilityDetail', () => {
  it('returns only the communities resolved to the requested facility', async () => {
    writeCommunitiesCsv([
      row({
        community_id: 'community_1', ward_name: '渋谷区', name: 'あみもの教室', description: '手芸',
        map_location_id: 'map_abc', latitude: '35.687641', longitude: '139.682785',
      }),
      row({ community_id: 'community_2', ward_name: '千代田区', name: '未登録の会', description: '謎' }),
    ]);

    const detail = await loadCommunityFacilityDetail('loc:map_abc');

    expect(detail).not.toBeNull();
    expect(detail?.communities.map((community) => community.name)).toEqual(['あみもの教室']);
    expect(detail?.latitude).toBeCloseTo(35.687641, 5);
    expect(detail?.precise).toBe(true);
  });

  it('returns null for a facility key with no matching communities', async () => {
    writeCommunitiesCsv([
      row({ community_id: 'community_1', ward_name: '千代田区', name: '未登録の会', description: '謎' }),
    ]);

    expect(await loadCommunityFacilityDetail('loc:map_missing')).toBeNull();
  });
});
