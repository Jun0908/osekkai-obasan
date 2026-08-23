# Plan 3 — LLM × Obsidianによる自然な「おかん会話」

**Status:** 実装・自動検証・Live接続確認済み。
**作成日:** 2026-08-23  
**実装日:** 2026-08-23
**対象:** `話す`の自然さ、長期記憶、文脈理解、返答生成  
**前提:** `Plan2.md`で実装したCalendar、Routes、Live Event、Connection判定、Conversation Episode、Participation Friction、Safetyを維持する

---

## 1. 結論

Plan3以前の`話す`は外部LLMを使用せず、Conversation Stateとキーワード分類に応じた固定文を返していました。現在は、安全判定後にLLMで自由発話を構造化し、既存Engineが候補と状態を決定し、Grounding済みDialogue PlanだけをLLMで自然な返答へ整えます。LLM停止時は同じState Machineの固定文へ戻るため、会話とDemoを継続できます。

既存のActive Vaultは確認できなかったため、Osekkai専用Vaultを`OSEKKAI_DATA_ROOT/obsidian-vault`へ新設する方針で実装しました。`OSEKKAI_VAULT_ROOT`で別Pathも指定できます。JSON StoreをPolicyの正本とし、Vaultは同意済みの短いエピソード記憶だけを保持します。

実装では、LLMへCalendar判断やEvent選択を丸投げしません。

- LLM: 発話の意味理解、関連記憶の利用、自然なおかん表現
- 既存Engine: Safety、状態遷移、Event検索、Calendar、Routes、候補順位、Cooldown
- Obsidian: 本人同意のあるエピソード記憶を人間にも読めるMarkdownで保持
- JSON Store: Policyが使う構造化Profileと運用状態の正本

この責任分離によって、自然な会話と、実在Eventだけを扱う安全性を両立します。

---

## 2. 目標

### 2.1 Product Goal

利用者が話すほど、次の3点が自然に改善する会話を作ります。

1. 何に惹かれるか
2. なぜ参加しにくいか
3. どの程度の言葉なら後押しとして受け取れるか

おばさんは過去の発言を毎回見せつけるのではなく、今回の話に関係する時だけさりげなく参照します。同じ質問を機械的に繰り返さず、現在のEpisodeに必要な一問だけを聞きます。

### 2.2 Demo Goal

Judge Demoでは、次の会話が一続きで成立することを目標とします。

1. 利用者が趣味または今の希望を自由入力する
2. 過去の関連記憶を必要な場合だけ参照する
3. Calendar、Routes、Live Eventから複数候補を提示する
4. 拒否理由を自由文から理解する
5. 理由に合わせて一度だけ候補と誘い方を変える
6. `行ってみる`を選ぶ
7. Event後のCheck-inを自然に行う
8. 次の会話で前回の反応が候補または言葉へ反映される

### 2.3 Non-goals

- LLMにEventを生成させない
- LLMにCalendar予定内容を読ませない
- LLMにSafety、PUSH可否、候補採用を最終決定させない
- ObsidianへGoogle token、API key、正確な現在地を保存しない
- Vault全体を毎回LLMへ送らない
- 本人の孤独状態、性格、診断名を推測・固定しない

---

## 3. 実装前の問題

### 3.1 固定文の反復

同じStateでは同じ`reply`を返すため、再読込や似た回答で同じ質問になります。State Machine自体は必要ですが、Stateと文章が一対一になっている点が問題です。

### 3.2 記憶が構造値に偏っている

現在のJSON ProfileはPolicyには適していますが、次のようなエピソード文脈を会話へ戻す仕組みが弱い状態です。

- 前回は何が不安だったか
- 実際に参加して何がよかったか
- 同じCommunityにまた行きたいと言ったか
- 強く誘われるのが嫌なのか、検索が面倒なだけなのか
- どの言い方なら本人が受け入れやすかったか

### 3.3 LLM接続境界がない

Plan3以前のNext.js–Python bridgeは、`OPENAI_API_KEY`等をPython child processへ渡さず、LLM Adapter、timeout、Schema検証、fallbackもありませんでした。現在は必要なLLM設定だけを明示allowlistでserver-side Pythonへ渡します。

### 3.4 Active Vaultがない

既存のActive Vaultは確認できなかったため、Repositoryへ入らないOsekkai専用Vaultを既定のData Rootへ新設しました。任意のVaultへ変更する時だけ`OSEKKAI_VAULT_ROOT`を設定します。

---

## 4. 推奨Architecture

```text
利用者の発話
    ↓
Deterministic Safety Gate
    ↓
JSON Profile + 関連Obsidian記憶の取得
    ↓
LLM Understanding
intent / attraction / friction / explicitness / clarification
    ↓
既存Conversation State Machine
    ↓
Live Event + Connection + FreeBusy + Routes + Policy
    ↓
Dialogue Plan
会話目的 / 使用可能な事実 / 禁止表現 / 質問上限
    ↓
LLM Response Renderer
    ↓
Schema + Grounding + Safety検査
    ↓
Chat表示
    ↓
Memory同意がある場合だけJSONとObsidianへEvidence保存
```

