import { calendarDisconnectPost } from '@/lib/server/osekkai-route-handlers';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  return calendarDisconnectPost(request);
}

export async function DELETE(request: Request) {
  return calendarDisconnectPost(request);
}
