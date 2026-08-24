import { promises as fs } from 'fs';
import path from 'path';

import type {
  CommunityDirectoryEntry,
  CommunityDirectoryResult,
  CommunityFacilityDetail,
  CommunityFacilitySummary,
  CommunityLocationKind,
} from './community-directory-types';

/**
 * Each community is placed on the map by trying, in order:
 *   1. the row's own geocoded latitude/longitude, carried directly by
 *      adult_official_opportunities.csv when the source pipeline resolved one;
 *   2. a legacy verified venue address kept in venue-address-directory.json;
 *   3. a known venue-name anchor such as 九段生涯学習館;
 *   4. otherwise the ward office.
 * Coordinates are geocoded once via the Geospatial Information Authority of
 * Japan address-search API and carried in the CSV. Shared venue anchors and
 * ward-office fallbacks remain in `ward-geocoding-directory.json`; the legacy
 * address dictionary remains a compatibility fallback. TypeScript and Python
 * read the same files, so their coordinates and precision labels cannot
 * drift apart.
 */
type FacilityDefinition = {
  key: string;
  match?: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  sourceUrl: string;
  locationKind?: CommunityLocationKind;
  locationPrecision?: string | null;
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
    locationKind: 'exact_address',
    locationPrecision: 'exact_address',
  };
}

function ownLocationFacility(
  venueAddress: string,
  venueName: string,
  ward: string,
  latitude: number,
  longitude: number,
  matchStatus: string,
  sourceUrl: string,
): FacilityDefinition {
  // A row can list multiple venue addresses separated by " | "; only the
  // first is used for the facility label (it also matches the coordinate).
  const firstAddress = venueAddress.split('|')[0]?.trim() ?? '';
  const label = firstAddress ? firstAddress.replace(/^東京都/, '') : venueName || `${ward}内の確認済み場所`;
  return {
    key: `latlng:${latitude.toFixed(6)},${longitude.toFixed(6)}`,
    name: label,
    address: firstAddress || label,
    latitude,
    longitude,
    sourceUrl,
    locationKind: 'exact_address',
    locationPrecision: matchStatus || null,
  };
}

function resolveFacility(
  ward: string,
  venueName: string,
  venueAddress: string,
  latitude: number | null,
  longitude: number | null,
  matchStatus: string,
  sourceUrl: string,
  wards: Map<string, WardDefinition>,
  addresses: Map<string, VenueAddressEntry>,
): FacilityDefinition | null {
  if (latitude !== null && longitude !== null) {
    return ownLocationFacility(venueAddress, venueName, ward, latitude, longitude, matchStatus, sourceUrl);
  }
  if (venueAddress) {
    const known = addresses.get(venueAddress);
    if (known && known.ward === ward) return addressFacility(venueAddress, known);
  }
  const definition = wards.get(ward);
  if (!definition) return null;
  for (const anchor of definition.anchors) {
    if (anchor.match && venueName.includes(anchor.match)) {
      return { ...anchor, locationKind: 'known_facility', locationPrecision: 'known_facility' };
    }
  }
  return { ...definition.wardOffice, locationKind: 'ward_office', locationPrecision: 'ward_office' };
}

function optionalNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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

const OPPORTUNITIES_CSV_FILE = 'adult_official_opportunities.csv';

let csvCache: { path: string; mtimeMs: number; text: string } | null = null;

async function readOpportunitiesCsv(): Promise<string> {
  const filePath = path.join(resolveDataRoot(), OPPORTUNITIES_CSV_FILE);
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
  'opportunity_id',
  'ward_name',
  'title',
  'genres',
  'description',
  'venue_name',
  'venue_address',
  'latitude',
  'longitude',
  'venue_address_match_status',
  'venue_address_source_url',
  'official_url',
  'source_updated_at',
  'fetched_at',
] as const;

// The CSV's own `genres` column is a `|`-separated set of structured tags
// (sports, music_culture, learning, social_contribution, community_exchange)
// assigned upstream, so the map's category buttons filter on it directly
// instead of guessing from free text. "social" is a UI-level grouping of the
// two civic-participation tags, which are usually reported together anyway.
export type CommunityGenreFilter = 'sports' | 'music_culture' | 'learning' | 'social';

function matchesGenreFilter(genres: string, filter: CommunityGenreFilter): boolean {
  const tokens = new Set(genres.split('|').map((token) => token.trim()));
  if (filter === 'social') return tokens.has('social_contribution') || tokens.has('community_exchange');
  return tokens.has(filter);
}

const DATA_SOURCE_NOTE =
  '区の公式名簿・案内をもとにした地域コミュニティ一覧（Open Data CSV）を地図へ表示しています。掲載団体自身のジオコーディング済み座標、確認済み施設、区役所の順に位置を解決します。個々の開催日時・現在の活動有無は確認していません。';