### 4.1 Safety Gate

既存の緊急性判定をLLMより前に実行します。緊急入力はLLMによるEvent会話へ渡さず、既存の`safety_handoff`を優先します。LLMがSafety判定を解除することはできません。

### 4.2 Memory Retrieval

発話、現在State、候補Event、既存Profileをqueryとして、本人のVaultから関係する記憶だけを最大3〜5件取得します。取得対象は本人の有効なMemoryだけに限定し、retention期限切れ、削除済み、別利用者のNoteを除外します。

### 4.3 LLM Understanding

自由入力を文章のままPolicyへ渡さず、Schemaで次へ構造化します。

- `intent`
- `attractions`
- `participationFrictions`
- `explicitness`
- `confidence`
- `needsClarification`
- `suggestedMemoryReferences`
- `doNotRemember`
- `doNotPush`

LLMの抽出結果は`inferred`として扱い、本人の明示設定を上書きしません。

### 4.4 Deterministic Decision

LLM理解後も、次は既存Python ownerが決定します。

- Conversation State遷移
- 一問だけ聞くか候補を提示するか
- Eventの適格性
- Connection Level
- Calendar fit
- Routes fit
- 料金、募集状態、鮮度
- 再提案回数
- Cooldown

### 4.5 Dialogue Plan

State Machineは固定文章ではなく、LLMへ渡す`Dialogue Plan`を作ります。

例:

```json
{
  "dialogueAct": "probe_first_time_anxiety",
  "goal": "初参加で最も不安な点を一問だけ確認する",
  "mustMention": ["候補は2件ある", "調整は一度だけ"],
  "allowedEventFacts": ["受付案内あり", "定員8名"],
  "relevantMemories": ["前回は大人数を断った"],
  "prohibitedClaims": ["絶対楽しい", "一人参加OK", "途中退出OK"],
  "questionBudget": 1,
  "tone": "casual_gentle"
}
```

### 4.6 LLM Response Renderer

LLMはDialogue Planの範囲だけで自然な返答を作ります。候補ID、日時、移動時間等の事実を書き換えず、根拠のない属性を追加しません。

LLM timeout、quota、malformed output、Grounding違反時は、現在の固定文をFallbackとして返します。

---

## 5. Obsidian Memory設計

### 5.1 Vaultの位置

環境変数`OSEKKAI_VAULT_ROOT`でOsekkai専用Vaultを指定できます。未設定時は`OSEKKAI_DATA_ROOT/obsidian-vault`を使います。Memory同意がない利用者にはNoteを作らず、検索にも使いません。

VaultはRepositoryへcommitしません。`.gitignore`対象とし、API key、OAuth token、正確な現在地を置きません。

### 5.2 推奨Folder構成

```text
osekkai-vault/
  .obsidian/
  users/
    <opaque-user-id>/
      Profile.md
      Preferences/
        <memory-id>.md
      Frictions/
        <memory-id>.md
      Episodes/
        <episode-id>.md
      Communities/
        <community-id>.md
```

### 5.3 JSONとObsidianの責任

| 保存先 | 責任 |
|---|---|
| JSON Profile | Policyが使う数値、明示設定、Friction confidence、Consent |
| Conversation Episode | State、提示回数、候補ID、Check-in時刻、Cooldown |
| Obsidian | 関連時だけ参照するエピソード要約、本人の言葉の短いEvidence |
| Semantic Index | Obsidian Noteを検索する再生成可能なIndex。正本ではない |

`Profile.md`はJSON Profileから作る人間向けProjectionとし、Policyの正本にはしません。Obsidianで本人が明示編集した内容を取り込む場合は、専用import操作とSchema検証を通します。

### 5.4 Note metadata

各NoteはYAML frontmatterに最低限、次を持ちます。

```yaml
---
schemaVersion: "1.0"
id: "memory-uuid"
kind: "preference | friction | episode | feedback | community"
userId: "opaque-user-id"
origin: "explicit | inferred"
referenceType: "conversation | feedback | attendance"
referenceId: "source-uuid"
confidence: 0.9
observedAt: "2026-08-23T10:00:00+09:00"
lastConfirmedAt: "2026-08-23T10:00:00+09:00"
retentionUntil: "2026-11-21T10:00:00+09:00"
---
```

本文は会話全文ではなく、後の会話に必要な短い要約を基本とします。raw textを保存する場合もMemory同意、長さ上限、削除、retentionを適用します。

### 5.5 Retrieval

検索は次の境界付きHybrid方式で実装しました。

1. `userId / kind / retention / origin`のmetadata filter
2. Category、Friction、Community IDの完全一致
3. 日本語・英数tokenの一致（Embedding検索はDemo必須経路に入れず、後から置換可能）
4. relevance、明示優先、更新日、confidenceで再順位付け
5. 最大3〜5件、token上限内だけLLMへ渡す

LLMへVault全体を送らず、「覚えてる」と言う場合は必ず参照Note IDを内部Evidenceへ残します。

### 5.6 削除と同期

