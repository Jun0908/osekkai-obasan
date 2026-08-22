# 「おっせかいおばさん」MVP 実装計画

- 作成日: 2026-08-22
- 対象: osekkai-obasan-submit-main
- 状態: P0 ローカルMVPの実装・最終受入完了。P1/P2の機能と外部adapterは未実装で、第17節の判断後に確定
- 優先順位: P0 を外部APIなしでエンドツーエンド完成させ、その後に P1 を実データ化する
- Repository更新: 依存0件の旧Tomo-san資産は `archive/tomo-san/` へ移動しGit追跡外。現在のプロダクト判断は `docs/brain/` を正本とする

> 2026-08-22の分離以前に書かれた「Tomo-san routeを残す」等の記述はP0実装時の履歴です。現在のActive routeはOsekkaiのみで、最新判断は `docs/brain/decision-history.md` を優先します。

この文書は、新規プロダクト「おっせかいおばさん」に関する実装の基準です。既存の Tomo-san、市民相談、PublicCase、World、NEAR、Talking Photo の計画や実装は置き換えません。

## 1. 目的と成功状態

既存の Tomo-san を改名・転用せず、同じリポジトリ内に独立した「おっせかいおばさん」MVP を追加します。

中心体験は次の一本です。

~~~text
会話する
→ 望む距離感を学ぶ
→ Calendar の空きを検知する
→ 今 PUSH すべきか判断する
→ 出典が確認できる候補から1件だけ提案する
→ 反応を学ぶ
→ 判断理由と KPI を記録する
~~~

P0 の成功状態は、外部APIや Talking Photo が停止していても、次のデモが2分程度で毎回同じように完走することです。

1. 「今週疲れた。何もしたくない」と会話する
2. Social Battery が低い状態へ更新される
3. Agent が do_not_push を選び、その理由を記録する
4. 「少し外に出たいが、話したくない」と会話する
5. デモ用の4時間の Free Window を読む
6. 徒歩圏・低 Social Intensity・会話不要の候補だけを残す
7. 候補を1件だけ PUSH する
8. ユーザーが「行ってみる」を選ぶ
9. ユーザーが「ちょうどいい」と距離評価する
10. 実参加をデモ操作として記録する
11. 再訪をデモ操作として記録する
12. impact 画面で Profile、PUSHした理由、PUSHしなかった理由、分類付きKPIの更新を確認できる

## 2. 現行リポジトリの監査結果

### 2.1 現行フロー

| 系統 | 現行の流れ | 新フローでの扱い |
|---|---|---|
| 市民相談 | frontend/app/page.tsx → World → /api/conversations → store.ts → PublicCase → OpenClaw → NEAR | 変更せず残し、取り込まない |
| Tomo-san | /tomo → /api/tomo/chat → tomo-chat.ts → SadTalker | 変更せず残し、取り込まない |
| スタッフ | /staff → OpenClaw 公開案件 | 変更せず残し、匿名 KPI 画面へ流用しない |
| OpenClaw | 政治案件、Calendar予定詳細、Telegram、各種ブリーフ | 保存・時刻・通知・実行パターンだけ参考にする |

### 2.2 再利用できる既存資産

| 既存資産 | 再利用する部分 | 再利用しない部分 |
|---|---|---|
| frontend/app/conversation/[id]/page.tsx、frontend/app/tomo/page.tsx | 会話UI、非同期状態、エラー表示のパターン | PublicCase化、動画生成 |
| frontend/lib/session.ts | 同一オリジン fetch ラッパーのパターン | Session、World、PublicCase の型 |
| frontend/lib/server/openclaw-bridge.ts | Python探索、spawn、stdin、stdout JSON、終了コード処理 | case_ingest と PublicCase 変換 |
| agents-OpenClaw/scripts/openclaw_core.py | JST時刻、安定ID、JSON、Telegram helper の限定利用 | 政治タグ、案件、判断ボード |
| agents-OpenClaw/scripts/tomo_profile.py | load → default merge → feedback → save の学習パターン | topic、region、brief_style の既存Profile |
| agents-OpenClaw/scripts/calendar_sync.py | Google OAuth Credentials の組み立て方だけ | events.list、タイトル、説明、場所、参加者の取得・保存 |
| agents-OpenClaw/scripts/telegram_bot.py | Bot API、chat allowlist の考え方 | 現行コマンド、政治案件応答 |
| agents-OpenClaw/scripts/run_all.py | 逐次ジョブ、fail-fast の形 | 既存の政治秘書 JOBS |
| frontend/app/globals.css | card、button などの基本的な見た目 | 既存全画面へ影響する変数の大幅変更 |

### 2.3 実装前に認識したベースライン（作業開始時点の履歴）

- ワークスペース直下に .git がなく、作業開始前の差分状態と復旧点を確認できませんでした。利用者からTomo-sanは別途保存済みとの申告がありますが、backup場所と復元テストの証跡はこのワークスペースにないため、TASK-P0-001は履歴上の未完事項として残します。
- 作業開始時点では frontend/node_modules と lockfile がなく、フロントエンドの build/typecheck は未検証でした。完了時の導入・検証結果は第19節と実装報告に記録しています。
- 作業開始時点の frontend/package.json には test と typecheck がなく、テストファイルとESLint設定もありませんでした。
- 作業開始時点の Python 側にも自動テストはありませんでした。既存の主要 Python スクリプトだけは Python 3.11 の py_compile を通過していました。
- 作業開始時点では、既存の日本語UI文字列、文書、生成データの一部に文字化けがありました。P0 では新規ファイルと変更箇所を UTF-8 に統一し、既存全体の文字化け修復へはスコープを広げず、build を妨げる構文破損だけを最小限修正する方針としました。
- 作業開始時点では frontend/README.md、TASKS.md と現行コードにドキュメントドリフトがありました。P0で追加したフローの説明は実装に合わせて更新済みです。
- Next.js Route Handler から child_process とローカルファイルを使う現行方式は、永続ディスクのある単一ホスト向けです。一般的な Edge/Serverless へはそのままデプロイできません。

## 3. この計画で確定する設計判断

| 論点 | 決定 |
|---|---|
| 既存Tomo-sanとの関係 | 改名しない。/tomo、/conversation、/cases、/staff は残す |
| 新規URL | UI は /osekkai 配下、API は /api/osekkai 配下に隔離する |
| P0のデータ | Free Windowと移動時間は明示された合成デモfixture、Opportunityは公式Open Dataから取得した改変なしのsource snapshotを使う |
| 実データ | 現在情報の同期、Google FreeBusy、Maps、Telegram は P1 で adapter を差し替える |
| Single source of truth | Profile、Conversation、Intervention は Python/OpenClaw 側の Osekkai 専用ストアだけに保存する |
| Next.js側ストア | frontend/.data へ二重保存しない。osekkai-store.ts は Python への薄い adapter に限定する |
| 利用者識別 | Worldは使わず、サーバー発行の署名付き匿名Cookieでユーザー領域を分離する。IDはUUIDに統一する |
| APIのuserId | request body や query から受け取らない。Cookieからサーバー側で解決する |
| Mutation保護 | SameSite Cookie、Origin照合、CSRF token、JSON Content-Typeを必須にする |
| スキーマ | contracts/osekkai の JSON Schema を正とし、TypeScript型を生成し、Pythonでも同じSchemaで検証する |
| 境界JSON | Next.js と Python の境界は camelCase に統一する |
| デモ時刻 | 固定時計または相対fixtureをサーバー側デモモードだけで使う。本番APIから任意時刻を注入できないようにする |
| ルート / | P0受入までは既存トップを維持して /osekkai への入口だけ追加する。redirect は受入後の別判断とする |
| Profile削除 | Profile、会話、推定根拠、介入、評価、派生KPIをユーザー単位で連鎖削除する |
| KPI | 分母ゼロは 0% ではなく null と「未計測」を返す |
| 効果表示 | 実測、参考推計、デモシナリオ、未検証をデータ型とUIの両方で分離する |

## 4. スコープ

### P0: 外部APIなしで完成させる

- /osekkai、/osekkai/chat、/osekkai/settings、/osekkai/demo、/osekkai/impact
- Distance Profile と明示設定
- 会話からの Profile 差分抽出
- 明示指示を最優先する Safety/Conversation 処理
- デモ Free/Busy、デモ Opportunity、デモ移動時間
- ガードレール優先の Distance Policy
- PUSH/no-PUSH の Intervention Episode 保存
- 4つの反応ボタンと3つの距離評価
- 記憶の閲覧、個別削除、送信前に指定するターン単位の「これは覚えないで」
- Profile とユーザーデータの削除
- Just-Right Push Rate、Overreach Rate、Under-Support Rate
- classification=demo の実参加・再訪シミュレーション
- 判断理由表示
- 完全未使用状態だけを原子的・非破壊で準備するdemo seed、確認付きdemo reset、固定fixture、固定時計
- JSON Schema、単体テスト、契約テスト、build/typecheck/test

P0 の会話抽出は、受入シナリオを確実に処理する決定論的ルールから始めます。外部LLMを使っているようには表示しません。将来LLMを接続する場合も、同じ出力Schema、安全判定、明示指示優先、保存同意を通す adapter とします。

P0の「外部APIなし」はデモ実行時の条件です。実装時に一度だけ公式Open Dataのsourceとlicenseを確認してsnapshotを作り、その後のデモではネットワークへ接続しません。

### P1: 実データ化

- Google Calendar FreeBusy API
- 1自治体のイベントデータと東京都公共施設データ
- Google Maps等による移動可能性
- Telegram通知、inline keyboard、callback
- scheduler
- 実参加、再訪、自発予定登録、Third Place、出典確認済みRole
- 承諾率、実参加率、再訪率、自発予定登録率、Third Place Acquisition Rate、Role Acquisition Rate
- UCLA-3 baseline/week 4/week 8
- 公式に確認した人間支援先の設定

### P2: 行政・実証価値

- Tokyo Connection Access Gap
- 町丁目別の社会接点供給
- 最小集計人数を設けた匿名集計
- 固定PUSHとAdaptive PUSHの比較
- Micro-Randomized Trial用ログ
- OSEKKAI Graduation Rate
- 対照群調整、Loneliness Point-Weeks Avoided

P0 が全受入条件を満たすまで P1 に進みません。P2 は研究設計、同意、倫理、統計定義が確定するまで実装しません。

### 明示的な非対象

