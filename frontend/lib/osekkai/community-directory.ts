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
 *   1. a verified single venue address, or the representative first point of
 *      an explicitly listed multi-venue record, carried by communities.csv;
 *   2. a known venue-name anchor such as 九段生涯学習館;
 *   3. an activity-area point derived from an official area statement or the
 *      town/chome in an official town-association name;
 *   4. otherwise the ward office.
 * Area points are explicitly approximate and must never be presented as a
 * confirmed meeting venue.
 * Address and area coordinates are geocoded once via the Geospatial
 * Information Authority of Japan address-search API and carried in the CSV.
 * Shared venue anchors and ward-office fallbacks remain in
 * `ward-geocoding-directory.json`; the legacy address dictionary remains a
 * compatibility fallback. TypeScript and Python read the same files, so their
 * coordinates and precision labels cannot drift apart.
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

type CsvMapLocation = {
  id: string;
  areaName: string;
  latitude: number | null;
  longitude: number | null;
  geocodedAddress: string;
  precision: string;
  source: string;
  sourceUrl: string;
};

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

function csvMapFacility(location: CsvMapLocation): FacilityDefinition | null {
  if (!location.id || location.latitude === null || location.longitude === null || !location.geocodedAddress) return null;
  const exact = ['venue_address', 'venue_name_address'].includes(location.source) && location.precision === 'exact_address';
  const multiple = location.source === 'venue_address' && location.precision === 'multiple_addresses_representative';
  return {
    key: location.id,
    name: exact
      ? location.geocodedAddress.replace(/^東京都/, '')
      : multiple
        ? `${location.geocodedAddress.replace(/^東京都/, '')}（複数会場の代表）`
        : `${location.areaName || location.geocodedAddress.replace(/^東京都[^区]+区/, '')}（活動区域の目安）`,
    address: location.geocodedAddress,
    latitude: location.latitude,
    longitude: location.longitude,
    sourceUrl: location.sourceUrl,
    locationKind: exact ? 'exact_address' : multiple ? 'multiple_addresses' : 'activity_area',
    locationPrecision: location.precision || null,
  };
}