- Evidence個別削除: JSON、Obsidian Note、Semantic Indexから削除
- 全削除: 利用者FolderとIndex entryを削除
- Memory同意OFF: 新規Noteを書かず、既存Noteの利用可否は設定に従う
- Retention: 既存Maintenance workerで期限切れNoteを削除
- 同期失敗: JSON updateを失敗させず、Vault同期状態を記録して再試行

---

## 6. 会話を自然にするRule

### 6.1 直近文脈

LLMへ次を渡します。

- 直近4〜6ターン
- 現在Episodeの短いsummary
- 直近3回のAssistant発話の表現signature
- 今回関係するMemory Note
- 現在のDialogue Act

### 6.2 反復防止

- 直近Assistant発話との完全一致を禁止
- 同じ質問を再度聞く場合は、なぜ確認が必要かをDialogue Planへ持たせる
- 既に明示回答済みの好みを再質問しない
- 返答ごとに新しい事実、確認、選択肢のいずれかを最低1つ含める
- `あんた何が好きなのよ`を万能Fallbackにしない
- 未完了Episodeは「最初から」ではなく続きから再開する

### 6.3 おかんTone

- 少し世話焼きだが、命令・罪悪感・脅しへ寄せない
- 本人を孤独とLabel付けしない
- 関西弁を強くしすぎず、読みやすい日本語を優先
- 相手の言葉をそのまま毎回オウム返ししない
- 過去記憶は関係する時だけ一つ参照する
- 一度に質問は一つだけ
- 断られた後の調整は一度だけ

### 6.4 Grounding

次の表現はSourceまたは既存Contractの根拠がある場合だけ許可します。

- 一人参加OK
- 初参加歓迎
- 少人数
- 途中退出OK
- 次回あり
- 募集中
- 料金
- 実移動時間
- 参加人数

LLM出力に根拠のないEvent claimが含まれた場合は再生成せず、まず安全なFallback文へ切り替えます。

---

## 7. Privacy・Security・Safety

- LLM API keyはserver/Pythonだけで使用し、`NEXT_PUBLIC_*`へ置かない
- Next.js bridgeの環境変数allowlistへ必要なserver keyだけを明示追加
- prompt、raw conversation、Vault本文を通常logへ出さない
- CalendarはFreeBusy集計だけをLLMへ渡す
- 正確な現在地をLLMまたはVaultへ渡さない
- 利用者間でMemory retrievalを混ぜない
- prompt injectionをEvent説明やObsidian Noteから受けても、Dialogue PlanとPolicyを変更させない
- LLM出力は必ずJSON Schema検証する
- Safety handoffをLLM fallbackより優先する
- LLM Provider障害でEventの事実確認を省略しない

---

## 8. 実装Boundary

PythonをLLM、Memory retrieval、Profile、Policy、Conversation Stateのownerとします。Next.jsに第二のLLM判断やMemory実装を作りません。

実装Module:

```text
agents-OpenClaw/scripts/
  osekkai_llm.py
  osekkai_llm_understanding.py
  osekkai_llm_renderer.py
  osekkai_memory_vault.py
  osekkai_memory_retrieval.py
  osekkai_dialogue_plan.py

contracts/osekkai/
  conversation-understanding.schema.json
  dialogue-plan.schema.json
  generated-reply.schema.json
  memory-note.schema.json
  memory-retrieval-result.schema.json
```

主な変更:

```text
agents-OpenClaw/scripts/osekkai_conversation.py
agents-OpenClaw/scripts/osekkai_chat.py
agents-OpenClaw/scripts/osekkai_profile.py
agents-OpenClaw/scripts/osekkai_store.py
agents-OpenClaw/scripts/osekkai_maintenance.py
frontend/lib/server/osekkai-openclaw-bridge.ts
frontend/components/osekkai/chat-client.tsx
frontend/.env.example
```

---

## 9. Task運用Rule

1. Contractを先に変更する
2. LLMなしでも既存Demoが動く状態を常に維持する
3. LLM出力を直接StateやProfileへ保存しない
4. 明示回答と推定を分ける
5. Vault未設定、Credential不足、timeoutでも固定文Fallbackで継続する
6. 正常系だけでなく、malformed output、quota、timeout、prompt injection、別利用者混入を検証する
7. 完了条件と検証を満たした後だけTaskを`[x]`にする
8. 実装途中で既存Calendar、Routes、Event Mapを壊さない

---

## 10. 実行順Task Queue

### Gate 1 — 現状Baseline

- [x] **TASK-300: 会話反復BaselineとVault所在を確定する**
  - Active product内外で、ユーザーが想定するObsidian Vaultの明示Pathを確認
  - `archive/tomo-san/`は確認対象にしない。移植が必要な場合は別Taskとしてユーザーの許可を得る
  - 現在の主要会話20〜30本をfixture化
  - 同一文反復率、好み再質問率、根拠のない記憶参照率をBaselineとして測定
  - 完了条件:
    - Vault Pathまたは新設方針が決まっている
    - 改善前後を比較できる会話fixtureがある

### Gate 2 — Contract

