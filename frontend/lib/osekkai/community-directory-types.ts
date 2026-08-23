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

export type CommunityFacility = {
  key: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  sourceUrl: string;
  communities: CommunityDirectoryEntry[];
};

export type CommunityDirectoryResult = {
  generatedAt: string;
  ward: string;
  dataSource: {
    file: string;
    classification: 'raw_open_data_unverified';
    note: string;
  };
  counts: {
    totalInWard: number;
    withKnownVenue: number;
    withoutKnownVenue: number;
  };
  facilities: CommunityFacility[];
};
