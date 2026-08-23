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
 * names two real public facilities, so those are geocoded once (via the
 * Geospatial Information Authority of Japan address-search API) and stored
 * in `data/tokyo-community/chiyoda-facility-directory.json`, which this
 * loader and the Python-side `osekkai_community_directory.py` both read, so
 * the coordinates never drift out of sync between the two languages. This is
 * intentionally coarser than a per-community address and is labelled as such
 * in the API response.
 */
type FacilityDefinition = {
  key: string;
  match: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  sourceUrl: string;
};

function resolveFacility(venueName: string, facilities: FacilityDefinition[]): FacilityDefinition | null {
  for (const facility of facilities) {
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

let csvCache: { path: string; mtimeMs: number; text: string } | null = null;

async function readCommunitiesCsv(): Promise<string> {
  const filePath = path.join(resolveDataRoot(), 'communities.csv');
  const stat = await fs.stat(filePath);
  if (csvCache && csvCache.path === filePath && csvCache.mtimeMs === stat.mtimeMs) return csvCache.text;
  const text = await fs.readFile(filePath, 'utf-8');
  csvCache = { path: filePath, mtimeMs: stat.mtimeMs, text };
  return text;
}

let facilityCache: { path: string; mtimeMs: number; facilities: FacilityDefinition[] } | null = null;

async function readFacilityDirectory(): Promise<FacilityDefinition[]> {
  const filePath = path.join(resolveDataRoot(), 'chiyoda-facility-directory.json');
  const stat = await fs.stat(filePath);
  if (facilityCache && facilityCache.path === filePath && facilityCache.mtimeMs === stat.mtimeMs) {
    return facilityCache.facilities;
  }
  const raw = await fs.readFile(filePath, 'utf-8');
  const parsed = JSON.parse(raw) as { facilities?: unknown };
  if (!Array.isArray(parsed.facilities)) {
    throw new Error('chiyoda-facility-directory.json is missing a facilities array');
  }
  const facilities = parsed.facilities.map((value, index) => {
    if (
      typeof value !== 'object' ||
      value === null ||
      typeof (value as Record<string, unknown>).key !== 'string' ||
      typeof (value as Record<string, unknown>).match !== 'string' ||
      typeof (value as Record<string, unknown>).name !== 'string' ||
      typeof (value as Record<string, unknown>).address !== 'string' ||
      typeof (value as Record<string, unknown>).latitude !== 'number' ||
      typeof (value as Record<string, unknown>).longitude !== 'number' ||
      typeof (value as Record<string, unknown>).sourceUrl !== 'string'
    ) {
      throw new Error(`chiyoda-facility-directory.json facilities[${index}] is malformed`);
    }
    return value as FacilityDefinition;
  });
  facilityCache = { path: filePath, mtimeMs: stat.mtimeMs, facilities };
  return facilities;
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
  const [raw, facilityDefinitions] = await Promise.all([readCommunitiesCsv(), readFacilityDirectory()]);
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
    const facility = resolveFacility(venueNameRaw, facilityDefinitions);
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