- [x] **TASK-301: LLM UnderstandingとDialogue Plan Contractを作る**
  - `ConversationUnderstanding`
  - `DialoguePlan`
  - `GeneratedReply`
  - `MemoryNote`
  - `MemoryRetrievalResult`
  - LLMは候補採用、PUSH可否、Safety解除を出力できないSchemaにする
  - Python / TypeScript型とvalidatorを生成
  - 完了条件:
    - unknown field、根拠のないEvent ID、質問2件以上を拒否する
    - explicit / inferredを混同しない

### Gate 3 — Provider Adapter

- [x] **TASK-302: Server-only LLM AdapterとFallbackを実装する**
  - Provider-neutral interfaceを作る
  - `OSEKKAI_LLM_PROVIDER`、`OSEKKAI_LLM_MODEL`、server-only API keyを扱う
  - timeout、quota、429、malformed JSON、Provider停止を分類
  - transport retryは上限付きとし、失敗時は固定文へFallback
  - API keyをNext client、log、CLI responseへ出さない
  - 完了条件:
    - LLM未設定でも既存Demoが動く
    - LLM有効時だけunderstanding / rendererを呼ぶ
    - 同一idempotency keyでMemoryを重複保存しない

### Gate 4 — Obsidian Memory

- [x] **TASK-303: Obsidian Vault Adapterを実装する**
  - 安全なPath解決と利用者Folder分離
  - YAML frontmatterをMemory Note Contractで検証
  - atomic write、lock、retention、個別削除、全削除
  - JSON Profileから`Profile.md`Projectionを生成
  - Vault未設定時はno-opとして動く
  - 完了条件:
    - path traversalと別利用者Note取得を拒否
    - Memory同意なしでNoteを作らない
    - token、API key、正確な現在地、Calendar予定内容を保存しない

- [x] **TASK-304: Relevant Memory Retrievalを実装する**
  - metadata filter、完全一致、token relevanceを段階実装
  - 外部Embeddingや第二の永続IndexをDemo必須経路に置かず、Vaultから毎回再現できる検索にする
  - 明示優先、confidence、更新日、関連度で最大3〜5件を返す
  - 削除・retentionをIndexへ伝播
  - 完了条件:
    - 無関係なMemoryを会話へ持ち込まない
    - `覚えてる`という発話に参照Note IDが存在する
    - 別利用者Memory混入が0件

### Gate 5 — Conversation Integration

- [x] **TASK-305: 自由発話をLLM Understandingへ接続する**
  - Safety Gate後にLLMを呼ぶ
  - Attraction、Participation Friction、intent、明示拒否を構造化
  - 明示回答を推定で上書きしない
  - ambiguityが高い場合だけ一問確認する
  - Memory同意なしではcurrent turnだけに利用し、永続化しない
  - 完了条件:
    - Keywordにない言い回しでも同じFrictionへ到達する
    - 好みと参加障壁を別々に抽出する
    - `覚えないで`、`もう誘わないで`を最優先する

- [x] **TASK-306: 固定replyをDialogue Plan + LLM Rendererへ置き換える**
  - State MachineがDialogue Planを作る
  - Rendererへ直近文脈、関連Memory、許可されたEvent事実だけを渡す
  - 反復防止、Tone、質問1件上限を適用
  - Grounding違反時は固定文Fallback
  - 完了条件:
    - 同一Stateでも直近文脈に合う異なる返答になる
    - 既に回答した好みを再質問しない
    - 一回の返答に質問が2つ以上入らない
    - Event名、日時、Routes、料金、募集状態を改変しない

### Gate 6 — Memory Learning Loop

- [x] **TASK-307: 会話・拒否・Check-inをObsidian Memoryへ接続する**
  - 好み、Friction、参加選択、Check-inを短いMemory Noteへ変換
  - raw transcriptではなく必要最小限の要約を基本とする
  - Community再参加や過去のよかった点を次の会話へ戻す
  - SettingsのEvidence削除、全削除、Consent変更へ接続
  - 完了条件:
    - 前回の参加理由が次の誘い方へ反映される
    - 削除後は会話でも参照されない
    - Memory OFFの会話は次回へ残らない

### Gate 7 — UI・Latency

- [x] **TASK-308: LLM会話の待ち時間と失敗表示を整える**
  - 既存typing indicatorをLLM処理へ接続
  - timeout時に技術Errorを露出せずFallback会話を続ける
  - 二重送信を防止
  - 必要なら最終文章だけstreamingし、構造判断の途中状態は表示しない
  - 目標:
    - 通常会話の体感待ち時間をDemoで許容できる範囲にする
    - Provider失敗でも会話画面が壊れない

### Gate 8 — Evaluation

- [x] **TASK-309: Conversation Quality Evaluationを作る**
  - 自由表現、曖昧表現、複数理由、拒否、再開、Check-inのfixture
  - 指標:
    - 同一文反復率
    - 既回答内容の再質問率
    - 関連Memory利用率
    - 無関係Memory参照率
    - unsupported Event claim率
    - 一返答あたり質問数
    - Safety / Consent違反数
  - exact string比較ではなく、Schemaと禁止事項、会話目的の達成を評価
  - 完了条件:
    - unsupported claim 0件
    - Safety / Consent違反0件
    - 同一文反復率がBaselineより明確に低下

