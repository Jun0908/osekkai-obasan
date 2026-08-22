'use client';

import { useEffect, useState } from 'react';

import styles from '@/app/osekkai/osekkai.module.css';
import { friendlyApiError, getOsekkaiSession, type SessionInfo } from './api-client';
import { ModeBadge } from './ui';

export default function HubStatus() {
  const [session, setSession] = useState<SessionInfo>();
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    void getOsekkaiSession()
      .then((next) => {
        if (active) setSession(next);
      })
      .catch((reason: unknown) => {
        if (active) setError(friendlyApiError(reason));
      });
    return () => {
      active = false;
    };
  }, []);

  if (error) {
    return (
      <span className={styles.connectionState} title={error}>
        <span className={styles.statusDotMuted} aria-hidden="true" />
        接続を確認中
      </span>
    );
  }
  if (!session) {
    return <span className={styles.connectionState}>準備中…</span>;
  }
  return <ModeBadge mode={session.dataMode} />;
}
