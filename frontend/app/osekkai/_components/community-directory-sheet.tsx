import type { CommunityFacility } from '@/lib/osekkai/community-directory-types';
import styles from '../osekkai.module.css';

export default function CommunityDirectorySheet({
  facility,
  note,
  onClose,
}: {
  facility: CommunityFacility;
  note: string;
  onClose: () => void;
}) {
  return (
    <aside className={styles.mapSheet} aria-label={`${facility.name}の地域コミュニティ一覧`}>
      <button className={styles.mapSheetClose} type="button" onClick={onClose} aria-label="地域コミュニティ一覧を閉じる">×</button>
      <div className={styles.mapSheetLabels}>
        <span>Open Data</span>
        <span>{facility.communities.length}件</span>
      </div>
      <h2>{facility.name}</h2>
      <p className={styles.mapSheetWhen}>{facility.address}</p>
      <p className={styles.communityDirectoryNote}>{note}</p>
      <ul className={styles.communityDirectoryList}>
        {facility.communities.map((community) => (
          <li key={community.id}>
            <strong>{community.name}</strong>
            <span>{community.category || 'カテゴリ未確認'}</span>
          </li>
        ))}
      </ul>
      <div className={styles.mapSheetSources}>
        <strong>Source</strong>
        <a href={facility.sourceUrl} target="_blank" rel="noreferrer">千代田区公式ページ ↗</a>
      </div>
    </aside>
  );
}
