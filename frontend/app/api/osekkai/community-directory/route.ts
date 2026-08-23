import { NextResponse } from 'next/server';

import { loadCommunityDirectory } from '@/lib/osekkai/community-directory';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const ward = (params.get('ward') ?? '千代田区').trim();
  if (!ward || ward.length > 20) {
    return NextResponse.json({ error: 'ward is invalid' }, { status: 400 });
  }
  try {
    const result = await loadCommunityDirectory(ward);
    return NextResponse.json(result);
  } catch {
    return NextResponse.json({ error: 'community directory is unavailable' }, { status: 503 });
  }
}