function resolveFacility(
  ward: string,
  venueName: string,
  venueAddress: string,
  mapLocation: CsvMapLocation,
  wards: Map<string, WardDefinition>,
  addresses: Map<string, VenueAddressEntry>,
): FacilityDefinition | null {
  const csvFacility = csvMapFacility(mapLocation);
  if (csvFacility?.locationKind === 'exact_address' || csvFacility?.locationKind === 'multiple_addresses') return csvFacility;
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
  if (csvFacility) return csvFacility;
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

// young_adult_opportunities.csv is a ward-official-sourced allowlist of
// community listings already screened for general-adult/young-adult
// participation. 96.8% of its rows match an existing communities.csv row by
// exact (ward_name, name) text, so it is used as the primary signal for the
// "18〜39" map toggle instead of a category/description keyword guess. The
// remaining ~3% are genuinely new listings, but none carry a venue address or
// coordinates, so they cannot be placed on the map and are not surfaced here.
function youngAdultKey(ward: string, name: string): string {
  return `${ward}::${name}`;
}

let youngAdultCache: { path: string; mtimeMs: number; keys: Set<string> } | null = null;

// Returns null (rather than throwing) when the file is absent, so callers can
// fall back to the keyword-only classification instead of failing the whole
// community-directory request.
async function readYoungAdultAllowlist(): Promise<Set<string> | null> {
  const filePath = path.join(resolveDataRoot(), 'young_adult_opportunities.csv');
  let stat;
  try {
    stat = await fs.stat(filePath);
  } catch {
    return null;
  }
  if (youngAdultCache && youngAdultCache.path === filePath && youngAdultCache.mtimeMs === stat.mtimeMs) {
    return youngAdultCache.keys;
  }
  const raw = await fs.readFile(filePath, 'utf-8');
  const rows = parseCsv(raw.replace(/^﻿/, ''));
  const keys = new Set<string>();
  if (rows.length > 0) {
    const header = rows[0].map((value) => value.trim());
    const wardAt = header.indexOf('ward_name');
    const titleAt = header.indexOf('title');
    if (wardAt !== -1 && titleAt !== -1) {
      for (const row of rows.slice(1)) {
        const ward = (row[wardAt] ?? '').trim();
        const title = (row[titleAt] ?? '').trim();
        if (ward && title) keys.add(youngAdultKey(ward, title));
      }
    }
  }
  youngAdultCache = { path: filePath, mtimeMs: stat.mtimeMs, keys };
  return keys;
}

const REQUIRED_COLUMNS = [
  'community_id',
  'ward_name',
  'name',
  'name_kana',
  'category',
  'description',
  'venue_name',
  'venue_address',
  'area_name',
  'map_location_id',
  'latitude',
  'longitude',
  'geocoded_address',
  'location_precision',
  'location_source',
  'location_source_url',
  'target_audience',
  'official_url',
  'online_participation',
  'source_updated_at',
  'fetched_at',
] as const;

// Raw category text spans two CSV columns depending on which ward's source
// listed it: `category` for ward-association style listings (e.g. 町会・自治会),
// `description` for hobby/genre-style listings (e.g. ダンス). The "20〜30代向け"
// map toggle excludes rows whose combined text names a town association,
// neighborhood council, or senior/elderly-only club.
const AGE_UNRELATED_KEYWORDS = ['町会', '自治会', '住区住民会議', 'シニアクラブ', '高齢者クラブ', '老人会', '老人クラブ'];

function isAgeUnrelatedCommunity(category: string, description: string): boolean {
  const text = `${category} ${description}`;
  return AGE_UNRELATED_KEYWORDS.some((keyword) => text.includes(keyword));
}

// A row counts as "18〜39" material only if the curated young-adult allowlist
// includes it AND it does not still carry a town-association/senior keyword
// (a small residual the source data did not fully screen out).
function isYoungAdultRelevant(
  ward: string,
  name: string,
  category: string,
  description: string,
  allowlist: Set<string> | null,
): boolean {
  if (isAgeUnrelatedCommunity(category, description)) return false;
  if (!allowlist) return true;
  return allowlist.has(youngAdultKey(ward, name));
}

// Keywords covering the ball sports, martial arts, dance, and health-exercise
// category/description values actually present in communities.csv (surveyed
// across all ~1,000 distinct raw values). Kept specific (e.g. "健康体操" not
// bare "健康") so it does not also match unrelated entries like 健康・医療.
const SPORTS_KEYWORDS = [
  'バレーボール', 'バドミントン', 'バスケットボール', 'サッカー', 'フットサル', '卓球', '水泳', '野球',
  'テニス', '剣道', 'ソフトボール', '太極拳', 'ダンス', '舞踊', '踊り', 'スポーツ', '空手', '合気道',
  '柔道', '少林寺拳法', 'なぎなた', '弓道', '相撲', '銃剣道', '居合道', 'テコンドー', '体操', 'ヨガ',
  'ヨーガ', '気功', 'ピラティス', '自彊術', 'エアロビクス', '球技', 'ビーチボール', 'ゲートボール',
  'グラウンドゴルフ', 'インディアカ', 'ラグビー', '登山', 'ハイキング', 'ウォーキング', 'スキー',
  '陸上競技', 'トライアスロン', 'ローラースケート', 'アーチェリー', 'レスリング', 'アクアサイズ',
  'ニュースポーツ',
];

function isSportsCommunity(category: string, description: string): boolean {
  const text = `${category} ${description}`;
  return SPORTS_KEYWORDS.some((keyword) => text.includes(keyword));
}

const DATA_SOURCE_NOTE =
  '区が公開する地域コミュニティ一覧（Open Data CSV）を地図へ表示しています。単一会場住所、複数会場の代表地点、確認済み施設、公式区域または地域名・町丁目、区役所の順に位置を解決します。複数会場は一覧の最初の住所、地域名・町丁目は活動区域の目安です。個々の開催日時・現在の活動有無は確認していません。';

function mapLocationFromRow(row: string[], at: (column: (typeof REQUIRED_COLUMNS)[number]) => number): CsvMapLocation {
  return {
    id: (row[at('map_location_id')] ?? '').trim(),
    areaName: (row[at('area_name')] ?? '').trim(),
    latitude: optionalNumber(row[at('latitude')] ?? ''),
    longitude: optionalNumber(row[at('longitude')] ?? ''),
    geocodedAddress: (row[at('geocoded_address')] ?? '').trim(),
    precision: (row[at('location_precision')] ?? '').trim(),
    source: (row[at('location_source')] ?? '').trim(),
    sourceUrl: (row[at('location_source_url')] ?? '').trim(),
  };
}

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

export async function loadCommunityDirectorySummary(
  options?: { excludeAgeUnrelated?: boolean; onlySports?: boolean },
): Promise<CommunityDirectoryResult> {
  const excludeAgeUnrelated = options?.excludeAgeUnrelated ?? false;
  const onlySports = options?.onlySports ?? false;
  const [{ header, columnAt, rows }, wards, addresses, youngAdultAllowlist] = await Promise.all([
    readRows(),
    readWardGeocodingDirectory(),
    readVenueAddressDirectory(),
    excludeAgeUnrelated ? readYoungAdultAllowlist() : Promise.resolve(null),
  ]);
  const at = columnAt;

  const counts = new Map<string, { facility: FacilityDefinition; ward: string; count: number }>();
  let total = 0;
  let withVenueAddress = 0;
  let withKnownFacility = 0;
  let withAreaLocation = 0;
  let withWardOfficeFallback = 0;

  for (const row of rows) {
    if (row.length < header.length) continue;
    const ward = (row[at('ward_name')] ?? '').trim();
    const id = (row[at('community_id')] ?? '').trim();
    const name = (row[at('name')] ?? '').trim();
    if (!ward || !id || !name) continue;
    if (
      excludeAgeUnrelated &&
      !isYoungAdultRelevant(ward, name, row[at('category')] ?? '', row[at('description')] ?? '', youngAdultAllowlist)
    ) continue;
    if (onlySports && !isSportsCommunity(row[at('category')] ?? '', row[at('description')] ?? '')) continue;
    const venueName = (row[at('venue_name')] ?? '').trim();
    const venueAddress = (row[at('venue_address')] ?? '').trim();
    const facility = resolveFacility(ward, venueName, venueAddress, mapLocationFromRow(row, at), wards, addresses);
    if (!facility) continue;
    total += 1;
    if (facility.locationKind === 'exact_address' || facility.locationKind === 'multiple_addresses') withVenueAddress += 1;
    else if (facility.locationKind === 'known_facility') withKnownFacility += 1;
    else if (facility.locationKind === 'activity_area') withAreaLocation += 1;
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
      file: 'data/tokyo-community/communities.csv',
      classification: 'raw_open_data_unverified',
      note: DATA_SOURCE_NOTE,
    },
    counts: { total, withVenueAddress, withKnownFacility, withAreaLocation, withWardOfficeFallback },
    facilities,
  };
}

