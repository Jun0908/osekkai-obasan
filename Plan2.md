# Plan2 — OpenClawで東京の「続く出会い」を見つけるDemo実装計画

- 更新日: 2026-08-22
- 対象: 東京都「都知事杯オープンデータ・ハッカソン 2026」
- プロダクト名: **おせっかいおばさん**
- タグライン: **近づきすぎず、離れすぎず。あなたが一歩動ける瞬間だけ、東京がおせっかいする。**
- 一次資料: `Tokyo_Social_Calibration.pdf` 全14ページ
- 現在のPV: 18秒「出会い、あるかもよ〜」

---

## 0. 今回の大修正

前版の次の方針は撤回します。

- 江東区を固定パイロットにしない
- 図書館や公園へ行くだけの提案を主役にしない
- 「今日はPUSHしない」SceneにDemo時間を使わない
- 大型イベント、展示、講演等を、開催中というだけで提案しない
- 古いOpen Data snapshotを最新イベントのように見せない
- PeatixやLu.maを無断で全面クロールできる前提にしない

新しい中心は次です。

> **OpenClawが東京都全域の最新イベントを更新し続け、その中から、共通の趣味・少人数の会話・次回参加など「関係が続く可能性」のある1件だけを見つける。**

東京都のOpen Dataは、最新イベントそのものだけを供給するデータではありません。行政が把握する施設・地域・人口・イベントデータを「東京の社会接点の骨格」とし、Lu.ma、Doorkeeper、connpass、公式施設サイト、主催者提供情報等を「現在動いている活動」として重ねます。

**Open Dataが骨格、OpenClawが鼓動です。**

---

## 1. PDFから外してはいけない目的

PDFの問題提起は、予定がないこと自体ではありません。

> 予定がないことより、誰にも気づかれないことが痛い。

そのため、製品の成果地点は次の順で考えます。

1. 家から出た
2. 誰かと同じ活動をした
3. もう一度同じ場へ行った
4. 顔を覚えてくれる人ができた
5. 自分から話せる相手・役割ができた

図書館、散歩、展示を見るだけでは1までは達成できますが、2以降は保証できません。今回のDemoで主役にするのは、**2と3へ進めるイベント**です。

### 東京都の課題として示す事実

- 内閣府の令和6年調査では、孤独感がある層は合計で約4割、20代・30代では「しばしばある・常にある」の割合が他の年代より高い
- 同調査では、社会活動へ「特に参加していない」が50.6%
- 東京都の若者調査では、若者の5.3%が、電話・メール・LINEを含めても毎日は他者と挨拶や会話をしていない
- 特に19〜23歳の低所得層男性では、他者との会話が4〜7日に1回以下の層が1割弱存在する

Demoでは、医療効果や金銭的損失を推測で断定しません。「支援窓口を検索する前の段階に、既存の東京の活動へつながる入口が不足している」という行政課題として説明します。

---

## 2. プロダクトの一文定義

> おせっかいおばさんは、本人の予定・移動可能範囲・興味を理解し、東京で今参加できる活動の中から、**次の関係につながる可能性が高い1件**を先回りして届けるOpenClaw Agentである。

これは次のサービスではありません。

- イベント検索結果を大量に並べるアプリ
- 単発の外出回数を増やすだけのアプリ
- 恋愛だけを目的にしたマッチングアプリ
- 孤独を診断する医療アプリ
- AIと会話し続けることで人間関係を代替するアプリ

PVの「出会い」は、恋愛に限定しません。趣味仲間、顔見知り、次回も会える人、地域で役割を持てる相手を含みます。

---

## 3. 「孤独に効く可能性があるイベント」の定義

イベント名に「交流」「Networking」と書いてあるだけでは不十分です。営業目的の名刺交換会や、数百人規模で誰とも話さず帰れる催事もあるからです。

### 3.1 優先する4タイプ

#### A. 継続型の趣味コミュニティ

- 読書会、ボードゲーム、写真、音楽、手芸、料理、ランニング、語学等
- 毎週・隔週・毎月など、次回がある
- 同じ主催者またはコミュニティで複数回開催
- 初参加・一人参加を受け入れる

#### B. 会話が設計された少人数イベント

- ペアトーク、テーブル対話、ワークショップ、共同制作
- 司会やファシリテーターがいる
- 参加者全員が短くても話す構造がある
- 定員が明示されている

#### C. 共食イベント

- 知らない人同士の少人数ディナー
- みんなで作る料理会、地域の食事会
- 席替えや会話カード等、交流の仕組みがある
- 食物アレルギー、価格、開催者、安全面が明確

#### D. 役割が生まれる活動

- ボランティア、地域行事の運営、共同制作、サークル体験
- 参加者が受け身ではなく、小さな役割を持てる
- 同じメンバーや運営者と再接触する導線がある

### 3.2 Connection Level

| Level | 意味 | 例 | 推薦 |
|---|---|---|---|
| 0 | 人と接触しない可能性が高い | 展示を見る、図書館で一人で過ごす | 今回は対象外 |
| 1 | 同じ場所にはいるが会話設計がない | 大型展示会、講演、コンサート | 原則対象外 |
| 2 | その場の会話が設計されている | 少人数交流会、共同ワーク | 条件付き候補 |
| 3 | 同じコミュニティに再参加できる | 月例趣味会、連続講座、定例食事会 | 優先候補 |
| 4 | 関係・役割・相互扶助が育つ | 継続ボランティア、運営参加、共同制作 | 最優先候補 |

Demoで提案するのはLevel 2以上、原則としてLevel 3または4です。

### 3.3 Connection Potentialの根拠項目

OpenClawは次の公開事実を集めます。

- `series_id`または同じ主催者の次回開催
- 開催頻度と将来日程数
- 定員、現在の参加者数、満席・キャンセル待ち
- 一人参加歓迎、初参加歓迎、初心者歓迎の明記
- ペア・グループワーク、自己紹介、共同作業の明記
- 終了後のコミュニティ、次回申込、フォロー導線
- 主催者名、過去開催回数、公開連絡先
- 料金、返金条件、勧誘や営業目的の有無
- 開催場所、開始終了時刻、申込締切

これらが公開情報にない場合は`unknown`とし、AIに埋めさせません。

---

## 4. 利用するデータ — 役割別の確定案

### 4.1 東京の社会接点の骨格: 東京都Open Data

