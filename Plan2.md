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

> **OpenClawが東京都全域の最新イベントを更新し続け、その中から、共通の趣味・少人数の会話・次回参加など「関係が続く可能性」のある複数候補を優先順位付きで見つける。**

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

> おせっかいおばさんは、本人の予定・移動可能範囲・興味を理解し、東京で今参加できる活動の中から、**次の関係につながる可能性が高い複数候補**を優先順位と理由付きで先回りして届けるOpenClaw Agentである。

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
  好み、少しの意外性、過去反応、Calendar、Routesで少数の複数候補へ絞り、順位を付ける
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
- 主催者、場所、Source URLが不明
- 営業・勧誘リスクが高い
- 本人の安全条件、予算、時間に合わない

料金がSourceで確認できない場合は無料と推定せず`料金未確認`として残します。予算超過が確認できた場合だけHard Filterします。

### 8.2 Connection Score

優先順位は次です。

1. 次回も同じ人・主催者に会える可能性
2. 会話や共同作業がイベント設計に含まれる
3. 一人・初参加の心理的負担が低い
4. 共通の趣味が会話の入口になる
5. 本人が過去に受け入れた参加形式・対人負荷に合う
6. CalendarとRoutesに無理なく収まる

`Networking`という単語だけでは加点しません。

### 8.3 継続性の判定

次のいずれかが必要です。

- 同じ`series_id`で将来回が存在する
- 同じCommunityに過去・将来イベントがある
- 定期開催の公開記載がある
- 主催者が次回開催またはCommunity導線を確認している

単発イベントでも、明確なCommunity参加導線があればLevel 2候補にできます。

### 8.4 Contextual Okan Conversation

`話す`は好み登録だけの画面ではなく、状況に応じておばさん側から始まり、断り方と参加後の反応まで扱う会話面にします。

内部状態は次を持ちます。

- `getting_to_know`: 好みがまだ少なく、一度に1つだけ聞く
- `calendar_sparse`: 対象時間帯のFreeBusyが薄く、参加可能な複数候補がある
- `nudge_sent`: 根拠付き候補を会話内へ提示済み
- `resistance`: 行きたくない理由を1つだけ確認し、別候補へ一度だけ調整する
- `accepted`: 行く候補が選ばれ、Event終了後の確認時刻を持つ
- `check_in_due`: 「昨日どうやった？」と一問だけ聞く
- `cooldown`: 断った後や通知上限到達後に追わない
- `safety_handoff`: 緊急性のある入力をEvent推薦から切り離す

Demoの会話開始Triggerは、追加設定や自宅判定を要求せず、次をすべて満たす場合に限定します。

1. PUSH同意とCalendar接続がある
2. 次の7日間の設定済み活動時間帯で、90分以上のFree Windowが2つ以上ある、またはBusy占有率が20%未満
3. Free WindowとGoogle Routesに収まるConnection Level 2以上の実Eventが複数ある
4. Quiet Hours、週次上限、Cooldown、安全条件に抵触しない
5. PUSH直前のSource再検証に成功する

Calendarから取得するのはFreeBusyだけです。予定名、説明、場所、参加者は取得せず、空きが多いことを孤独や「家にいる」証拠として扱いません。文面は「あんた、今週末けっこう空いてるやろ」のように、確認できた空き時間だけを根拠にします。

Mapでは既に、本人が`現在地から探す`を押した時だけBrowser Geolocationを取得しています。座標はFrontendの一時状態に置き、選択EventのRoutes計算にだけ渡し、Profileやlogへ保存しません。今回のCalendar Triggerには位置情報を使いません。会話中に現在地からの移動時間が必要な場合だけ、本人の明示操作で同じ一時取得を再利用します。

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

#### 0〜8秒: Calendarの疎な期間をTriggerにする

Demo用Google Calendarの次の7日間をFreeBusyだけで確認します。対象時間帯のBusy占有率と90分以上のFree Window数を画面へ短く表示し、予定名、説明、場所、参加者は表示しません。同時にOpenClawが東京のLive Sourceを更新し、PUSH直前の募集状態まで再検証します。

#### 8〜23秒: おばさん側から会話を始める

過去会話の好み、Calendarの空き、Google Routes、Connection Evidenceを使い、会話内へ優先順位付きの複数候補を出します。

> 「あんた、今週末けっこう空いてるやろ。前に料理好き言うてたな。予定に収まるやつ、3つ見つけたで。」

各カードには、実Event名、日時、Routes実測、料金または`料金未確認`、募集状態、交流・継続根拠、Sourceと更新時刻を表示します。`ひとり参加OK`、`途中退出OK`、`次回あり`等はSource根拠がある場合だけ言います。

#### 23〜36秒: 行きたくない理由を一つだけ聞く

> 利用者「イベントとか行きたくない」

> おばさん「そら最初はめんどいわ。人が多いのと、遠いのと、どっちが嫌なん？」

Quick Replyは候補と状況に応じて`人が多い / 遠い / 今日は気が乗らない`等へ変えます。通常の自由入力も残します。ここで回答をSurveyのように並べすぎず、一問ずつ進めます。

#### 36〜46秒: 一度だけ候補を調整して後押しする

たとえば`人が多い`なら、大人数候補を外し、共同作業や少人数会話の根拠がある別候補へ順位を変えます。

> 「ほな大人数のはやめとこ。少人数で一緒に作る方ならどう？ 絶対楽しいとは言わんけど、あんたにはこっちの方が合いそうやで。」