export async function loadCommunityFacilityDetail(
  facilityKey: string,
  options?: { excludeAgeUnrelated?: boolean; onlySports?: boolean },
): Promise<CommunityFacilityDetail | null> {
  const excludeAgeUnrelated = options?.excludeAgeUnrelated ?? false;
  const onlySports = options?.onlySports ?? false;
  const [{ header, columnAt, rows }, wards, addresses, youngAdultAllowlist] = await Promise.all([
    readRows(),
    readWardGeocodingDirectory(),
    readVenueAddressDirectory(),
    excludeAgeUnrelated ? readYoungAdultAllowlist() : Promise.resolve(null),
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
    if (
      excludeAgeUnrelated &&
      !isYoungAdultRelevant(ward, name, row[at('category')] ?? '', row[at('description')] ?? '', youngAdultAllowlist)
    ) continue;
    if (onlySports && !isSportsCommunity(row[at('category')] ?? '', row[at('description')] ?? '')) continue;
    const venueName = (row[at('venue_name')] ?? '').trim();
    const venueAddress = (row[at('venue_address')] ?? '').trim();
    const facility = resolveFacility(ward, venueName, venueAddress, mapLocationFromRow(row, at), wards, addresses);
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
      locationKind: facility.locationKind ?? 'ward_office',
      locationPrecision: facility.locationPrecision ?? null,
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
    locationKind: matchedFacility.locationKind ?? 'ward_office',
    locationPrecision: matchedFacility.locationPrecision ?? null,
    count: communities.length,
    communities,
  };
}
