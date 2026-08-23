import { spawn } from 'child_process';
import { promises as fs } from 'fs';
import path from 'path';

import { isOsekkaiMutation, type OsekkaiCommand } from './osekkai-commands';
import type {
  JsonObject,
  OsekkaiCliResponse,
  OsekkaiCommandResult,
} from './osekkai-contract';
import { createRequestId, OsekkaiHttpError, publicCliError } from './osekkai-errors';
import { validateOsekkaiCommandPayload } from './osekkai-request-validation';
import { withOsekkaiBridgePermit } from './osekkai-resource-guards';
import { validateOsekkaiCommandData } from './osekkai-response-validation';
import { isValidOsekkaiUserId } from './osekkai-user';

const DEFAULT_TIMEOUT_MS = 25_000;
const MAX_TIMEOUT_MS = 120_000;
// The complete live Event Mesh intentionally includes non-recommended,
// canceled, sold-out, and evidence-unknown events for the map. JsonStore
// already caps its canonical file at 2 MiB; allow envelope overhead without
// truncating that bounded, server-owned response.
const MAX_STDOUT_BYTES = 3 * 1024 * 1024;
const MAX_STDERR_BYTES = 256 * 1024;

export type InvokeOsekkaiOptions = {
  command: OsekkaiCommand;
  userId: string;
  payload?: JsonObject;
  idempotencyKey?: string | null;
};

function openClawRoot(): string {
  // OpenClaw is a separately provisioned runtime, not a build-time bundle input.
  return path.resolve(
    /* turbopackIgnore: true */
    process.env.OPENCLAW_ROOT || path.join(process.cwd(), '..', 'agents-OpenClaw'),
  );
}

function osekkaiDataRoot(): string {
  return path.resolve(
    /* turbopackIgnore: true */
    process.env.OSEKKAI_DATA_ROOT || path.join(openClawRoot(), 'data', 'osekkai'),
  );
}

function cliPath(): string {
  return path.join(openClawRoot(), 'scripts', 'osekkai_cli.py');
}

function timeoutMs(): number {
  const configured = Number(process.env.OSEKKAI_BRIDGE_TIMEOUT_MS);
  if (!Number.isFinite(configured) || configured < 100) {
    return DEFAULT_TIMEOUT_MS;
  }
  return Math.min(Math.floor(configured), MAX_TIMEOUT_MS);
}

