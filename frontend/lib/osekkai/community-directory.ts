import { promises as fs } from 'fs';
import path from 'path';

import type {
  CommunityDirectoryEntry,
  CommunityDirectoryResult,
  CommunityFacilityDetail,
  CommunityFacilitySummary,
} from './community-directory-types';

/**
 * `data/tokyo-community/communities.csv` carries almost no usable address or
 * coordinate data (venue_address is populated for only ~1.3% of rows, mostly
 * in 渋谷区). Each community is placed on the map by trying, in order:
 *   1. its own `venue_address`, if that exact string was geocoded into
 *      `data/tokyo-community/venue-address-directory.json` (real, per-row
 *      precision — the closest this data gets to an actual building);
 *   2. for 千代田区, a `venue_name` match against one of two real facilities;
 *   3. otherwise the ward office, so every community still lands somewhere
 *      real rather than being dropped.
 * All of these are geocoded once via the Geospatial Information Authority of
 * Japan address-search API and stored in
 * `data/tokyo-community/{ward-geocoding-directory,venue-address-directory}.json`,
 * which this loader and the Python-side `osekkai_community_directory.py`
 * both read, so coordinates never drift apart between the two languages.
 */
type FacilityDefinition = {
  key: string;
  match?: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  sourceUrl: string;
};

type WardDefinition = {
  wardOffice: FacilityDefinition;
  anchors: FacilityDefinition[];
};

type VenueAddressEntry = { ward: string; latitude: number; longitude: number };

function addressFacility(address: string, entry: VenueAddressEntry): FacilityDefinition {
  return {
    key: `addr:${address}`,
    name: address.replace(/^東京都/, ''),
    address,
    latitude: entry.latitude,
    longitude: entry.longitude,
    sourceUrl: '',
  };
}

