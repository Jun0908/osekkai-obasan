import { NextResponse } from 'next/server';

import { loadCommunityDirectorySummary, loadCommunityFacilityDetail } from '@/lib/osekkai/community-directory';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const key = params.get('key')?.trim();
  if (key) {
    if (key.length > 80) {
      return NextResponse.json({ error: 'key is invalid' }, { status: 400 });
    }
    try {
      const detail = await loadCommunityFacilityDetail(key);
      if (!detail) {
        return NextResponse.json({ error: 'facility not found' }, { status: 404 });
      }
      return NextResponse.json(detail);
    } catch {
      return NextResponse.json({ error: 'community directory is unavailable' }, { status: 503 });
    }
  }
  try {
    const summary = await loadCommunityDirectorySummary();
    return NextResponse.json(summary);
  } catch {
    return NextResponse.json({ error: 'community directory is unavailable' }, { status: 503 });
  }
}