- World Human Badge
- NEAR receipt
- PublicCase、公開案件、案件ステータス
- 政治家向け判断ボード、スタッフ画面
- 市民相談の案件化
- Talking Photo、SadTalker、動画生成
- 「案件を生成する」ボタン
- Calendarの予定タイトル、説明、場所、参加者
- 根拠のないイベント、役割、一人参加歓迎情報の生成

## 5. アーキテクチャ

~~~mermaid
flowchart LR
    B[Browser / osekkai] --> A[Next.js /api/osekkai]
    A --> I[匿名Cookie・入力検証]
    I --> R[osekkai-openclaw-bridge.ts]
    R --> C[osekkai_cli.py]
    C --> P[Profile / Safety / Policy / Metrics]
    P --> S[(OSEKKAI_DATA_ROOT)]
    P --> F[Demo fixtures]
    P -. P1 adapter .-> G[Google FreeBusy]
    P -. P1 adapter .-> O[Tokyo Open Data]
    P -. P1 adapter .-> M[Maps]
    P -. P1 adapter .-> T[Telegram]
~~~

### 境界ルール

1. Next.js は UI、HTTP、Cookie、入力サイズ制限、HTTPエラー変換を担当します。
2. Python は Profile 更新、Policy、Episode、KPI、scheduler、PUSH を担当します。
3. すべての mutation は Python CLI を通し、Next.js に Osekkai JSON の別コピーを作りません。
4. stdout は認可後の構造化結果JSONだけにし、ログは stderr へ出します。Profile閲覧APIの結果JSONには本人のevidenceを含められますが、通常ログには出しません。
5. bridge は shell を使わず引数配列で spawn し、timeout、終了コード、最大stdout、壊れたJSONを検査します。
6. OPENCLAW_ROOT はコードと仮想環境、OSEKKAI_DATA_ROOT はユーザーデータとして分離します。
7. 各 Route Handler は Node.js runtime を明示し、Edge runtime へ誤配置しません。
8. Pythonへの入力はSchemaとcommand allowlistを通し、任意スクリプト名や任意パスを受け付けません。
9. userId、episodeId はサーバー生成UUIDと正規表現で検証し、パスへ直接連結しません。CLIデモも予約語ではなく固定の有効なUUIDを使います。
10. read-modify-write はユーザー単位のクロスプラットフォーム・ファイルロック内で行い、その上で同一ディレクトリの一時ファイル、flush、atomic replace を使います。Profileはユーザー単位、Episodeはエピソード単位のファイルに分けます。
11. idempotencyの確認と状態更新は同じロック区間で行い、同一ホスト上の複数Route Handlerによるlost updateを防ぎます。
12. すべてのmutationはContent-Type、OriginとHost、CSRF tokenを検証します。

## 6. 共有契約とデータモデル

### 6.1 Canonical Schema

次を JSON Schema 2020-12 で新設します。

~~~text
contracts/osekkai/
├── common.schema.json
├── distance-profile.schema.json
├── conversation.schema.json
├── chat-result.schema.json
├── freebusy.schema.json
├── opportunity.schema.json
├── decision.schema.json
├── intervention-episode.schema.json
└── metrics.schema.json
~~~

- frontend/lib/osekkai/types.generated.ts はSchemaから生成します。
- frontend/lib/osekkai/validators.generated.ts はAjv standalone等で生成し、rootのcontractsディレクトリを実行時に参照せずAPI入力・Python結果を検証できるようにします。
- frontend/lib/osekkai/types.ts は生成型の再exportとUI専用型だけを持ちます。
- agents-OpenClaw/scripts/osekkai_contracts.py は同じSchemaでPythonの入出力とfixtureを検証します。
- persisted object は schemaVersion、id、userId、createdAt、updatedAt を必要に応じて持ちます。
- API mutation は idempotencyKey を受け取り、同一操作の二重反映を防ぎます。

### 6.2 Python CLI契約

osekkai_cli.py をNext.jsから呼ぶ唯一のPython command入口にします。許可するsubcommandは chat、profile-get、profile-update、profile-delete、freebusy、opportunities、decide、interventions、feedback、metrics、demo-seed、demo-reset、cleanup です。匿名sessionとCSRFの発行はNext.jsだけが担当します。任意のモジュール名やファイルパスは実行できません。

- stdin: 1つのJSON envelope。schemaVersion、requestId、command、userId、idempotencyKey、payloadを持つ
- stdout成功: 1つのJSON envelope。ok=true、requestId、dataを持つ
- stdout業務エラー: ok=false、requestId、error.code、error.messageを持つ
- stderr: 機微情報を除いた診断ログだけ
- exit code 0: parseできた成功または業務エラー
- exit code 2: request/schema不正
- exit code 3: storage/lock失敗
- exit code 4: provider失敗
- timeout/kill: Next.js bridgeが 504相当の共通エラーへ変換

userIdはAPI bodyではなくbridgeがCookieからenvelopeへ追加します。idempotencyKeyの照合とmutationは同じユーザーロック内で実行します。

### 6.3 Distance Profile

原要件に加えて、曖昧だった範囲を次のように固定します。

- socialBattery は 0〜100。未観測は null とし、空き時間だけから値を作りません。
- maxSocialIntensity は 0〜5。
- memoryConsent と pushConsent を別の明示設定にします。
- explicitPreferences と inferredPreferences を別フィールドに保持します。
- inferredPreferences の各値に confidence 0〜1 と evidence を持たせます。
- evidence は必要最小限の短い抜粋に制限し、Profile画面で閲覧・個別削除できます。
- 承諾・拒否履歴そのものは Episode を正とし、Profileには rejectionStreak、cooldownUntil、lastPushAt の派生状態だけを置きます。

P0 の安全側デフォルトは次です。これらは科学的に確立された値ではなく、設定可能なMVP初期値として扱います。

| 設定 | 初期値 |
|---|---|
| memoryConsent | false |
| pushConsent | false |
| quietHours | 21:00〜08:00、Asia/Tokyo |
| maxPushesPerWeek | 2 |
| preferredTone | gentle |
| maxTravelMinutes | 30 |
| maxBudgetYen | 2,000 |
| maxSocialIntensity | 2 |
| socialBattery | null |

demo modeでは、Profileが安全な初期値と完全一致し、会話0件・Episode 0件の完全未使用状態だけを、同一user lock内の `demo-seed` で説明付きデモProfileへ準備します。デモfixture上の `memoryConsent` と `pushConsent` はtrueですが、実利用者の同意として扱いません。設定・会話・Episodeが1つでもあれば `seeded=false` とし、何も変更しません。手動resetは削除範囲と不可逆性を表示し、正確な `リセット` 入力後だけ現匿名sessionのアプリデータを削除して同じfixtureを再作成します。通常利用やlive modeでは明示操作なしに同意済みにしません。

### 6.4 Opportunity と provenance

提示された型に次を追加します。

- dataMode: demo または live
- verificationStatus: synthetic_demo、source_snapshot、source_verified、organizer_verified、unverified
- fieldProvenance: フィールドごとの source URL、分類、取得日時、confidence
- travelEstimate: mode、minutes、source

raw open data、公開説明からのAI推定、主催者確認済み情報、合成デモfixtureを混同しません。roleAvailable、roleDescription、soloFriendly などを元データに根拠がないまま true にしません。

P0のOpportunityは、実装開始時に選定する公式Open Dataの実レコードを raw snapshot と normalized snapshot の両方で保存します。sourceUrl、dataset、license、capturedAt、checksumを必須にし、タイトル・日時・住所・役割等をデモ都合で書き換えません。Social Intensityや会話必要度を公開説明から推定する場合は fieldProvenance=ai_derived、confidence、根拠フィールドを付け、元データの事実とは表示しません。安全に推定できないレコードはP0候補に採用しません。固定時計上で再生し、UIには「公開データの過去スナップショットを使ったデモです。現在の開催情報ではありません」と表示します。Free Windowと移動時間だけは synthetic_demo と明示します。live Policy では source_snapshot や synthetic_demo を候補に入れません。

### 6.5 Intervention Episode

原要件の単一 feedback フィールドでは、行動反応と距離評価が上書きし合うため、次のように分けます。

- actionResponse: accepted、declined、show_another、pause_one_week
- distanceFeedback: too_much、just_right、push_more

Episodeには次を明示保存します。

- 判断時Profile snapshot
- policyVersion
- Free Window snapshot
- フィルタ前後の候補IDと除外理由
- 選択候補
- decision、shouldPush、reasonCodes
- 通知文、tone
- pushedAt または noPushAt
- actionResponse と日時
- distanceFeedback と日時
- attendedAt、revisitedAt、selfInitiatedAt
- dataMode と metricClassification

PUSHしなかった判断も必ず保存します。

### 6.6 保存構造

~~~text
OSEKKAI_DATA_ROOT/
├── profiles/
├── conversations/
├── interventions/
├── opportunities/
├── credentials/
├── assessments/
├── outcomes/
├── third-places/
├── roles/
├── metrics/
├── idempotency/
├── .locks/                 # raw UUIDを含まないHMAC化lock名
└── retention-maintenance.json
~~~

開発時の既定値は agents-OpenClaw/data/osekkai としますが、.gitignore へ追加します。本番はリポジトリ外の永続領域を必須とします。コミット可能なデモデータは agents-OpenClaw/fixtures/osekkai に分離します。

Profile削除は、解決後の絶対パスが OSEKKAI_DATA_ROOT 内であることを再確認してから、そのCookieのユーザーに属するProfile、会話、Episode、評価、派生KPI、冪等ledger、将来用token領域を削除します。共有Opportunity fixtureや他ユーザーのデータは削除しません。Windows上で保持中のHMAC化lock fileは運用artifactとして残り得ますが、名前にraw UUIDを含めません。

P0 の既定保持期間は30日とし、cleanup/maintenanceで会話と推定根拠、およびEpisode・冪等再生情報内の根拠コピーを期限後に削除します。Profileの明示設定、Episode、feedback、KPI自体は本人の全削除まで残します。冪等ledgerは24時間で、remember=falseの本文は保存せず、HMAC fingerprintと最小再生metadataだけを保持します。保持期間と削除方針は設定画面に表示し、保持期間テストを追加します。

## 7. Distance Policy

Policy は純粋関数を中心にし、テストを先に作ります。処理順は変更できません。