再度断られたらCooldownへ入り、追いかけません。受け入れた場合は、選択Eventと終了時刻をEpisodeへ記録します。

#### 46〜60秒: イベント後の一言で次の精度を上げる

Demoでは時間を進め、Event終了後の`check_in_due`を表示します。

> 「昨日の料理のやつ、どうやった？ また行ってもええ感じやった？」

`また行きたい / 人の感じはよかった / ちょっと遠かった / 人が多すぎた / 行けなかった`の一つと自由入力から、カテゴリだけでなく参加形式、対人負荷、移動許容、時間帯、押し方を更新します。更新後、次の複数候補の順位が変わるところまで見せます。

このDemoの主役は検索結果ではありません。**Calendarの余白を見つけ、断られ方を理解し、参加後の一言まで覚えることで、おかんの距離感が育つこと**を見せます。

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
| 38〜78秒 | Live Conversation | 疎なCalendarをTriggerに、おばさんが複数候補を持って話しかけ、断った理由で一度だけ調整する |
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
- [ ] 本人の好みと隣接興味から、選びやすい少数の複数候補を順位と理由付きで選べる
- [ ] Calendarの疎な期間と実候補が揃った時だけ、おばさん側から会話を開始できる
- [ ] 行きたくない理由によって候補を一度だけ調整し、再拒否時はCooldownへ入る
- [ ] Event後の一問Check-inが次の候補順位へ反映される
- [ ] Live / AI推定 / Organizer Verifiedを画面で区別できる
- [ ] Sourceの最終更新時刻を表示できる
- [ ] 実在する現在イベントで60秒Demoを完走できる
- [ ] Live Demoのイベント種別・表示項目・台詞が、ユーザー制作中PVの世界観と矛盾しない

### Demo安定化

- [ ] 表示予定の複数候補と追加Backup候補をDemo前日に確保
- [ ] Demo開始10分前に表示候補とBackup候補をすべて再検証
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

- [x] **TASK-000: 現在のP0 baselineを再確認する**
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
  - 完了記録（2026-08-23）:
    - Python: 69 tests passed、16 schemas / 8 instances validated
    - Frontend: 78 tests passed、typecheck / lint / build成功
    - 退避済みTomo-san routeを参照する古い`.next/dev`型を`tsconfig.json`の検証対象から除外し、Active routeだけでbaselineを確立

#### Gate 1 — Live Event共通契約

- [x] **TASK-010: Event / Series / Community / Source契約を追加する**
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
    - Live decisionに、順位、推薦理由、除外理由を持つ`rankedOpportunities`配列を追加し、候補数を1件へ固定しない
  - 完了条件:
    - TypeScriptとPythonが同じ正常fixtureを受理する
    - 期限、Source、Connection根拠のないLive候補を拒否する
    - 複数候補の順序と各候補のEvidenceをContractで検証できる
    - P0 fixtureは既存schemaVersionのまま読み取れるか、明示Migrationがある
  - 検証:
    - `npm.cmd run generate:contracts; npm.cmd run typecheck`
    - `python scripts/osekkai_contracts.py --validate-all`
  - 完了記録（2026-08-23）:
    - 21 Schemaを正本化し、Event / Series / Community / Source Registry / Connection Evidenceと、複数順位付き候補を追加
    - `dataMode=live`だけに鮮度、募集状態、Source分類、交流根拠を必須化し、既存P0 fixtureとの互換を維持
    - 同一Live fixtureをPythonと生成TypeScript validatorの双方で検証。順位の連番・重複IDも境界で拒否
    - Python 72 tests、contract 21 schemas / 19 instances、frontend 80 tests、typecheck / lint成功
    - 残課題: 実Providerが生成する値はTASK-030以降、実接続はCredential設定後のLive smokeで確認

- [x] **TASK-020: Source Registryと利用条件を実装する**
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
  - 完了記録（2026-08-23）:
    - 必須4 Sourceとoptional / organizer intake / deep-link 4 Sourceの取得方式、規約、Attribution、更新間隔、stale基準、Credential名を一元化
    - `enabled`、利用許可、Credential準備状態を分離し、同期対象をfail-closedで選択
    - 秘密値は保存せず環境変数名だけを登録。stale境界、重複ID、未知Source、未確定Sourceの拒否を検証
    - `test_osekkai_source_registry.py`: 5 tests成功、contract validation: 21 schemas / 19 instances成功
    - 残課題: Lu.ma / DoorkeeperはCredential投入まで`credential_missing`。Tokyo CKAN / 公共施設はCredential不要でready

#### Gate 2 — OpenClaw Live Event Mesh

- [x] **TASK-030: Tokyo CKAN Discoveryを実装する**
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
  - 完了記録（2026-08-23）:
    - `package_search`→`package_show`→最新CSV/JSON Resource解決を区固定なしで実装
    - Resource本体の将来日付、行数、SHA-256、取得時刻を検査し、カタログだけ新しい期限切れDatasetを`no_future_event`化
    - 1 Dataset取得失敗でも他Datasetを継続し、エラーをSource単位で返す
    - fixture 4 tests成功。公式CKAN live smokeで3候補を発見し、取得できた19行に将来Eventがないことを正しくinactive判定、別Resourceの取得失敗も分離
    - 残課題: active Datasetは検索時点で0件のため、推薦供給はLu.ma / Doorkeeper / 公共施設Providerを使用

