# おっせかいおばさん（ねえさん）

PV Movie


東京都の孤独課題に対して、利用者を「人とつながる可能性のある実在の場」へ一歩だけ後押しするプロアクティブAIです。

本人の好みをそのまま反復するのではなく、好みに隣接する少し意外なEventから、Calendar、移動時間、料金、対人負荷に収まる1件を選びます。利用者自身が現在地周辺の交流Eventを地図で探す導線も提供します。

## 解決したいこと

一般的なEvent検索は「何に行くか」を利用者自身に探させます。孤独状態では、その検索、比較、予定調整、移動判断自体が負担になります。

おっせかいおばさんは、次の処理をOpenClawで継続実行することを目指します。

1. 東京都内の最新Eventを複数Sourceから更新
2. 会話、共同活動、継続参加などのConnection Evidenceを確認
3. 利用者の好みと、はまりそうな隣接ジャンルを照合
4. Google Calendarの空き時間をFreeBusyで確認
5. Google Routesで実移動時間を確認
6. 条件に合う1件だけを、おせっかいだが押しつけすぎない言葉で提案
7. `行ってみる / これは違う / 今回は無理 / 次回も知らせて`から次の提案を学習

単に図書館、公園、展示へ外出させるアプリではありません。孤独の緩和につながる会話・共同活動・再参加の可能性を説明できるEventを対象にします。

## 現在の実装状態

### 実装済み：P0ローカルデモ

- Next.jsの`/osekkai` UIと`/api/osekkai` API
- PythonをownerとするProfile、Policy、保存、判断、Feedback、KPI
- JSON Schemaを正本とするPython–TypeScript間Contract
- 匿名Session、記憶同意、Quiet Hours、休止、全削除、保持期間
- 固定fixtureによる再現可能なオフラインデモ
- 合成Free Window、合成移動時間、過去Open Data snapshotを明示したP0表示

### これから実装：Live Demo

- 東京都Open Data CKAN、Lu.ma、Doorkeeper、公共文化施設などの最新Event同期
- Event / Series / Community / Source Registryと重複・鮮度管理
- 孤独解消につながるConnection EvidenceとPersonal Fit判定
- Google OAuthとCalendar FreeBusy実接続
- Google Routesによる徒歩・公共交通の実移動時間
- OpenClaw Schedulerによる定期更新とPUSH直前再検証
- 現在地または指定地域から探せるGoogle Maps Event Map
- Live Source、最終更新時刻、交流根拠を示すJudge向け1件PUSH画面

