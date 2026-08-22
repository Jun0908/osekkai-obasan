import Link from 'next/link';
import type { ReactNode } from 'react';

import styles from '@/app/osekkai/osekkai.module.css';

export function PageIntro({
  eyebrow,
  title,
  children,
  aside,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <header className={styles.pageIntro}>
      <div>
        <p className={styles.eyebrow}>{eyebrow}</p>
        <h1>{title}</h1>
        <div className={styles.pageLead}>{children}</div>
      </div>
      {aside ? <div className={styles.introAside}>{aside}</div> : null}
    </header>
  );
}

export function ModeBadge({ mode }: { mode?: string }) {
  const live = mode === 'live';
  return (
    <span className={live ? styles.modeLive : styles.modeDemo}>
      <span className={styles.statusDot} aria-hidden="true" />
      {live ? 'ライブデータ' : 'オフラインデモ'}
    </span>
  );
}

export function InlineNotice({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'success' | 'warning' | 'error';
  title?: string;
  children: ReactNode;
}) {
  return (
    <div className={`${styles.notice} ${styles[`notice_${tone}`]}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span className={styles.noticeIcon} aria-hidden="true">
        {tone === 'success' ? '✓' : tone === 'warning' ? '!' : tone === 'error' ? '×' : 'i'}
      </span>
      <div>
        {title ? <strong>{title}</strong> : null}
        <div>{children}</div>
      </div>
    </div>
  );
}

export function LoadingBlock({ label = '読み込んでいます' }: { label?: string }) {
  return (
    <div className={styles.loadingBlock} role="status" aria-live="polite">
      <span className={styles.spinner} aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({
  title,
  children,
  href,
  action,
}: {
  title: string;
  children: ReactNode;
  href?: string;
  action?: string;
}) {
  return (
    <div className={styles.emptyState}>
      <span className={styles.emptyMark} aria-hidden="true">○</span>
      <h2>{title}</h2>
      <div>{children}</div>
      {href && action ? <Link className={styles.secondaryButton} href={href}>{action}</Link> : null}
    </div>
  );
}

export function ClassificationBadge({ classification }: { classification?: string }) {
  const normalized = classification ?? 'unverified';
  const labels: Record<string, string> = {
    measured: '実測',
    reference_estimate: '参考推計',
    demo: 'デモシナリオ',
    unverified: '未検証',
  };
  return (
    <span className={`${styles.classification} ${styles[`classification_${normalized}`] ?? ''}`}>
      {labels[normalized] ?? normalized}
    </span>
  );
}

export function VisuallyHidden({ children }: { children: ReactNode }) {
  return <span className={styles.srOnly}>{children}</span>;
}