### Gate 9 — Judge Demo

- [x] **TASK-310: LLM × Obsidianの60秒Demoを通す**
  - Google Calendar接続済みDemo accountを使用
  - Live Event、Google Routes、関連Memoryを使用
  - シナリオ:
    1. 前に話した好みをさりげなく参照
    2. 実在する複数候補を提示
    3. 自由文の参加障壁を理解
    4. 一度だけ候補と言い方を調整
    5. 参加を選択
    6. Check-in
    7. 次の誘い方が変化
  - LLM OFFでも固定文Fallback Demoを完走できることを確認
  - 完了条件:
    - 同じ質問の機械的反復がない
    - 記憶参照が自然で、見せつける感じがない
    - Event事実がSourceと一致する
    - Calendar予定内容と正確な現在地を表示・保存しない

### Gate 10 — 地域コミュニティOpen DataのLLM Grounding

**問題**: `data/tokyo-community/communities.csv`（千代田区の地域コミュニティ・サークル一覧、Open Data）は`/osekkai/map`には反映済みだが、`話す`のLLM経路からは一切参照できない。

**原因の切り分け**:
- このCSVを読んでいるのは`frontend/lib/osekkai/community-directory.ts`（Node/TypeScriptのみ、`fs`で直接CSVを読む）と、それを返す`frontend/app/api/osekkai/community-directory/route.ts`だけ。`agents-OpenClaw`配下には`tokyo-community`/`communities.csv`を参照するコードが1件も無い（grep確認済み）
- LLM経路（`osekkai_chat.py`）は、既存のLive Event Mesh由来の`opportunity`のみを事実として扱う。`osekkai_dialogue_plan.py`の`_event_facts()`（48行目）と`build_dialogue_plan()`（79行目）は`context["recommendations"]`（＝Opportunity）からしか`allowedEventFacts`を作らず、地域コミュニティ一覧を渡す引数自体が存在しない
- `osekkai_chat.py`の`understand_message()`呼び出し（216〜243行目付近）も、渡しているのは`message` / `memories`（本人のObsidian記憶） / `recent_turns` / `episode_state`だけで、地域のOpen Data候補は渡していない
- 地域コミュニティのデータは`verification_status: official_source_unverified_current`（活動有無・開催日時は未確認）であり、Plan2 §7のProvenance区分では「Raw Open Data」。既存の`opportunity`（Live Provider Data、必ず`startsAt`/`endsAt`と募集状態を持つ）とは型が異なるため、既存の`_event_facts()`にそのまま混ぜることはできない

