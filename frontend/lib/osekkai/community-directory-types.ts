export type CommunityDirectoryEntry = {
  id: string;
  name: string;
  nameKana: string | null;
  category: string | null;
  venueName: string;
  venueAddress: string;
  latitude: number;
  longitude: number;
  targetAudience: string | null;
  officialUrl: string | null;
  onlineParticipation: string | null;
  sourceUpdatedAt: string | null;
  fetchedAt: string | null;
};

export type CommunityFacilitySummary = {
  key: string;
  ward: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  sourceUrl: string;
  precise: boolean;
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
    withPreciseLocation: number;
    withWardOfficeFallback: number;
  };
  facilities: CommunityFacilitySummary[];
};
