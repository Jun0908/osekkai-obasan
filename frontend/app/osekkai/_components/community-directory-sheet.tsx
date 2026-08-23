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
        <span>{facility.locationKind === 'exact_address' || facility.locationKind === 'known_facility' ? '確認済み場所' : facility.locationKind === 'multiple_addresses' ? '複数会場の代表' : facility.locationKind === 'activity_area' ? '活動区域の目安' : '区役所単位の目安'}</span>
        <span>{facility.communities.length}件</span>
      </div>
      <h2>{facility.name}</h2>
      <p className={styles.mapSheetWhen}>{facility.address}</p>
      {facility.locationKind === 'activity_area' ? <p className={styles.communityDirectoryNote}>このピンは町丁目の代表点です。実際の集合場所・開催場所ではありません。</p> : null}
      {facility.locationKind === 'multiple_addresses' ? <p className={styles.communityDirectoryNote}>複数の会場住所が掲載されているため、地図には一覧の最初の会場を代表表示しています。</p> : null}
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
          <a href={facility.sourceUrl} target="_blank" rel="noreferrer">位置・掲載情報の根拠 ↗</a>
        </div>
      ) : null}
    </aside>
  );
}
