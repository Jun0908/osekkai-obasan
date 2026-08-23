import { promises as fs } from 'fs';
import path from 'path';

import type {
  CommunityDirectoryEntry,
  CommunityDirectoryResult,
  CommunityFacilityDetail,
  CommunityFacilitySummary,
} from './community-directory-types';

/**
 * `data/tokyo-community/communities.csv` now carries its own geocoding
 * (`latitude`/`longitude`, plus `map_location_id` grouping communities that
 * resolved to the same real place) for about two thirds of rows, produced by
 * the upstream https://github.com/Jun0908/tokyo_community_data pipeline. For
 * every other row (still no usable address at all), this loader falls back
 * to the community's ward office, geocoded once via the Geospatial
 * Information Authority of Japan address-search API and stored in
 * `data/tokyo-community/ward-geocoding-directory.json`, which this loader
 * and the Python-side `osekkai_community_directory.py` both read, so
 * coordinates never drift apart between the two languages.
 */
type WardOffice = {
  key: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  sourceUrl: string;
};

type ResolvedPoint = {
  key: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  sourceUrl: string;
  precise: boolean;
};

function asWardOffice(value: unknown, context: string): WardOffice {
  if (typeof value !== 'object' || value === null) throw new Error(`${context} is malformed`);
  const record = value as Record<string, unknown>;
  if (
    typeof record.key !== 'string' ||
    typeof record.name !== 'string' ||
    typeof record.address !== 'string' ||
    typeof record.latitude !== 'number' ||
    typeof record.longitude !== 'number' ||
    typeof record.sourceUrl !== 'string'
  ) {
    throw new Error(`${context} is malformed`);
  }
  return record as WardOffice;
}

