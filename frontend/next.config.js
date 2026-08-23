// eslint-disable-next-line @typescript-eslint/no-require-imports -- Next.js config files load as CommonJS.
const path = require('path');

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // `data/tokyo-community/*` lives one level above this Next.js app (repo
  // root), read via `path.resolve(process.cwd(), '..', 'data', ...)` in
  // lib/osekkai/community-directory.ts. Vercel's build-time file tracer only
  // bundles files it can statically discover from *inside* this app's
  // directory, so both roots below must point at the repo root (Turbopack
  // and outputFileTracing must agree, or Next.js rejects the config) for the
  // community-directory API routes to work on Vercel, not just locally.
  turbopack: {
    root: path.join(__dirname, '..'),
  },
  outputFileTracingRoot: path.join(__dirname, '..'),
  outputFileTracingIncludes: {
    '/api/osekkai/community-directory': ['../data/tokyo-community/**/*'],
    '/api/osekkai/map-events': ['./lib/osekkai/map-events-snapshot.generated.json'],
  },
};

module.exports = nextConfig;
