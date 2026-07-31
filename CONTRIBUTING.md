# Contributing

Engineering Expert Curriculumへの貢献を歓迎します。小さな誤字修正から、教材、検証処理、アクセシビリティ、出典、コンピテンシー対応の改善まで、同じ「理由・証拠・再現可能性」の基準で扱います。

参加前に[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)を確認してください。教材の訂正は[ERRATA.md](ERRATA.md)、脆弱性の疑いは[SECURITY.md](SECURITY.md)の非公開経路を使います。機密性が必要な内容を通常のIssueやPull Requestへ含めないでください。

## 最初の貢献

1. 既存IssueとPull Requestを検索し、同じ変更が進行中でないか確認します。
2. 変更が誤字を超える場合はIssueを作り、なぜ必要か、目標、守る品質、実装案、受け入れ条件、検証方法を明記します。
3. Maintainerとscopeを合意してから、`main`の最新状態から短命なfeature branchを作ります。
4. 失敗する契約テストまたは再現手順を先に追加し、期待した理由で失敗することを確認します。
5. 最小の変更で契約を通し、自己レビューと全検証を実行します。

依存追加、schema変更、教材の構造変更、フレームワーク版更新は、実装前のIssue合意を必須とします。単純な表記修正ではIssueを省略できますが、Pull Requestで理由と影響を説明してください。

## GitHub FlowとTDD

標準の流れは次のとおりです。

> Issue → feature branch → RED → GREEN → REFACTOR → full validation → self-review → Pull Request → required review/CI → squash merge → branch cleanup

短く表すと、`Issue → feature branch → RED → GREEN → REFACTOR`を繰り返します。

- **RED:** 期待する振る舞いを表す最小のテストを先に書き、実装不足を理由に失敗することを確認します。
- **GREEN:** その失敗だけを解消する最小のコードまたは内容を追加します。テストを弱めて通しません。
- **REFACTOR:** 全テストが通る状態で、重複、命名、責任境界を改善します。

変更とテストを同じ巨大コミットへまとめず、レビュー可能な小さな単位でコミットします。可能な場合は、契約を示すREDと実装するGREENを分離してください。生成済み`site/`やローカルのprototype成果物はコミットしません。

マージ後は、GitHub上の自動削除結果を確認し、ローカルとリモートのマージ済みブランチを削除します。未マージの作業、別worktreeで使用中のbranch、利用者所有の成果物は削除しません。

## 実行する検証

対象テストでRED/GREENを確認した後、リポジトリ全体を検証します。

```sh
python3 -m unittest discover -s tests -v
python3 tools/build.py
git diff --check
```

テスト選択に失敗した場合、変更影響が不明な場合、対象が0件になった場合は全テストを実行します。skip、未実行、生成だけの成功を品質ゲート通過として扱いません。

Pull Requestには、実行したコマンド、終了結果、対象commit、既知の制限を記載してください。UIやアクセシビリティに影響する場合は、`file://`でのkeyboard、見出し、200% zoom、狭幅、high contrast、printの確認証拠も添えます。

## 教材変更の基準

コアレッスンの品質規範は[docs/content-standard.md](docs/content-standard.md)です。少なくとも次を守ります。

- objectiveを観測可能な行動で書き、labまたはassessmentのevidenceへ追跡させる。
- Learn → Practice → Explain → Prove → Transfer → Reviewの六段階を崩さない。
- 具体的な制約、代替案、failure mode、結論を変える条件を示す。
- 異なる2件以上のHTTPS出典を置き、規範・実装・経験的主張に最も近い一次資料を優先する。
- `body.html`へscriptable要素、inline handler、form、unsafe URL、inline styleを入れない。
- `status: complete`を、技術的正確性や公開承認の代替にしない。

CS2023、SWEBOK V4.0a、SFIA 9のmappingを変える場合は、対象だけでなく30レッスンとCapstoneへの波及を調べ、根拠と版を更新します。

## 4つのreview dimensions

公開可能性は、次の4観点を独立して確認します。一人が複数観点を担当しても、finding、author fix、再確認結果は観点ごとに記録します。

| 観点 | 確認する責任 |
|---|---|
| 技術的正確性 | 機構、コード、測定、制約、failure mode、出典との一致 |
| 学習設計・証拠 | objective、六段階loop、assessment、transfer、rubricの採点可能性 |
| アクセシビリティ | semantic HTML、keyboard、読み順、zoom、contrast、print |
| 編集・出典 | 用語、断定範囲、版、引用、link、Errata履歴 |

各review記録は`reviewerKind`を`human`、`ai-assisted`、`automated`のいずれかで開示します。AI支援または自動レビューはhuman approvalに数えません。著者のself-reviewは必須ですが、4観点の独立した承認を置き換えません。重大な修正後は、修正後のcommitを再評価します。

## Pull Requestの内容

単独で判断できるPull Requestを作ります。

- なぜ変更が必要か。利用者、学習者、Contributorへの影響は何か。
- 変更前はどうで、変更後に何が変わるか。
- 採用した案、却下した案、制約、残るrisk。
- REDの失敗、GREENの成功、全検証の証拠。
- security、privacy、accessibility、互換性への影響。
- 教材なら、出典、evidence、4つのreview dimensions、`reviewerKind`。
- OSSとして再利用、理解、保守をどう改善するか。

Maintainerによる明示的な公開判断と必須CIが揃うまでmergeしません。承認は対象commitにのみ有効で、後続commitへ自動継承しません。
