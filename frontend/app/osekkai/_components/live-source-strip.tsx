import type { SourceStatusResult } from '@/lib/osekkai/types';
import styles from '../osekkai.module.css';

const healthLabel: Record<string, string> = {
  healthy: '同期済み',
  stale: '更新確認中',
  error: '一時停止',
  never_synced: '未同期',
  credential_missing: '接続待ち',
  unauthorized: '未許可',
  disabled: '任意',
};

function syncTime(value: string | null): string {
  if (!value) return 'まだ取得していません';
  return new Intl.DateTimeFormat('ja-JP', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(value));
}

export default function LiveSourceStrip({ status }: { status: SourceStatusResult | null }) {
  if (!status) {
    return <div className={styles.liveSourceStrip} aria-live="polite">Live Sourceを確認しています…</div>;
  }
  return (
    <section className={styles.liveSourcePanel} aria-labelledby="live-source-heading">
      <div className={styles.liveSourceHeading}>
        <div>
          <span className={styles.livePulse} aria-hidden="true" />
          <strong id="live-source-heading">OpenClaw Live</strong>
          <span>{status.counts.events}件を取得・{status.counts.opportunities}件を推薦候補化</span>
        </div>
        <time dateTime={status.generatedAt}>更新 {syncTime(status.generatedAt)}</time>
      </div>
      <div className={styles.sourceChips}>
        {status.sources.filter((source) => source.requiredForDemo).map((source) => (
          <div className={styles.sourceChip} data-health={source.health} key={source.id}>
            <span className={styles.sourceDot} aria-hidden="true" />
            <span>
              <strong>{source.displayName}</strong>
              <small>{healthLabel[source.health] ?? source.health} · {source.eventCount}件 · {syncTime(source.lastSuccessAt)}</small>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
