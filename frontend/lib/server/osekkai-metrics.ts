import { OSEKKAI_COMMANDS } from './osekkai-commands';
import type { OsekkaiCommandResult } from './osekkai-contract';
import { invokeOsekkaiCommand } from './osekkai-openclaw-bridge';

/** Python owns metric derivation; Next.js only maps the authenticated user. */
export function getOsekkaiMetrics<T = unknown>(userId: string): Promise<OsekkaiCommandResult<T>> {
  return invokeOsekkaiCommand<T>({ command: OSEKKAI_COMMANDS.metrics, userId });
}
