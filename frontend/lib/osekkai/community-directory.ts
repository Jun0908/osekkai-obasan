import { promises as fs } from 'fs';
import path from 'path';

import type {
  CommunityDirectoryEntry,
  CommunityDirectoryResult,
  CommunityFacility,
} from './community-directory-types';

/**
 * `data/tokyo-community/communities.csv` carries almost no usable address or
 * coordinate data (venue_address is populated for a tiny minority of rows).
 * Within the Chiyoda scope the map already targets, `venue_name` only ever
 * names two real public facilities, so those are geocoded once via the
 * Geospatial Information Authority of Japan (GSI) address-search API and
 * reused as an approximate, facility-level pin for every community that
 * lists that venue. This is intentionally coarser than a per-community
 * address and is labelled as such in the API response.
 */
const KNOWN_FACILITIES = [
  {
    key: 'kudan',
    match: '九段',
    name: '九段生涯学習館',
    address: '東京都千代田区九段南1-5-10',
    latitude: 35.695339,
    longitude: 139.751984,
    sourceUrl: 'https://www.city.chiyoda.lg.jp/shisetsu/bunka/kudan-gakushu.html',
  },
  {
    key: 'sports-center',
    match: 'スポーツセンター',
    name: '千代田区立スポーツセンター',
    address: '東京都千代田区内神田2-1-8',
    latitude: 35.689342,
    longitude: 139.767685,
    sourceUrl: 'https://www.city.chiyoda.lg.jp/shisetsu/bunka/sportscenter.html',
  },
] as const;

function resolveFacility(venueName: string): (typeof KNOWN_FACILITIES)[number] | null {
  for (const facility of KNOWN_FACILITIES) {
    if (venueName.includes(facility.match)) return facility;
  }
  return null;
}

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;
  let index = 0;
  const length = text.length;
  while (index < length) {
    const char = text[index];
    if (inQuotes) {
      if (char === '"') {
        if (text[index + 1] === '"') {
          field += '"';
          index += 2;
          continue;
        }
        inQuotes = false;
        index += 1;
        continue;
      }
      field += char;
      index += 1;
      continue;
    }
    if (char === '"') {
      inQuotes = true;
      index += 1;
      continue;
    }
    if (char === ',') {
      row.push(field);
      field = '';
      index += 1;
      continue;
    }
    if (char === '\r') {
      index += 1;
      continue;
    }
    if (char === '\n') {
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
      index += 1;
      continue;
    }
    field += char;
    index += 1;
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

function resolveDataRoot(): string {
  const configured = process.env.OSEKKAI_COMMUNITY_DATA_ROOT;
  if (configured && configured.trim()) return configured.trim();
  return path.resolve(process.cwd(), '..', 'data', 'tokyo-community');
}

let cache: { path: string; mtimeMs: number; text: string } | null = null;

async function readCommunitiesCsv(): Promise<string> {
  const filePath = path.join(resolveDataRoot(), 'communities.csv');
  const stat = await fs.stat(filePath);
  if (cache && cache.path === filePath && cache.mtimeMs === stat.mtimeMs) return cache.text;
  const text = await fs.readFile(filePath, 'utf-8');
  cache = { path: filePath, mtimeMs: stat.mtimeMs, text };
  return text;
}

const REQUIRED_COLUMNS = [
  'community_id',
  'ward_name',
  'name',
  'name_kana',
  'description',
  'venue_name',
  'venue_address',
  'target_audience',
  'official_url',
  'online_participation',
  'source_updated_at',
  'fetched_at',
] as const;

export async function loadCommunityDirectory(ward = '千代田区'): Promise<CommunityDirectoryResult> {
  const raw = await readCommunitiesCsv();
  const rows = parseCsv(raw.replace(/^﻿/, ''));
  if (rows.length === 0) throw new Error('communities.csv is empty');

  const header = rows[0].map((value) => value.trim());
  const columnIndex = new Map<string, number>();
  for (const column of REQUIRED_COLUMNS) {
    const at = header.indexOf(column);
    if (at === -1) throw new Error(`communities.csv is missing expected column: ${column}`);
    columnIndex.set(column, at);
  }
  const at = (column: (typeof REQUIRED_COLUMNS)[number]) => columnIndex.get(column) as number;

  const facilitiesByKey = new Map<string, CommunityFacility>();
  let totalInWard = 0;
  let withKnownVenue = 0;
  let withoutKnownVenue = 0;

  for (const row of rows.slice(1)) {
    if (row.length < header.length) continue;
    if ((row[at('ward_name')] ?? '').trim() !== ward) continue;
    totalInWard += 1;

    const venueNameRaw = (row[at('venue_name')] ?? '').trim();
    const facility = resolveFacility(venueNameRaw);
    if (!facility) {
      withoutKnownVenue += 1;
      continue;
    }
    withKnownVenue += 1;

    const entry: CommunityDirectoryEntry = {
      id: (row[at('community_id')] ?? '').trim(),
      name: (row[at('name')] ?? '').trim(),
      nameKana: (row[at('name_kana')] ?? '').trim() || null,
      category: (row[at('description')] ?? '').trim() || null,
      venueName: facility.name,
      venueAddress: (row[at('venue_address')] ?? '').trim() || facility.address,
      latitude: facility.latitude,
      longitude: facility.longitude,
      targetAudience: (row[at('target_audience')] ?? '').trim() || null,
      officialUrl: (row[at('official_url')] ?? '').trim() || null,
      onlineParticipation: (row[at('online_participation')] ?? '').trim() || null,
      sourceUpdatedAt: (row[at('source_updated_at')] ?? '').trim() || null,
      fetchedAt: (row[at('fetched_at')] ?? '').trim() || null,
    };
    if (!entry.id || !entry.name) continue;

    let bucket = facilitiesByKey.get(facility.key);
    if (!bucket) {
      bucket = {
        key: facility.key,
        name: facility.name,
        address: facility.address,
        latitude: facility.latitude,
        longitude: facility.longitude,
        sourceUrl: facility.sourceUrl,
        communities: [],
      };
      facilitiesByKey.set(facility.key, bucket);
    }
    bucket.communities.push(entry);
  }

  const facilities = Array.from(facilitiesByKey.values())
    .map((facility) => ({
      ...facility,
      communities: [...facility.communities].sort((left, right) => left.name.localeCompare(right.name, 'ja')),
    }))
    .sort((left, right) => right.communities.length - left.communities.length);

  return {
    generatedAt: new Date().toISOString(),
    ward,
    dataSource: {
      file: 'data/tokyo-community/communities.csv',
      classification: 'raw_open_data_unverified',
      note:
        '区が公開する地域コミュニティ一覧（Open Data CSV）を、施設名から特定できた拠点（九段生涯学習館・千代田区立スポーツセンター）単位の目安地点として表示しています。個々の開催日時・現在の活動有無は確認していません。',
    },
    counts: { totalInWard, withKnownVenue, withoutKnownVenue },
    facilities,
  };
}
