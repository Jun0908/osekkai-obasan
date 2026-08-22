import {
  interventionsGet,
  interventionsPost,
} from '@/lib/server/osekkai-route-handlers';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  return interventionsGet(request);
}

export async function POST(request: Request) {
  return interventionsPost(request);
}
