'use client';

import styles from './osekkai.module.css';

export default function OsekkaiError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <section className={styles.errorPage}>
      <p className={styles.eyebrow}>うまく開けませんでした</p>
      <h1>ここで、ひと休み。</h1>
      <p>入力した内容はこの画面では送信されていません。少し待って、もう一度お試しください。</p>
      <button className={styles.primaryButton} type="button" onClick={reset}>
        もう一度開く
      </button>
    </section>
  );
}