詳細な依存関係、対象ファイル、完了条件、検証方法は[Plan2.md](Plan2.md#131-task運用ルール)を正本とします。現在のTaskが完了するまで、Live接続済みとは扱いません。

## 都知事杯5評価基準に対する設計

都知事杯の公式5評価基準を、機能の有無ではなく「課題解決までつながっているか」を確認する設計レビューに使います。リリース判定では各基準を20点、合計100点で内部採点しますが、**これは公式の配点ではなく、本チームの内部チェック用です**。

### 1. データ活用

東京都Open DataはEvent一覧を飾るためではなく、開催日時、場所、主催、対象、継続性などを推薦判断へ実際に使います。CalendarとMapsは「行けるか」を確かめる制約であり、それだけで推薦を成立させません。Event / Series / Community / Source、Connection Evidence、本人のDistance Profileを統合し、「近い人気Event」ではなく「この人が関係を作れる可能性のある場」という新しい判断を作ります。

Source URL、取得時刻、欠損、stale、canceled、sold outも表示・除外理由として保持し、データの弱点を隠しません。本人の同意と匿名・集計を前提に、参加を妨げた時間、距離、料金、交流形式や、地域ごとの接点不足を東京都・主催者へ返せる設計にします。

### 2. アイデア力

中心にある発明はEvent推薦そのものではなく、本人ごとに「おせっかいの距離感」を学ぶDistance Profileです。「誰かとつながりたいが、探す・決める・失敗するのは面倒」という矛盾を、候補を1件に絞り、断り方まで用意することで解きます。好み、少しずらした提案、反応、参加、再参加を継続的に学び、単発の検索体験ではなく関係形成まで伴走します。

### 3. 技術力

技術要素は独立したデモ機能ではなく、次の判断経路として接続します。

`Conversation Memory → Distance Profile → Live Open Data検索 → Connection判定 → Free/Busy → 地理・時間制約 → Safety Guardrail → PUSH Policy → Feedback`

P0でConversation Memory、Distance Profile、PUSH Policy、Safety Guardrailと監査可能な判断記録を実装し、Live DemoではOpen Data同期、Google Free/Busy、Google Routes、Event Mapを接続します。Contextual Bandit / JITAIは、最初から不透明な自動最適化を行わず、明示Policy、Feedback蓄積、オフライン評価、安全制約付き最適化の順で段階導入します。既存資産をContractでつなぎ、実際に動く一連のDemoで検証します。

### 4. ソーシャルインパクト

PAINを「Eventを知らない」ではなく、孤独時に大きくなる検索、比較、予定調整、移動、初参加の心理的負担として捉えます。Clickや参加数だけで成功とせず、参加、再参加、自発的な外出、継続接点に加え、本人同意のある妥当な孤独尺度を段階的に測ります。

効果検証では、推薦を受けなかった期間・異なる介入強度との比較など、因果効果を確認できる設計を事前に定めます。金銭換算は実測、推計、仮定を分離し、東京都全体へ安易に外挿しません。個人の変化を匿名・集計し、接点が不足する地域・時間帯・参加形式を東京都施策の改善へつなげます。

### 5. サービスデザイン

本人を画面上で「孤独な人」とラベル付けしません。通知頻度、Quiet Hours、言葉の強さ、移動時間、料金、対人負荷、休止を本人が調整でき、`これは違う / 今回は無理 / 次回も知らせて`で距離感を修正できます。1件PUSHとEvent Mapの併用により、検索負担を減らしながら本人の主体性を残します。

利用を続けさせることだけを成功にせず、本人が自分から外出・再参加できるようになり通知が不要になることも成功とします。CalendarはFreeBusyだけを使い、正確な現在地を永続保存せず、記憶同意、削除、保持期間、緊急時のSafety導線を製品機能として扱います。

## Event Mapの目標

`/osekkai/map`では、現在地または駅名・地域名から、参加可能な交流Eventを自分でも探せるようにします。

- `今日 / 今週末 / 30分以内 / ひとり参加可 / 継続あり / Networking / みんなで食事`で絞り込み
- Markerから開催時刻、実移動時間、料金、募集状態、交流根拠、Source、更新時刻を確認
- Policyが選んだ1件を`おばさんのおすすめ`として区別
- 交流根拠のない施設、expired、canceled、sold out、stale Eventは表示しない
- 正確な現在地は明示操作時だけ利用し、Profileやlogへ永続保存しない

このMapは`TASK-145`として計画済みで、現時点では未実装です。

## 利用予定のデータ

| Source | 用途 | Plan2上の扱い |
|---|---|---|
| 東京都Open Data CKAN | 東京都・自治体が公開する最新Event | 必須Provider |
| Lu.ma公開Event | Community、趣味、Networking | 必須Provider |
| Doorkeeper公開Event | 継続Community、勉強会 | 必須Provider |
| 公共文化施設の公式情報 | ワークショップ、交流・参加型企画 | 必須Provider |
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
  scripts/osekkai_*        Event取得・判断・保存・CLIのowner
  fixtures/osekkai/        再現可能なP0デモデータ
  config/osekkai_policy.json
  tests/test_osekkai_*.py

contracts/osekkai/         JSON Schemaの正本
Plan2.md                   Live Demo実装Taskの正本
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
Copy-Item .env.example .env.local
npm.cmd ci
npm.cmd run dev
```

ブラウザで`http://localhost:3000/`を開くと`/osekkai`へ移動します。P0デモは`http://localhost:3000/osekkai/demo`です。

`.env.local`の既定値`OSEKKAI_DEMO_MODE=true`では、外部APIや外部LLMを使いません。Google Calendar、Routes、Maps、Live Provider用Credentialは、該当Taskの実装と環境変数追加が完了してから設定します。

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
python scripts/osekkai_contracts.py --validate-all
```

## Data・Privacy原則

- synthetic、過去snapshot、Live、AI Derived、Organizer Verifiedを同じ表示へ混ぜない
- CalendarはFreeBusyだけを使用し、予定タイトル、説明、場所、参加者を取得・保存しない
- 現在地は明示操作時だけ取得し、正確な座標を永続保存しない
- 根拠のない`一人参加OK`、`次回あり`、定員、交流形式を生成しない
- 候補がなければ0件を返し、架空EventでDemoを成立させない
- 本サービスを医療診断・治療として表現しない

PV・Demo動画の制作、編集、書き出しはユーザー側の作業であり、本Repositoryの実装完了Gateには含めません。製品UIが動画内の主張と一致することはLive Demo Gateで確認します。