- [x] **TASK-040: Lu.ma Providerを実装する**
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
  - 完了記録（2026-08-23）:
    - 利用者または主催者が許可した`LUMA_ICAL_URL`だけを取得する境界を実装し、全Lu.ma取得とは表示しない
    - VEVENT、RRULE、Community、日時変更、SEQUENCE、取消、満席・受付状態、容量、料金を共通Schemaへ正規化
    - fixture 4 tests成功。Event / Series / Community Schema検証成功
    - 初回記録時は`LUMA_ICAL_URL`未設定だったが、同日中に許可されたiCal URLを設定し、Live 50 Eventの取得を確認。API/WebhookはPlus Credentialがないため未採用（iCal経路で必須機能は実装済み）

- [x] **TASK-050: Doorkeeper Providerを実装する**
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
  - 完了記録（2026-08-23）:
    - 公式APIの東京・期間・更新順Query、Bearer認証、最大50 page pagination、429 bounded backoffを実装
    - Event / Group / Series、定員、参加人数、waitlist、料金、更新時刻、継続する将来回を正規化
    - fixture 5 tests成功。Event / Series / Community Schema検証成功
    - 初回記録時は`DOORKEEPER_API_TOKEN`未設定だったが、同日中にtokenを設定し、Live 25 Eventの取得を確認。他Sourceとの障害分離は維持

- [x] **TASK-060: 公共文化施設Providerを実装する**
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
  - 完了記録（2026-08-23）:
    - Provider共通の地域Filterから分離した、江東区文化コミュニティ財団公式domain adapterを実装
    - 一覧→公式詳細から募集状態、全開催日、時間、会場、定員、対象、受講料・教材費、申込期限を取得し、各回EventとSeriesへ展開
    - HTML fixture 4 tests成功。公式Site live smokeで5講座から現在Event 16件、Series 5件、Community 5件を取得、error 0
    - 残課題: 会場住所・座標は公式詳細にない場合があるため、TASK-070/110で会場解決とRoutes取得を行う

- [x] **TASK-070: Event Normalizer・Dedup・Freshness Gateを実装する**
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
  - 完了記録（2026-08-23）:
    - canonical URL、Provider ID、題名・開始時刻・Venueを用いる横断Dedupと、統合後の全Source保持を実装
    - 全EventはMap用に保持し、PUSH用だけended / canceled / sold out / 締切済み / stale / 出典・場所欠損を除外
    - Connection EvidenceとGoogle Routes実測が揃うまでLive Opportunityを生成しない境界を追加
    - Event normalizer 4 tests、Opportunity sync 3 tests、21 Schema validation成功。2019 fixtureのlive混入拒否を確認
    - 残課題: Evidence生成はTASK-080、実Routes付与はTASK-110、永続Cache更新はTASK-120

#### Gate 3 — Connection Intelligence

- [x] **TASK-080: Connection Evidence Extractorを実装する**
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
  - 完了記録（2026-08-23）:
    - recurrence / future occurrence / solo / beginner / structured conversation / shared meal / group work / role / solicitation riskを根拠文・URL・field付きで抽出
    - 公開記載・Series事実・Organizer確認を分類し、AI推測は使用せず、非記載項目を`unknown`に固定
    - `Networking`単語だけ、単発講演、大型展示をLevel 0、営業・投資勧誘をhigh riskとして検証
    - 月例趣味会、共食、継続Volunteerを含む5 tests成功。生成結果はConnection Evidence Schemaで毎回検証
    - 残課題: Profile適合・隣接興味と複数順位付けはTASK-090で統合

- [x] **TASK-090: Connection LevelとPersonal FitをPolicyへ統合する**
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
    - 条件を満たす候補は、優先順位付きの複数候補として返る。上限はPolicy設定で調整でき、1件に固定しない
    - 選定理由と除外理由を同じ入力から再現できる
  - 検証:
    - `python -m unittest discover -s tests -p "test_osekkai_*policy*.py" -v`
    - `python -m unittest discover -s tests -p "test_osekkai_connection.py" -v`
  - 完了記録（2026-08-23）:
    - LiveのConnection Level 0〜1と募集不可をHard Rejectし、継続性、本人好み、隣接興味、Calendar/Routes実現性を分離Score化
    - `maxRankedOpportunities=3`のPolicy設定で複数候補を順位付けし、各候補にSource分類付き推薦理由を保存
    - 既存好み一致と「少しずらした隣接ジャンル」を別根拠にし、価格、対人負荷、avoided category、拒否streakを反映
    - live/P0 Policy 14 tests、Connection 5 tests、contract validation、TypeScript生成・typecheck成功。P0の単一候補挙動は互換維持
    - 後続状況: TASK-100/110とLive orchestrationはコード実装済み。実Google Credentialによるsmokeだけを外部設定待ちとして継続

#### Gate 4 — 本人の現実条件

