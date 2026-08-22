import styles from './osekkai.module.css';

export default function Loading() {
  return (
    <div className={styles.routeLoading} role="status" aria-live="polite">
      <span className={styles.spinner} aria-hidden="true" />
      <p>ゆっくり準備しています…</p>
    </div>
  );
}