- [x] **TASK-311: 地域コミュニティOpen DataをPython側から読めるようにし、Dialogue Planへ根拠付きで渡す**
  - 依存: TASK-306（Dialogue Plan + LLM Renderer）
  - 対象:
    - `agents-OpenClaw/scripts/osekkai_community_directory.py`（新規）
    - `data/tokyo-community/`配下に、施設名→座標の対応表を共有データとして切り出す（例: `chiyoda-facility-directory.json`）。現状この対応表は`frontend/lib/osekkai/community-directory.ts`内にTypeScriptの定数として直書きされており、Python側に複製すると九段生涯学習館・千代田区立スポーツセンターの座標が二重管理でズレる恐れがあるため、JSONを正本にしてTS・Python両方から読む形に揃える
    - `agents-OpenClaw/scripts/osekkai_dialogue_plan.py`（`_event_facts`に相当する`_community_facts()`を追加し、`build_dialogue_plan()`に`communities`引数を追加）
    - `agents-OpenClaw/scripts/osekkai_chat.py`（地域コミュニティ候補を取得し、`understand_message`または`build_dialogue_plan`へ渡す箇所を追加）
    - `contracts/osekkai/dialogue-plan.schema.json`（`allowedEventFacts`と別に、Raw Open Data由来であることが分かる`allowedCommunityFacts`等のフィールドを追加）
    - 生成されるTypeScript型・validator
  - 作業:
    - `osekkai_community_directory.py`で`communities.csv`を千代田区に絞って読み込み、共有facility JSONで施設座標へ解決する（`frontend/lib/osekkai/community-directory.ts`と同じロジック・同じ出力件数になることをテストで突き合わせる）
    - ユーザーの発話が地域のサークル・活動場所を尋ねている時だけ（毎ターン全件を渡さない）、該当する施設・コミュニティ名をDialogue Planの事実として渡す
    - Factの文言に「Open Data・活動有無や開催日時は未確認」を必ず含め、`osekkai_dialogue_plan.py`の`PROHIBITED_CLAIMS`と矛盾しないようにする（「次回あり」「募集中」等をこのFactから断定させない）
    - LLM UnderstandingがCalendar予定やLive Eventと混同しないよう、事実の出典（Raw Open Data）をRendererのGrounding検査でも区別する
  - 完了条件:
    - 「九段でどんなサークルがある？」のような発話に対し、実際に`communities.csv`に載っている名称で応答できる
    - 応答が「募集中」「次回あり」等、CSVに存在しない確度の高い主張をしない
    - 該当しない発話では地域コミュニティFactを渡さず、既存の応答挙動・トークン量を悪化させない
    - Map側（`frontend/lib/osekkai/community-directory.ts`）とPython側の対象件数・施設座標が一致する
  - 検証:
    - `python -m unittest discover -s tests -p "test_osekkai_community_directory.py" -v`（新規）
    - `python -m unittest discover -s tests -p "test_osekkai_dialogue_plan.py" -v`
    - `npm.cmd run generate:contracts; npm.cmd run typecheck`
  - 完了記録（2026-08-23）:
    - 実装は当初案から1点簡略化: `dialogue-plan.schema.json`へ`allowedCommunityFacts`を新設せず、既存の`allowedEventFacts`（`type: string`の配列で形式制約なし）にOpen Data由来と分かる接頭辞付き文字列として合流させた。Contract・生成TypeScript・codegenパイプラインを一切変更せずに済み、他作業と衝突するリスクを避けられるため
    - `data/tokyo-community/chiyoda-facility-directory.json`を新設し、施設名（九段生涯学習館・千代田区立スポーツセンター）の名称・住所・座標・出典URLをTypeScript（`frontend/lib/osekkai/community-directory.ts`）とPython（新規`agents-OpenClaw/scripts/osekkai_community_directory.py`）の両方から読む形に統一。座標の二重管理・drift問題を解消
    - `osekkai_community_directory.py`: `communities.csv`を指定区で絞り込み、施設ごとにグルーピングして件数・座標を返す。`format_community_facts()`で1施設1Factに圧縮し、`Open Data・活動有無/開催日時は未確認`の注記を必ず含める（`osekkai_dialogue_plan.py`の`PROHIBITED_CLAIMS`と矛盾しない）
    - `osekkai_dialogue_plan.py`の`build_dialogue_plan()`に`community_facts`引数を追加。既存呼び出し（引数省略）は完全に無変更の挙動
    - `osekkai_chat.py`に`COMMUNITY_INQUIRY_MARKERS`（「サークル」「コミュニティ」「九段」「スポーツセンター」等）を追加し、該当キーワードを含む発話の時だけ`load_community_directory()`→`format_community_facts()`を呼び、`build_dialogue_plan`へ渡す。CSV・共有JSONの読み込み失敗は`OSError/ValueError/KeyError`で握りつぶし、Enhancement-onlyとして会話を止めない
    - 新規テスト: `test_osekkai_community_directory.py`（5件、実リポジトリCSVとの突き合わせを含む）、`test_osekkai_dialogue_plan.py`（4件、新規ファイル）、`test_osekkai_chat_community_directory.py`（2件、キーワード該当/非該当の両方を`process_chat_unlocked`経由でEnd-to-End検証）
    - 検証結果: Python 182 tests / contract 35 schemas・22 instances 成功。Frontend 98 tests / typecheck / lint / production build 成功。実行中のdev serverで`/api/osekkai/community-directory`が改修後も同じ実データを返すことを確認
    - 残課題: `COMMUNITY_INQUIRY_MARKERS`はキーワード一致のみで、LLM Understandingの`intent`（`ask_question`等）は使っていない。誤検知・見逃しが目立つ場合はLLM intentとの併用を検討
  - 追記（2026-08-23、Mapの東京23区拡張に伴う変更）:
    - 共有ジオコーディングファイルを`chiyoda-facility-directory.json`（千代田区専用）から`data/tokyo-community/ward-geocoding-directory.json`（23区、区ごとに`wardOffice`＋`anchors`）へ置き換えた。千代田区は従来通り九段生涯学習館／千代田区立スポーツセンターへ解決し、他22区は区役所へフォールバックする
    - `osekkai_community_directory.py`・`frontend/lib/osekkai/community-directory.ts`とも新形式に追従済み。Python側の`load_community_directory(ward)`は引き続き単一区スコープ（Chat Groundingは1区分のFactで十分なため）、TypeScript側はMap向けに23区サマリー＋施設単位オンデマンド詳細（`loadCommunityDirectorySummary`/`loadCommunityFacilityDetail`）へ分離
    - 検証: `test_osekkai_community_directory.py`（6件、実リポジトリの23区分クロスチェック含む）、`test_osekkai_chat_community_directory.py`（2件）を新形式で更新して成功
  - 追記（2026-08-23、地域名・町丁目単位のMap分散）:
    - `communities.csv`に`area_name`、`map_location_id`、緯度経度、`geocoded_address`、`location_precision`、`location_source`、根拠URLを追加。単一会場住所、公式の区域記載、町会・自治会名の町丁目を国土地理院住所検索で照合し、区が一致しない候補は採用しない
    - TypeScript / Pythonの解決順を「単一会場住所 → 確認済み施設アンカー → 活動区域の目安 → 区役所」に統一。活動区域を実開催地として表示しないため、API型とMap Sheetに`locationKind` / `locationPrecision`と注意書きを追加
    - 初回実装では、実データ10,076件のうち4,452件を区役所集約から分散し、Map上は23区1,706地点になった
    - 追加改善で、ハイフン住所と「丁目・番・号」の表記差を正規化し、複数会場は最初の公式住所を`multiple_addresses_representative`として区別、公式Sourceの「○○地区」は活動区域として扱った。最終的に単一・複数会場2,929件、活動区域3,684件を個別位置へ解決し、合計6,613件を区役所集約から分散。Map上は23区2,249地点、区役所フォールバックは3,463件になった
  - セッション合流に関する注記（2026-08-23）: 同時並行の別セッションが上記の4段階解決（単一会場住所→施設アンカー→活動区域→区役所）へ発展させ、`venue-address-directory.json`（レガシー住所辞書）も互換フォールバックとして残していた。本セッションはこれと並行して「CSVの緯度経度→区役所」の2段階へ単純化する設計を試作していたが、`git push`時にorigin/mainの上記実装と競合したため、より情報量の多いorigin側（4段階解決・活動区域の目安分類）をマージ後の正本として採用した。本セッション側で追加した価値（Vercel向け`outputFileTracingRoot`/`outputFileTracingIncludes`設定、Python不通時の静的snapshotフォールバック、地図初期表示を千代田区だけに絞るUI）はそのまま維持している