- [x] **TASK-100: Google OAuthとFreeBusy実接続を実装する**
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
  - 実装記録（2026-08-23）:
    - `calendar.freebusy`だけを要求するOAuth Web flow、state/PKCE、匿名session紐付け、10分TTL、one-time callbackを実装
    - token/stateをFernet暗号化し、refresh、disconnect、Profile全削除でのcredential削除を実装・自動テスト化
    - Calendar responseにtitle、description、location、attendeesが含まれる場合はfail closed。FreeBusyのbusy区間からprivacy-minimalな空き時間だけを返す
    - Next.jsのconnect/callback/disconnect、設定画面、Live Demoの`CALENDAR_NOT_CONNECTED`導線までBrowser確認済み
    - Billing連携、OAuth Client ID/Secret、callback、暗号化keyを設定し、Demo Google accountの認可と実FreeBusy取得を確認
    - 空予定の30日Live horizonを有効なFree Windowとして扱えるようvalidatorを修正し、自動testを追加

- [x] **TASK-110: Google Routes実接続を実装する**
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
  - 実装記録（2026-08-23）:
    - Routes `computeRoutes`でWALK/TRANSITを比較し、最短の実移動時間、距離、取得時刻、confidenceを保存するadapterを実装
    - 座標がないEventはGeocodingし、往復、30分滞在、bufferがCalendar Free Windowへ収まるか同じresponseから判定
    - Credential不足、認証失敗、quota、timeout、zero result、malformed responseを公開用error codeへ分類。Live modeで合成移動時間へfallbackしない
    - Event選択時だけ現在地を一時利用する`event-route` Contract/CLI/APIを追加し、UIとPolicyが同じRoutes resultを使う
    - Fixtureによる徒歩・公共交通・失敗4 tests成功。Billingと制限付きAPI keyを設定し、実Google Routes responseの取得を確認

#### Gate 5 — SchedulerとAPI

- [x] **TASK-120: OpenClaw Live Sync Schedulerを実装する**
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
  - 完了記録（2026-08-23）:
    - `sources-sync`、`sources-status`、`events`、`opportunities --live`のoperator CLIとNext用envelope commandを実装
    - Source interval、incremental cache、Source lock、最大5回のbounded retry/backoff、1 Source障害時の継続、health/count/freshnessを実装
    - PUSH直前にshortlistのProviderだけをforce refreshし、中止・満席・期限切れ・再検証不能をfail closedにする経路を実装
    - 実同期でTokyo CKAN 5 dataset、KCF 169開催回を取得。Lu.ma/DoorkeeperはCredential不足を他Sourceと分離して表示
    - Scheduler unit/failure injection、CKAN timeout隔離、PUSH前取消test成功

- [x] **TASK-130: Live APIとNext.js bridgeを接続する**
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
    - BrowserからSource状態、現在候補、順位付きRecommendation Setを取得できる
    - Python SSOT以外にProvider responseを二重保存しない
    - demo/liveを切り替えても同じContractを使う
  - 検証:
    - frontend server adapter unit test
    - mutationのCSRF / Origin / Content-Type negative test
    - malformed Python response rejection test
  - 完了記録（2026-08-23）:
    - Source status/sync、全Event Mesh、Live opportunities/decision、Calendar、Event Routeをallowlist済みPython CLIへ接続
    - Browser入力の候補・移動値をDecisionへ直接渡さず、server-owned cache/Contractから取得
    - 3 MiB上限内で全Event Meshを検証し、Windows pyenv実行解決、120秒timeout、UTF-8、必要Credentialだけのchild env allowlistを実装
    - 非0 exitでもpublic-safe CLI envelopeを保持し、`CALENDAR_NOT_CONNECTED`等を汎用502へ潰さないよう修正
    - API/validator/security unit testとBrowserからSource/Events/Opportunities 200応答を確認

#### Gate 6 — Judge用Live UI

- [x] **TASK-140: Live Source StripとRecommendation Shortlistを実装する**
  - 依存: TASK-130
  - 対象:
    - `frontend/app/osekkai/_components/live-source-strip.tsx`
    - `frontend/app/osekkai/_components/recommendation-shortlist.tsx`
    - `frontend/app/osekkai/_components/connection-evidence.tsx`
    - `frontend/app/osekkai/osekkai.module.css`
  - 作業:
    - Provider、last sync、healthを短く表示
    - 優先順位付きの複数Eventについて、Routes時間、Calendar空き、定員、料金、募集状態を表示
    - 各候補に一人参加・継続性・会話設計・本人適合の根拠を表示
    - Raw / Live / AI Derived / Organizer Verifiedをラベル分離
  - 完了条件:
    - Judgeが10秒で「最新データ」「なぜ交流につながるか」「なぜ本人に合うか」を理解できる
    - Source URLと最終更新時刻を開ける
    - モバイル幅で複数候補を比較でき、各候補の主要情報とCTAへ到達できる
  - 検証:
    - component test
    - 390x844と1440x900のbrowser確認
    - keyboard、focus、aria-live確認
  - 完了記録（2026-08-23）:
    - Live Source、health、last sync、取得/推薦件数、複数候補の順位、Calendar/Routes、料金、募集状態、Connection/本人適合根拠を実装
    - Raw Open Data / Live Provider / AI Derived / Organizer VerifiedをContract classificationのまま表示し、Source URLへ到達可能
    - CTAを`行ってみる / これは違う / 今回は無理 / 次回も知らせて`で実装し、候補件数を1件へ固定しない
    - Component test、1440x900/390x844のBrowser確認、横overflowなし、主要button/linkのkeyboard到達可能を確認