function parseCoordinate(value: string): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function resolvePoint(
  ward: string,
  csvRow: { latitude: string; longitude: string; mapLocationId: string; venueName: string; venueAddress: string; geocodedAddress: string; venueAddressSourceUrl: string; officialUrl: string },
  wardOffices: Map<string, WardOffice>,
): ResolvedPoint | null {
  const latitude = parseCoordinate(csvRow.latitude);
  const longitude = parseCoordinate(csvRow.longitude);
  if (latitude !== null && longitude !== null) {
    const locationId = csvRow.mapLocationId || `latlng:${latitude.toFixed(5)},${longitude.toFixed(5)}`;
    const rawName = csvRow.venueName.split(';')[0]?.trim();
    const address = csvRow.geocodedAddress || csvRow.venueAddress.split('|')[0]?.trim() || '';
    const name = rawName || address.replace(/^東京都/, '') || `${ward}の活動場所`;
    return {
      key: `loc:${locationId}`,
      name,
      address,
      latitude,
      longitude,
      sourceUrl: csvRow.venueAddressSourceUrl || csvRow.officialUrl || '',
      precise: true,
    };
  }
  const office = wardOffices.get(ward);
  if (!office) return null;
  return { ...office, precise: false };
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

let wardOfficeCache: { path: string; mtimeMs: number; offices: Map<string, WardOffice> } | null = null;

async function readWardOffices(): Promise<Map<string, WardOffice>> {
  const filePath = path.join(resolveDataRoot(), 'ward-geocoding-directory.json');
  const stat = await fs.stat(filePath);
  if (wardOfficeCache && wardOfficeCache.path === filePath && wardOfficeCache.mtimeMs === stat.mtimeMs) return wardOfficeCache.offices;
  const raw = await fs.readFile(filePath, 'utf-8');
  const parsed = JSON.parse(raw) as { wards?: unknown };
  if (typeof parsed.wards !== 'object' || parsed.wards === null) {
    throw new Error('ward-geocoding-directory.json is missing a wards object');
  }
  const offices = new Map<string, WardOffice>();
  for (const [wardName, value] of Object.entries(parsed.wards as Record<string, unknown>)) {
    if (typeof value !== 'object' || value === null) throw new Error(`ward-geocoding-directory.json wards.${wardName} is malformed`);
    offices.set(wardName, asWardOffice((value as Record<string, unknown>).wardOffice, `ward-geocoding-directory.json wards.${wardName}.wardOffice`));
  }
  wardOfficeCache = { path: filePath, mtimeMs: stat.mtimeMs, offices };
  return offices;
}

const REQUIRED_COLUMNS = [
  'community_id',
  'ward_name',
  'name',
  'name_kana',
  'description',
  'venue_name',
  'venue_address',
  'venue_address_source_url',
  'map_location_id',
  'latitude',
  'longitude',
  'geocoded_address',
  'target_audience',
  'official_url',
  'online_participation',
  'source_updated_at',
  'fetched_at',
] as const;

const DATA_SOURCE_NOTE =
  '区が公開する地域コミュニティ一覧（Open Data CSV）を地図へ表示しています。ジオコーディング済みの活動場所（緯度経度）があればその場所、無い行は区役所単位の目安地点です。個々の開催日時・現在の活動有無は確認していません。';

async function readRows(): Promise<{ header: string[]; columnAt: (column: (typeof REQUIRED_COLUMNS)[number]) => number; rows: string[][] }> {
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
  return { header, columnAt: (column) => columnIndex.get(column) as number, rows: rows.slice(1) };
}

function resolveRowPoint(
  row: string[],
  at: (column: (typeof REQUIRED_COLUMNS)[number]) => number,
  ward: string,
  wardOffices: Map<string, WardOffice>,
): ResolvedPoint | null {
  return resolvePoint(
    ward,
    {
      latitude: (row[at('latitude')] ?? '').trim(),
      longitude: (row[at('longitude')] ?? '').trim(),
      mapLocationId: (row[at('map_location_id')] ?? '').trim(),
      venueName: (row[at('venue_name')] ?? '').trim(),
      venueAddress: (row[at('venue_address')] ?? '').trim(),
      geocodedAddress: (row[at('geocoded_address')] ?? '').trim(),
      venueAddressSourceUrl: (row[at('venue_address_source_url')] ?? '').trim(),
      officialUrl: (row[at('official_url')] ?? '').trim(),
    },
    wardOffices,
  );
}

export async function loadCommunityDirectorySummary(): Promise<CommunityDirectoryResult> {
  const [{ header, columnAt, rows }, wardOffices] = await Promise.all([readRows(), readWardOffices()]);
  const at = columnAt;

  const counts = new Map<string, { point: ResolvedPoint; ward: string; count: number }>();
  let total = 0;
  let withPreciseLocation = 0;
  let withWardOfficeFallback = 0;

  for (const row of rows) {
    if (row.length < header.length) continue;
    const ward = (row[at('ward_name')] ?? '').trim();
    const id = (row[at('community_id')] ?? '').trim();
    const name = (row[at('name')] ?? '').trim();
    if (!ward || !id || !name) continue;
    const point = resolveRowPoint(row, at, ward, wardOffices);
    if (!point) continue;
    total += 1;
    if (point.precise) withPreciseLocation += 1;
    else withWardOfficeFallback += 1;
    const entry = counts.get(point.key);
    if (entry) entry.count += 1;
    else counts.set(point.key, { point, ward, count: 1 });
  }

  const facilities: CommunityFacilitySummary[] = Array.from(counts.values())
    .map(({ point, ward, count }) => ({
      key: point.key,
      ward,
      name: point.name,
      address: point.address,
      latitude: point.latitude,
      longitude: point.longitude,
      sourceUrl: point.sourceUrl,
      precise: point.precise,
      count,
    }))
    .sort((left, right) => right.count - left.count);

  return {
    generatedAt: new Date().toISOString(),
    dataSource: {
      file: 'data/tokyo-community/communities.csv',
      classification: 'raw_open_data_unverified',
      note: DATA_SOURCE_NOTE,
    },
    counts: { total, withPreciseLocation, withWardOfficeFallback },
    facilities,
  };
}

export async function loadCommunityFacilityDetail(facilityKey: string): Promise<CommunityFacilityDetail | null> {
  const [{ header, columnAt, rows }, wardOffices] = await Promise.all([readRows(), readWardOffices()]);
  const at = columnAt;

  let matchedPoint: ResolvedPoint | null = null;
  let matchedWard: string | null = null;
  const communities: CommunityDirectoryEntry[] = [];

  for (const row of rows) {
    if (row.length < header.length) continue;
    const ward = (row[at('ward_name')] ?? '').trim();
    const id = (row[at('community_id')] ?? '').trim();
    const name = (row[at('name')] ?? '').trim();
    if (!ward || !id || !name) continue;
    const point = resolveRowPoint(row, at, ward, wardOffices);
    if (!point || point.key !== facilityKey) continue;
    matchedPoint = point;
    matchedWard = ward;
    communities.push({
      id,
      name,
      nameKana: (row[at('name_kana')] ?? '').trim() || null,
      category: (row[at('description')] ?? '').trim() || null,
      venueName: (row[at('venue_name')] ?? '').trim() || point.name,
      venueAddress: (row[at('venue_address')] ?? '').trim() || point.address,
      latitude: point.latitude,
      longitude: point.longitude,
      targetAudience: (row[at('target_audience')] ?? '').trim() || null,
      officialUrl: (row[at('official_url')] ?? '').trim() || null,
      onlineParticipation: (row[at('online_participation')] ?? '').trim() || null,
      sourceUpdatedAt: (row[at('source_updated_at')] ?? '').trim() || null,
      fetchedAt: (row[at('fetched_at')] ?? '').trim() || null,
    });
  }

  if (!matchedPoint || !matchedWard) return null;
  communities.sort((left, right) => left.name.localeCompare(right.name, 'ja'));

  return {
    key: matchedPoint.key,
    ward: matchedWard,
    name: matchedPoint.name,
    address: matchedPoint.address,
    latitude: matchedPoint.latitude,
    longitude: matchedPoint.longitude,
    sourceUrl: matchedPoint.sourceUrl,
    precise: matchedPoint.precise,
    count: communities.length,
    communities,
  };
}