### Gate 11 — Google Calendar接続がCloudflare Tunnel経由で失敗する（運用上の既知事象・コード修正なしで解決）

**症状**: 開発サーバーを外部公開するCloudflare Quick Tunnel（`cloudflared tunnel --url http://localhost:3000`）を張った状態で、そのトンネルURL（`https://<random>.trycloudflare.com`）を開いて「Googleカレンダーに接続」を行うと接続が完了しない。

**原因**:
- `GOOGLE_REDIRECT_URI`（`frontend/.env`）は`http://localhost:3000/api/osekkai/calendar/callback`に固定（[osekkai_google_credentials.py](agents-OpenClaw/scripts/osekkai_google_credentials.py)の`GoogleOAuthConfig.from_env`は`http`スキームを`localhost`/`127.0.0.1`以外で拒否するため、そもそも動的にトンネルのホストへ差し替える設計にもなっていない）
- セッションCookieは`Domain`未指定のホスト限定Cookie（[osekkai-user.ts:140,179](frontend/lib/server/osekkai-user.ts)、`sameSite: 'lax'`）
- トンネルのホスト（例: `benz-....trycloudflare.com`）で「接続」を開始するとセッションCookieはそのホストにだけ発行される
- Googleの認証後リダイレクト先は固定で`localhost:3000`のため、ブラウザはトンネル用Cookieを送らない
- `calendarCallbackGet`（[osekkai-route-handlers.ts:65](frontend/lib/server/osekkai-route-handlers.ts)）は`requireOsekkaiSession()`でセッション必須のため、`SESSION_REQUIRED`（401）で失敗する
- 実データ上の証拠: `agents-OpenClaw/data/osekkai/credentials/`に`google-state-*.enc`（未完了のOAuth試行）が複数残っており、トンネル経由での失敗試行と一致する時刻だった

**確認したこと・コード修正は不要と判断した根拠**:
- `http://localhost:3000`を直接開いて接続した既存2ユーザーについて、保存済みRefresh Tokenでの実アクセストークン更新（Google `/token`エンドポイントへの実通信）と実FreeBusy取得を両方とも実行し、両ユーザーとも成功を確認（2026-08-23）
- したがってCalendar接続の実装自体（OAuth・PKCE・トークン保存・FreeBusy取得）にバグはない。原因は100%、トンネルのホストと固定`redirect_uri`のホストが一致しないことによるセッションCookieの不一致

**運用ルール（今後この事象を再発させないために）**:
- **Google Calendarへの接続操作は必ず`http://localhost:3000`を直接開いて行う。**Cloudflare Tunnel等の別ホスト経由では行わない
- 一度`localhost:3000`で接続が完了すれば、以後の閲覧（`/osekkai/map`等）はトンネル経由でも問題ない（Calendar関連のCookie依存はOAuthの往復時だけ）
- トンネル経由でもCalendar接続を成立させたい場合は、(1) `GOOGLE_REDIRECT_URI`をトンネルのURLに変更し、(2) Google Cloud ConsoleのOAuthクライアントの「承認済みのリダイレクトURI」に同じURLを追加登録する必要がある。ただしCloudflare Quick TunnelのURLは起動のたびに変わるため、固定ホスト名のNamed Tunnelに切り替えない限りこの対応は再起動ごとに崩れる
- 失敗した接続試行の残骸（`agents-OpenClaw/data/osekkai/credentials/google-state-*.enc`）は自動的には削除されない（`consume_state`は成功時のみ削除）。機能には影響しないが、気になる場合は手動削除で問題ない

---

## 11. Test方針

### Python