- [x] **TASK-145: 現在地周辺の全Event Mapを実装する**
  - 依存: TASK-110、TASK-130
  - 対象:
    - `frontend/app/osekkai/map/page.tsx`
    - `frontend/app/osekkai/_components/event-map.tsx`
    - `frontend/app/osekkai/_components/map-event-sheet.tsx`
    - `frontend/app/osekkai/osekkai.module.css`
    - `frontend/app/api/osekkai/opportunities/route.ts`
    - `frontend/lib/osekkai/api.ts`
  - 作業:
    - Google Maps JavaScript APIで、利用者の現在地と、選択期間・地域で取得した全live Eventを地図表示
    - 現在地は利用者が`現在地から探す`を押した時だけBrowser Geolocationから取得し、Profileやlogへ保存しない
    - 位置情報を拒否した場合は駅名・地域名による手動検索へ切り替える
    - PUSHの推薦条件とMapの掲載条件を分離し、Connection LevelやEvidenceの有無によってMarkerを除外しない
    - 既定filterを`すべて`とし、`今日 / 今週末 / 30分以内 / ひとり参加可 / 継続あり / Networking / みんなで食事 / おすすめのみ`で任意に絞り込めるようにする
    - 推薦、推薦対象外、交流根拠未確認、sold out、canceled、expired、stale、情報欠損をMarkerの色・icon・labelで区別する
    - 同一Eventを複数Sourceから取得した場合は1つのMarkerへ統合し、詳細に全Sourceを表示する
    - 大量のMarkerをviewport loadingとclusteringで扱い、全EventにRoutesを一括実行しない
    - Marker選択時にだけGoogle Routes実移動時間を取得し、開催時刻、料金、募集状態、Connection Level、交流根拠、Source、最終更新時刻を表示
    - Policyが選んだ複数候補には順位と`おばさんのおすすめ理由`を表示し、他のEventと区別
    - 地図を操作できない場合にも同じ全Eventを一覧で閲覧できるfallbackを用意
  - 完了条件:
    - 利用者が現在地または指定地域から、取得できた全Eventを自分で地図探索できる
    - Connection Level 0〜4、根拠未確認、図書館等で開催されるEvent、大型展示もMapには表示され、推薦可否と理由を確認できる
    - sold out、canceled、expired、stale、情報欠損Eventも隠れず、状態表示とCTA無効化が行われる
    - 同一Eventの重複Markerだけが統合され、カテゴリや推薦対象外を理由にEventが欠落しない
    - Markerの移動時間とRecommendation Shortlistの移動時間が同じRoutes responseに基づく
    - 正確な現在地を永続保存せず、位置情報拒否時も地域検索で利用できる
    - 390x844で地図、Event詳細、戻る操作、主要CTAが使用できる
  - 検証:
    - Geolocation許可・拒否・timeoutとMaps API key未設定のcomponent test
    - `すべて`で取得Event数と重複統合後Marker数が一致するintegration test
    - Connection Level、期間、移動時間、継続性、`おすすめのみ`filterのintegration test
    - expired / canceled / sold out / stale / 根拠未確認Eventが状態付きMarkerになることを確認
    - viewport外Eventの遅延読込、clustering、Marker選択時だけのRoutes呼出を確認
    - Google Routes結果とMarker詳細・Recommendation Shortlist表示の一致を確認
    - 390x844と1440x900のbrowser smoke test
  - 実装記録（2026-08-23）:
    - `/osekkai/map`、Google Maps loader、direct座標/Geocoder、簡易viewport clustering、全Event一覧fallbackを実装
    - Map掲載をPUSH条件から分離し、既定`すべて`で169 Eventを保持。推薦外、根拠未確認、満席、中止等を状態付きで表示
    - 現在地は明示buttonからのみ一時取得し、拒否/timeout時は駅名・地域名へ切替。選択EventだけをEvent Routes APIへ送る
    - 9 filter、Event detail/close、Source/再検証時刻、CTA無効化、Routes結果cache、API key未設定placeholderを実装
    - Component testと1440x900/390x844 Browserで169件、詳細、閉じる、位置拒否fallback、横overflowなしを確認
    - BillingとMaps JavaScript/Routes/Geocoding keyを設定し、実Google Mapの読込とEvent表示を確認。deprecated Marker警告は非blockingで、移行は最終Gateを止めない

- [x] **TASK-150: 複数候補のPUSHで完走するLive Demo画面を実装する**
  - 依存: TASK-140、TASK-145
  - 対象:
    - `frontend/app/osekkai/demo/page.tsx`
    - `frontend/lib/osekkai/api.ts`
    - 必要な`frontend/app/osekkai/_components/*`
  - 作業:
    - 主経路をSource更新 → Connection判定 → Calendar → Routes → 優先順位付き複数候補PUSHへ変更
    - P0のno-PUSH機能と安全ロジックは残すが、Judge向け主シナリオから外す
    - CTAを`行ってみる / これは違う / 今回は無理 / 次回も知らせて`にする
    - おばさんの文面を実Eventの根拠項目だけから生成する
  - 完了条件:
    - 実在する現在Eventで60秒以内に複数候補のPUSHまで到達する
    - 図書館・公園・古いEventが主候補にならない
    - 根拠にない`一人参加OK`、`次回あり`、定員等を表示しない
  - 検証:
    - live Provider fixtureによるcomponent/integration test
    - 実Credentialを使ったbrowser smoke test
  - 完了記録（2026-08-23）:
    - Judge主経路をSource force sync → Calendar FreeBusy → Routes付きLive opportunities → Policy → 優先順位付き複数候補へ実装
    - 交流根拠と本人適合根拠を分離表示し、図書館・公園・大型展示を場所だけで主候補化せず、根拠のないclaimを表示しない
    - 候補0件時は架空Eventを補わず、Provider/Calendar/Routesの不足を具体的に案内
    - Live fixtureの複数候補component/integration testに加え、実Provider 4系統から239 Event、適格91件、Google Routes確認済み6候補を約10秒で同期
    - 実Google FreeBusy、実Routes、好みを使うPolicyの読取専用通し確認で、標準設定から優先順位付き3候補を生成。全主要画面とLive opportunities APIのHTTP 200を確認
    - 料金未確認を無料と誤認させず候補へ残し、公開title/descriptionから導出したカテゴリは`ai_derived` provenanceを保持。Schema上限を超える遠距離経路は同期全体を止めず除外
    - Chatの明示CTAで記憶同意とPUSH同意を設定し、未保存だった直前の好みを保存してLive Demoへ遷移する導線を追加
    - 審査Browser sessionで本人同意を含めて操作する最終リハーサルは`TASK-LIVE-DEMO-GATE`で別管理

