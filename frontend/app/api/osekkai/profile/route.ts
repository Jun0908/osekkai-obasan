import {
  profileDelete,
  profileGet,
  profileUpdate,
} from '@/lib/server/osekkai-route-handlers';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  return profileGet(request);
}

export async function PATCH(request: Request) {
  return profileUpdate(request);
}

export async function PUT(request: Request) {
  return profileUpdate(request);
}

export async function DELETE(request: Request) {
  return profileDelete(request);
}
