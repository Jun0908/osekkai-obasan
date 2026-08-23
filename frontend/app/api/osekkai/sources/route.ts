import { sourcesGet, sourcesPost } from '@/lib/server/osekkai-route-handlers';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export function GET(request: Request) {
  return sourcesGet(request);
}

export function POST(request: Request) {
  return sourcesPost(request);
}