- [x] **TASK-155: 好み起点の短いOnboardingと学習UIへ修正する**
  - 依存: TASK-090、TASK-140、TASK-150
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_chat.py`
    - `agents-OpenClaw/scripts/osekkai_profile.py`
    - `agents-OpenClaw/config/osekkai_policy.json`
    - `frontend/app/osekkai/page.tsx`
    - `frontend/components/osekkai/chat-client.tsx`
    - `frontend/components/osekkai/settings-client.tsx`
  - 作業:
    - 初回質問を「あんた、何が好きなのよ」にし、一度に1つの趣味・関心だけを聞く
    - ヨガ、ボルダリング、料理、音楽等の入力を本人同意の範囲でProfile Storeへ根拠付きで蓄積し、隣接ジャンルを含む複数候補rankingへ接続
    - 通常ChatからToday / Memory / Whyと推定根拠を外し、保存内容は設定で開いた場合だけ確認・個別削除できるようにする
    - 初期設定を標準値へまとめ、通知時間、移動時間、予算、強度は詳細設定へ折りたたむ
    - `今日は何もしない`をホームと初回会話から外し、Safety / Feedbackの副次選択肢としてだけ残す
  - 完了条件:
    - 好みの短文が推定カテゴリへ入り、次のPolicy rankingで使用される
    - Chatに内部Profileや推論根拠が常時表示されない
    - 推薦結果は1件へ固定されず、Live Demoの複数候補経路を維持する
  - 完了記録（2026-08-23）:
    - 好み抽出、明示設定とのmerge、Evidence削除時の復元、隣接カテゴリPolicyを実装
    - Home、Chat、Settingsを好み起点へ修正し、詳細設定と保存された好みをprogressive disclosureへ移動
    - 匿名Live sessionで「ボルダリングが好き」から`趣味・実用`が保存されることをAPI smokeで確認
    - Python 140 tests、Contract 24 schemas / 19 instances、Frontend 18 files / 90 tests、typecheck、lint、production build成功

#### Gate 6.5 — Contextual Okan Conversation

- [ ] **TASK-156: 会話EpisodeとState MachineのContractを作る**
  - 依存: TASK-155
  - 対象:
    - `contracts/osekkai/conversation-context.schema.json`
    - `contracts/osekkai/conversation-episode.schema.json`
    - `contracts/osekkai/chat-request.schema.json`
    - `contracts/osekkai/chat-result.schema.json`
    - `agents-OpenClaw/scripts/osekkai_conversation.py`
    - 生成Python / TypeScript validator・型・test
  - 作業:
    - `getting_to_know / calendar_sparse / nudge_sent / resistance / accepted / check_in_due / cooldown / safety_handoff`を明示状態として定義
    - 状態遷移、開始理由、根拠Event、提示回数、再提案回数、次回確認時刻をEpisodeへ保存
    - Trigger優先順位を`Safety > check-in > user initiated > calendar sparse > preference intake > quiet`へ固定
    - UIへ返す情報と内部根拠を分け、Today / Memory / Whyのような内部Panelを通常Chatへ復活させない
  - 完了条件:
    - 同一入力・Profile・時刻・Live候補から同じ状態遷移になる
    - 不正な状態遷移、根拠EventなしのPUSH、2回を超える再提案をContract境界で拒否する
    - Safety入力は他の状態より先に`Safety handoff`へ移る
  - 検証:
    - 全状態と不正遷移のPython unit test
    - Python / TypeScriptの同一fixture検証

- [ ] **TASK-157: Google Calendarの疎なFreeBusyを会話Triggerへ接続する**
  - 依存: TASK-156、TASK-100、TASK-120
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_freebusy.py`
    - `agents-OpenClaw/scripts/osekkai_context_trigger.py`
    - `agents-OpenClaw/scripts/osekkai_scheduler.py`
    - `agents-OpenClaw/config/osekkai_policy.json`
    - 対応Contract・test
  - 作業:
    - 追加設定なしのDemo標準として、次の7日間の設定済み活動時間帯を評価
    - `90分以上のFree Windowが2つ以上`または`Busy占有率20%未満`を`CALENDAR_SPARSE_WINDOW`候補とする。閾値はPolicy設定値に置き、コードへ埋め込まない
    - PUSH同意、Quiet Hours、週次上限、Cooldown、安全条件を先に適用
    - Free WindowとRoutesに収まるConnection Level 2以上の実Eventが複数あり、PUSH直前再検証が成功した時だけ会話Episodeを作る
    - Trigger文面を確認済みFreeBusyの範囲へ限定し、孤独、自宅滞在、予定内容を推測しない
  - 位置情報境界:
    - 現在のMapは明示buttonでBrowser Geolocationを一時取得済みだが、Calendar Triggerには使用しない
    - 会話内で実移動時間が必要な場合だけ`現在地から確認`の明示操作を出し、座標はRoutes request後に破棄する
    - Demo用の大まかなOriginは`OSEKKAI_LIVE_ORIGIN_*`を使えるが、実現在地と表示上区別する
  - 完了条件:
    - 疎なCalendarでも実候補がなければ話しかけない
    - 密なCalendar、Cooldown、同意なし、Quiet Hoursでは話しかけない
    - Calendar title、description、location、attendees、正確な現在地がEpisode・log・Profileへ入らない
  - 検証:
    - empty / sparse / dense / malformed / timeout FreeBusy fixture
    - 実Demo Calendarを使うread-only smoke

