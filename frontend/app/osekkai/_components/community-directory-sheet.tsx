import type { CommunityFacilityDetail } from '@/lib/osekkai/community-directory-types';
import styles from '../osekkai.module.css';

export default function CommunityDirectorySheet({
  facility,
  note,
  onClose,
}: {
  facility: CommunityFacilityDetail;
  note: string;
  onClose: () => void;
}) {
  return (
    <aside className={styles.mapSheet} aria-label={`${facility.name}の地域コミュニティ一覧`}>
      <button className={styles.mapSheetClose} type="button" onClick={onClose} aria-label="地域コミュニティ一覧を閉じる">×</button>
      <div className={styles.mapSheetLabels}>
        <span>Open Data</span>
        <span>{facility.ward}</span>
        <span>{facility.precise ? '活動場所の座標' : '区役所の目安地点'}</span>
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
      {facility.sourceUrl ? (
        <div className={styles.mapSheetSources}>
          <strong>Source</strong>
          <a href={facility.sourceUrl} target="_blank" rel="noreferrer">{facility.ward}公式ページ ↗</a>
        </div>
      ) : null}
    </aside>
  );
}