osekkai_policy.json は policyVersion を必須とします。P0のreason code enumは少なくとも NO_PUSH_CONSENT、QUIET_HOURS、COOLDOWN_ACTIVE、WEEKLY_LIMIT_REACHED、EXPLICIT_PAUSE、EXPLICIT_NO_ACTION、HUMAN_SUPPORT_REQUIRED、NO_FREE_WINDOW、NO_VERIFIED_OPPORTUNITY、OUTSIDE_FREE_WINDOW、TRAVEL_LIMIT、OVER_BUDGET、SOCIAL_INTENSITY_LIMIT、INVALID_SOURCE、SCORE_BELOW_THRESHOLD、FREE_WINDOW_AVAILABLE、LOW_SOCIAL_BATTERY、LOW_CONVERSATION_REQUIREMENT、WITHIN_TRAVEL_LIMIT、UNDER_BUDGET を含め、Schema外の文字列を保存しません。

### 7.1 第1段階: 強制ガードレール

次のどれかに該当したらスコア計算をせず do_not_push にします。

- pushConsent が false
- Quiet Hours中
- cooldownUntil が未来
- 月曜00:00 JST起点の週上限に到達
- 明示的な「今週は放っておいて」状態
- 現在ターンの明示的な「何もしたくない」から interventionHint=do_not_push が出ている
- safety.requiresHumanSupport が true
- 最低180分の Free Window がない
- liveでは現在性を含む出典確認済み候補、demoではprovenance付きsource snapshot候補がない

### 7.2 第2段階: 候補フィルター

- 開催時間と往復移動が Free Window 内
- travelMinutes が maxTravelMinutes 以下
- priceYen が maxBudgetYen 以下
- socialIntensity が maxSocialIntensity 以下
- 開催日時、住所、provider、source/provenance が有効
- 期限切れでない
- 明示的な avoidedCategories に該当しない

Social Battery は 0〜30をlow、31〜60をmedium、61〜100をhighとします。effectiveMaxSocialIntensity は lowで1、mediumで2、highで5を上限とし、必ず本人設定の maxSocialIntensity との小さい方を使います。不明な属性は都合よく推定せず、安全側に除外または低く評価します。

### 7.3 第3段階: PUSH判断と1件選択

Opportunity Fit、Current Receptivity、Trust、Feasibility、Burden、Intrusion Risk を0〜1へ正規化し、agents-OpenClaw/config/osekkai_policy.json のP0初期値で評価します。UIには「判断ルール」と表示し、医学的・科学的に確立した式とは表示しません。

~~~text
score =
  0.30 * opportunityFit
  + 0.30 * currentReceptivity
  + 0.20 * trust
  + 0.20 * feasibility
  - 0.15 * burden
  - 0.15 * intrusionRisk

PUSH threshold = 0.55
~~~

受入シナリオの決定論的parserでは、「何もしたくない」をcurrentReceptivity=0.0かつEXPLICIT_NO_ACTION、「少し外に出たい」を0.8、「話したくない」を maxSocialIntensity=1 とします。一般会話をこの少数ルールだけで理解できるとは表示しません。

- 同点時は source trust、開始時刻、移動時間、IDの順で決定し、毎回同じ結果にします。
- selectedOpportunity は最大1件です。
- 候補が0件なら NO_VERIFIED_OPPORTUNITY で do_not_push を返します。
- AIに候補や役割を補作させません。

### 7.4 拒否とcooldown

P0では設定可能な初期ルールとして次を使います。

| 反応 | 更新 |
|---|---|
| 今日はやめる | rejectionStreak + 1。1回目24時間、2回目72時間、3回目以降7日のcooldown |
| 今週は放っておいて | 即時に7日停止 |
| もう少し放っておいて | too_much として最低72時間停止し、頻度を下げる |
| ちょうどいい | rejectionStreak を max(0, rejectionStreak - 1) にし、期限切れcooldownだけを消す。同意・週上限・Intensity上限は変えない |
| もう少し押して | inferredPreferences.pushCadenceDelta=1 をconfidence=1.0で保存し、次回以降のreceptivityへ最大+0.10だけ加える。週上限やガードレールは変えず、即時追撃しない |
| 別のにして | ユーザー起点の明示要求として、同一Episode内で既出を除く代替を最大1件返す |

「今日はやめる」後は別候補を自動送信しません。「別のにして」は明示要求なので例外ですが、候補がなければその旨だけ返します。同一Episode内の代替は週PUSH数を重複加算しません。

## 8. API計画

すべて同一オリジン、署名付き匿名Cookie、生成済みruntime validatorによるSchema検証、no-store を前提とします。エラーは error.code、error.message の共通形で返し、内部パスやstderr全文をブラウザへ出しません。

匿名session Cookieは HttpOnly、SameSite=Strict、Path=/api/osekkai、Max-Age=30日とし、本番では Secure を必須にします。署名不正または期限切れなら既存IDを信用せず新しいsessionを発行します。秘密鍵rotation時は現行鍵と直前鍵だけを検証に使い、新規発行は現行鍵に限定します。GET /api/osekkai/session はuserIdを公開せず、sessionに結び付いた10分有効のCSRF tokenとdataModeだけを返します。API clientはmutationごとに token を専用headerへ付け、サーバーはOrigin/Hostとtokenを検証します。DELETE ProfileはUI上の明示確認も必要です。

| Method / Path | P | 役割 |
|---|---:|---|
| GET /api/osekkai/session | P0 | 匿名sessionを初期化し、短命CSRF tokenとdataModeを返す |
| POST /api/osekkai/chat | P0 | reply、profileDelta、interventionHint、confidence、safetyを返す。remember=falseなら会話・推定差分を保存しないが、本人が確認したpause/通知停止は明示制御として本文なしで保存する |
| GET /api/osekkai/profile | P0 | 明示設定、推定、Social Battery、保存根拠を表示する |
| PATCH /api/osekkai/profile | P0 | 明示設定更新、推定項目の個別削除、今週休む |
| DELETE /api/osekkai/profile | P0 | 現ユーザーのOsekkaiデータを連鎖削除し、匿名session Cookieも失効させる |
| GET /api/osekkai/freebusy | P0/P1 | P0 fixture、P1 Google FreeBusyを同一契約で返す |
| GET /api/osekkai/opportunities | P0/P1 | P0は公式Open Dataのsource snapshot、P1は現在情報を同期した正規化Open Dataを返す |
| POST /api/osekkai/decide | P0 | サーバー側のProfile/signalsからPolicyを実行し、no-PUSHを含むEpisodeを保存する |
| GET /api/osekkai/interventions | P0 | 現ユーザーの判断履歴と理由を返す |
| POST /api/osekkai/interventions | P0/P1 | demo outcome、P1の参加・再訪等を状態遷移付きで記録する |
| POST /api/osekkai/feedback | P0 | actionResponse または distanceFeedback を冪等に反映する |
| GET /api/osekkai/metrics | P0 | EpisodeからKPIを再計算し分類付きで返す |
| POST /api/osekkai/demo/seed | P0 | demo mode時、完全未使用状態だけを同一user lock内で非破壊・原子的に準備する。本番UIは呼ばない |
| POST /api/osekkai/demo/reset | P0 | demo mode時だけ、確認済みの現CookieユーザーのOsekkaiアプリデータを削除してfixtureを再作成する。本番は404 |
| GET/POST /api/osekkai/assessments | P1 | 明示同意後のUCLA-3を保存する |

POST /api/osekkai/decide は Profile、Free Window、Opportunity をブラウザから丸ごと信用せず、Python側ストアと現在のproviderから読みます。これにより予算、同意、候補出典の改ざんを防ぎます。

memoryConsent は会話本文と推定学習への同意です。falseでも、PUSH同意、Quiet Hours、pauseUntilなど本人が確認した運用設定と、サービス提供に必要な最小Episodeは保存できます。「これは覚えないで」と「今週は放っておいて」が同時に指定された場合、会話本文・推定・evidenceは保存せず、pauseUntilだけを明示制御として保存します。最小Episodeには会話本文、evidence、inferredPreferences、詳細Profile snapshotを入れず、decision、reasonCodes、配信有無、dataMode、時刻だけを保存します。これもProfile全削除の対象です。

## 9. UI計画

| 画面 | P0の内容 |
|---|---|
| /osekkai | 正式タイトル、指定コピー、「話してみる」、有効な「デモの空き時間を使う」、disabledの「Google Calendarをつなぐ（P1）」、demo/live状態 |
| /osekkai/chat | 通常会話、Social Battery、今回の学習差分、remember切替、記憶の閲覧・個別削除 |
| /osekkai/settings | memory/PUSH同意、頻度、Quiet Hours、強さ、口調、移動時間、予算、今週休む、全削除 |
| /osekkai/demo | fresh時の非破壊seed、確認付きreset、12段階実行、現在のProfile、Free Window、候補、Policy結果、反応ボタン |
| /osekkai/impact | 最新判断、reasonCodes、PUSH/no-PUSH履歴、分類付きKPI、未検証指標 |

トップコピーは次で固定します。

~~~text
おっせかいおばさん

近づきすぎず、離れすぎず。
あなたが一歩動ける瞬間だけ、
東京がおっせかいする。
~~~

P0では「Google Calendarをつなぐ（P1）」をdisabled表示し、実接続を装いません。デモは別ボタン「デモの空き時間を使う」で開始します。P1でのみOAuth導線を有効化します。

frontend/app/layout.tsx の既存 Political Intake header は全ルートに出るため、route-aware な SiteChrome を新設します。/osekkai だけ専用header、既存URLは従来headerを表示します。route groupへの大規模移動は行いません。OsekkaiのCSSは namespace または CSS Modules に分離し、既存ページの見た目を変えません。

アクセシビリティとして、全設定にlabel、処理中状態、aria-live、キーボードfocus、色以外の状態表示を用意します。モバイル幅でも反応ボタンとKPIが読めることを確認します。

## 10. KPI定義

KPIは保存済みカウンターを正とせず、Episodeから再計算します。必要ならmetrics/へ計算snapshotを置きます。

| KPI | P0定義 | 分母ゼロ |
|---|---|---|
| Just-Right Push Rate | just_right の距離評価数 ÷ 距離評価回答数 | null / 未計測 |
| Overreach Rate | too_much、pause_one_week、明示的通知停止のいずれかがある一意なPUSH Episode数 ÷ PUSH Episode数 | null / 未計測 |
| Under-Support Rate | push_more の距離評価数 ÷ 距離評価回答数 | null / 未計測 |
| 提案承諾率 | accepted Episode数 ÷ actionResponse対象PUSH Episode数 | null / 未計測 |