- [ ] **TASK-158: 断り方を理解する一度だけの後押しと会話内複数候補を実装する**
  - 依存: TASK-157、TASK-150
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_chat.py`
    - `agents-OpenClaw/scripts/osekkai_policy.py`
    - `frontend/components/osekkai/chat-client.tsx`
    - `frontend/app/osekkai/_components/recommendation-shortlist.tsx`
    - 対応Contract・test
  - 作業:
    - Chat初期表示を固定の好み質問から、現在Episodeに応じたおばさん発話へ変更
    - `人が多い / 遠い / 今日は気が乗らない`等の抵抗理由を一問だけ取得し、Group size、Conversation format、Travel、Timingへ構造化
    - 理由に合わない候補を外して複数候補を再順位付けし、再提案は最大1回に制限
    - 2回目の拒否、`もういい`、pause操作ではCooldownへ入り、罪悪感・孤独Label・脅しを使わない
    - 候補カードを会話内へ表示し、実Event名、日時、Routes、料金状態、募集状態、Connection根拠、Sourceを保持
    - `ひとり参加OK / 途中退出OK / 次回あり / 少人数`をSource根拠なしで生成しない
  - 完了条件:
    - 利用者の抵抗理由によって候補の除外・順位・文面が実際に変わる
    - 自由入力とDynamic Quick Replyの両方で同じState Machineを通る
    - Chatに内部Profile、推論confidence、Calendar詳細、正確な現在地を露出しない
  - 検証:
    - 拒否理由別Policy test、unsupported claim test、二度目拒否Cooldown test
    - Desktop / mobile component testとbrowser smoke

- [ ] **TASK-159: Event後のさりげないCheck-inと学習Loopを実装する**
  - 依存: TASK-158、TASK-160
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_conversation.py`
    - `agents-OpenClaw/scripts/osekkai_profile.py`
    - `agents-OpenClaw/scripts/osekkai_maintenance.py`
    - `frontend/components/osekkai/chat-client.tsx`
    - attendance / feedback / revisit Contract・API・test
  - 作業:
    - `行ってみる`で選択Eventと終了時刻をEpisodeへ紐付け、終了後の活動時間帯に`check_in_due`を作る
    - 「昨日どうやった？ また行ってもええ感じやった？」のように一問ずつ聞き、Survey画面へ分離しない
    - `また行きたい / 人の感じはよかった / ちょっと遠かった / 人が多すぎた / 行けなかった`と自由入力を学習Evidenceへ変換
    - カテゴリ、参加形式、Group size、移動許容、時間帯、継続意向、言葉の強さを別々のconfidenceで更新
    - 明示設定を推定で上書きせず、Memory同意なしでは会話本文・推定Profileを保存しない
    - Evidence個別削除と全削除を既存Settingsへ接続し、削除後の順位を再計算
  - 完了条件:
    - Event終了前にはCheck-inしない。未参加、取消、延期を参加成功として学習しない
    - Feedback後に次の複数候補の順位または除外理由が再現可能に変わる
    - 同じCheck-in回答を再送しても一度だけ記録する
  - 検証:
    - Event終了前後、未参加、取消、重複送信、Memory同意なし、Evidence削除test
    - 60秒Demo fixtureで`Calendar Trigger → 抵抗 → 一度だけ後押し → 参加 → Check-in → 次の順位変化`を完走

#### Gate 7 — 完成検証

- [x] **TASK-160: Provider・Connection・Calendar・Routes統合テストを作成する**
  - 依存: TASK-120〜TASK-150
  - 対象:
    - `agents-OpenClaw/tests/test_osekkai_live_demo.py`
    - frontendのLive Demo component/API test
  - 作業:
    - 大型展示、営業交流会、月例趣味会、共食、継続ボランティアを同時入力
    - expired、canceled、sold out、stale、duplicate、API timeoutを混ぜる
    - CalendarとRoutesによって候補群の内容と順位が変わることを検証
  - 完了条件:
    - 月例または継続Eventを中心とする複数候補だけが最終Recommendation Setに残る
    - 0件時に架空候補を生成しない
    - 同じ入力・時刻・Provider fixtureで同じ結果になる
  - 検証:
    - Python全test
    - frontend全test、typecheck、lint、build
  - 完了記録（2026-08-23）:
    - 大型展示、営業交流会、月例趣味会、共食、継続ボランティアと、canceled/sold out/duplicateを混ぜるLive統合testを追加
    - Calendar Free WindowとRoutes時間によって最終候補群/順位が変わること、Connection Levelの低いEventがMapには残りPUSHから外れることを確認
    - 候補0件でもsynthetic Eventを生成せず、同一fixture/時刻で決定論的な結果を返す
    - Python 131 tests、Contract 24 schemas/19 instances、Frontend 18 files/88 tests、typecheck、ESLint、Next production build成功

