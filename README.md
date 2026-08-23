# おっせかいおばさん

**Current Version — Three-Distance Judge Demo + LLM Memory + Chiyoda Fast Map Build 2026-08-23**

[スライドを見る](https://canva.link/uro4qx4tm4llm9n) · [PVを見る](https://www.youtube.com/watch?v=me60PvZPABQ)

東京都の孤独課題に対して、利用者を「人とつながる可能性のある実在の場」へ一歩だけ後押しするプロアクティブAIです。

話した好みと反応を覚え、Calendar、移動時間、料金、対人負荷に収まる実在Eventを、選びやすい複数候補へ絞ります。利用者自身は、推薦対象に限らず、現在のDemo対象である千代田区の取得Eventを地図で探せます。

## 解決したいこと

一般的なEvent検索は「何に行くか」を利用者自身に探させます。孤独状態では、その検索、比較、予定調整、移動判断自体が負担になります。

おっせかいおばさんは、次の処理をOpenClawで継続実行します。

1. 東京都内の最新Eventを複数Sourceから更新
2. 会話、共同活動、継続参加などのConnection Evidenceを確認
3. 利用者の好み、参加形式、過去の反応を照合
4. Google Calendarの空き時間をFreeBusyで確認
5. Google Routesで実移動時間を確認
6. 条件に合う複数候補を、おせっかいだが押しつけすぎない言葉と推薦理由付きで提案
7. `行ってみる / これは違う / 今回は無理 / 次回も知らせて`と参加後の会話から次の提案を学習

単に図書館、公園、展示へ外出させるアプリではありません。孤独の緩和につながる会話・共同活動・再参加の可能性を説明できるEventを対象にします。

## 現在版の体験

最初から長い質問票は出しません。標準設定で始まり、おっせかいおばさんが必要なことを一度に1つだけ聞きます。ヨガ、ボルダリング、料理、音楽などの好みと、初参加、大人数、会話量、移動、料金などのひっかかりを自然な言葉から分けて理解します。記憶への同意がある場合だけ、判断用のProfile Storeと、人が読める短いObsidian Memoryへ根拠付きで蓄積します。

Today、Memory、Whyといった内部判断パネルは通常の会話画面に表示しません。保存された好みの確認・個別削除、通知時間、移動時間、予算、言葉の強さは、必要な人だけが設定画面の詳細を開いて変更できます。`今日は何もしない`は安全・Feedbackの選択肢として残しますが、ホームや最初の会話では前面に出しません。

`話す`では、関連する過去の反応だけを参照し、CalendarとRoutesに収まる実Eventを2〜3件提示します。断られた時だけ「何がひっかかった？」と一問だけ聞き、候補と誘い方を一度だけ調整します。LLMは自由な言い回しの理解と自然な返答を担いますが、Event選択、Calendar、Routes、Safety、PUSH可否は既存Engineが決め、根拠のないEvent情報は返答へ入れません。`行ってみる`を選ぶとEvent終了後の活動時間に短いCheck-inへつながり、その回答が次の順位や言葉へ反映されます。

先回り会話は、Google Calendarの次の7日間に長いFree Windowがあり、PUSH同意・Quiet Hours・週次上限・Cooldown・Safetyを満たし、再検証できた実Eventが複数ある時だけ始まります。Calendarから取得するのはFreeBusyだけで、予定名や「家にいる」といった推測には使いません。本人が`話す`を開いた時はCalendarが疎くなくても会話でき、未完了の候補選びや期限が来たCheck-inから再開します。Live Dataの詳細は[Plan2.md](Plan2.md#132-実行順task-queue)、自然な会話と長期記憶は[Plan3.md](Plan3.md#10-実行順task-queue)に記録しています。

## 現在の実装状態

### 実装・自動検証済み

- Next.jsの`/osekkai` UI、`/api/osekkai` API、匿名Session、記憶・通知同意、休止、全削除
- PythonをownerとするProfile、Distance Profile、Policy、Safety Guardrail、判断記録、Feedback、KPI
- JSON Schema 35件を正本とするPython–TypeScript Contractと生成validator
- 東京都Open Data CKAN、許可されたLu.ma iCal、Doorkeeper API、公共文化施設公式SiteのProvider adapter
- Event / Series / Community / Source Registry、重複統合、鮮度・募集状態、Connection Evidence
- Calendar OAuthのstate・PKCE・匿名session紐付け、暗号化token、FreeBusyだけを使うCalendar adapter
- Google Routesの徒歩・公共交通・住所解決、往復・滞在・bufferを含む実現可能性判定
- Sourceごとの更新間隔、lock、retry/backoff、障害分離、PUSH直前再検証を行うScheduler
- 優先順位付きの複数候補、根拠、Source状態、CTAを表示するLive Demo UI
- GoogleログインやBackendなしでも、実Event snapshot 4件、合成FreeBusy、記録済みRoutesを使い、`誘う / 引く / 続ける`を選んで完走できる静的Judge Demo
- `引く`StoryではCalendarが空いていても`今日は疲れた`を優先して候補を出さず、`続ける`Storyでは参加後の希望から継続講座へ順位を変える距離学習
- Conversation Episodeの9状態、Calendar Trigger、11種のParticipation FrictionとEvidence優先・減衰Rule
- `話す`内で完結する`複数候補 → 一問だけの理由確認 → 一度だけ調整 → 参加選択 → Event後Check-in`
- OpenAI Responses APIによる構造化理解とGrounding済み返答、timeout・quota・不正応答時の固定文Fallback
- 利用者別Obsidian Vaultへの短いMemory Note、関連検索、同意OFF、個別削除、全削除、retention
- 麹町を初期表示し、千代田区の住所・座標を確認できたEventを250件ずつ段階取得するMapと一覧fallback
- Map上の明示操作でBrowser Geolocationを一時取得し、選択EventのRoutes計算にだけ使う位置情報導線
- 再現可能なJudge Demo・P0オフラインデモと、Live Provider fixtureを使う統合テスト

### 2026-08-23の実接続確認

- Google Cloud Billingの有効化、Calendar OAuth / FreeBusy、Google Routes / Geocoding、Google Maps JavaScriptの実接続を確認
- 許可されたLu.ma iCalから50 Event、Doorkeeper APIから25 EventをLive取得
- Credential不要経路では東京都CKAN 5 dataset、江東区文化コミュニティ財団公式Site 169開催回を取得
- 実Provider 4系統から239 Eventを統合し、鮮度・募集状態・Connection Evidenceで91件を適格化、Google Routesで8件の実移動時間を確認
- Doorkeeperの長文説明はSource全文への導線を残して表示上限へ収め、1件の異常データでLive同期全体を止めない。現在は推薦可能7件
- 文京区公式CSV 1件は外部URLの取得に失敗しているためSource Errorとして明示し、そのEventをLive PUSHへ混ぜず他Sourceを継続
- 実Google FreeBusy、実Routes、好みを使うPolicyの通し確認で、標準設定から優先順位付き3候補を生成
- 実LLMで自由文の好み・参加障壁の構造化と自然な返答を確認し、LLM OFFでも同じ会話経路を完走
- 料金がSourceで確認できないEventは無料と推定せず`料金未確認`と表示し、遠すぎる経路や根拠不足のEventは推薦から除外
- Sourceの強制再同期を毎画面表示から外し、通常表示は保存済みLive Cacheを読む

### 次に行うこと

個別ProviderとGoogle実接続、実データを使う複数候補生成、Calendarの疎な期間から始まる先回り会話、自由文の参加障壁に応じた一度だけの再提案、参加後Check-in、次回へ戻るObsidian Memoryまで実装済みです。審査用の`/osekkai/demo`は外部接続に依存せず、`誘う / 引く / 続ける`の各Storyを個別に短く再生できます。Vercel上でProviderやPythonが停止しても、空き時間から趣味を聞く、疲れた日は追わない、参加後は再会できる継続Eventを上げる、という価値仮説を確認できます。次はGoogle Calendar接続済みの`/osekkai/chat`でLive経路を最終リハーサルし、Demo当日のSource件数、Routes quota、Maps key制限、候補2件以上を確認します。継続運用では外部Task Scheduler / cronからSource同期、Calendar Trigger、Maintenanceを定期起動します。

Live Dataの依存関係は[Plan2.md](Plan2.md#131-task運用ルール)、LLMとObsidianの実装・検証記録は[Plan3.md](Plan3.md#14-実装検証記録)を正本とします。Credentialがない機能を接続済みとは表現しません。

## 設計の考え方

東京都Open Dataは画面を飾る一覧ではなく、開催日時、場所、主催、対象、継続性を判断する土台です。そこへLu.ma、Doorkeeper、公共施設公式情報などの現在データを重ね、Event / Series / Community、Connection Evidence、本人の反応を統合します。CalendarとMapsは「実際に行けるか」を確かめる制約であり、それだけで推薦を成立させません。Source URL、取得時刻、欠損、stale、canceled、sold outも残し、データの弱点を隠しません。

中心にあるのはEvent検索ではなく、本人ごとに「どんな誘われ方なら一歩動けるか」を学ぶDistance Profileです。好みだけでなく、少人数か大人数か、会話か共同作業か、許容できる移動、断った理由、参加後の感想を少しずつ覚えます。候補を一つへ決めつけず、理由の異なる複数案と断れる選択肢を残します。

判断経路は`Conversation Episode → Attraction / Participation Friction → Live Data → Connection判定 → FreeBusy → Routes → Safety Guardrail → PUSH Policy → Check-in`としてつながっています。不透明な自動最適化を最初から入れず、明示Policy、Feedback蓄積、オフライン評価、安全制約付き最適化の順に育てます。

成果はClickだけでは測りません。参加、再参加、自発的な外出、同じCommunityとの継続接点を追い、本人同意が得られる段階で孤独尺度も扱います。実測、推計、仮定を分離し、個人の変化を東京都全体の金額へ安易に外挿しません。匿名・集計できる段階では、時間、距離、料金、交流形式による参加障壁や、接点が不足する地域を施策改善へ返せます。

画面上で本人を「孤独な人」と決めつけません。通知頻度、Quiet Hours、言葉の強さ、移動時間、料金、対人負荷、休止を本人が変更でき、記憶は確認・個別削除・全削除できます。利用を続けさせることだけを成功とせず、本人が自分から参加先を見つけられるようになり、おせっかいが不要になることも成功として扱います。

## Event Map

`/osekkai/map`はDemoの初期範囲を千代田区に絞り、麹町を中心とするGoogle MapをEvent APIより先に描画します。東京都全件はBrowserへ送らず、住所で千代田区と確認でき、座標を持つEventだけを軽量な専用APIから最大250件ずつ段階取得します。PUSHはConnection Evidenceで厳選しますが、区内Mapでは推薦外のEventも隠しません。

- 既定表示は`すべて`。`今日 / 今週末 / 30分以内 / ひとり参加可 / 継続あり / Networking / みんなで食事 / おすすめのみ`で任意に絞り込み
- Markerから開催時刻、実移動時間、料金、募集状態、Connection Level、交流根拠、Source、更新時刻を確認
- Policyが選んだ複数候補を順位と推薦理由付きで表示し、他のEventと区別
- Connection EvidenceがないEventも`交流根拠未確認`または`推薦対象外`として表示
- sold out、canceled、expired、stale、情報欠損も状態を付けて表示し、申込CTAを無効化
- 同一Eventの複数Sourceは1つのMarkerへ統合し、すべてのSourceを詳細で確認可能
- 正確な現在地は明示操作時だけ選択Eventの移動時間計算に利用し、Profileやlogへ永続保存しない
- 座標がない区内Eventは件数を表示し、Browserで大量Geocodingを実行して初期描画を止めない
- Event APIや推薦履歴が失敗してもGoogle Map本体は表示したままにする

Mapは`/osekkai/map`に実装済みです。Maps keyがない場合は取得できた千代田区Eventを一覧fallbackで閲覧でき、Event APIが失敗した場合も地図操作は維持します。東京都全域への再拡張は、Server側の空間検索またはtile APIを導入してから行います。

## 利用予定のデータ

| Source | 用途 | Plan2上の扱い |
|---|---|---|
| 東京都Open Data CKAN | 東京都・自治体が公開する最新Event | 必須・Credential不要・同期確認済み |
| Lu.ma公開Event | Community、趣味、Networking | 必須・許可されたiCalから同期確認済み |
| Doorkeeper公開Event | 継続Community、勉強会 | 必須・APIから同期確認済み |
| 公共文化施設の公式情報 | ワークショップ、交流・参加型企画 | 必須・KCF公式Site同期確認済み |
| connpass | 技術Community | Optional |
| Peatix | 主催者許諾のある取込導線 | Optional。無断scrapingを前提にしない |
| 共食・食事会Provider | みんなで食べる接点 | 規約と取得方法を確認後にOptional接続 |

取得できることと、孤独解消に適したことは別です。各Eventについて、Source URL、取得時刻、開催状態、交流形式、継続性を検証してから候補へ入れます。

## Repository構成

```text
frontend/
  app/osekkai/             UI
  app/api/osekkai/         HTTP API
  components/osekkai/      既存UIロジック
  lib/osekkai/             生成型・validator・API client
  lib/server/osekkai-*     Next.js–Python境界

agents-OpenClaw/
  scripts/osekkai_*        Event取得・判断・LLM・Memory・CLIのowner
  fixtures/osekkai/        Judge Story、P0、Providerの再現データ
  config/osekkai_policy.json
  tests/test_osekkai_*.py

contracts/osekkai/         JSON Schemaの正本
Plan2.md                   Live Demo実装Taskの正本
Plan3.md                   LLM会話・Obsidian Memory実装記録
PLAN.md                    P0の設計・実装履歴
Tokyo_Social_Calibration.pdf
                           課題背景と価値仮説
archive/tomo-san/          旧資産の退避領域（Git追跡外）
```

`archive/tomo-san/`は削除していませんが、Active productからは隔離しています。Tomo-san復元の明示依頼がない限り、実装、検索、importの対象にしません。

## ローカル起動

Node.js 20.9以上、npm、Python 3.11以上を使用します。リポジトリ直下からPowerShellで実行してください。

```powershell
python -m pip install -r agents-OpenClaw\requirements.txt
Set-Location frontend
Copy-Item .env.example .env
npm.cmd ci
npm.cmd run dev
```

ブラウザで`http://localhost:3000/`を開くと`/osekkai`へ移動します。`/osekkai/demo`がBackend非依存のJudge用Demo、`/osekkai/chat`が実接続を使う会話、`/osekkai/map`が麹町中心・千代田区限定のEvent Mapです。

`/osekkai/demo`の閲覧にはCredentialもBackendも不要です。Eventは取得日時付きSource snapshot、Routesは記録済み実計算値、Calendarは合成FreeBusy、会話は決定論的な再現として画面内で区別します。`.env`の既定値`OSEKKAI_DEMO_MODE=true`は、その他のAPIを外部接続なしで確認するP0設定です。Live経路は次の設定後に`OSEKKAI_DEMO_MODE=false`へ変更します。既に`.env`がある場合は上書きせず、そのファイルを編集してください。

## Live Demo設定

### 1. Google Cloud

1. 使用するGoogle Cloud projectへBilling Accountをリンクする
2. Calendar API、Routes API、Geocoding API、Maps JavaScript APIを有効化する
3. OAuth consent screenを構成し、Web application OAuth Clientを作る
4. Authorized redirect URIへ`http://localhost:3000/api/osekkai/calendar/callback`を完全一致で登録する
5. Routes/Geocoding用のserver keyとMaps JavaScript用のbrowser keyを分ける
6. server keyは使用APIとserver側の制限、browser keyはMaps JavaScript APIとHTTP referrerへ制限する

本アプリが要求するCalendar scopeは`https://www.googleapis.com/auth/calendar.freebusy`だけです。予定のtitle、description、location、attendeesは要求・保存しません。

Demo projectではBilling Accountのリンクと必要APIの有効化を確認済みです。別projectへ移す場合だけ1〜6を再実施してください。課金を伴う紐付けをアプリから自動実行しません。

### 2. `.env`

`frontend/.env.example`を`frontend/.env`へコピーし、少なくとも次を設定します。秘密値はcommitしません。

```dotenv
OSEKKAI_DEMO_MODE=false
OPENAI_API_KEY=...
OSEKKAI_LLM_PROVIDER=openai
OSEKKAI_LLM_MODEL=gpt-5.4-mini
OSEKKAI_LLM_TIMEOUT_SECONDS=7
# 任意。未設定時はOSEKKAI_DATA_ROOT/obsidian-vault
OSEKKAI_VAULT_ROOT=
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:3000/api/osekkai/calendar/callback
OSEKKAI_CREDENTIAL_ENCRYPTION_KEY=...
GOOGLE_ROUTES_API_KEY=...
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=...
OSEKKAI_LIVE_ORIGIN_LATITUDE=35.xxxx
OSEKKAI_LIVE_ORIGIN_LONGITUDE=139.xxxx
LUMA_ICAL_URL=https://...
DOORKEEPER_API_TOKEN=...
```

暗号化keyはPowerShellから生成できます。

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`OSEKKAI_LIVE_ORIGIN_*`はLive推薦確認用の大まかな出発地点です。Mapで利用者が明示取得する正確な現在地とは別で、Browserの座標はProfileやlogへ保存しません。

`OPENAI_API_KEY`はserver-onlyでPython child processへ渡し、BrowserやAPI responseへ露出しません。Keyがある時はLLMが有効になり、停止する場合は`OSEKKAI_LLM_ENABLED=false`を設定します。LLM障害時は固定文Fallbackへ切り替わるため、Calendar、Routes、Event提案は継続します。

### 3. Live同期と確認

`frontend/.env`はPython CLIへ自動読込されないため、CLI単体で運用する場合は同じ値をprocess environmentへ設定します。Webアプリから実行する場合はNext.js bridgeが必要な値だけをallowlistでPythonへ渡します。

```powershell
Set-Location agents-OpenClaw
python scripts/osekkai_cli.py sources-sync --json --force
python scripts/osekkai_cli.py sources-status --json
python scripts/osekkai_cli.py events --json
python scripts/osekkai_cli.py opportunities --live --json
```

Webを起動したら、審査用Storyはそのまま`/osekkai/demo`で再生できます。実接続は`/osekkai/settings`でGoogle Calendarを接続し、`/osekkai/chat`から会話を始めます。Mapは`/osekkai/map`を開くと麹町から先に表示され、必要な時だけ`千代田区Eventを更新`を押します。

Schedulerは上の`source-sync`を各Sourceのrefresh間隔より短い外部cron/Task Schedulerから呼べます。内部でinterval判定、Source lock、bounded retry/backoffを行うため、1 Sourceの停止で他Sourceを止めません。PUSH直前にも選ばれたEventだけを再検証し、stale、取消、満席、検証不能なら推薦から外します。

Google設定の一次資料:

- [Cloud Billingをprojectへ有効化・変更](https://docs.cloud.google.com/billing/docs/how-to/modify-project)
- [Web server OAuthとredirect URI](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Calendar FreeBusy queryとscope](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query)
- [Routes APIの利用とBilling](https://developers.google.com/maps/documentation/routes/usage-and-billing)
- [Maps API keyの制限](https://developers.google.com/maps/api-security-best-practices)

## Source運用・Attribution・既知の制約

Source定義の正本は`agents-OpenClaw/config/osekkai_sources.json`です。各EventにSource URL、取得・更新・再検証時刻、classification、checksumを保存し、画面から原典へ戻れるようにします。

- 東京都Open Dataはdatasetごとのlicenseと提供者表記を引き継ぎます。catalogの検索結果だけでEventを捏造しません
- Lu.maは利用者または主催者から利用許可を得たiCal URLだけを取り込みます。公開ページの無断scrapingはしません
- DoorkeeperはAPI tokenと[利用規約](https://www.doorkeeper.jp/terms)に従い、Event/CommunityのSourceへlink backします
- KCFは公式講座ページの事実項目を取得し、公益財団法人江東区文化コミュニティ財団を表示して原文へlink backします。本番継続運用前に取得頻度と利用条件を主催者へ再確認します
- Peatix、共食Service、connpassは取得権限が確定していないため、Live Demo必須経路へ混ぜません

Providerの規約や画面構造は変更されます。parser失敗、429、timeout、Credential不足はSource単位の状態として表示し、最後に正常取得したEventを無期限にLive扱いしません。Mapにはstale等の状態を付けて残せますが、PUSHは再検証できない時点でfail closedです。

現在のJSON file store、instance-local rate limit、外部cronはハッカソンDemo規模の構成です。複数instanceの本番運用では共有DB/queue/rate limit、監視、backup、Google OAuth consent screenの公開要件、Providerとの利用合意を別途整備する必要があります。

## 検証

Frontend:

```powershell
Set-Location frontend
npm.cmd run generate:contracts
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

Python:

```powershell
Set-Location agents-OpenClaw
python -m compileall scripts tests
python -m unittest discover -s tests -p "test_osekkai_*.py" -v
python scripts/osekkai_judge_demo.py --check
python scripts/osekkai_contracts.py --validate-all
```

## Data・Privacy原則

- synthetic、過去snapshot、Live、AI Derived、Organizer Verifiedを同じ表示へ混ぜない
- CalendarはFreeBusyだけを使用し、予定タイトル、説明、場所、参加者を取得・保存しない
- 現在地は明示操作時だけ取得し、正確な座標を永続保存しない
- 根拠のない`一人参加OK`、`次回あり`、定員、交流形式を生成しない
- LLMへVault全体、Calendar予定内容、正確な現在地、token、API keyを送らない
- Obsidian Memoryは同意がある短い要約だけを保存し、個別削除・全削除・retentionを適用する
- 候補がなければ0件を返し、架空EventでDemoを成立させない
- 本サービスを医療診断・治療として表現しない

PV・Demo動画の制作、編集、書き出しはユーザー側の作業であり、本Repositoryの実装完了Gateには含めません。製品UIが動画内の主張と一致することはLive Demo Gateで確認します。
