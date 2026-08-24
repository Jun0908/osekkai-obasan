import { NextResponse } from 'next/server';

import type { CommunityGenreFilter } from '@/lib/osekkai/community-directory';
import { loadCommunityDirectorySummary, loadCommunityFacilityDetail } from '@/lib/osekkai/community-directory';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const GENRE_FILTERS: readonly CommunityGenreFilter[] = ['sports', 'music_culture', 'learning', 'social'];

function parseGenre(value: string | null): CommunityGenreFilter | undefined {
  return GENRE_FILTERS.find((candidate) => candidate === value);
}

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const key = params.get('key')?.trim();
  const genre = parseGenre(params.get('genre'));
  if (key) {
    if (key.length > 80) {
      return NextResponse.json({ error: 'key is invalid' }, { status: 400 });
    }
    try {
      const detail = await loadCommunityFacilityDetail(key, { genre });
      if (!detail) {
        return NextResponse.json({ error: 'facility not found' }, { status: 404 });
      }
      return NextResponse.json(detail);
    } catch {
      return NextResponse.json({ error: 'community directory is unavailable' }, { status: 503 });
    }
  }
  try {
    const summary = await loadCommunityDirectorySummary({ genre });
    return NextResponse.json(summary);
  } catch {
    return NextResponse.json({ error: 'community directory is unavailable' }, { status: 503 });
  }
}