| データ | 取得方法 | 更新 | 使用目的 |
|---|---|---|---|
| [東京都オープンデータカタログ](https://catalog.data.metro.tokyo.lg.jp/) | CKAN `package_search` / `package_show` | 毎日メタデータ差分を確認 | 区市町村のイベント・施設データを自動発見し、最新版Resource URLとライセンスを解決 |
| [施設関連情報_社会教育施設](https://catalog.data.metro.tokyo.lg.jp/dataset/t000021d2000000001) | 公式CSV | カタログ更新時 | 社会教育会館等の信頼できる公共拠点を特定し、公式サイトの活動情報へつなぐ |
| `施設関連情報_公民館` | 東京都カタログから最新Resourceを解決 | カタログ更新時 | 公民館・文化施設・学習拠点を東京都全域で発見 |
| `地域のイベント会場（貸出可能施設）一覧` | `package_search?q=地域のイベント会場` | 毎日メタデータ確認 | 定員、設備、場所等から、小規模で交流可能な会場を特定 |
| 区市町村の`イベント一覧` | `package_search?q=イベント一覧` | 毎日。各Resourceの実日付も検査 | 将来日付が存在し、内容が交流型の場合だけ候補化 |
| 町丁別・年齢別人口 | 東京都統計・各自治体の最新版CSV | 月次または年次 | 個人推薦ではなく、地域別Connection Access Gapの分母に使用 |

Open Dataのイベント一覧は、カタログ更新日だけを信用しません。イベント行の開始日・終了日・申込期限を毎回検査します。将来イベントがないDatasetは自動で`inactive`にします。

### 4.2 現在動いているイベント: Machine-readable Live Feed

| 優先 | 情報源 | 正式な取得方法 | 更新方法 | 強み | 制約 |
|---|---|---|---|---|---|
| 1 | Lu.ma | Tokyo City / CalendarのiCal、Osekkai Curated Calendar API | iCalは定期取得、APIは差分取得、Webhookは即時反映 | コミュニティCalendar、外部イベント登録、次回イベント、登録導線 | APIはLuma Plusかつ管理・掲載Calendar中心。全Lu.maイベントの自由な一括APIではない |
| 2 | Doorkeeper | 公式API `GET /events` / `GET /groups/:group/events` | 30分ごと、`updated_at`差分 | Tokyo、期間、Keyword、Group、定員、参加者数、開催履歴 | API tokenが必要。Featuredだけでは全イベントを網羅しない |
| 3 | connpass | 公式API v2 | API Key取得後、30分ごと | 技術・趣味コミュニティ、Group、参加者数、継続開催を扱える | Key申請が必要。法人利用は有料条件があるため申請区分を確認 |
| 4 | 公共施設・文化施設公式サイト | JSON-LD、RSS、iCal、公開HTMLの順に取得 | 6時間ごと。申込締切前は1時間ごと | 公民館・文化センターの連続講座、地域サークル、区民企画講座 | robots.txt・利用条件・負荷制御をSourceごとに確認。無断高頻度クロール禁止 |

公民館系の実例として、[江東区文化コミュニティ財団の講座情報](https://www.kcf.or.jp/koto/koza/)には、複数月にわたる英会話、手芸、音楽、区民企画講座等と募集状況が掲載されています。江東区だけに限定するのではなく、東京都Open Dataの施設一覧から各区市町村の同様の公式ページを発見し、Source Adapterを増やします。

### 4.3 有力だが、取得権限を先に解決する情報源

| 情報源 | 孤独課題との相性 | Demoでの扱い |
|---|---|---|
| Peatix | グループ、フォロワー、定期開催、定額コミュニティがあり継続性が高い | 一般公開Discovery APIを確認できていないため、全面スクレイピングしない。主催者がURLと構造化項目を提供する、提携Feedを得る、またはLu.ma Curated Calendarへ外部イベントとして承認登録する |
| Meetup | 趣味Groupと繰り返しイベントに強い | APIはMeetup Proと承認が必要。権限取得後のProviderとする |
| Timeleft | 東京で知らない人同士の少人数ディナーを組成し、会話設計が明確 | 公開イベントFeedを前提にしない。Deep Linkまたは提携Providerとして扱う |
| KitchHike | 共食コミュニティという体験がテーマに合う | 現在提供されるイベント範囲と外部利用条件を確認し、主催者・事業者提供Feedが得られた場合に追加 |

Peatixの定期開催機能は、同じ内容を毎週・毎月開催でき、交流会や趣味コミュニティの継続性を示す有力なシグナルです。だからこそ、検索結果HTMLを勝手に複製するのではなく、公式連携または主催者同意で使う価値があります。

### 4.4 Demoで実際に使うSource Set

一次Demoは、次の4本で成立させます。

1. 東京都Open Data Catalog API: 施設・公式Dataset・ライセンスの発見
2. Lu.ma Tokyo iCalまたはOsekkai Curated Calendar: 現在イベント
3. Doorkeeper API: 現在イベントと継続Group
4. 公共文化施設の公式講座ページ: 連続講座・募集状況

connpass、Peatix、Timeleft、KitchHikeは、キー・許諾・提携が間に合えば追加します。Demoの必須経路を、取得権限が未確定のProviderへ依存させません。

---

## 5. Osekkai Curated Calendar

Lu.ma上に`Osekkai Tokyo — 続く出会いCalendar`を作ります。

### 目的

- Lu.ma主催イベントだけでなく、Peatix、Meetup、Doorkeeper、公共施設等の外部イベントを1つの承認Calendarへ集める
- 主催者が自分のイベントを提出できる
- `初参加歓迎`、`少人数`、`継続開催`、`共食`、`共同作業`等のTagを付ける
- OpenClawがAPI / Webhookで最新状態を受け取る
- Cancel、日時変更、満席をPUSH前に再検証する

### 承認条件

- 公開URLと主催者が確認できる
- 日時・場所・料金・定員・申込方法が確認できる
- Connection Level 2以上の根拠がある
- 営業・宗教・政治・投資勧誘等の目的が明示され、誤認を生まない
- ハラスメント対応または主催者連絡先がある
- 初参加者が何をするのか説明できる

### 主催者確認項目

- 一人参加歓迎か
- 初参加者への案内があるか
- 会話または共同作業があるか
- 途中退出できるか
- 次回開催があるか
- 終了後の連絡・コミュニティ導線があるか
- 定員と想定参加人数
- 営業・勧誘の有無

この情報は`Organizer Verified`として扱い、AI推定やOpen Dataと混ぜません。

---

## 6. OpenClawを使う意味 — 常時更新Agent

OpenClawはチャット画面の裏側で、次のLoopを無人実行します。

```text
Discover
  東京都CKANから新Dataset・新Resource・公共施設URLを発見
  ↓
Fetch
  iCal / API / Webhook / 公式サイトから最新情報を取得
  ↓
Normalize
  Event・Series・Community・Venueを共通Schemaへ変換
  ↓
Quality Gate
  期限切れ、取消、満席、欠損、重複、権利不明を除外
  ↓
Connection Classifier
  会話設計、継続性、一人参加、役割を根拠付きで判定
  ↓
Personal Fit
  好み、少しの意外性、過去反応、Calendar、Routesで1件へ絞る
  ↓
Pre-Push Revalidation
  PUSH直前に日時・申込・満席・移動時間を再確認
  ↓
Push and Learn
  行く / 興味ない / 今回は無理 / また今度 → 次の提案を調整
```

### 更新間隔

| Source | 通常 | イベント直前 |
|---|---:|---:|
| Lu.ma Webhook | 即時 | 即時 |
| Lu.ma iCal | 30分 | 10分 |
| Doorkeeper / connpass API | 30分 | 10分 |
| 公共施設公式ページ | 6時間 | 1時間 |
| 東京都CKAN metadata | 24時間 | 変更通知時に即時 |

### 保存するFreshness情報

- `source_published_at`
- `source_updated_at`
- `fetched_at`
- `last_seen_at`
- `revalidated_at`
- `registration_deadline`
- `status`: open / sold_out / waitlist / canceled / ended / unknown
- ETag / Last-Modified / content hash
- Source URL / license / retrieval method

PUSH時点で再検証できない候補は薦めません。過去snapshotを自動的に現在扱いへ昇格させることも禁止します。

---

## 7. データSchema

### Event

- event ID / source ID
- title / description
- start / end / timezone
- venue ID / address / coordinates
- capacity / participants / waitlist
- fee / registration deadline / status
- public URL / booking URL
- organizer ID / community ID / series ID

### Community / Series

- group name
- past event count
- next event count
- recurrence interval
- member or follower count（公開されている場合のみ）
- follow-up channel existence
- organizer history

### Connection Evidence

- solo friendly
- beginner friendly
- facilitated introductions
- pair or group activity
- shared meal
- collaborative task
- recurring event
- next event exists
- role available
- sales solicitation risk
- evidence text / evidence URL / confidence / verification type

### Provenance

| Type | 意味 | 例 |
|---|---|---|
| Raw Open Data | 行政が公開した事実 | 施設名、所在地、座標、施設種別 |
| Live Provider Data | API・iCal・公式ページ上の現在情報 | 開催日時、定員、残席、募集状況 |
| AI Derived | 公開説明からの推定 | Connection Level、対人強度、本人との相性 |
| Organizer Verified | 主催者が確認した情報 | 一人参加歓迎、途中退出可、初参加案内 |
| Private User Data | 本人が同意して提供 | Calendar FreeBusy、興味、拒否履歴 |

AI Derivedには必ず根拠文、Source URL、confidenceを付けます。

---

## 8. 推薦ロジック

### 8.1 Hard Filter

- 終了、取消、満席、申込終了
- 東京都外またはRoutesで現実的でない
- Connection Level 0〜1
- 主催者・場所・料金が不明
- 営業・勧誘リスクが高い
- 本人の安全条件、予算、時間に合わない

### 8.2 Connection Score

優先順位は次です。

1. 次回も同じ人・主催者に会える可能性
2. 会話や共同作業がイベント設計に含まれる
3. 一人・初参加の心理的負担が低い
4. 共通の趣味が会話の入口になる
5. 本人の既存好みから少しだけ外れている
6. CalendarとRoutesに無理なく収まる

`Networking`という単語だけでは加点しません。

### 8.3 継続性の判定

次のいずれかが必要です。

- 同じ`series_id`で将来回が存在する
- 同じCommunityに過去・将来イベントがある
- 定期開催の公開記載がある
- 主催者が次回開催またはCommunity導線を確認している

単発イベントでも、明確なCommunity参加導線があればLevel 2候補にできます。

---

## 9. Demoで見せるもの

### Demoでは見せないもの

- 「今日はPUSHしません」という長いScene
- 図書館や公園だけの提案
- 検索結果一覧
- 2019年イベント
- データ同期の細かいログを延々見せること

PUSHしない機能は安全上残しますが、2分Demoの主役にはしません。

### 60秒Live Demo

#### 0〜10秒: OpenClawが最新の東京を見ている

画面上部にSource状態を短く表示します。

```text
Tokyo Open Data  更新: 08:02
Lu.ma             更新: 08:14
Doorkeeper        更新: 08:10
公共施設公式Site 更新: 07:55
```

「固定データではなく、今日の募集状況まで更新している」と一言で説明します。

#### 10〜25秒: 交流につながらないイベントを落とす

3件の一覧は出さず、判定だけを一瞬表示します。

```text
大型展示会     → 会話設計なし / 単発       除外
名刺交換会     → 営業色・対人負荷が高い   除外
月例の趣味会   → 初参加OK / 8名 / 次回あり 採用
```

#### 25〜45秒: 本人に合わせた1件

- 過去会話から好きな趣味を取得
- 既存の好みと完全一致ではなく、会話の入口がある隣接ジャンルを選ぶ
- Google Calendar FreeBusyで参加可能時間を確認
- Google Routesで実移動時間を確認
- 最新Provider Dataで残席・申込期限を再確認

#### 45〜60秒: PUSH

> 「あんた、この前○○好きって言うてたやろ。今日、8分のとこで月イチの初心者会あるで。ひとり参加OKで、次もある。30分だけ顔出してみ。合わんかったら帰ったらええから。」

表示項目:

- 実イベント名
- `徒歩8分`等のRoutes実測
- `一人参加歓迎`の根拠
- `月例 / 次回あり`の継続根拠
- 定員、料金、申込状況
- Sourceと最終更新時刻
- `行ってみる / これは違う / 今回は無理`

このおばさんは、「人と話さなくていい場所」へ送るのではありません。**本人が話し始める理由を、共通の趣味と小さな滞在時間で作ります。**

---

## 10. 18秒PVの修正版

> 制作・編集・書き出しはユーザー側で進行中のため、本実装Taskの対象外です。この節はLive Demoのイベント種別、表示項目、台詞がPVと矛盾しないための参照仕様として残します。

現在のPVの良い点は残します。

- おばさんの圧とテンポ
- 女の子の「……言い方」
- 「30分だけ。合わなかったら帰ればいい」
- 共通の好みから会話が始まる
- 最後の「……まあ、悪くない」

ただし、偶然の1回だけで終わらせず、**次も会える**ことを18秒内に入れます。

### 起｜0〜4秒

休日、女の子がソファでスマホを見ている。通知が飛び出す。

**おばさん**

「あんた今日ちょっと空いてるやろ。この前これ好き言うてたやん。」

カード:

**「徒歩8分 / 月1回 / 8名 / 初参加・ひとり参加OK」**

**おばさん**

「初心者会あるで。出会い、あるかもよ〜！」

**女の子**

「……言い方。」

### 承｜4〜8秒

**女の子**

「そういうの、めんどくさい……」

**おばさん**

「知ってる！ 30分だけ。合わんかったら帰ったらええ！」

**女の子**

「アプリの圧じゃないんよ。」

`行ってみる`をタップ。

### 転｜8〜13秒

イベント会場。最初は壁際にいる女の子。

**男性**

「あ、それ僕も好きです。」

**女性参加者**

「え、私も。それめっちゃ分かる！」

3人で笑う。

### 継続｜13〜16秒

画面に小さく**「翌月」**。

同じ会場へ入る女の子に、2人が手を振る。

**2人**

「お、また来た！」

女の子が自然に笑う。

### 結｜16〜18秒

おばさんの通知。

**「ほら、次も会えたやろ？」**

**女の子**

「……まあ、悪くない。」

エンド:

**出会いは、検索するより、おせっかいされた方が早い日もある。**

**おせっかいおばさん**

この修正で、PVの成果が「知らない人と一度話した」から「顔を覚えてくれる人ができ始めた」へ変わります。

---

## 11. 2分審査構成

| 時間 | 内容 | Judgeに残すこと |
|---:|---|---|
| 0〜20秒 | 東京都の孤独・社会参加データ | 東京には場所ではなく、継続する接点へのアクセスGapがある |
| 20〜38秒 | 18秒PV | プロダクト体験を感情で理解 |
| 38〜78秒 | Live Demo | OpenClawが今日の実イベントを更新し、Connection Levelで1件に絞る |
| 78〜100秒 | データ構造 | Open Data、Live Provider、AI推定、主催者確認の分離 |
| 100〜115秒 | 東京都への還元 | 地域別の「継続接点不足」を匿名集計 |
| 115〜120秒 | 結論 | 通知数ではなく、顔を覚えてくれる人が増える東京へ |

---

## 12. Demo完成条件

### 必須

- [ ] 東京都全域を対象にSourceを検索し、区固定コードがない
- [ ] Tokyo CKANからDatasetと最新Resourceを自動発見できる
- [ ] Lu.ma iCalまたはAPIから最新イベントを同期できる
- [ ] Doorkeeper公式APIから東京の将来イベントを同期できる
- [ ] 少なくとも1つの公共文化施設公式サイトから連続講座を同期できる
- [ ] 開催終了、取消、満席、申込終了をPUSH前に除外できる
- [ ] EventだけでなくCommunity / Seriesを保存できる
- [ ] Connection Level 2以上だけが推薦候補になる
- [ ] `一人参加OK`、`次回あり`等の根拠URL・根拠文を表示できる
- [ ] Google Calendar FreeBusyが実接続で動く
- [ ] Google Routesが実移動時間を返す
- [ ] 本人の好みと隣接興味から1件だけ選べる
- [ ] Live / AI推定 / Organizer Verifiedを画面で区別できる
- [ ] Sourceの最終更新時刻を表示できる
- [ ] 実在する現在イベントで60秒Demoを完走できる
- [ ] Live Demoのイベント種別・表示項目・台詞が、ユーザー制作中PVの世界観と矛盾しない

### Demo安定化

- [ ] 本番候補1件とBackup候補2件をDemo前日に確保
- [ ] Demo開始10分前に3件を再検証
- [ ] Cancel・満席の場合は自動でBackupへ切り替える
- [ ] Network障害時は直前取得Cacheを使うが、取得時刻を大きく表示
- [ ] 過去fixtureへ切り替える場合は`HISTORICAL DEMO`を画面全体に表示

---

## 13. 実装Task

### 13.1 Task運用ルール

- この節の`TASK-*`を上から順に実行する
- 依存Taskが完了するまで後続Taskを開始しない
- コードを追加しただけでは完了にせず、完了条件と検証を満たしてから`[x]`にする
- PythonをLive Data、Profile、Policy、Schedulerのownerとし、Next.jsに第二のProvider実装を作らない
- 実データ、AI推定、主催者確認、過去fixtureを同じ型・表示へ混ぜない
- 外部Credentialが未設定の場合は、そのProviderだけを`blocked`にし、他Providerの実装と検証を続ける
- PV・Demo動画の制作、編集、書き出しはユーザー側で進行中のため、このTask Queueの対象外とする
- 動画と製品の整合確認は行うが、動画完成を実装Gateの依存にしない
- 完了時はTask直下に、完了日、変更ファイル、検証コマンド、結果、残課題を記録する
- 検証コマンドは、Pythonを`agents-OpenClaw`、npmを`frontend`へ移動してから実行する

### 13.2 実行順Task Queue

#### Gate 0 — 現在のP0を壊さない

- [ ] **TASK-000: 現在のP0 baselineを再確認する**
  - 依存: なし
  - 対象: 既存コード全体。変更はテスト失敗の原因調査時だけ
  - 作業:
    - Python unit test、contract validation、demo runnerを実行
    - frontendのcontract生成、typecheck、lint、test、buildを実行
    - `/osekkai`の現在の主要画面とAPIを記録
  - 完了条件:
    - 新しいLive実装前の成功・失敗数を記録できている
    - 既存P0の失敗と今回変更による退行を区別できる
  - 検証:
    - `python -m unittest discover -s tests -p "test_osekkai_*.py" -v`
    - `python scripts/osekkai_contracts.py --validate-all`
    - `npm.cmd run generate:contracts; npm.cmd run typecheck; npm.cmd run lint; npm.cmd test; npm.cmd run build`

#### Gate 1 — Live Event共通契約

- [ ] **TASK-010: Event / Series / Community / Source契約を追加する**
  - 依存: TASK-000
  - 対象:
    - `contracts/osekkai/event.schema.json`
    - `contracts/osekkai/event-series.schema.json`
    - `contracts/osekkai/community.schema.json`
    - `contracts/osekkai/source-registry.schema.json`
    - `contracts/osekkai/connection-evidence.schema.json`
    - `contracts/osekkai/opportunity.schema.json`
    - `contracts/osekkai/decision.schema.json`
    - `contracts/osekkai/intervention-episode.schema.json`
    - 生成されるTypeScript型・validator
  - 作業:
    - EventとCommunityを分離する
    - recurrence、future occurrences、capacity、participants、registration statusを定義する
    - Raw / Live Provider / AI Derived / Organizer Verified / Private User Dataを列挙する
    - `sourceUpdatedAt`、`fetchedAt`、`revalidatedAt`、`status`、根拠文、根拠URLを必須化する
  - 完了条件:
    - TypeScriptとPythonが同じ正常fixtureを受理する
    - 期限、Source、Connection根拠のないLive候補を拒否する
    - P0 fixtureは既存schemaVersionのまま読み取れるか、明示Migrationがある
  - 検証:
    - `npm.cmd run generate:contracts; npm.cmd run typecheck`
    - `python scripts/osekkai_contracts.py --validate-all`

- [ ] **TASK-020: Source Registryと利用条件を実装する**
  - 依存: TASK-010
  - 対象:
    - `agents-OpenClaw/config/osekkai_sources.json`
    - `agents-OpenClaw/scripts/osekkai_source_registry.py`
    - `agents-OpenClaw/tests/test_osekkai_source_registry.py`
  - 作業:
    - Tokyo CKAN、Lu.ma、Doorkeeper、公共施設公式サイトを必須Sourceとして登録
    - connpass、Peatix、Timeleft、KitchHikeをoptionalまたはorganizer intakeとして登録
    - 取得方式、利用規約、ライセンス、Attribution、refresh interval、TTL、Credential名を保存
    - `enabled`と`authorized`を分離する
  - 完了条件:
    - 利用条件または取得方式が未確定のSourceは同期されない
    - 秘密値が設定ファイルやGit対象ファイルへ入らない
    - Sourceごとの更新頻度とstale基準が1箇所で管理される
  - 検証:
    - `python -m unittest discover -s tests -p "test_osekkai_source_registry.py" -v`

#### Gate 2 — OpenClaw Live Event Mesh

- [ ] **TASK-030: Tokyo CKAN Discoveryを実装する**
  - 依存: TASK-020
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_tokyo_ckan.py`
    - `agents-OpenClaw/tests/test_osekkai_tokyo_ckan.py`
  - 作業:
    - CKAN `package_search`でイベント、社会教育施設、公民館、イベント会場を探索
    - `package_show`で最新Resource、license、provider、modified日時を解決
    - 自治体名を固定せず、設定と検索結果からProvider候補を作る
    - CSV内の将来日付を検査し、将来イベント0件のDatasetを`inactive`にする
  - 完了条件:
    - 江東区固定条件なしで東京都内のDataset候補を列挙できる
    - カタログ更新日が新しくても中身が期限切れなら候補化しない
    - Resource URL、license、checksum、取得日時が保存される
  - 検証:
    - fixtureを使うunit test
    - Credential不要の公式CKANに対するlive smoke test

- [ ] **TASK-040: Lu.ma Providerを実装する**
  - 依存: TASK-020、TASK-010
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_luma.py`
    - `agents-OpenClaw/tests/test_osekkai_luma.py`
    - API/Webhookを使う場合のみ`frontend/app/api/osekkai/providers/luma/webhook/route.ts`
  - 作業:
    - 最低経路としてTokyo CityまたはCurated CalendarのiCalを取得・解析
    - Lu.ma Plus Credentialがある場合はCalendar APIと署名付きWebhookを追加
    - create、update、cancel、calendar event addedを同じEventへ反映
    - 外部イベントは元Source URLを保持
  - 完了条件:
    - API Keyがなくても許可されたiCalから現在イベントを同期できる
    - 取消・日時変更が既存Eventへ反映される
    - 全Lu.maイベントを取得できるという誤った実装・表示がない
  - 検証:
    - iCal fixtureの正常・取消・時刻変更test
    - Webhook実装時は署名正常・不正・replay test

- [ ] **TASK-050: Doorkeeper Providerを実装する**
  - 依存: TASK-020、TASK-010
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_doorkeeper.py`
    - `agents-OpenClaw/tests/test_osekkai_doorkeeper.py`
  - 作業:
    - 公式APIを`prefecture=tokyo`、`since`、`until`、`sort=updated_at`で取得
    - Event、Group、定員、参加人数、waitlist、公開URLを保存
    - rate limit、pagination、429 backoffを実装
  - 完了条件:
    - 東京の将来イベントを公式APIから取得できる
    - Groupの過去・将来開催から継続性を判定できる材料がある
    - API token未設定時は他Sourceを止めず、Source statusだけが`blocked`になる
  - 検証:
    - API response fixtureによるpagination、429、欠損、終了イベントtest
    - token設定時のlive smoke test

- [ ] **TASK-060: 公共文化施設Providerを実装する**
  - 依存: TASK-030、TASK-020
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_public_events.py`
    - `agents-OpenClaw/tests/test_osekkai_public_events.py`
    - `agents-OpenClaw/config/osekkai_sources.json`
  - 作業:
    - Tokyo CKANの施設情報を公式Site発見のseedにする
    - JSON-LD、RSS、iCalを優先し、必要なSourceだけHTML Adapterを実装
    - 最初の実Providerとして江東区文化コミュニティ財団の連続講座を扱うが、domain adapterと地域条件を分離する
    - 募集中・募集終了、全開催日、定員、対象、料金、会場を取得
  - 完了条件:
    - 少なくとも1つの公式公共施設Siteから現在の連続講座を取得できる
    - 江東区という地域条件が共通ロジックに入っていない
    - robots、利用条件、request intervalをRegistryへ記録している
  - 検証:
    - 保存HTML fixtureによる募集状態・連続日程test
    - 許可条件内のlive smoke test

- [ ] **TASK-070: Event Normalizer・Dedup・Freshness Gateを実装する**
  - 依存: TASK-030〜TASK-060
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_event_normalizer.py`
    - `agents-OpenClaw/scripts/osekkai_opportunity_sync.py`
    - `agents-OpenClaw/tests/test_osekkai_event_normalizer.py`
    - `agents-OpenClaw/tests/test_osekkai_opportunity_sync.py`
  - 作業:
    - Provider固有Eventを共通Event / Series / Communityへ変換
    - canonical URL、provider ID、開始時刻、Venueで重複統合
    - ended、canceled、sold out、deadline passed、stale、必須欠損を除外
    - 同じ外部イベントがLu.ma Calendarにも存在する場合に統合
  - 完了条件:
    - 推薦APIへ渡るEventが将来日付・有効Source・取得時刻を持つ
    - 重複Eventが複数通知されない
    - 2019年fixtureがlive modeへ入らない
  - 検証:
    - `python -m unittest discover -s tests -p "test_osekkai_event_*.py" -v`
    - `python -m unittest discover -s tests -p "test_osekkai_opportunity_sync.py" -v`

#### Gate 3 — Connection Intelligence

- [ ] **TASK-080: Connection Evidence Extractorを実装する**
  - 依存: TASK-070
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_connection.py`
    - `agents-OpenClaw/config/osekkai_connection_policy.json`
    - `agents-OpenClaw/tests/test_osekkai_connection.py`
  - 作業:
    - recurrence、solo friendly、beginner friendly、structured conversation、shared meal、group work、role、next event、solicitation riskを抽出
    - Raw field、公開説明、主催者確認を別Evidenceとして保存
    - AI推定を使う場合は根拠文、URL、confidence、model/versionを保存
    - 根拠のない項目は`unknown`
  - 完了条件:
    - `Networking`という語だけで高評価にならない
    - `一人参加OK`、`次回あり`を根拠なしで生成しない
    - Judge UIへ渡せる短いEvidenceが作られる
  - 検証:
    - 月例趣味会、単発講演、大型展示、営業交流会、共食、継続ボランティアfixtureで分類test

- [ ] **TASK-090: Connection LevelとPersonal FitをPolicyへ統合する**
  - 依存: TASK-080
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_policy.py`
    - `agents-OpenClaw/config/osekkai_policy.json`
    - `agents-OpenClaw/tests/test_osekkai_policy.py`
  - 作業:
    - Connection Level 0〜1をlive候補からHard Reject
    - Level 3〜4、再参加、共同活動を優先
    - 本人の好みと隣接ジャンルを分離し、少しずらした理由を保存
    - 価格、対人負荷、過去の拒否理由を加味
  - 完了条件:
    - 受動的大型イベントより継続少人数イベントが優先される
    - 候補は0件または1件
    - 選定理由と除外理由を同じ入力から再現できる
  - 検証:
    - `python -m unittest discover -s tests -p "test_osekkai_*policy*.py" -v`
    - `python -m unittest discover -s tests -p "test_osekkai_connection.py" -v`

#### Gate 4 — 本人の現実条件

- [ ] **TASK-100: Google OAuthとFreeBusy実接続を実装する**
  - 依存: TASK-010、TASK-000
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_google_credentials.py`
    - `agents-OpenClaw/scripts/osekkai_freebusy.py`
    - `agents-OpenClaw/tests/test_osekkai_google_freebusy.py`
    - `frontend/app/api/osekkai/calendar/connect/route.ts`
    - `frontend/app/api/osekkai/calendar/callback/route.ts`
    - `frontend/app/api/osekkai/calendar/disconnect/route.ts`
  - 作業:
    - state、PKCE、匿名session紐付け、暗号化token保存、失効・削除を実装
    - `freebusy.query`だけを使用
    - 予定タイトル、説明、場所、参加者を取得・保存しない
  - 完了条件:
    - 実Google CalendarのFreeBusyから空き時間を返す
    - disconnectとProfile全削除でtokenが削除される
    - demo fixtureとlive responseをUI・Schemaで区別する
  - 検証:
    - OAuth state/PKCE/token暗号化unit test
    - FreeBusy response fixture test
    - Demo Google accountによるconnect/freebusy/disconnect smoke test

- [ ] **TASK-110: Google Routes実接続を実装する**
  - 依存: TASK-070、TASK-100
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_routes.py`
    - `agents-OpenClaw/tests/test_osekkai_routes.py`
  - 作業:
    - 徒歩・公共交通のRoutes adapterを実装
    - 往復時間、30分滞在、bufferがFree Windowへ収まるか計算
    - Source座標がない場合の住所解決とconfidenceを保存
    - quota、timeout、zero resultsを処理
  - 完了条件:
    - UI表示とPolicyが同じRoutes responseを使う
    - 実移動時間が合わないEventは除外される
    - 合成移動時間をlive modeで使用しない
  - 検証:
    - Routes response fixtureによる徒歩・公共交通・失敗test
    - Demo originと実Eventによるlive smoke test

#### Gate 5 — SchedulerとAPI

- [ ] **TASK-120: OpenClaw Live Sync Schedulerを実装する**
  - 依存: TASK-070、TASK-080
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_scheduler.py`
    - `agents-OpenClaw/scripts/osekkai_cli.py`
    - `agents-OpenClaw/tests/test_osekkai_scheduler.py`
  - 作業:
    - `sources-sync`、`sources-status`、`opportunities --live`をCLI allowlistへ追加
    - Sourceごとのrefresh interval、incremental sync、retry、backoffを実装
    - Source単位のlockを使い、1Source失敗でも他Sourceを継続
    - PUSH直前のEvent再検証commandを実装
  - 完了条件:
    - 定期実行でEventが更新され続ける
    - Provider health、last sync、取得・更新・除外件数を返す
    - canceled / sold-out変更がPUSH前に反映される
  - 検証:
    - `python -m unittest discover -s tests -p "test_osekkai_scheduler.py" -v`
    - `python scripts/osekkai_cli.py sources-sync --json`
    - `python scripts/osekkai_cli.py sources-status --json`

- [ ] **TASK-130: Live APIとNext.js bridgeを接続する**
  - 依存: TASK-090〜TASK-120
  - 対象:
    - `frontend/app/api/osekkai/sources/route.ts`
    - `frontend/app/api/osekkai/opportunities/route.ts`
    - `frontend/app/api/osekkai/decide/route.ts`
    - `frontend/lib/server/osekkai-commands.ts`
    - `frontend/lib/server/osekkai-route-handlers.ts`
    - `frontend/lib/server/osekkai-response-validation.ts`
    - `frontend/lib/osekkai/api.ts`
  - 作業:
    - Source status、live opportunities、live decisionをPython CLIへ接続
    - `dataMode=live`ではbrowser提供の候補・時刻・移動時間を信用しない
    - responseを生成validatorで検証
    - API errorをSource unavailable / credential missing / stale / no candidateへ分類
  - 完了条件:
    - BrowserからSource状態、現在候補、1件Decisionを取得できる
    - Python SSOT以外にProvider responseを二重保存しない
    - demo/liveを切り替えても同じContractを使う
  - 検証:
    - frontend server adapter unit test
    - mutationのCSRF / Origin / Content-Type negative test
    - malformed Python response rejection test

#### Gate 6 — Judge用Live UI

- [ ] **TASK-140: Live Source StripとOne Push Cardを実装する**
  - 依存: TASK-130
  - 対象:
    - `frontend/app/osekkai/_components/live-source-strip.tsx`
    - `frontend/app/osekkai/_components/one-push-card.tsx`
    - `frontend/app/osekkai/_components/connection-evidence.tsx`
    - `frontend/app/osekkai/osekkai.module.css`
  - 作業:
    - Provider、last sync、healthを短く表示
    - 実Event、Routes時間、Calendar空き、定員、料金、募集状態を表示
    - 一人参加・継続性・会話設計の根拠を表示
    - Raw / Live / AI Derived / Organizer Verifiedをラベル分離
  - 完了条件:
    - Judgeが10秒で「最新データ」「なぜ交流につながるか」「なぜ本人に合うか」を理解できる
    - Source URLと最終更新時刻を開ける
    - モバイル幅で主要情報とCTAが収まる
  - 検証:
    - component test
    - 390x844と1440x900のbrowser確認
    - keyboard、focus、aria-live確認

- [ ] **TASK-145: 現在地周辺の交流Event Mapを実装する**
  - 依存: TASK-110、TASK-130
  - 対象:
    - `frontend/app/osekkai/map/page.tsx`
    - `frontend/app/osekkai/_components/event-map.tsx`
    - `frontend/app/osekkai/_components/map-event-sheet.tsx`
    - `frontend/app/osekkai/osekkai.module.css`
    - `frontend/app/api/osekkai/opportunities/route.ts`
    - `frontend/lib/osekkai/api.ts`
  - 作業:
    - Google Maps JavaScript APIで、利用者の現在地とlive Eventを地図表示
    - 現在地は利用者が`現在地から探す`を押した時だけBrowser Geolocationから取得し、Profileやlogへ保存しない
    - 位置情報を拒否した場合は駅名・地域名による手動検索へ切り替える
    - 地図へ出すのは、Connection Evidenceがあり、孤独解消につながる会話・共同活動・再参加導線のあるEventだけに限定
    - `今日 / 今週末 / 30分以内 / ひとり参加可 / 継続あり / Networking / みんなで食事`で絞り込めるようにする
    - Marker選択時に、開催時刻、Google Routes実移動時間、料金、募集状態、交流根拠、Source、最終更新時刻を表示
    - Policyが選んだ1件には`おばさんのおすすめ`を表示し、他のEventと区別
    - 地図を操作できない場合にも同じ候補を一覧で閲覧できるfallbackを用意
  - 完了条件:
    - 利用者が現在地または指定地域から、参加可能な交流Eventを自分で地図探索できる
    - 図書館、公園、大型展示など、交流根拠のない場所・Eventは表示されない
    - expired、canceled、sold out、stale Eventは地図に残らない
    - Markerの移動時間とOne Push Cardの移動時間が同じRoutes responseに基づく
    - 正確な現在地を永続保存せず、位置情報拒否時も地域検索で利用できる
    - 390x844で地図、Event詳細、戻る操作、主要CTAが使用できる
  - 検証:
    - Geolocation許可・拒否・timeoutとMaps API key未設定のcomponent test
    - Connection Level、期間、移動時間、継続性filterのintegration test
    - expired / canceled / sold out / stale EventがMarkerにならないことを確認
    - Google Routes結果とMarker詳細・One Push Card表示の一致を確認
    - 390x844と1440x900のbrowser smoke test

- [ ] **TASK-150: 正の1件PUSHだけで完走するLive Demo画面を実装する**
  - 依存: TASK-140、TASK-145
  - 対象:
    - `frontend/app/osekkai/demo/page.tsx`
    - `frontend/lib/osekkai/api.ts`
    - 必要な`frontend/app/osekkai/_components/*`
  - 作業:
    - 主経路をSource更新 → Connection判定 → Calendar → Routes → 1件PUSHへ変更
    - P0のno-PUSH機能と安全ロジックは残すが、Judge向け主シナリオから外す
    - CTAを`行ってみる / これは違う / 今回は無理 / 次回も知らせて`にする
    - おばさんの文面を実Eventの根拠項目だけから生成する
  - 完了条件:
    - 実在する現在Eventで60秒以内に1件PUSHまで到達する
    - 図書館・公園・古いEventが主候補にならない
    - 根拠にない`一人参加OK`、`次回あり`、定員等を表示しない
  - 検証:
    - live Provider fixtureによるcomponent/integration test
    - 実Credentialを使ったbrowser smoke test

#### Gate 7 — 完成検証

- [ ] **TASK-160: Provider・Connection・Calendar・Routes統合テストを作成する**
  - 依存: TASK-120〜TASK-150
  - 対象:
    - `agents-OpenClaw/tests/test_osekkai_live_demo.py`
    - frontendのLive Demo component/API test
  - 作業:
    - 大型展示、営業交流会、月例趣味会、共食、継続ボランティアを同時入力
    - expired、canceled、sold out、stale、duplicate、API timeoutを混ぜる
    - CalendarとRoutesで最終候補が1件へ変わることを検証
  - 完了条件:
    - 月例または継続Eventだけが最終候補になる
    - 0件時に架空候補を生成しない
    - 同じ入力・時刻・Provider fixtureで同じ結果になる
  - 検証:
    - Python全test
    - frontend全test、typecheck、lint、build

- [ ] **TASK-170: 外部障害・Freshness・Privacy検証を実行する**
  - 依存: TASK-160
  - 対象: Live Provider、OAuth、Routes、API route、scheduler
  - 作業:
    - Lu.ma停止、Doorkeeper 429、公共Site parser破損、CKAN timeoutを再現
    - Google token失効、Routes quota超過、PUSH前取消を再現
    - token、Calendar詳細、Provider秘密値がlog/UIへ出ないことを確認
  - 完了条件:
    - 1Source障害で全体が停止しない
    - staleまたは再検証不能EventをPUSHしない
    - UIがlive成功を装わず、取得時刻と障害を表示する
  - 検証:
    - failure injection test
    - log secret scan
    - Profile削除 / disconnect後のcredential削除test

- [ ] **TASK-180: README・env・運用手順を更新する**
  - 依存: TASK-170
  - 対象:
    - `README.md`
    - `frontend/README.md`
    - `frontend/.env.example`
    - `agents-OpenClaw/.env.example`
    - `IMPLEMENTATION_REPORT.md`
  - 作業:
    - 必須・optional ProviderとCredentialを記載
    - Live sync、scheduler、Source status、Calendar接続、Routes接続の起動手順を記載
    - 利用規約、Attribution、stale動作、既知の制約を記載
    - 動画制作は実装範囲外と明記
  - 完了条件:
    - 新しい環境で秘密値を除き手順を再現できる
    - 実装済み、Credential待ち、optional、未実装を区別している
  - 検証:
    - README手順をfresh shellから実行
    - `.env.example`に実秘密値がないことを確認

- [ ] **TASK-LIVE-DEMO-GATE: Live Demoを最終承認する**
  - 依存: TASK-000〜TASK-180
  - 完了条件:
    - Tokyo CKAN、Lu.maまたは許可されたiCal、Doorkeeper、公共施設Siteのうち3系統以上が同期される
    - Eventが現在募集中で、Connection Level 2以上、原則Level 3以上である
    - CalendarとRoutesが実接続で判断を変える
    - 最新EventをPUSH直前に再検証する
    - 1件だけのPUSH、根拠、Source、更新時刻、CTAが表示される
    - 既存P0と全自動テストに退行がない
    - Demo動画の完成状態には依存しない

### 13.3 Optional Provider Task

次はLive Demo Gateを止めません。必須経路の完成後に実行します。

- [ ] **TASK-OPT-001: connpass Providerを追加する**
  - 開始条件: 適切な区分でAPI Keyが発行されている
  - 対象: `agents-OpenClaw/scripts/osekkai_connpass.py`、対応test
  - 完了条件: API利用条件、rate limit、Group、Event、参加状況を公式API経由で扱う

- [ ] **TASK-OPT-002: Peatix Organizer Intakeを追加する**
  - 開始条件: 全面スクレイピングを行わない
  - 対象: 主催者提出Schema、提出API、Curated Calendar承認処理
  - 完了条件: Peatix URLと主催者確認項目から、許諾済みEventを取り込める

- [ ] **TASK-OPT-003: 共食Providerを追加する**
  - 開始条件: Timeleft、KitchHike等とのDeep Linkまたはデータ利用許諾が確認できる
  - 完了条件: 食事制約、価格、参加人数、会話設計、安全情報を根拠付きで扱う

### 13.4 Task完了記録Template

各Taskを完了したら、Task直下に次を追記します。

```text
完了日:
変更ファイル:
実行した検証:
結果:
残課題 / Credential待ち:
```

### 13.5 Provider別・機能別の詳細要件

以下は上の実行Taskから参照する機能要件です。これ自体を別の重複Taskとして数えません。

#### Sourceと権限

#### SOURCE-001 Source Registry

- Provider名
- 取得方式: API / iCal / Webhook / JSON-LD / HTML / Organizer submission
- 利用規約・ライセンス
- robots確認
- 認証方式
- 更新間隔
- 保存可能範囲
- 必須Attribution

完了条件: Providerごとに「取得できる」と「使ってよい」を分けて記録する。

#### SOURCE-002 API Key

- Lu.ma Plus / APIまたはTokyo City iCal URLを確定
- Doorkeeper Public API token取得
- connpass API利用申請
- Google Calendar / Routes credentials確認

完了条件: 必須Demo SourceのCredentialが揃い、秘密値がGitへ入らない。

### 13.6 Live Event Mesh詳細要件

#### DATA-001 Tokyo CKAN Discovery

- `package_search`でイベント、社会教育施設、公民館、イベント会場を検索
- `package_show`で最新Resource URLを解決
- dataset modifiedとresource modifiedを分離
- CSV内の将来日付有無を検査

完了条件: 新しい自治体Datasetをコード変更なしでSource候補へ追加できる。

#### DATA-002 Lu.ma Provider

- Tokyo City / Calendar iCal parser
- Curated Calendar API
- Webhook signature検証
- created / updated / canceled / calendar event addedを処理

完了条件: Lu.ma上の変更がOpenClawへ反映される。

#### DATA-003 Doorkeeper Provider

- `prefecture=tokyo`
- `since` / `until`
- `sort=updated_at`
- EventとGroupを保存
- participants / ticket limit / waitlistを保存

完了条件: 東京の将来イベントと継続Groupを公式APIから取得できる。

#### DATA-004 Public Facility Provider

- 東京都Open Dataの施設をSource seedにする
- JSON-LD / RSS / iCalを優先
- HTML Adapterは公式ページごとに実装
- 連続講座の全日程、募集状態、締切を取得

完了条件: 公民館・文化センターの連続講座を少なくとも1Providerで同期できる。

#### DATA-005 Peatix / Meal Provider Intake

- 主催者向け提出Form
- Peatix・Timeleft・KitchHike等のSource URL
- 主催者確認項目
- Curated Calendar承認
- 公式連携が得られたProviderだけ自動同期

完了条件: 無断クロールをせず、外部イベントを最新情報付きで扱う経路がある。

#### DATA-006 Common Schema / Dedup

- Event / Series / Community / Venueを分離
- URL canonicalization
- provider ID + start + venueの複合Dedup
- 外部イベントがLu.ma Calendarにもある場合の重複統合

完了条件: 同じイベントが複数Sourceから来ても1件として扱える。

#### DATA-007 Freshness Worker

- scheduler
- incremental sync
- retry / backoff
- ETag / Last-Modified / hash
- stale TTL
- cancellation / sold-out revalidation
- Provider health status

完了条件: OpenClawを停止せず、更新失敗Sourceだけを隔離できる。

### 13.7 Connection Intelligence詳細要件

#### BRAIN-001 Evidence Extractor

- recurrence
- solo / beginner friendly
- structured conversation
- shared meal
- group activity
- role
- next event
- solicitation risk

完了条件: 各判定に根拠文・URL・confidenceがある。

#### BRAIN-002 Connection Level

- Level 0〜4分類
- Level 0〜1のHard Reject
- Networkingという単語だけで昇格しない
- unknownを保ったまま判定する

完了条件: 受動的大型イベントが「孤独解消イベント」と誤判定されない。

#### BRAIN-003 Personal Shift

- 本人の強い好み
- 隣接ジャンル
- 過去に受け入れた / 断った理由
- 初参加負荷
- 価格・時間・距離

完了条件: 好み完全一致だけでなく、「少しずらしているが会話の入口はある」候補を説明できる。

#### LIVE-001 Google Calendar FreeBusy

- OAuth read-only
- FreeBusyだけを使用
- 予定タイトル・参加者・内容を保存しない

完了条件: 実カレンダーの空きが参加可能判定へ使われる。

#### LIVE-002 Google Routes

- 徒歩 / 公共交通
- 往復 + 30分滞在 + buffer
- Candidate座標の解決

完了条件: UI表示時間と選定ロジックが同じ実レスポンスを使う。

### 13.8 Judge UI詳細要件

#### UI-001 One Push Card

- 実イベント
- 距離
- 一人参加根拠
- 継続根拠
- 定員・料金・募集状態
- 最終更新
- Source

完了条件: 10秒で「なぜ孤独に効く可能性があるのか」を説明できる。

#### UI-002 OpenClaw Live Strip

- Provider health
- last sync
- updated event count
- rejected stale count

完了条件: 固定fixtureではなく常時更新Agentであることが一目で分かる。

#### UI-003 Action / Feedback

- 行ってみる
- これは違う
- 今回は無理
- 次回も知らせて

完了条件: 理由が次回の距離・ジャンル・強度へ反映される。

### 13.9 検証詳細要件

#### VERIFY-001 Data Quality

- expired / canceled / sold-out
- missing time / place / organizer
- duplicate event
- stale source
- time zone
- malformed iCal
- API rate limit
- source terms violation

#### VERIFY-002 Connection Quality

- 大型展示会をReject
- 一方通行講演をReject
- 営業NetworkingをRejectまたはRisk表示
- 月例少人数趣味会をLevel 3
- 継続ボランティアをLevel 4
- 根拠なし`一人参加OK`を生成しない

#### VERIFY-003 Rehearsal

- Demo候補3件を確保
- Calendar実接続
- Routes実接続
- Source再検証
- 60秒通し
- 2分Pitch

---

## 14. 東京都へのデータ還元

個人の会話や孤独度は行政へ送りません。匿名・集計した次の情報だけを、将来の`Tokyo Connection Access Gap`へ使います。

- 地域別のLevel 2〜4イベント数
- 夜間・休日別の参加可能イベント数
- 徒歩 / 公共交通30分以内の継続イベント数
- 一人参加・初心者対応イベント数
- 満席や申込終了で到達できなかった件数
- 低価格・無料の継続イベント数
- 年齢人口あたりのConnection Opportunity

これにより東京都は、「施設があるか」だけでなく、**都民が継続的な関係へ入れる機会が足りない地域・時間帯**を把握できます。

---

## 15. 審査基準への対応

| 審査観点 | 証拠 |
|---|---|
| データ活用 | 東京都Open Dataで社会施設を発見し、Live Providerの現在イベントと結合。Connection Levelが推薦を変える |
| アイデア力 | イベント検索ではなく、「次も会える可能性」を先回りして届ける |
| 技術力 | OpenClaw scheduler、API / iCal / Webhook / HTML統合、鮮度再検証、Series判定、Calendar、Routes |
| ソーシャルインパクト | 外出回数ではなく、再参加・顔見知り・役割へ進むことを成果にする |
| サービスデザイン | 1件だけ、30分だけ、断れる、好みを少しずらす、おばさんの人格で背中を押す |

---

## 16. 現在地

### できている

- オフラインP0の体験骨格
- Profile、会話、Policy、PUSH / HOLDの基本構造
- Open Data provenanceの基本構造
- synthetic Calendar / RoutesのDemo

### 未完成

- 東京都全域のSource Discovery
- Live Event Mesh
- Lu.ma / Doorkeeper / 公共施設Provider
- Event / Series / Community Schema
- Connection Level
- Google Calendar実接続
- Google Routes実接続
- 1件の現在イベントを使うJudge UI

Demo動画・PV制作はユーザー側で進行中のため、未完成実装には数えません。こちらの責任範囲は、動画と矛盾しない実イベント・根拠・台詞をLive UIへ出すことです。

現在は30点という評価で妥当です。体験の形はありますが、「東京の最新イベントをOpenClawが見続け、継続する関係に変える」という核心が未実装です。

---

## 17. 公式参照先

- [都知事杯オープンデータ・ハッカソン 2026 募集要項](https://odhackathon.metro.tokyo.lg.jp/recruitment/)
- [東京都オープンデータカタログ](https://catalog.data.metro.tokyo.lg.jp/)
- [東京都 若者の社会的孤立に関する調査概要](https://www.fukushi.metro.tokyo.lg.jp/documents/d/fukushi/dai2kai-siryou5-2)
- [内閣府 孤独・孤立の実態把握に関する全国調査](https://www.cao.go.jp/kodoku_koritsu/torikumi/zenkokuchousa/r6.html)
- [Lu.ma API](https://help.luma.com/p/luma-api)
- [Lu.ma Webhooks](https://help.luma.com/p/webhooks)
- [Lu.ma iCal Syncing](https://help.luma.com/p/ical-syncing)
- [Lu.ma 外部イベントのCalendar登録](https://help.luma.com/p/submitting-events-to-calendars)
- [Doorkeeper公式API](https://www.doorkeeper.jp/developer/api?locale=ja)
- [connpass API利用案内](https://help.connpass.com/api/)
- [Peatix 定期開催イベント](https://help-organizer.peatix.com/ja-JP/support/solutions/articles/44002645658)
- [江東区文化コミュニティ財団 講座情報](https://www.kcf.or.jp/koto/koza/)
- [Timeleft](https://timeleft.com/dinners-with-strangers/)
- [KitchHike](https://kitchhike.com/)

---

## 18. 最終判断

今回のDemoで伝えるべきなのは、「近くに図書館があります」ではありません。

> **今日、あなたの好きなことを入口に、次も会える人がいる場が東京にある。OpenClawは、それが生まれた瞬間を見逃さない。**

PVは感情を動かし、Live Demoはそれが作り話ではなく、東京都のOpen Dataと最新Provider Dataから今この瞬間に選ばれたことを証明します。
