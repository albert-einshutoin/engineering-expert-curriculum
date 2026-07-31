# Pull Request

このPull Requestだけで、背景、変更、判断、検証、残るリスクを再現できるように記録してください。機密情報や未修正の脆弱性は記載せず、`SECURITY.md`の非公開経路を使ってください。

## なぜ変更するのか

- 解決する利用者・学習者・Contributorの課題:
- 現行状態を維持した場合の影響:
- 関連Issueと、そこで合意したscope:

## なぜ今なのか

- この時点で対応する根拠、依存関係、期限または機会:
- 先送りした場合の具体的なコスト:

## 変更前 / 変更後

### 変更前

- 利用者に見える挙動、教材内容、運用、品質保証:

### 変更後

- 何がどう変わり、誰がどの価値を得るか:
- 維持する互換性と不変条件:

## 意思決定と代替案

| 選択肢 | 採用・却下 | 判断根拠 | トレードオフ |
|---|---|---|---|
| 採用案 | 採用 |  |  |
| 代替案 | 却下 |  |  |

- 判断を変える条件:
- 制約と、意図的にscope外とした事項:

## 実装内容

- 変更した責任境界、file、data、公開interface:
- 処理または教材の流れ:
- 重要な実装理由とfailure modeの扱い:
- migration、互換性、生成物への影響:

## テスト証拠

### RED

- 先に追加したテストまたは再現手順:
- 実行command、対象commit、期待どおり失敗した理由:

### GREEN / full validation

- focused testのcommandと結果:
- `python3 -m unittest discover -s tests -v`の結果:
- `python3 tools/build.py`の結果:
- `git diff --check`の結果:
- 生成差分、性能測定、目視確認など追加証拠:
- skip、未実行項目、既知の制限と理由:

## セキュリティ・privacy

- 信頼境界、入力、path、HTML escape、権限、secret、依存、配布物への影響:
- 実施したsecurity checkと残余リスク:
- learner dataを保存しない契約への影響:

## アクセシビリティ・表示確認

- semantic HTML、keyboard、focus、読み順、見出し、link nameへの影響:
- `file://`、200% zoom、狭幅、high contrast、printでの確認結果:
- 視覚変更のbefore/after画像または、画像が不要な理由:

## 教材・出典レビュー

教材やmappingへ影響しない場合も、その根拠を記載してください。各観点はfinding、author fix、再確認結果を分け、`reviewerKind`を`human`、`ai-assisted`、`automated`のいずれかで開示します。AI支援と自動確認はhuman approvalを置き換えません。

| review dimension | reviewer / reviewerKind | finding | author fix | 再確認結果 |
|---|---|---|---|---|
| 技術的正確性 |  |  |  |  |
| 学習設計・証拠 |  |  |  |  |
| アクセシビリティ |  |  |  |  |
| 編集・出典 |  |  |  |  |

- 追加・更新した一次出典、版、該当箇所:
- objectiveからassessment・evidenceへの追跡:
- CS2023、SWEBOK、SFIA、Capstoneへの波及確認:

## リスクとロールバック

- 残るリスク、影響範囲、監視方法:
- rollbackを開始する条件:
- 安全に戻す手順と、戻した後に再検証する項目:

## OSSとしての価値

- forkや下流利用者の再利用性、理解可能性、保守性への価値:
- private contextに依存せず、第三者が判断・再現できる証拠:
- documentation、CHANGELOG、Errata、公開interfaceへの反映:

## 最終チェック

- [ ] 変更scope外の差分や生成済み`site/`を含めていません。
- [ ] author self-reviewを実施し、重大な修正後のcommitを再検証しました。
- [ ] 必須CIとhuman reviewが揃うまでmergeしません。
- [ ] Maintainerはマージ後の責任として、GitHub上の自動削除を確認し、安全を確認したマージ済みブランチをローカルとリモートの両方から削除します。
