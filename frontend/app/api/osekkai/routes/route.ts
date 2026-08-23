import { eventRoutePost } from '@/lib/server/osekkai-route-handlers';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export function POST(request: Request) {
  return eventRoutePost(request);
}
