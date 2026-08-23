export type CommunityDirectoryEntry = {
  id: string;
  name: string;
  nameKana: string | null;
  category: string | null;
  venueName: string;
  venueAddress: string;
  latitude: number;
  longitude: number;
  locationKind: CommunityLocationKind;
  locationPrecision: string | null;
  targetAudience: string | null;
  officialUrl: string | null;
  onlineParticipation: string | null;
  sourceUpdatedAt: string | null;
  fetchedAt: string | null;
};

export type CommunityLocationKind = 'exact_address' | 'known_facility' | 'activity_area' | 'ward_office';

export type CommunityFacilitySummary = {
  key: string;
  ward: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  sourceUrl: string;
  locationKind: CommunityLocationKind;
  locationPrecision: string | null;
  count: number;
};

export type CommunityFacilityDetail = CommunityFacilitySummary & {
  communities: CommunityDirectoryEntry[];
};

export type CommunityDirectoryResult = {
  generatedAt: string;
  dataSource: {
    file: string;
    classification: 'raw_open_data_unverified';
    note: string;
  };
  counts: {
    total: number;
    withVenueAddress: number;
    withKnownFacility: number;
    withAreaLocation: number;
    withWardOfficeFallback: number;
  };
  facilities: CommunityFacilitySummary[];
};