- [x] **TASK-170: 外部障害・Freshness・Privacy検証を実行する**
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
  - 完了記録（2026-08-23）:
    - Lu.ma Credential不足/取消、Doorkeeper 429、KCF detail parser失敗、CKAN timeoutを再現し、1 Source障害で他Source/Event Meshが停止しないことを確認
    - Calendar detail混入/token失効、Routes quota/zero result、PUSH前取消を再現し、stale/再検証不能Eventをfail closedにすることを確認
    - OAuth token/state暗号化、Calendar disconnect、Profile全削除のcredential削除test成功
    - 高信頼secret patternをworkspace全体でscanし、実Credential 0件。UI/logはpublic-safe error codeとSource状態だけを返す

- [x] **TASK-180: README・env・運用手順を更新する**
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
  - 完了記録（2026-08-23）:
    - Root/Frontend README、両`.env.example`、`IMPLEMENTATION_REPORT.md`を実装状態に更新
    - Billing、API enable、OAuth callback、server/browser key分離、暗号化key、Source sync、Calendar接続、Demo/Map確認を手順化
    - 必須/optional/Credential待ち、Attribution、利用条件、stale/failure動作、本番既知制約、動画Scope外を明記
    - exampleに秘密値がないことをsecret scanで確認し、README記載のPython/Frontend検証commandをfresh processで成功

- [ ] **TASK-LIVE-DEMO-GATE: Live Demoを最終承認する**
  - 依存: TASK-000〜TASK-180
  - 完了条件:
    - Tokyo CKAN、Lu.maまたは許可されたiCal、Doorkeeper、公共施設Siteのうち3系統以上が同期される
    - Eventが現在募集中で、Connection Level 2以上、原則Level 3以上である
    - CalendarとRoutesが実接続で判断を変える
    - 最新EventをPUSH直前に再検証する
    - 複数候補のPUSH、候補ごとの根拠、Source、更新時刻、CTAが表示される
    - Calendarの疎な期間をTriggerに会話が始まり、抵抗理由で一度だけ候補が調整される
    - Event後Check-inの回答で次の候補順位が変わる
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

#### UI-001 Recommendation Shortlist

- 優先順位付きの複数実イベント
- 候補ごとの距離
- 候補ごとの一人参加根拠
- 候補ごとの継続根拠
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
| サービスデザイン | 選びやすい少数の複数候補、断れる、好みを少しずらす、おばさんの人格で背中を押す |

---

## 16. 現在地

### できている

- オフラインP0の体験骨格
- Profile、会話、Policy、PUSH / HOLDの基本構造
- Event / Series / Community / Source RegistryとOpen Data provenance
- Tokyo CKAN、Lu.ma iCal、Doorkeeper、KCF Provider adapterと障害分離Scheduler
- Connection Evidence / Level、継続性、Personal Shift、複数候補Policy
- Google Calendar OAuth / FreeBusyとGoogle Routes / Geocodingの実接続コード
- Source更新から複数候補までのJudge UIと、取得した全EventのMap/一覧
- Credential不要の実同期（Tokyo CKAN 5 dataset、KCF 169開催回）
- 許可されたLu.ma iCal 50 Event、Doorkeeper API 25 EventのLive取得
- Google Calendar OAuth / FreeBusy、Google Routes / Geocoding、Google Maps JavaScriptの実接続
- 好みを1つ聞いてProfile Storeへ学習し、隣接ジャンルを含む複数候補Policyへ渡す通常導線
- Mapの明示buttonからBrowser Geolocationを一時取得し、選択EventのRoutes計算にだけ使う導線
- 実Provider 4系統239 Event、適格91件、Routes確認済み6候補と、実Calendar・Routes・好みによる優先順位付き3候補の通し確認
- Python/Frontendの統合・障害・Privacy自動テスト

### 次に実装する

- `TASK-156`: Conversation EpisodeとState Machine
- `TASK-157`: 疎なGoogle Calendar FreeBusyを使う会話Trigger
- `TASK-158`: 断った理由に合わせる一度だけの後押しと会話内複数候補
- `TASK-159`: Event後のCheck-inと次の順位へ反映する学習Loop
- 実装後、審査Browser sessionで本人同意を含む60秒会話Demoを行う最終リハーサル

Demo動画・PV制作はユーザー側で進行中のため、未完成実装には数えません。こちらの責任範囲は、動画と矛盾しない実イベント・根拠・台詞をLive UIへ出すことです。

Live Provider、Google実接続、複数候補生成、Mapの一時位置取得は実装・接続・通し確認済みです。現在の`話す`は好みを一つ聞くところまでで、Calendar Trigger、抵抗理由による調整、Event後Check-inはTASK-156〜159として未実装です。候補が0件の場合は成功を装わず、Provider、Calendar、Routes、Connection条件のどこで外れたかをUIへ出します。

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
