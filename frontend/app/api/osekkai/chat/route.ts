import { chatGet, chatPost } from '@/lib/server/osekkai-route-handlers';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  return chatGet(request);
}

export async function POST(request: Request) {
  return chatPost(request);
}