同一Episodeの複数反応を重複計上しません。「今日はやめる」は必ずしも過干渉を意味しないため、declined だけでは Overreach に数えません。

各Metricに classification を必須とします。

- measured → UI表示「実測」: 実際の同意済み利用データ
- reference_estimate → UI表示「参考推計」: 前提と算式を表示した参考推計
- demo → UI表示「デモシナリオ」: source snapshot、合成fixture、またはデモ操作
- unverified → UI表示「未検証」: 未検証・未収集

P0のdemo namespaceはすべて demo です。UCLA-3、Third Place、Role、Graduation、対照群調整、Loneliness Point-Weeks Avoided は値を作らず unverified と表示します。

| Phase | 指標 |
|---|---|
| P0 | Just-Right、Overreach、Under-Support、デモ承諾率 |
| P1 | 実承諾率、実参加率、再訪率、自発予定登録率、Third Place Acquisition、Role Acquisition、UCLA-3 baseline/week 4/week 8 |
| P2 | OSEKKAI Graduation、固定対Adaptive比較、対照群調整後の孤独尺度改善、Loneliness Point-Weeks Avoided |

## 11. Privacy / Safety

### Calendar

- P1は Calendar APIの freebusy.query だけを呼びます。
- 保存するのは算出後の freeWindows と生成時刻だけです。
- タイトル、説明、場所、参加者、元のbusy詳細を保存しません。
- Calendarの空白を孤独、暇、支援必要性の証拠にしません。
- 照会期間は既定7日、生活時間帯は08:00〜21:00 JST、最低空きは180分とし、設定可能にします。

### 会話と記憶

- memoryConsent=false の間は Profile 推定と会話本文を永続化しません。
- memoryConsent=falseでも、本人が確認したpauseUntil、pushConsent、Quiet Hoursなどの明示制御は本文・evidenceなしで保存し、安全上の停止を維持します。
- 各ターンを送信する前に「これは覚えないで」を選べます。送信済みの記憶はProfile画面のevidence単位削除または全削除で消します。
- 保存内容、confidence、evidence、更新日時を本人が確認できます。
- 推定項目の個別削除と、全ユーザーデータ削除を提供します。
- raw会話やevidenceをアプリログ、stderr、Telegramへ出しません。本人がProfileを閲覧する認可済みAPIの構造化stdout JSONだけは例外です。
- session CookieはHttpOnly、SameSite=Strict、本番Secureとし、mutationはOrigin照合と短命CSRF tokenを必須にします。

### Safety

- 感情だけから精神疾患や孤独を断定しません。
- 明示的な「放っておいて」「今週は休む」は推定より優先します。
- severe/urgent相当の明示的な苦痛を検知した場合は requiresHumanSupport=true、do_not_push とし、イベント提案を止めます。
- P0では診断や自動通報を行いません。支援導線の構造と安全な一般文だけを実装します。
- 公開運用前に、日本国内の公式支援先、緊急時コピー、更新責任者を確認して設定ファイルへ登録します。未確認の連絡先を生成しません。
- 管理者向けの個票閲覧画面は作りません。P2の匿名集計には認証と最小集計人数を別途必要とします。

## 12. ファイル計画

### 12.1 P0で新規作成

~~~text
contracts/osekkai/
  common.schema.json
  distance-profile.schema.json
  conversation.schema.json
  chat-result.schema.json
  freebusy.schema.json
  opportunity.schema.json
  decision.schema.json
  intervention-episode.schema.json
  metrics.schema.json

frontend/app/
  site-chrome.tsx
  osekkai/
    layout.tsx
    osekkai.module.css
    page.tsx
    chat/page.tsx
    settings/page.tsx
    demo/page.tsx
    impact/page.tsx
    _components/...
  api/osekkai/
    session/route.ts
    chat/route.ts
    profile/route.ts
    freebusy/route.ts
    opportunities/route.ts
    decide/route.ts
    interventions/route.ts
    feedback/route.ts
    metrics/route.ts
    demo/reset/route.ts

frontend/lib/osekkai/
  types.generated.ts
  validators.generated.ts
  types.ts
  api.ts
  constants.ts
  errors.ts

frontend/lib/server/
  osekkai-user.ts
  osekkai-openclaw-bridge.ts
  osekkai-store.ts
  osekkai-metrics.ts

agents-OpenClaw/fixtures/osekkai/
  profile.json
  freebusy.json
  opportunities.raw.json
  opportunities.normalized.json
  opportunity-source-metadata.json

agents-OpenClaw/config/
  osekkai_policy.json

agents-OpenClaw/scripts/
  osekkai_contracts.py
  osekkai_store.py
  osekkai_profile.py
  osekkai_safety.py
  osekkai_chat.py
  osekkai_freebusy.py
  osekkai_opportunity_sync.py
  osekkai_policy.py
  osekkai_metrics.py
  osekkai_cli.py
  osekkai_run.py

agents-OpenClaw/tests/
  test_osekkai_contracts.py
  test_osekkai_store.py
  test_osekkai_concurrency.py
  test_osekkai_security.py
  test_osekkai_retention.py
  test_osekkai_profile.py
  test_osekkai_safety.py
  test_osekkai_freebusy.py
  test_osekkai_policy.py
  test_osekkai_metrics.py
  test_osekkai_demo.py

frontend/package-lock.json
frontend/.env.example
~~~

frontend/lib/server/osekkai-store.ts と osekkai-metrics.ts はPython CLIへの型付き薄いmapperです。ファイルI/O、KPI計算、provider取得は実装しません。

空のAPI stubや未実装ボタンは作りません。P1専用の assessments、Maps、Telegram はP1着手時に追加します。

### 12.2 P0で最小変更する既存ファイル

| ファイル | 変更 |
|---|---|
| frontend/app/layout.tsx | route-aware SiteChrome を使用し、/osekkai と既存ブランドを分ける |
| frontend/app/page.tsx | redirectせず、/osekkai への入口だけ追加する |
| frontend/package.json | generate:contracts、typecheck、test、lintを非対話で実行できるようにする |
| .gitignore | runtimeの agents-OpenClaw/data/osekkaiを除外し、!frontend/package-lock.jsonだけを限定的に追跡可能にする。fixtureは除外しない |
| agents-OpenClaw/requirements.txt | Python JSON Schema validatorとクロスプラットフォームfile lockなど、P0で実際に使う最小依存だけ追加する |
| agents-OpenClaw/.env.example | Osekkai用環境変数を追記する |
| README.md、frontend/README.md | P0完了後に起動、デモ、制約を追記する |

### 12.3 P1で追加

~~~text
frontend/app/api/osekkai/assessments/route.ts
frontend/app/api/osekkai/calendar/connect/route.ts
frontend/app/api/osekkai/calendar/callback/route.ts
frontend/app/api/osekkai/calendar/disconnect/route.ts
contracts/osekkai/assessment.schema.json
contracts/osekkai/outcome.schema.json
contracts/osekkai/third-place.schema.json
contracts/osekkai/role.schema.json
agents-OpenClaw/config/osekkai_sources.json
agents-OpenClaw/config/osekkai_support_resources.json
agents-OpenClaw/scripts/osekkai_google_credentials.py
agents-OpenClaw/scripts/osekkai_routes.py
agents-OpenClaw/scripts/osekkai_push.py
agents-OpenClaw/tests/test_osekkai_google_freebusy.py
agents-OpenClaw/tests/test_osekkai_opportunity_sync.py
agents-OpenClaw/tests/test_osekkai_push.py
agents-OpenClaw/tests/test_osekkai_outcomes.py
agents-OpenClaw/tests/test_osekkai_assessments.py
~~~

P1のFreeBusy、Open Data、Mapsの取得・正規化・provenanceのownerはPythonに統一します。既存のNext.js API routeとosekkai-openclaw-bridge.tsは同じPython commandを呼ぶだけとし、TypeScript側に第二のprovider実装を作りません。

### 12.4 原則変更しない

- frontend/lib/types.ts
- frontend/lib/server/store.ts
- frontend/lib/server/openclaw-bridge.ts
- frontend/lib/server/mock-intake.ts
- frontend/lib/server/near.ts
- frontend/lib/server/tomo-chat.ts
- frontend/lib/world.ts
- frontend/app/conversation
- frontend/app/cases
- frontend/app/staff
- frontend/app/tomo
- frontend/app/api/world
- frontend/app/api/tomo
- agents-OpenClaw/scripts/calendar_sync.py
- agents-OpenClaw/scripts/tomo_profile.py
- agents-OpenClaw/scripts/run_all.py
- agents-OpenClaw/scripts/case_ingest.py
- backend/

## 13. 実装フェーズと完了条件

### Phase 0: ベースラインを固定

作業:

- Git管理またはバックアップを用意する
- Node/Pythonバージョンと依存を記録する
- package lockを作成する
- 既存 build、Python compile、主要routeのbaseline結果を記録する
- 新規ファイルのUTF-8方針を固定する

完了条件:

- 変更前に失敗していた項目と、今回の変更で発生した失敗を区別できる
- 実装後に既存routeの退行を確認できる

### Phase P0-A: Schema、テスト基盤、単一ストア

作業:

- canonical JSON Schemaとfixtureを作る
- 公式Open Dataの対象dataset、license、source URLを確認し、実レコードのraw/normalized snapshotとchecksumを作る
- TypeScript型とbundle済みruntime validatorを生成する
- Python validatorとcontract testを作る
- 署名付き匿名Cookie、CSRF token、Origin検証、ID検証を作る
- ユーザー単位lock、atomic JSON store、連鎖削除を作る
- osekkai_cli.py cleanup と保持期間テストを作る
- runtime dataとfixtureを分離する

完了条件:

- TS/Pythonが同じfixtureを受理し、壊れたfixtureを拒否する
- Next.js APIが生成済みvalidatorで不正なrequest/responseを拒否する
- Next.js側にProfileのコピーがない
- 他userId、path traversal、重複mutationを拒否する
- 同一Profileへの並行更新でlost updateが起きない
- foreign Origin、CSRF tokenなしのmutationを拒否する
- Profile削除テストが通る

### Phase P0-B: Conversation、Profile、Safety

作業:

- reply/profileDelta/interventionHint/confidence/safety契約を実装する
- Social Battery、強度上限、口調、好み/苦手の差分を抽出する
- explicit/inferredを分離する
- memoryConsent、remember=false、個別削除を実装する
- remember=falseと明示pauseが同時の場合、本文を保存せずpause制御だけを保存する
- 明示的な休止と人間支援判定を最優先にする

完了条件:

- 受入用の2会話が期待する差分を返す
- 「放っておいて」が常に提案を抑止する
- 感情から診断名や孤独を生成しない
- remember=falseの本文、差分、evidenceが保存されない
- remember=falseでも確認済みpauseUntilが維持され、後日のPUSHを止める

### Phase P0-C: Demo signal、Policy、Episode

作業:

- 4時間の合成Free Window、Open Data source snapshot候補、合成移動時間をfixture化する
- fixtureの時刻を固定時計へ正規化する
- guardrail、filter、deterministic scoreを実装する
- PUSH/no-PUSH双方をEpisodeへ保存する
- 理由コードと除外理由を実装する

完了条件:

- 最初の会話は do_not_push
- 次の会話では低Intensity候補を1件だけ返す
- 候補0件なら NO_VERIFIED_OPPORTUNITY となる
- live modeでsource snapshotやsynthetic demo fixtureを選ばない
- 同じ入力、時計、fixtureなら同じ結果になる
- EpisodeのpolicyVersionとreasonCodesから同じ判断を再現できる

### Phase P0-D: API、UI、Feedback、KPI

作業:

- 専用APIと5画面を接続する
- session初期化、Cookie属性、CSRF headerをAPI clientへ接続する
- 4反応、3距離評価、cooldown、Profile更新を接続する
- KPIをEpisodeから計算する
- 非破壊・原子的seed、確認付きreset、demo stepper、impactを実装する
- route-aware headerと分離CSSを実装する

完了条件:

- 12段階の中心デモをブラウザで完走できる
- 外部API、World、NEAR、Talking Photoを一度も呼ばない
- impactにPUSH/no-PUSH理由とclassification付きKPIが出る
- Profileの閲覧、個別削除、全削除が動く
- build、typecheck、lint、testが非対話で成功する

### Phase P0-E: 退行確認と引き渡し

作業:

- 既存 /tomo、/conversation、/cases、/staff のroute/buildとHTTP/browser smoke test
- READMEとenv example更新
- 実装済み/未実装、環境変数、デモ、テスト結果、制約を報告する

完了条件:

- 既存routeが消えていない
- /osekkai から World、NEAR、PublicCase、Talking Photoへのimport/callがない
- P1項目を「実装済み」と表示していない

### Phase P1: 実データadapter

開始条件:

- P0の全テストとデモが成功している
- 対象自治体、dataset URL、ライセンス、更新頻度、必須フィールドが決まっている
- Google OAuthの同意画面と保存方針が決まっている
- Cookie user単位のOAuth state、PKCE、暗号化credential store、失効・削除テストが決まっている
- Maps providerと位置情報同意が決まっている
- Telegram本人紐付け、callback、再送方針が決まっている

実装順:

1. 匿名sessionに結び付くOAuth start/callback/disconnectと暗号化token storeを実装する
2. Google FreeBusyをfixture契約へ接続
3. 1自治体Open Dataを正規化しprovenanceを保存
4. 東京都公共施設adapterを追加
5. Mapsで往復移動を検証
6. Telegram PUSHとcallback
7. scheduler
8. 参加、再訪、Third Place、Role、UCLA-3

## 14. テスト計画

### 14.1 必須の単体・契約テスト

- 明示的な「放っておいて」は常にPUSHしない
- pushConsent=false は常にPUSHしない
- Quiet Hoursの日跨ぎを正しく扱う
- cooldown中はPUSHしない
- 週上限超過はPUSHしない
- safety.requiresHumanSupport=true はPUSHしない
- 180分未満の空きではPUSHしない
- Social Battery低時に高Intensityを出さない
- 予算、移動、開催時間、出典不備の候補を除外する
- Opportunity source snapshotのchecksum、sourceUrl、dataset、license、capturedAtを検証し、rawにない役割や参加条件をnormalizedへ追加しない
- source snapshotを現在開催中またはliveとして表示しない
- 候補0件で架空候補を作らない
- 同点候補を決定論的に1件へ絞る
- 拒否後に自動追撃しない
- show_anotherは既出候補を除外し最大1件
- PUSHしなかったEpisodeも保存する
- feedbackのidempotencyKeyで二重加算しない
- 並行feedback/Profile更新でもlost updateしない
- Profile削除が他ユーザーへ影響しない
- path traversal形式のIDを拒否する
- foreign Origin、CSRF token欠落、不正Content-Typeを拒否する
- CookieがHttpOnly、SameSite=Strict、本番Secureになる
- remember=falseを保存しない
- remember=falseと明示pauseの同時入力では、本文/evidenceなしでpauseUntilだけを保存する
- memoryConsent=falseの最小Episodeに会話、evidence、推定Profileが入らない
- 保持期限を過ぎた会話/evidenceだけをcleanupし、他ユーザーや新しいデータを残す
- FreeBusy保存物に title、summary、description、attendees、location がない
- KPI分母ゼロを null にする
- demo/measured/unverifiedを混ぜない
- TypeScriptとPythonのcontract fixtureが一致する
- policyVersion、reason code enum、重み、閾値が設定とEpisodeで一致する
- 非同意時の距離評価が推定cadenceを永続化しない
- evidence/preference削除と期限切れが、直下のderived判断値とEpisode/replay copyにも反映される
- demo seedが完全未使用状態だけを同一lock内で更新し、並行writerと既存進捗を上書きしない
- file/ユーザー単位byte quota、FIFO queue、permit解放、rate limit、429/503 `Retry-After` が動く

### 14.2 フロントエンド検証

実装後に package.json のscriptを整え、PowerShellでは次を実行します。

~~~powershell
Set-Location frontend
npm.cmd ci
npm.cmd run generate:contracts
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
~~~

lockfile作成後の通常検証は npm.cmd ci を使います。Vitest、Testing Library、非対話ESLint設定を追加し、少なくともAPI client、主要UI状態、KPI表示、demo stepperを検証します。

### 14.3 Python検証

~~~powershell
Set-Location agents-OpenClaw
python -m pip install -r requirements.txt
python -m compileall scripts tests
python -m unittest discover -s tests -p "test_osekkai_*.py" -v
python scripts/osekkai_contracts.py --validate-all
python scripts/osekkai_run.py --demo --reset --user-id 00000000-0000-4000-8000-000000000001 --json
~~~

テストは一時ディレクトリを OSEKKAI_DATA_ROOT に指定し、既存dataと実ユーザーデータへ書き込みません。

### 14.4 既存機能の退行確認

~~~powershell
Set-Location agents-OpenClaw
python scripts/case_ingest.py --help
python scripts/run_all.py --help

Set-Location ../frontend
npm.cmd run build
~~~

さらに、Osekkai領域から禁止機能をimportしていないことを検索し、/tomo、/conversation、/cases、/staff がbuild成果物に残ることを確認します。build後にローカルサーバーを起動し、ブラウザまたはHTTP smokeで /、/tomo、/staff、/osekkai が200、動的な /conversation/[id] と /cases/[id] がroute manifestに存在することを確認します。SiteChromeのcomponent testでは、legacy pathで従来header、/osekkai pathで専用headerになることを検証します。

## 15. 再現可能なデモ手順

準備:

1. OSEKKAI_DEMO_MODE=true で起動する
2. freshな匿名Cookieで /osekkai/demo を開く。完全未使用状態だけが自動seedされ、手動resetが不要なことを確認する
3. Free Windowと移動時間は「合成デモ」、Opportunityは「公開データの過去スナップショット・現在の開催情報ではない」と表示されることを確認する
4. 既存設定・会話・Episodeがある場合、自動seedが何も上書きしないことを確認する

12段階の中心デモ:

1. 「今週疲れた。何もしたくない」を送る
2. Social Battery=low相当への更新を確認する
3. do_not_pushと理由コードを確認する
4. 「少し外に出たいが、話したくない」を送る
5. 4時間の空きを確認する
6. 候補フィルタとsource snapshot候補を確認する
7. 1件だけの提案を確認する
8. 「行ってみる」を押す
9. 「ちょうどいい」を押す
10. 「実参加をシミュレーション」を押す
11. 「再訪をシミュレーション」を押す
12. impactへ移動し、Profile、PUSH/no-PUSH理由、Just-Right、Overreach、再訪率、classificationを確認する

運用確認:

1. 手動resetは削除対象と不可逆性を表示し、`リセット` の正確な入力なしには実行できないことを確認する
2. 確認付きresetから再実行し、同じ判断になることを確認する
3. settingsでProfileを削除し、chat、Episode、KPIが消えることを確認する

デモではネットワークを切っても同じシナリオが完走しなければなりません。

## 16. 環境変数

### P0

| 変数 | 用途 |
|---|---|
| OPENCLAW_ROOT | agents-OpenClaw のコード配置先 |
| OPENCLAW_PYTHON_BIN | Python実行ファイルの明示指定。未指定時はvenv→systemの順に探索 |
| OSEKKAI_DATA_ROOT | Osekkai専用の永続データ領域 |
| OSEKKAI_SESSION_SECRET | 匿名Cookie署名 |
| OSEKKAI_SESSION_SECRET_PREVIOUS | 秘密鍵rotation中だけ使う直前鍵 |
| OSEKKAI_DEMO_MODE | demo fixture、非破壊seed、確認付きresetの有効化 |
| OSEKKAI_TIMEZONE | 既定 Asia/Tokyo |
| OSEKKAI_DATA_RETENTION_DAYS | 既定30日 |
| OSEKKAI_BRIDGE_TIMEOUT_MS | Python bridge timeout |
| OSEKKAI_BRIDGE_MAX_CONCURRENCY | instance内のPython同時実行数。既定4、最大16 |
| OSEKKAI_BRIDGE_MAX_QUEUE | instance内FIFO待ち行列。既定16 |
| OSEKKAI_BRIDGE_QUEUE_TIMEOUT_MS | bridge待ち時間。既定2000ms |
| OSEKKAI_RATE_LIMIT_REQUESTS | IP/user単位のinstance-local request上限。既定120/window |
| OSEKKAI_SESSION_ISSUE_RATE_LIMIT | 匿名session発行のIP単位上限。既定60/window |
| OSEKKAI_RATE_LIMIT_WINDOW_MS | rate limit window。既定60000ms |
| OSEKKAI_RATE_LIMIT_MAX_KEYS | instance内bucket最大数。既定10000 |
| OSEKKAI_TRUST_PROXY_IP_HEADERS | caller headerをproxyが必ず除去・上書きする場合だけtrue |

