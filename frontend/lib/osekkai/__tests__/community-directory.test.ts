import { mkdtempSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import path from 'path';
import { afterEach, describe, expect, it } from 'vitest';

import { loadCommunityDirectory } from '../community-directory';

const ORIGINAL_ROOT = process.env.OSEKKAI_COMMUNITY_DATA_ROOT;

const HEADER = [
  'community_id', 'ward_code', 'ward_name', 'name', 'name_kana', 'category', 'activity_status',
  'description', 'source_comment', 'target_audience', 'target_audience_notes', 'venue_name',
  'venue_notes', 'venue_address', 'official_url', 'online_participation', 'foreign_language_support',
  'supported_languages', 'inbound_program', 'notes', 'source_updated_at', 'fetched_at',
];

function writeCommunitiesCsv(rows: string[][]): void {
  const dir = mkdtempSync(path.join(tmpdir(), 'osekkai-community-'));
  const lines = [HEADER, ...rows].map((row) => row.map((value) => `"${value.replace(/"/g, '""')}"`).join(','));
  writeFileSync(path.join(dir, 'communities.csv'), `﻿${lines.join('\n')}\n`, 'utf-8');
  process.env.OSEKKAI_COMMUNITY_DATA_ROOT = dir;
}

afterEach(() => {
  if (ORIGINAL_ROOT === undefined) delete process.env.OSEKKAI_COMMUNITY_DATA_ROOT;
  else process.env.OSEKKAI_COMMUNITY_DATA_ROOT = ORIGINAL_ROOT;
});

function row(overrides: Partial<Record<(typeof HEADER)[number], string>>): string[] {
  return HEADER.map((column) => overrides[column] ?? '');
}

describe('loadCommunityDirectory', () => {
  it('groups Chiyoda communities by known facility and geocodes them from official addresses', async () => {
    writeCommunitiesCsv([
      row({ community_id: 'community_1', ward_name: '千代田区', name: '読書会さくら', description: '読書', venue_name: '九段;スポーツセンター' }),
      row({ community_id: 'community_2', ward_name: '千代田区', name: '卓球クラブ', description: 'スポーツ', venue_name: 'スポーツセンター' }),
      row({ community_id: 'community_3', ward_name: '千代田区', name: '行き先不明の会', description: '謎', venue_name: '未知の施設' }),
      row({ community_id: 'community_4', ward_name: '新宿区', name: 'よその区の会', description: 'その他', venue_name: '九段' }),
    ]);

    const result = await loadCommunityDirectory('千代田区');

    expect(result.ward).toBe('千代田区');
    expect(result.counts).toEqual({ totalInWard: 3, withKnownVenue: 2, withoutKnownVenue: 1 });
    expect(result.facilities).toHaveLength(2);

    const kudan = result.facilities.find((facility) => facility.key === 'kudan');
    expect(kudan?.communities.map((community) => community.name)).toEqual(['読書会さくら']);
    expect(kudan?.latitude).toBeCloseTo(35.695339, 5);
    expect(kudan?.longitude).toBeCloseTo(139.751984, 5);
    expect(kudan?.address).toBe('東京都千代田区九段南1-5-10');

    const sportsCenter = result.facilities.find((facility) => facility.key === 'sports-center');
    expect(sportsCenter?.communities.map((community) => community.name)).toEqual(['卓球クラブ']);
    expect(sportsCenter?.latitude).toBeCloseTo(35.689342, 5);
    expect(sportsCenter?.longitude).toBeCloseTo(139.767685, 5);
  });

  it('excludes rows outside the requested ward even when the venue is known', async () => {
    writeCommunitiesCsv([
      row({ community_id: 'community_5', ward_name: '新宿区', name: '新宿の会', description: '謎', venue_name: '九段' }),
    ]);

    const result = await loadCommunityDirectory('千代田区');

    expect(result.counts).toEqual({ totalInWard: 0, withKnownVenue: 0, withoutKnownVenue: 0 });
    expect(result.facilities).toEqual([]);
  });
});