async function fileExists(target: string): Promise<boolean> {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

async function pythonBin(): Promise<string> {
  const explicit = process.env.OPENCLAW_PYTHON_BIN?.trim();
  if (explicit) {
    if (process.platform === 'win32' && ['python', 'python3'].includes(explicit.toLowerCase())) {
      const pyenvRoot = process.env.PYENV_ROOT || process.env.PYENV_HOME || process.env.PYENV;
      if (pyenvRoot) {
        try {
          const version = (await fs.readFile(path.join(pyenvRoot, 'version'), 'utf8')).trim().split(/\s+/)[0];
          const resolved = path.join(pyenvRoot, 'versions', version, 'python.exe');
          if (version && await fileExists(resolved)) return resolved;
        } catch {
          // Fall through to an explicit command or bundled environment.
        }
      }
    }
    return explicit;
  }

  const bundled =
    process.platform === 'win32'
      ? path.join(openClawRoot(), '.venv', 'Scripts', 'python.exe')
      : path.join(openClawRoot(), '.venv', 'bin', 'python');
  if (await fileExists(bundled)) {
    return bundled;
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

const CHILD_ENV_KEYS = [
  'PATH',
  'SystemRoot',
  'WINDIR',
  'TEMP',
  'TMP',
  'PATHEXT',
  'COMSPEC',
  'OSEKKAI_DEMO_MODE',
  'OSEKKAI_TIMEZONE',
  'OSEKKAI_DATA_RETENTION_DAYS',
  'OSEKKAI_FIXTURE_ROOT',
  'OSEKKAI_FIXED_NOW',
  'OSEKKAI_POLICY_PATH',
  'OSEKKAI_CONNECTION_POLICY_PATH',
  'OSEKKAI_LIVE_OPPORTUNITIES_PATH',
  'OSEKKAI_FREEBUSY_HORIZON_DAYS',
  'GOOGLE_CLIENT_ID',
  'GOOGLE_CLIENT_SECRET',
  'GOOGLE_REDIRECT_URI',
  'OSEKKAI_CREDENTIAL_ENCRYPTION_KEY',
  'GOOGLE_ROUTES_API_KEY',
  'GOOGLE_MAPS_API_KEY',
  'LUMA_ICAL_URL',
  'DOORKEEPER_API_TOKEN',
  'OSEKKAI_LIVE_ORIGIN_LATITUDE',
  'OSEKKAI_LIVE_ORIGIN_LONGITUDE',
  'OSEKKAI_MAX_ROUTE_CANDIDATES',
  'OSEKKAI_ROUTES_TIMEOUT_SECONDS',
  'OSEKKAI_LLM_ENABLED',
  'OSEKKAI_LLM_PROVIDER',
  'OSEKKAI_LLM_MODEL',
  'OSEKKAI_LLM_TIMEOUT_SECONDS',
  'OPENAI_API_KEY',
  'OPENAI_BASE_URL',
  'OSEKKAI_VAULT_ROOT',
  'OSEKKAI_MEMORY_SEMANTIC_SEARCH',
] as const;

function readEnvCaseInsensitive(source: NodeJS.ProcessEnv, key: string): string | undefined {
  const actualKey = Object.keys(source).find((candidate) => candidate.toLowerCase() === key.toLowerCase());
  return actualKey ? source[actualKey] : undefined;
}

/** Builds the privacy-minimal environment inherited by the Python child. */
export function buildOsekkaiChildEnv(source: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const sourceNodeEnv = readEnvCaseInsensitive(source, 'NODE_ENV');
  const nodeEnv =
    sourceNodeEnv === 'development' || sourceNodeEnv === 'test' ? sourceNodeEnv : 'production';
  const childEnv: NodeJS.ProcessEnv = { NODE_ENV: nodeEnv };
  for (const key of CHILD_ENV_KEYS) {
    const value = readEnvCaseInsensitive(source, key);
    if (value !== undefined) {
      childEnv[key] = value;
    }
  }
  childEnv.OPENCLAW_ROOT = openClawRoot();
  childEnv.OSEKKAI_DATA_ROOT = osekkaiDataRoot();
  childEnv.PYTHONIOENCODING = 'utf-8';
  childEnv.PYTHONUTF8 = '1';
  return childEnv;
}

export function isCliResponse<T>(value: unknown, requestId: string): value is OsekkaiCliResponse<T> {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  if (candidate.requestId !== requestId || typeof candidate.ok !== 'boolean') {
    return false;
  }
  if (candidate.ok) {
    const allowed = new Set(['ok', 'requestId', 'data', 'idempotentReplay']);
    return (
      Object.keys(candidate).every((key) => allowed.has(key)) &&
      Object.prototype.hasOwnProperty.call(candidate, 'data') &&
      (!Object.prototype.hasOwnProperty.call(candidate, 'idempotentReplay') ||
        candidate.idempotentReplay === true)
    );
  }
  const error = candidate.error;
  return (
    Object.keys(candidate).length === 3 &&
    Object.keys(candidate).every((key) => ['ok', 'requestId', 'error'].includes(key)) &&
    Boolean(error) &&
    typeof error === 'object' &&
    Object.keys(error as Record<string, unknown>).length === 2 &&
    Object.keys(error as Record<string, unknown>).every((key) => ['code', 'message'].includes(key)) &&
    typeof (error as Record<string, unknown>).code === 'string' &&
    typeof (error as Record<string, unknown>).message === 'string'
  );
}

function exitError(code: number | null, requestId: string): OsekkaiHttpError {
  switch (code) {
    case 2:
      return new OsekkaiHttpError(
        'PYTHON_REQUEST_REJECTED',
        'リクエスト内容を処理できませんでした。',
        400,
        requestId,
      );
    case 3:
      return new OsekkaiHttpError(
        'STORAGE_UNAVAILABLE',
        '保存領域を利用できません。時間をおいてお試しください。',
        503,
        requestId,
      );
    case 4:
      return new OsekkaiHttpError(
        'PROVIDER_UNAVAILABLE',
        '候補情報を取得できませんでした。',
        502,
        requestId,
      );
    default:
      return new OsekkaiHttpError(
        'PYTHON_PROCESS_FAILED',
        'おっせかいエンジンを実行できませんでした。',
        502,
        requestId,
      );
  }
}

async function runCliWithPermit<T>(
  request: JsonObject & { requestId: string },
): Promise<OsekkaiCliResponse<T>> {
  const executable = await pythonBin();
  const script = cliPath();
  const root = openClawRoot();

  if (!(await fileExists(script))) {
    throw new OsekkaiHttpError(
      'PYTHON_CLI_NOT_FOUND',
      'おっせかいエンジンが見つかりません。',
      503,
      request.requestId,
    );
  }

  return new Promise((resolve, reject) => {
    const child = spawn(/* turbopackIgnore: true */ executable, [script], {
      cwd: root,
      env: buildOsekkaiChildEnv(),
      shell: false,
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const stdoutChunks: Buffer[] = [];
    let stderrBytes = 0;
    let stdoutBytes = 0;
    let timedOut = false;
    let outputExceeded = false;
    let settled = false;

    const finishReject = (error: unknown) => {
      if (!settled) {
        settled = true;
        reject(error);
      }
    };

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill();
    }, timeoutMs());

    child.stdout.on('data', (chunk: Buffer | string) => {
      const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      stdoutBytes += buffer.byteLength;
      if (stdoutBytes > MAX_STDOUT_BYTES) {
        outputExceeded = true;
        child.kill();
        return;
      }
      stdoutChunks.push(buffer);
    });

    child.stderr.on('data', (chunk: Buffer | string) => {
      const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      stderrBytes += buffer.byteLength;
      // stderr is intentionally neither retained nor returned. Killing an
      // excessively noisy child bounds memory and protects logs from raw text.
      if (stderrBytes > MAX_STDERR_BYTES) {
        outputExceeded = true;
        child.kill();
      }
    });

    child.on('error', () => {
      clearTimeout(timer);
      finishReject(
        new OsekkaiHttpError(
          'PYTHON_PROCESS_UNAVAILABLE',
          'おっせかいエンジンを起動できませんでした。',
          503,
          request.requestId,
        ),
      );
    });

    child.on('close', (code) => {
      clearTimeout(timer);
      if (settled) {
        return;
      }
      if (timedOut) {
        finishReject(
          new OsekkaiHttpError(
            'PYTHON_TIMEOUT',
            '処理に時間がかかっています。もう一度お試しください。',
            504,
            request.requestId,
          ),
        );
        return;
      }
      if (outputExceeded) {
        finishReject(
          new OsekkaiHttpError(
            'PYTHON_OUTPUT_TOO_LARGE',
            'おっせかいエンジンからの応答が大きすぎます。',
            502,
            request.requestId,
          ),
        );
        return;
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(Buffer.concat(stdoutChunks).toString('utf8'));
      } catch {
        if (code !== 0) {
          finishReject(exitError(code, request.requestId));
          return;
        }
        finishReject(
          new OsekkaiHttpError(
            'PYTHON_INVALID_JSON',
            'おっせかいエンジンの応答を確認できませんでした。',
            502,
            request.requestId,
          ),
        );
        return;
      }

      // The CLI intentionally exits non-zero for a public-safe provider error.
      // Preserve that structured envelope so callers can surface an actionable
      // code such as CALENDAR_NOT_CONNECTED instead of flattening it to a 502.
      if (code !== 0) {
        if (isCliResponse<T>(parsed, request.requestId) && !parsed.ok) {
          settled = true;
          resolve(parsed);
          return;
        }
        finishReject(exitError(code, request.requestId));
        return;
      }

      if (!isCliResponse<T>(parsed, request.requestId)) {
        finishReject(
          new OsekkaiHttpError(
            'PYTHON_INVALID_RESPONSE',
            'おっせかいエンジンの応答形式が正しくありません。',
            502,
            request.requestId,
          ),
        );
        return;
      }

      settled = true;
      resolve(parsed);
    });

    child.stdin.on('error', () => {
      // A close/error event carries the public-safe failure classification.
    });
    child.stdin.end(JSON.stringify(request), 'utf8');
  });
}

async function runCli<T>(
  request: JsonObject & { requestId: string },
): Promise<OsekkaiCliResponse<T>> {
  return withOsekkaiBridgePermit(request.requestId, () => runCliWithPermit<T>(request));
}

export async function invokeOsekkaiCommand<T = unknown>(
  options: InvokeOsekkaiOptions,
): Promise<OsekkaiCommandResult<T>> {
  if (!isValidOsekkaiUserId(options.userId)) {
    throw new OsekkaiHttpError('INVALID_USER_ID', 'セッションを確認できません。', 401);
  }
  if (isOsekkaiMutation(options.command, options.payload || {}) && !options.idempotencyKey) {
    throw new OsekkaiHttpError(
      'IDEMPOTENCY_KEY_REQUIRED',
      '有効な冪等キーを指定してください。',
      400,
    );
  }

  const requestId = createRequestId();
  const payload = validateOsekkaiCommandPayload(
    options.command,
    options.payload || {},
    requestId,
  );
  const response = await runCli<T>({
    schemaVersion: '1.0',
    requestId,
    command: options.command,
    userId: options.userId,
    idempotencyKey: options.idempotencyKey || null,
    payload,
  });

  if (!response.ok) {
    throw publicCliError(response.error.code, requestId);
  }

  const data = validateOsekkaiCommandData<T>(
    options.command,
    payload,
    response.data,
    options.userId,
    requestId,
  );
  return { data, requestId };
}
