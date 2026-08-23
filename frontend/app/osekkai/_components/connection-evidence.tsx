import type { ConnectionEvidence } from '@/lib/osekkai/types.generated';
import styles from '../osekkai.module.css';

const facts: Array<[keyof ConnectionEvidence, string]> = [
  ['soloFriendly', 'ひとり参加'],
  ['beginnerFriendly', '初心者'],
  ['recurring', '次回・継続'],
  ['structuredConversation', '会話のきっかけ'],
  ['sharedMeal', 'みんなで食事'],
  ['groupWork', '共同作業'],
  ['roleAvailable', '小さな役割'],
];

export default function ConnectionEvidenceView({ evidence }: { evidence?: ConnectionEvidence }) {
  if (!evidence) {
    return <p className={styles.evidenceUnknown}>交流につながる根拠は、まだ確認できていません。</p>;
  }
  return (
    <div className={styles.connectionEvidence}>
      <div className={styles.connectionLevel}>
        <span>Connection</span>
        <strong>Level {evidence.connectionLevel}</strong>
        <small>根拠信頼度 {Math.round(evidence.model.confidence * 100)}%</small>
      </div>
      <div className={styles.evidenceFacts}>
        {facts.map(([key, label]) => {
          const value = evidence[key];
          if (value !== 'yes') return null;
          return <span key={String(key)}>✓ {label}</span>;
        })}
      </div>
      <ul className={styles.evidenceList}>
        {evidence.evidence.slice(0, 3).map((item, index) => (
          <li key={`${item.kind}-${index}`}>
            <span>{item.text}</span>
            <a href={item.url} target="_blank" rel="noreferrer">根拠 ↗</a>
          </li>
        ))}
      </ul>
    </div>
  );
}