- Contract validation
- LLM Provider timeout / quota / malformed output
- prompt injection
- Memory同意あり・なし
- explicit優先
- Vault path traversal
- 利用者分離
- retention / 個別削除 / 全削除
- Semantic Index再構築
- unsupported Event claim
- LLM failure時Fallback
- 既存State Machineとidempotency回帰

### Frontend

- typing中の二重送信防止
- LLM timeout時Fallback表示
- Conversation Contextの復元
- 内部Memory、prompt、confidenceを通常Chatへ露出しない
- Desktop / mobile
- Safety handoff

### Browser

- 初回会話
- 過去Memoryがある会話
- 複数候補
- Friction自由入力
- 一度だけの調整
- 選択
- Check-in
- LLM OFF fallback
- Calendar未接続
- Provider timeout

---

## 12. 実装時に必要な設定

実装済みの設定です。値はRepositoryへcommitしません。`OPENAI_API_KEY`があればLLMは自動で有効になり、明示的に止める時だけ`OSEKKAI_LLM_ENABLED=false`を指定します。

```dotenv
OSEKKAI_LLM_ENABLED=true
OSEKKAI_LLM_PROVIDER=openai
OSEKKAI_LLM_MODEL=gpt-5.4-mini
OSEKKAI_LLM_TIMEOUT_SECONDS=7
OPENAI_API_KEY=
OSEKKAI_VAULT_ROOT=
OSEKKAI_MEMORY_SEMANTIC_SEARCH=false
```

Provider固有値をFrontendへ渡しません。`OPENAI_API_KEY`等はPython child processの明示allowlistへ追加し、server-onlyで扱います。

---

## 13. 最終判断

自然な会話に必要なのは、固定文をすべてLLMへ置き換えることではありません。

必要なのは、次の組み合わせです。

1. 過去の関連記憶を正しく取り出すObsidian Memory
2. 自由な言い回しを理解するLLM
3. Eventと行動判断を守る既存の決定論的Engine
4. 事実と会話目的だけをLLMへ渡すDialogue Plan
5. 根拠のない発言を止めるGrounding Guard

これにより、Calendar、Routes、実Event、安全性を維持したまま、「話すほど相手のことが分かり、同じことを繰り返さないおかん」へ進化させます。

---

## 14. 実装・検証記録

### 実装結果

- OpenAI Responses APIをserver-onlyで接続し、`store: false`、strict structured output、timeout、bounded retry、決定論的Fallbackを実装
- Safety GateをLLMより前に維持し、LLMへはFreeBusy集計、関連Memory、採用済みEvent事実だけを渡す
- `preference / friction / episode / feedback`を利用者別Markdown Noteとしてatomic writeし、同意OFF、個別削除、全削除、retentionへ接続
- 同じTurnの好みと参加障壁を同時に順位付けへ反映し、質問上限、必須事実、根拠のない数値・Event claim、直前返答の完全反復をGuard
- おかんToneは標準語を基本とし、作った関西弁や攻撃的な決めつけを生成しない
- `/osekkai/demo`はLive経路から分離し、実Event snapshot 3件、記録済みRoutes、合成FreeBusy、決定論的会話で、参加障壁による順位変更からCheck-in後のMemory更新までを約45秒で再現
- Judge DemoはRuntime API callを0件とし、Provider、Python、Calendar、Routes、LLMが停止しても完走できる静的Routeとしてproduction buildで確認

### 2026-08-23の確認値

- 実LLM Understanding: 自由文から好みCategoryと複数Frictionを構造化（約2.2秒）
- 実LLM Renderer: Dialogue PlanからGrounding済み返答を生成（約1.7秒）
- Web実経路: Next.js → Python → 実LLM → Grounding済み返答がHTTP 200（約4.1秒）。Memory OFF時に永続化されないことも確認
- Conversation評価: 完全反復率`1.0 → 0.0`、既回答再質問`2 → 0`、関連Memory利用率`1.0`、unsupported claim`0`、Safety / Consent違反`0`
- Live data: 239 Event、Connection適格91件、推薦可能7件、Routes実測8件
- Source状態: 文京区公式CSV 1件は外部URLの取得失敗を明示し、そのEventをLive PUSHへ混ぜずに他Sourceを継続
- Google Calendar: 接続済み利用者1件でFreeBusy成功とFree Windowを確認
- Judge経路: `好み → 複数候補 → 自由文Friction → 一度だけ調整 → 選択 → Check-in → 次回Memory`を統合テストで完走
- LLM OFF、timeout、quota、malformed outputでも固定文Fallbackで完走

### 検証結果

- Python: 168 tests passed、33 schemas / 21 instances validated
- Frontend: 92 tests passed、typecheck / lint / production build成功
- Production buildで`/osekkai/demo`がStatic Routeとしてprerenderされ、Backend失敗を強制したcomponent testでもRuntime API callなしで全Sceneを完走
- `http://127.0.0.1:3000/osekkai/chat`のHTTP 200を確認
- この実行環境では操作可能Browser runtimeが提供されなかったため、見た目を含む手動60秒リハーサルだけはDemo当日のBrowserで行う。これは実装未完了ではなく運用前確認として扱う