function resolveFacility(
  ward: string,
  venueName: string,
  venueAddress: string,
  wards: Map<string, WardDefinition>,
  addresses: Map<string, VenueAddressEntry>,
): FacilityDefinition | null {
  if (venueAddress) {
    const known = addresses.get(venueAddress);
    if (known && known.ward === ward) return addressFacility(venueAddress, known);
  }
  const definition = wards.get(ward);
  if (!definition) return null;
  for (const anchor of definition.anchors) {
    if (anchor.match && venueName.includes(anchor.match)) return anchor;
  }
  return definition.wardOffice;
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

function asFacilityDefinition(value: unknown, context: string): FacilityDefinition {
  if (typeof value !== 'object' || value === null) throw new Error(`${context} is malformed`);
  const record = value as Record<string, unknown>;
  if (
    typeof record.key !== 'string' ||
    typeof record.name !== 'string' ||
    typeof record.address !== 'string' ||
    typeof record.latitude !== 'number' ||
    typeof record.longitude !== 'number' ||
    typeof record.sourceUrl !== 'string' ||
    (record.match !== undefined && typeof record.match !== 'string')
  ) {
    throw new Error(`${context} is malformed`);
  }
  return record as FacilityDefinition;
}

let wardCache: { path: string; mtimeMs: number; wards: Map<string, WardDefinition> } | null = null;

async function readWardGeocodingDirectory(): Promise<Map<string, WardDefinition>> {
  const filePath = path.join(resolveDataRoot(), 'ward-geocoding-directory.json');
  const stat = await fs.stat(filePath);
  if (wardCache && wardCache.path === filePath && wardCache.mtimeMs === stat.mtimeMs) return wardCache.wards;
  const raw = await fs.readFile(filePath, 'utf-8');
  const parsed = JSON.parse(raw) as { wards?: unknown };
  if (typeof parsed.wards !== 'object' || parsed.wards === null) {
    throw new Error('ward-geocoding-directory.json is missing a wards object');
  }
  const wards = new Map<string, WardDefinition>();
  for (const [wardName, value] of Object.entries(parsed.wards as Record<string, unknown>)) {
    if (typeof value !== 'object' || value === null) throw new Error(`ward-geocoding-directory.json wards.${wardName} is malformed`);
    const record = value as Record<string, unknown>;
    const wardOffice = asFacilityDefinition(record.wardOffice, `ward-geocoding-directory.json wards.${wardName}.wardOffice`);
    if (!Array.isArray(record.anchors)) throw new Error(`ward-geocoding-directory.json wards.${wardName}.anchors must be an array`);
    const anchors = record.anchors.map((anchor, index) =>
      asFacilityDefinition(anchor, `ward-geocoding-directory.json wards.${wardName}.anchors[${index}]`),
    );
    wards.set(wardName, { wardOffice, anchors });
  }
  wardCache = { path: filePath, mtimeMs: stat.mtimeMs, wards };
  return wards;
}

let addressCache: { path: string; mtimeMs: number; addresses: Map<string, VenueAddressEntry> } | null = null;

async function readVenueAddressDirectory(): Promise<Map<string, VenueAddressEntry>> {
  const filePath = path.join(resolveDataRoot(), 'venue-address-directory.json');
  const stat = await fs.stat(filePath);
  if (addressCache && addressCache.path === filePath && addressCache.mtimeMs === stat.mtimeMs) return addressCache.addresses;
  const raw = await fs.readFile(filePath, 'utf-8');
  const parsed = JSON.parse(raw) as { addresses?: unknown };
  if (typeof parsed.addresses !== 'object' || parsed.addresses === null) {
    throw new Error('venue-address-directory.json is missing an addresses object');
  }
  const addresses = new Map<string, VenueAddressEntry>();
  for (const [address, value] of Object.entries(parsed.addresses as Record<string, unknown>)) {
    if (typeof value !== 'object' || value === null) throw new Error(`venue-address-directory.json addresses.${address} is malformed`);
    const record = value as Record<string, unknown>;
    if (typeof record.ward !== 'string' || typeof record.latitude !== 'number' || typeof record.longitude !== 'number') {
      throw new Error(`venue-address-directory.json addresses.${address} is malformed`);
    }
    addresses.set(address, { ward: record.ward, latitude: record.latitude, longitude: record.longitude });
  }
  addressCache = { path: filePath, mtimeMs: stat.mtimeMs, addresses };
  return addresses;
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

const DATA_SOURCE_NOTE =
  '区が公開する地域コミュニティ一覧（Open Data CSV）を地図へ表示しています。活動場所の住所が記載されている行はその住所（主に渋谷区）、千代田区は施設名から特定できた拠点（九段生涯学習館・千代田区立スポーツセンター）、それ以外は区役所単位の目安地点です。個々の開催日時・現在の活動有無は確認していません。';

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

export async function loadCommunityDirectorySummary(): Promise<CommunityDirectoryResult> {
  const [{ header, columnAt, rows }, wards, addresses] = await Promise.all([
    readRows(),
    readWardGeocodingDirectory(),
    readVenueAddressDirectory(),
  ]);
  const at = columnAt;

  const counts = new Map<string, { facility: FacilityDefinition; ward: string; count: number }>();
  let total = 0;
  let withVenueAddress = 0;
  let withKnownFacility = 0;
  let withWardOfficeFallback = 0;

  for (const row of rows) {
    if (row.length < header.length) continue;
    const ward = (row[at('ward_name')] ?? '').trim();
    const id = (row[at('community_id')] ?? '').trim();
    const name = (row[at('name')] ?? '').trim();
    if (!ward || !id || !name) continue;
    const venueName = (row[at('venue_name')] ?? '').trim();
    const venueAddress = (row[at('venue_address')] ?? '').trim();
    const facility = resolveFacility(ward, venueName, venueAddress, wards, addresses);
    if (!facility) continue;
    total += 1;
    if (facility.key.startsWith('addr:')) withVenueAddress += 1;
    else if (facility.match) withKnownFacility += 1;
    else withWardOfficeFallback += 1;
    const entry = counts.get(facility.key);
    if (entry) entry.count += 1;
    else counts.set(facility.key, { facility, ward, count: 1 });
  }

  const facilities: CommunityFacilitySummary[] = Array.from(counts.values())
    .map(({ facility, ward, count }) => ({
      key: facility.key,
      ward,
      name: facility.name,
      address: facility.address,
      latitude: facility.latitude,
      longitude: facility.longitude,
      sourceUrl: facility.sourceUrl,
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
    counts: { total, withVenueAddress, withKnownFacility, withWardOfficeFallback },
    facilities,
  };
}

export async function loadCommunityFacilityDetail(facilityKey: string): Promise<CommunityFacilityDetail | null> {
  const [{ header, columnAt, rows }, wards, addresses] = await Promise.all([
    readRows(),
    readWardGeocodingDirectory(),
    readVenueAddressDirectory(),
  ]);
  const at = columnAt;

  let matchedFacility: FacilityDefinition | null = null;
  let matchedWard: string | null = null;
  const communities: CommunityDirectoryEntry[] = [];

  for (const row of rows) {
    if (row.length < header.length) continue;
    const ward = (row[at('ward_name')] ?? '').trim();
    const id = (row[at('community_id')] ?? '').trim();
    const name = (row[at('name')] ?? '').trim();
    if (!ward || !id || !name) continue;
    const venueName = (row[at('venue_name')] ?? '').trim();
    const venueAddress = (row[at('venue_address')] ?? '').trim();
    const facility = resolveFacility(ward, venueName, venueAddress, wards, addresses);
    if (!facility || facility.key !== facilityKey) continue;
    matchedFacility = facility;
    matchedWard = ward;
    communities.push({
      id,
      name,
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
    });
  }

  if (!matchedFacility || !matchedWard) return null;
  communities.sort((left, right) => left.name.localeCompare(right.name, 'ja'));

  return {
    key: matchedFacility.key,
    ward: matchedWard,
    name: matchedFacility.name,
    address: matchedFacility.address,
    latitude: matchedFacility.latitude,
    longitude: matchedFacility.longitude,
    sourceUrl: matchedFacility.sourceUrl,
    count: communities.length,
    communities,
  };
}
