/**
 * The only Python commands the Next.js process is allowed to invoke.
 *
 * Keep this list in one place: route handlers must never turn request data into
 * a Python module name, script path, or command.
 */
export const OSEKKAI_COMMANDS = {
  chat: 'chat',
  profileGet: 'profile-get',
  profileUpdate: 'profile-update',
  profileDelete: 'profile-delete',
  freebusy: 'freebusy',
  opportunities: 'opportunities',
  decide: 'decide',
  interventions: 'interventions',
  feedback: 'feedback',
  metrics: 'metrics',
  demoSeed: 'demo-seed',
  demoReset: 'demo-reset',
  cleanup: 'cleanup',
} as const;

export type OsekkaiCommand = (typeof OSEKKAI_COMMANDS)[keyof typeof OSEKKAI_COMMANDS];

export const OSEKKAI_MUTATING_COMMANDS: ReadonlySet<OsekkaiCommand> = new Set([
  OSEKKAI_COMMANDS.chat,
  OSEKKAI_COMMANDS.profileUpdate,
  OSEKKAI_COMMANDS.profileDelete,
  OSEKKAI_COMMANDS.decide,
  OSEKKAI_COMMANDS.feedback,
  OSEKKAI_COMMANDS.demoSeed,
  OSEKKAI_COMMANDS.demoReset,
  OSEKKAI_COMMANDS.cleanup,
]);

export function isOsekkaiMutation(
  command: OsekkaiCommand,
  payload: Readonly<Record<string, unknown>>,
): boolean {
  return (
    OSEKKAI_MUTATING_COMMANDS.has(command) ||
    (command === OSEKKAI_COMMANDS.interventions && payload.action === 'record')
  );
}