秘密値を NEXT_PUBLIC_ 変数へ置きません。demo mode は本番で明示的に false とします。外部retention workerは `frontend/.env.local` を自動読込しないため、frontendと同じdata rootとruntime modeをscheduler側で渡し、JSONの `status`、`cycleCompleted`、`usersSkipped` を監視します。

### P1

| 変数 | 用途 |
|---|---|
| GOOGLE_CLIENT_ID | Google OAuth |
| GOOGLE_CLIENT_SECRET | Google OAuth |
| GOOGLE_REDIRECT_URI | user単位OAuth callback |
| OSEKKAI_CREDENTIALS_KEY | user単位refresh tokenの暗号化。session署名鍵とは分離 |
| OSEKKAI_OPEN_DATA_SOURCE_CONFIG | dataset設定 |
| MAPS_API_KEY | 移動時間adapter |
| TELEGRAM_BOT_TOKEN | PUSH送信 |
| TELEGRAM_CHAT_ID または本人紐付けストア | 送信先 |

実装時に frontend/.env.example と agents-OpenClaw/.env.example へ秘密値なしの説明を追加します。

P1の通常モードでグローバルなGOOGLE_REFRESH_TOKENは使いません。tokenはOAuth stateと匿名sessionを結び、userId単位で暗号化保存します。単一デモアカウント用の環境変数fallbackを設ける場合も、明示的な開発モードだけに限定し、本番起動時は拒否します。

## 17. P1開始前に決める未決事項

次はP0を止めませんが、P1着手前の必須判断です。

1. 対象とする最初の自治体、dataset URL、利用規約、ライセンス、更新頻度
2. 東京都公共施設データの具体的なsource
3. Opportunityのsource trust閾値と期限切れルール
4. Maps provider、課金上限、徒歩/公共交通、生活圏の取得・同意
5. Google OAuth tokenの暗号化と失効・削除
6. Telegram callback方式、本人紐付け、再送、送信失敗時のEpisode状態
7. schedulerの実行頻度と同時実行制御
8. 公開運用で表示する日本国内の公式支援先と更新責任
9. 実参加、再訪、Third Place、Role、Graduationの操作的定義
10. UCLA-3の同意、採点、保持、利用目的
11. 匿名集計の管理者認証、最小集計人数、保持期間
12. 本番デプロイ先。現構成は永続ディスクとPython子プロセスが必要
13. P0受入後に / を /osekkai へredirectするか

## 18. 既知の制約

- P0の会話理解は受入シナリオ中心の決定論的ルールで、自由会話全般を理解するLLMではありません。
- P0のFree Window、Opportunity、移動時間、参加・再訪はデモデータです。
- P0の匿名Cookieは本格的なアカウント認証ではありません。複数端末同期や本人復旧はできません。
- JSONファイルストアは、P0でユーザー単位のプロセス間lockを持つ単一ホストMVP向けです。複数ホスト運用では共有DB、transaction、分散排他が必要です。
- request rate limitとPython permit/queueはNode.js instance内だけです。複数instance公開運用ではingress側の共有rate limitが必要です。
- 保存量はfile単位とユーザー単位で制限しますが、全ユーザー合算disk/namespace上限はありません。公開運用ではOS/container disk quotaと監視が必要です。
- 既存コードの文字化け全体はこの計画の修復対象ではありません。
- 対照群、医学的効果、行政効果を示す実測データはP0にありません。
- 現在の作業ディレクトリにGit履歴がなく、変更前commitまたはbackup場所も記録で確認できません。実装の差分監査と変更前状態への復旧可否は未確認です。

## 19. P0最終受入チェックリスト

- [x] /osekkai 配下の製品名表記がすべて「おっせかいおばさん」
- [x] /osekkai 配下の5画面がある
- [x] 既存Tomo-sanルートが残っている
- [x] World認証なしで開始できる
- [x] Talking Photoを呼ばない
- [x] Profileの明示設定と推定が分離されている
- [x] memoryConsentとpushConsentが分離されている
- [x] 「これは覚えないで」が保存されない
- [x] 記憶の閲覧、個別削除、全削除ができる
- [x] Osekkaiフローで扱うCalendarはFree/Busy契約だけ
- [x] 空き時間を孤独の証拠にしない
- [x] Opportunityのsource snapshotにURL・dataset・license・capturedAt・checksumがあり、現在開催中と誤表示しない
- [x] ガードレールがスコアより先に動く
- [x] PUSHしない判断もEpisodeへ残る
- [x] 候補0件でPUSHせず、架空候補を作らない
- [x] 候補を最大1件だけ提示する
- [x] 4反応と3距離評価が動く
- [x] 拒否直後に自動追撃しない
- [x] Just-Right、Overreach、Under-Supportが計算できる
- [x] 分母ゼロが「未計測」になる
- [x] demo、measured、reference estimate、unverifiedが区別される
- [x] 12段階の中心デモとreset/deleteの運用確認がオフラインで完走する
- [x] build、typecheck、lint、testが成功する
- [x] 既存routeの退行がない
- [x] 実ユーザーデータがリポジトリ追跡対象に入らない

2026-08-22の最終証跡は、Vitest 17 files/80 tests、Python 69 tests、16 Schema/8 instance validation、12/12 runner、fresh Cookie・外部HTTPS遮断の実ブラウザ12/12、390x844/1440x900の5画面、legacy route、production smoke、Privacy/Security negative HTTP testです。未実装のP1/P2や未検証効果はこのチェックに含めません。

## 20. 実装完了時の報告形式

実装完了時は、次を事実ベースで報告します。

1. 変更した既存ファイル
2. 新規ファイル
3. 実装済み機能
4. 未実装のP1/P2機能
5. 起動方法
6. 必要な環境変数
7. 2分デモ手順
8. 実行したテストコマンドと結果
9. 既知の制約
10. / を /osekkai へ切り替えるかの判断待ち

架空の効果、未実行のテスト、未接続の外部APIを実装済みとして報告しません。

## 21. 実行Task一覧

この節を実装時の作業キューとして使用します。Taskは原則としてID順に実行し、依存Taskが完了するまで後続Taskを開始しません。

### 21.1 Task運用ルール

- 未着手は [ ]、完了は [x] で管理する
- コードを書いただけでは完了にせず、各Taskの完了条件と検証を満たしてから [x] にする
- 外部API、実データ、P1機能へ先回りしない
- Task中に仕様変更が必要になった場合は、先に本文の設計・Schema・受入条件を更新する
- テスト結果、未解決事項、判断理由をTask直下または実装報告へ残す
- 変更前backup証跡のように後付け不能な履歴Taskだけは、未完理由と後続作業への影響を明記したうえで [ ] のまま履歴例外にできる
- P0-GATEが完了するまでP1 Taskを開始しない
- P1-GATEが完了するまでP2 Taskを開始しない

### 21.2 Phase 0: ベースライン

- [ ] **TASK-P0-001: 復旧可能な作業基盤を用意する**
  - 依存: なし
  - 作業: Git管理された作業コピーを用意するか、現ワークスペースのバックアップを取得する
  - 完了条件: 変更前状態へ戻せることを確認し、現在のbranchまたはbackup場所を記録する
  - 未完注記: 利用者からTomo-sanは保存済みとの申告があるが、現ワークスペースに `.git` がなく、変更前commit、backup場所、復元テストの証跡を確認できない。後から作る現行backupでは変更前復旧を証明できないため、事実どおり未完のまま残す

- [x] **TASK-P0-002: 開発環境と既存状態を記録する**
  - 依存: TASK-P0-001（後付け不能な履歴例外を記録し、現時点のbaseline採取は続行）
  - 作業: Node、npm、Python、OS、既存env、依存未導入状態を記録する
  - 完了条件: baselineログにバージョンと不足依存が記載されている

- [x] **TASK-P0-003: npm依存とlockfileを固定する**
  - 依存: TASK-P0-002
  - 対象: frontend/package.json、frontend/package-lock.json、.gitignore
  - 作業: frontendだけのpackage-lockを生成し、!frontend/package-lock.jsonを追跡対象にする
  - 完了条件: npm.cmd ci が再現可能に成功する

- [x] **TASK-P0-004: テスト・型検査・lint scriptを準備する**
  - 依存: TASK-P0-003
  - 対象: frontend/package.json、Vitest、Testing Library、ESLint設定
  - 完了条件: 空の初期状態でも typecheck、lint、test が非対話で起動する

- [x] **TASK-P0-005: 既存機能のbaselineを取得する**
  - 依存: TASK-P0-004
  - 作業: frontend build、Python compile、既存route一覧、既知の文字化け・失敗を記録する
  - 完了条件: 今回の実装前から存在する失敗と、新規退行を区別できる

- [x] **TASK-P0-006: P0用Open Data source snapshotを選定する**
  - 依存: TASK-P0-001
  - 作業: 公式source、dataset、license、対象レコード、sourceUrl、capturedAtを確認する
  - 完了条件: デモに必要な日時・住所・説明があり、低Intensity推定の根拠を保持でき、利用条件上snapshot同梱が可能である

### 21.3 Phase P0-A: Contract、Store、Security