async function readRows(): Promise<{ header: string[]; columnAt: (column: (typeof REQUIRED_COLUMNS)[number]) => number; rows: string[][] }> {
  const raw = await readOpportunitiesCsv();
  const rows = parseCsv(raw.replace(/^﻿/, ''));
  if (rows.length === 0) throw new Error(`${OPPORTUNITIES_CSV_FILE} is empty`);
  const header = rows[0].map((value) => value.trim());
  const columnIndex = new Map<string, number>();
  for (const column of REQUIRED_COLUMNS) {
    const at = header.indexOf(column);
    if (at === -1) throw new Error(`${OPPORTUNITIES_CSV_FILE} is missing expected column: ${column}`);
    columnIndex.set(column, at);
  }
  return { header, columnAt: (column) => columnIndex.get(column) as number, rows: rows.slice(1) };
}

export async function loadCommunityDirectorySummary(
  options?: { genre?: CommunityGenreFilter },
): Promise<CommunityDirectoryResult> {
  const genre = options?.genre;
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
  const withAreaLocation = 0;
  let withWardOfficeFallback = 0;

  for (const row of rows) {
    if (row.length < header.length) continue;
    const ward = (row[at('ward_name')] ?? '').trim();
    const id = (row[at('opportunity_id')] ?? '').trim();
    const name = (row[at('title')] ?? '').trim();
    if (!ward || !id || !name) continue;
    const genres = row[at('genres')] ?? '';
    if (genre && !matchesGenreFilter(genres, genre)) continue;
    const venueName = (row[at('venue_name')] ?? '').trim();
    const venueAddress = (row[at('venue_address')] ?? '').trim();
    const latitude = optionalNumber(row[at('latitude')] ?? '');
    const longitude = optionalNumber(row[at('longitude')] ?? '');
    const matchStatus = (row[at('venue_address_match_status')] ?? '').trim();
    const sourceUrl = (row[at('venue_address_source_url')] ?? '').trim();
    const facility = resolveFacility(ward, venueName, venueAddress, latitude, longitude, matchStatus, sourceUrl, wards, addresses);
    if (!facility) continue;
    total += 1;
    if (facility.locationKind === 'exact_address' || facility.locationKind === 'multiple_addresses') withVenueAddress += 1;
    else if (facility.locationKind === 'known_facility') withKnownFacility += 1;
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
      locationKind: facility.locationKind ?? 'ward_office',
      locationPrecision: facility.locationPrecision ?? null,
      count,
    }))
    .sort((left, right) => right.count - left.count);

  return {
    generatedAt: new Date().toISOString(),
    dataSource: {
      file: `data/tokyo-community/${OPPORTUNITIES_CSV_FILE}`,
      classification: 'raw_open_data_unverified',
      note: DATA_SOURCE_NOTE,
    },
    counts: { total, withVenueAddress, withKnownFacility, withAreaLocation, withWardOfficeFallback },
    facilities,
  };
}

export async function loadCommunityFacilityDetail(
  facilityKey: string,
  options?: { genre?: CommunityGenreFilter },
): Promise<CommunityFacilityDetail | null> {
  const genre = options?.genre;
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
    const id = (row[at('opportunity_id')] ?? '').trim();
    const name = (row[at('title')] ?? '').trim();
    if (!ward || !id || !name) continue;
    const genres = row[at('genres')] ?? '';
    if (genre && !matchesGenreFilter(genres, genre)) continue;
    const description = row[at('description')] ?? '';
    const venueName = (row[at('venue_name')] ?? '').trim();
    const venueAddress = (row[at('venue_address')] ?? '').trim();
    const latitude = optionalNumber(row[at('latitude')] ?? '');
    const longitude = optionalNumber(row[at('longitude')] ?? '');
    const matchStatus = (row[at('venue_address_match_status')] ?? '').trim();
    const sourceUrl = (row[at('venue_address_source_url')] ?? '').trim();
    const facility = resolveFacility(ward, venueName, venueAddress, latitude, longitude, matchStatus, sourceUrl, wards, addresses);
    if (!facility || facility.key !== facilityKey) continue;
    matchedFacility = facility;
    matchedWard = ward;
    communities.push({
      id,
      name,
      nameKana: null,
      category: description.trim() || null,
      venueName: facility.name,
      venueAddress: venueAddress || facility.address,
      latitude: facility.latitude,
      longitude: facility.longitude,
      locationKind: facility.locationKind ?? 'ward_office',
      locationPrecision: facility.locationPrecision ?? null,
      targetAudience: null,
      officialUrl: (row[at('official_url')] ?? '').trim() || null,
      onlineParticipation: null,
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
    locationKind: matchedFacility.locationKind ?? 'ward_office',
    locationPrecision: matchedFacility.locationPrecision ?? null,
    count: communities.length,
    communities,
  };
}