- [x] **TASK-P0-101: Canonical JSON Schemaを作成する**
  - 依存: TASK-P0-006
  - 対象: contracts/osekkai/*.schema.json
  - 作業: common、Profile、Conversation、ChatResult、FreeBusy、Opportunity、Decision、Episode、Metricsを定義する
  - 完了条件: schemaVersion、ID、日時、provenance、classification、policyVersion、reasonCodesがSchemaに含まれる

- [x] **TASK-P0-102: TypeScript型を生成する**
  - 依存: TASK-P0-101
  - 対象: frontend/lib/osekkai/types.generated.ts、types.ts
  - 完了条件: npm.cmd run generate:contracts で生成でき、手書きの重複domain型がない

- [x] **TASK-P0-103: Runtime validatorを生成する**
  - 依存: TASK-P0-101
  - 対象: frontend/lib/osekkai/validators.generated.ts
  - 完了条件: build後にroot contractsを実行時参照せず、API requestとPython responseを検証できる

- [x] **TASK-P0-104: Python contract validatorを作成する**
  - 依存: TASK-P0-101
  - 対象: agents-OpenClaw/scripts/osekkai_contracts.py
  - 完了条件: 正常fixtureを受理し、必須項目欠落・未知reason code・不正型を拒否する

- [x] **TASK-P0-105: Open Data raw/normalized fixtureを作成する**
  - 依存: TASK-P0-006、TASK-P0-101
  - 対象: agents-OpenClaw/fixtures/osekkai/opportunities.raw.json、opportunities.normalized.json、opportunity-source-metadata.json
  - 完了条件: checksum、sourceUrl、dataset、license、capturedAt、fieldProvenanceがあり、rawにない事実を追加していない

- [x] **TASK-P0-106: Runtime data領域を分離する**
  - 依存: TASK-P0-001
  - 対象: OSEKKAI_DATA_ROOT、.gitignore、env example
  - 完了条件: runtime Profile・会話・EpisodeがGit追跡対象に入らず、fixtureだけが追跡可能である

- [x] **TASK-P0-107: Osekkai JSON Storeを実装する**
  - 依存: TASK-P0-101、TASK-P0-106
  - 対象: agents-OpenClaw/scripts/osekkai_store.py
  - 作業: ID検証、ユーザー単位ファイル、atomic replace、パス境界検証を実装する
  - 完了条件: Profile、Conversation、EpisodeのCRUDが一時データ領域で動く

- [x] **TASK-P0-108: プロセス間lockと冪等処理を実装する**
  - 依存: TASK-P0-107
  - 作業: read-modify-write、idempotency確認、状態更新を同じユーザーロック内で行う
  - 完了条件: 並行更新テストでlost updateと二重feedbackが発生しない

- [x] **TASK-P0-109: 連鎖削除と保持期限cleanupを実装する**
  - 依存: TASK-P0-107、TASK-P0-108
  - 対象: osekkai_cli.py profile-delete、cleanup
  - 完了条件: 対象ユーザーだけを削除し、期限内データ・他ユーザー・共有fixtureを残す

- [x] **TASK-P0-110: 匿名session Cookieを実装する**
  - 依存: TASK-P0-103
  - 対象: frontend/lib/server/osekkai-user.ts、GET /api/osekkai/session
  - 完了条件: 署名付きUUID、HttpOnly、SameSite=Strict、30日有効、本番Secure、鍵rotationが動く

- [x] **TASK-P0-111: CSRF・Origin・Content-Type検証を実装する**
  - 依存: TASK-P0-110
  - 完了条件: 正常mutationだけを許可し、foreign Origin、token欠落、期限切れtoken、不正Content-Typeを拒否する

- [x] **TASK-P0-112: Python CLI契約を実装する**
  - 依存: TASK-P0-104、TASK-P0-107
  - 対象: agents-OpenClaw/scripts/osekkai_cli.py
  - 完了条件: command allowlist、stdin/stdout envelope、exit code、stderr分離、requestId、idempotencyKeyが計画どおり動く

- [x] **TASK-P0-113: Next.js–Python bridgeを実装する**
  - 依存: TASK-P0-103、TASK-P0-112
  - 対象: frontend/lib/server/osekkai-openclaw-bridge.ts、osekkai-store.ts
  - 完了条件: shellを使わずPythonをspawnし、timeout、最大出力、Schema、exit codeを安全にHTTPエラーへ変換する

- [x] **TASK-P0-A-GATE: Contract・Store・Securityを承認する**
  - 依存: TASK-P0-101〜TASK-P0-113
  - 完了条件: contract、concurrency、path traversal、CSRF、削除、retentionの全テストが成功する

### 21.4 Phase P0-B: Profile、Conversation、Safety

- [x] **TASK-P0-201: Distance Profile初期値を実装する**
  - 依存: TASK-P0-A-GATE
  - 対象: agents-OpenClaw/scripts/osekkai_profile.py
  - 完了条件: memoryConsent=false、pushConsent=false、安全側初期値、explicit/inferred分離がSchemaどおりである

- [x] **TASK-P0-202: Profile更新と根拠管理を実装する**
  - 依存: TASK-P0-201
  - 完了条件: confidence、evidence、更新日時を保存し、明示設定を推定で上書きしない

- [x] **TASK-P0-203: remember=falseと明示pauseを実装する**
  - 依存: TASK-P0-202
  - 完了条件: 会話・推定・evidenceを保存せず、本人確認済みpauseUntilだけを保存できる

- [x] **TASK-P0-204: Safety判定を実装する**
  - 依存: TASK-P0-201
  - 対象: agents-OpenClaw/scripts/osekkai_safety.py
  - 完了条件: 診断を行わず、明示的苦痛では requiresHumanSupport=true と do_not_push を返す

- [x] **TASK-P0-205: 決定論的Conversation処理を実装する**
  - 依存: TASK-P0-202、TASK-P0-204
  - 対象: agents-OpenClaw/scripts/osekkai_chat.py
  - 完了条件: reply、profileDelta、interventionHint、confidence、safetyを返し、受入用2会話を正しく処理する

- [x] **TASK-P0-206: Profile・Conversation・Safety単体テストを作成する**
  - 依存: TASK-P0-203〜TASK-P0-205
  - 完了条件: 明示指示優先、非診断、remember=false、evidence削除、Profile全削除のテストが成功する

- [x] **TASK-P0-B-GATE: 会話学習とSafetyを承認する**
  - 依存: TASK-P0-201〜TASK-P0-206
  - 完了条件: 受入用2会話とPrivacy/Safetyテストがすべて成功する

### 21.5 Phase P0-C: FreeBusy、Opportunity、Policy、Episode

- [x] **TASK-P0-301: 合成FreeBusy fixtureを作成する**
  - 依存: TASK-P0-101
  - 対象: agents-OpenClaw/fixtures/osekkai/freebusy.json、osekkai_freebusy.py
  - 完了条件: 固定時計上の4時間の空きを返し、Calendar予定詳細を含まない

- [x] **TASK-P0-302: Opportunity normalizerを実装する**
  - 依存: TASK-P0-105
  - 対象: agents-OpenClaw/scripts/osekkai_opportunity_sync.py
  - 完了条件: raw snapshotから共通形式を生成し、AI由来項目とsource事実を分離する

- [x] **TASK-P0-303: Version付きPolicy設定を作成する**
  - 依存: TASK-P0-101
  - 対象: agents-OpenClaw/config/osekkai_policy.json
  - 完了条件: Battery閾値、Intensity上限、重み、PUSH閾値、cooldown、reason code、tie-breakが固定される

- [x] **TASK-P0-304: Guardrail-first Policyを実装する**
  - 依存: TASK-P0-201、TASK-P0-301〜TASK-P0-303
  - 対象: agents-OpenClaw/scripts/osekkai_policy.py
  - 完了条件: consent、Quiet Hours、pause、cooldown、週上限、Safety、空き、候補有無をスコアより先に評価する

- [x] **TASK-P0-305: 候補filterと1件選択を実装する**
  - 依存: TASK-P0-304
  - 完了条件: 時間、往復移動、予算、Intensity、期限、sourceを検証し、同点でも決定論的に最大1件を返す

- [x] **TASK-P0-306: Intervention Episode保存を実装する**
  - 依存: TASK-P0-304、TASK-P0-305
  - 完了条件: PUSH/no-PUSH双方、policyVersion、reasonCodes、snapshot、classificationを保存する

- [x] **TASK-P0-307: 非同意時の最小Episodeを実装する**
  - 依存: TASK-P0-306
  - 完了条件: memoryConsent=false時に会話・evidence・推定Profileを保存せず、運用上必要な最小項目だけを残す

- [x] **TASK-P0-308: Feedbackとcooldown更新を実装する**
  - 依存: TASK-P0-206、TASK-P0-306
  - 完了条件: 4反応、3距離評価、rejectionStreak、cooldown、show_another、pushCadenceDeltaが計画どおり動く

- [x] **TASK-P0-309: KPI計算を実装する**
  - 依存: TASK-P0-306、TASK-P0-308
  - 対象: agents-OpenClaw/scripts/osekkai_metrics.py
  - 完了条件: EpisodeからJust-Right、Overreach、Under-Support、承諾率を再計算し、分母ゼロをnullにする

- [x] **TASK-P0-310: デモrunnerを実装する**
  - 依存: TASK-P0-301〜TASK-P0-309
  - 対象: agents-OpenClaw/scripts/osekkai_run.py
  - 完了条件: 固定UUID・固定時計・snapshotで、外部通信なしに同一結果を返す

- [x] **TASK-P0-311: Policy・Episode・Metricsテストを作成する**
  - 依存: TASK-P0-304〜TASK-P0-310
  - 完了条件: 第14.1節のguardrail、candidate、feedback、KPI、再現性テストがすべて成功する

- [x] **TASK-P0-C-GATE: Agent coreを承認する**
  - 依存: TASK-P0-301〜TASK-P0-311
  - 完了条件: 最初はdo_not_push、次は候補1件、候補なしでは生成しない中心判断がCLIで完走する

### 21.6 Phase P0-D: APIとUI

- [x] **TASK-P0-401: Profile・Chat APIを実装する**
  - 依存: TASK-P0-B-GATE、TASK-P0-113
  - 対象: /api/osekkai/chat、/api/osekkai/profile
  - 完了条件: GET/PATCH/DELETE/POSTがSchema・Cookie・CSRFを通してPython SSOTへ接続する

- [x] **TASK-P0-402: Signal・Decision APIを実装する**
  - 依存: TASK-P0-C-GATE、TASK-P0-113
  - 対象: /api/osekkai/freebusy、opportunities、decide
  - 完了条件: ブラウザ入力のProfileや候補を信用せず、サーバー側providerとstoreから判断する

- [x] **TASK-P0-403: Intervention・Feedback・Metrics APIを実装する**
  - 依存: TASK-P0-C-GATE、TASK-P0-113
  - 対象: /api/osekkai/interventions、feedback、metrics
  - 完了条件: 状態遷移、冪等feedback、classification付きKPIを返す

- [x] **TASK-P0-404: Demo seed/reset APIを実装する**
  - 依存: TASK-P0-110〜TASK-P0-113、TASK-P0-310
  - 対象: /api/osekkai/demo/seed、/api/osekkai/demo/reset
  - 完了条件: seedは完全未使用状態だけを原子的・非破壊で準備し、resetはdemo modeかつ確認済み現sessionだけを削除・再作成し、本番では404を返す

- [x] **TASK-P0-405: TypeScript API clientを実装する**
  - 依存: TASK-P0-401〜TASK-P0-404
  - 対象: frontend/lib/osekkai/api.ts、errors.ts
  - 完了条件: session初期化、CSRF header、runtime validation、共通エラー、no-storeを処理する

- [x] **TASK-P0-406: Route-aware SiteChromeを実装する**
  - 依存: TASK-P0-004
  - 対象: frontend/app/site-chrome.tsx、layout.tsx
  - 完了条件: /osekkaiだけ専用header、既存routeは従来headerを表示する

- [x] **TASK-P0-407: /osekkaiトップを実装する**
  - 依存: TASK-P0-405、TASK-P0-406
  - 完了条件: 正式表記・指定コピー・会話CTA・デモCTA・disabledのCalendar P1表示がある

- [x] **TASK-P0-408: Chat画面を実装する**
  - 依存: TASK-P0-401、TASK-P0-405
  - 完了条件: 会話、Social Battery、学習差分、送信前remember切替、記憶表示・個別削除が動く

- [x] **TASK-P0-409: Settings画面を実装する**
  - 依存: TASK-P0-401、TASK-P0-405
  - 完了条件: 同意、頻度、Quiet Hours、強さ、口調、移動、予算、休止、全削除が動く

- [x] **TASK-P0-410: Demo画面を実装する**
  - 依存: TASK-P0-402〜TASK-P0-405
  - 完了条件: fresh時の非破壊seed、確認付きreset、12段階中心デモ、実参加・再訪シミュレーションをオフラインで実行できる

- [x] **TASK-P0-411: Impact画面を実装する**
  - 依存: TASK-P0-403、TASK-P0-405
  - 完了条件: PUSH/no-PUSH理由、Episode、実測/参考推計/デモシナリオ/未検証の日本語ラベルを表示する

- [x] **TASK-P0-412: Osekkai専用CSSとアクセシビリティを実装する**
  - 依存: TASK-P0-407〜TASK-P0-411
  - 対象: frontend/app/osekkai/osekkai.module.css
  - 完了条件: 既存CSSへ波及せず、label、focus、aria-live、keyboard、mobile表示を確認できる

- [x] **TASK-P0-413: frontend unit/component testを作成する**
  - 依存: TASK-P0-405〜TASK-P0-412
  - 完了条件: API client、SiteChrome、Chat、Settings、Demo stepper、KPI分類表示のテストが成功する
  - 検証: Chat、Settings、fresh 12/12 Demo、reset確認、Impact canonical KPIを直接renderし、全17 files/80 testsが成功

- [x] **TASK-P0-D-GATE: UI/API統合を承認する**
  - 依存: TASK-P0-401〜TASK-P0-413
  - 完了条件: 5画面、専用API、Profile削除、12段階デモがブラウザで動く

### 21.7 Phase P0-E: 検証と引き渡し

- [x] **TASK-P0-501: Python検証を完走する**
  - 依存: TASK-P0-D-GATE
  - 完了条件: compileall、unittest、contract validation、demo runnerが成功する
  - 検証: compileall成功、69 tests成功、16 schemas/8 instances成功、runner 12/12成功

- [x] **TASK-P0-502: Frontend検証を完走する**
  - 依存: TASK-P0-D-GATE
  - 完了条件: npm.cmd ci、generate:contracts、typecheck、lint、test、buildが成功する
  - 検証: ci成功、contract生成2回同一、typecheck/lint成功、17 files/80 tests成功、Next.js 16.3.2 production build成功

- [x] **TASK-P0-503: 12段階デモをブラウザ検証する**
  - 依存: TASK-P0-501、TASK-P0-502
  - 完了条件: 外部networkを遮断し、fresh seedまたは確認付きresetからimpact更新まで同じ結果で完走する
  - 検証: fresh Cookie、手動resetなし、外部HTTPS abortで12/12。通信先は127.0.0.1のみ、page error 0件

- [x] **TASK-P0-504: Privacy/Security negative testを実行する**
  - 依存: TASK-P0-501、TASK-P0-502
  - 完了条件: CSRF、foreign Origin、path traversal、他ユーザー削除、不正Schema、demo reset本番拒否を確認する
  - 検証: live HTTPで403/403/415/413/400の厳密no-store error、Pythonでpath/他user、productionでdemo reset 404を確認

- [x] **TASK-P0-505: 既存routeの退行確認を実行する**
  - 依存: TASK-P0-502
  - 完了条件: /、/tomo、/staff、/conversation、/casesが残り、legacy/Osekkai headerが正しく分かれる
  - 検証: production HTTP 200、実ブラウザlegacy chrome、build manifestのdynamic routeを確認

- [x] **TASK-P0-506: 禁止依存を確認する**
  - 依存: TASK-P0-502
  - 完了条件: /osekkaiからWorld、NEAR、PublicCase、case_ingest、Talking Photoをimport・callしていない

- [x] **TASK-P0-507: READMEとenv exampleを更新する**
  - 依存: TASK-P0-501〜TASK-P0-506
  - 完了条件: 起動、環境変数、デモ、データ分類、制約、P1未実装が事実どおり記載される

- [x] **TASK-P0-508: 実装報告を作成する**
  - 依存: TASK-P0-507
  - 完了条件: 第20節の10項目と実際のテスト結果を報告する

- [x] **TASK-P0-GATE: P0を最終承認する**
  - 依存: TASK-P0-501〜TASK-P0-508
  - 完了条件: 第19節の全チェックが [x] になり、未実行テストや架空効果表示がない
  - 承認注記: code/product受入は完了。TASK-P0-001の変更前backup証跡だけは後付け不能な履歴上の例外として残し、既知の制約に明記する

### 21.8 P1 Taskバックログ

以下はTASK-P0-GATE完了後に開始します。

- [ ] **TASK-P1-001: P1のsource・provider・運用判断を確定する**
  - 依存: TASK-P0-GATE
  - 完了条件: 第17節の未決事項のうち、対象Taskに必要な判断が文書化される

- [ ] **TASK-P1-002: Assessment・Outcome・Third Place・Role Schemaを追加する**
  - 依存: TASK-P1-001
  - 完了条件: P1 canonical schema、生成型、validator、保存先、test fixtureがそろう

- [ ] **TASK-P1-003: ユーザー別Google OAuthを実装する**
  - 依存: TASK-P1-001
  - 完了条件: state、PKCE、暗号化token store、connect/callback/disconnect、削除・失効が動く

- [ ] **TASK-P1-004: Google FreeBusyを実装する**
  - 依存: TASK-P1-003
  - 完了条件: freebusy.queryだけを使い、保存物にタイトル・説明・参加者・場所・busy詳細がない

- [ ] **TASK-P1-005: Open Data live syncを実装する**
  - 依存: TASK-P1-001、TASK-P1-002
  - 完了条件: 1自治体と東京都公共施設をPython ownerで同期し、license、provenance、期限を検証する

- [ ] **TASK-P1-006: Maps移動可能性を実装する**
  - 依存: TASK-P1-001、TASK-P1-005
  - 完了条件: 同意済み生活圏からの往復時間を計算し、Free Window内到着を検証する

- [ ] **TASK-P1-007: Telegram PUSHとcallbackを実装する**
  - 依存: TASK-P1-001、TASK-P1-005、TASK-P1-006
  - 完了条件: 本人紐付け、4反応、再送、失敗Episode、署名付きcallbackが動く

- [ ] **TASK-P1-008: Schedulerを実装する**
  - 依存: TASK-P1-004〜TASK-P1-007
  - 完了条件: Profile→FreeBusy→Opportunity→Maps→Policy→Episode→PUSHを同時実行制御付きで処理する

- [ ] **TASK-P1-009: 参加・再訪・Third Place・Roleを実装する**
  - 依存: TASK-P1-002、TASK-P1-008
  - 完了条件: 実データ分類で承諾率、実参加率、再訪率、自発予定登録率、Third Place、Role KPIを計測できる

- [ ] **TASK-P1-010: UCLA-3 Assessmentを実装する**
  - 依存: TASK-P1-002、TASK-P1-001
  - 完了条件: 明示同意、baseline/week 4/week 8、削除、未検証表示が動く

- [ ] **TASK-P1-011: 公式支援先設定を実装する**
  - 依存: TASK-P1-001
  - 完了条件: 公式source、更新責任、最終確認日があり、未確認の連絡先を表示しない

- [ ] **TASK-P1-012: P1統合・Privacy・外部障害テストを実行する**
  - 依存: TASK-P1-003〜TASK-P1-011
  - 完了条件: token分離、FreeBusy最小化、source provenance、API障害fallback、Telegram冪等性が検証される

- [ ] **TASK-P1-GATE: P1を最終承認する**
  - 依存: TASK-P1-001〜TASK-P1-012
  - 完了条件: liveとdemoを混同せず、P1 KPIと外部連携が同意・削除・障害テストを通る

### 21.9 P2 Taskバックログ

以下はTASK-P1-GATE完了後に開始し、研究・行政利用の承認を別途必要とします。

- [ ] **TASK-P2-001: 指標・研究・倫理要件を確定する**
  - 依存: TASK-P1-GATE
  - 完了条件: Graduation、Access Gap、比較実験、孤独指標、同意、保持、利用目的が定義される

- [ ] **TASK-P2-002: 匿名集計と管理者認証を実装する**
  - 依存: TASK-P2-001
  - 完了条件: 個票を表示せず、最小集計人数、アクセス制御、監査ログが動く

- [ ] **TASK-P2-003: Tokyo Connection Access Gapを実装する**
  - 依存: TASK-P2-001、TASK-P2-002
  - 完了条件: 町丁目別供給指標を匿名・集計済みデータだけで計算する

- [ ] **TASK-P2-004: Fixed対Adaptive比較とMRTログを実装する**
  - 依存: TASK-P2-001、必要な倫理承認
  - 完了条件: 割付、介入確率、exposure、outcome、withdrawalを再現可能に記録する

- [ ] **TASK-P2-005: Graduation・孤独関連KPIを実装する**
  - 依存: TASK-P2-001、TASK-P2-004
  - 完了条件: 実測・参考推計・未検証を分離し、対照群なしに効果を主張しない

- [ ] **TASK-P2-GATE: P2を最終承認する**
  - 依存: TASK-P2-001〜TASK-P2-005
  - 完了条件: Privacy、倫理、統計レビューを通り、行政画面が匿名集計だけを表示する
