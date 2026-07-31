# Governance

Engineering Expert Curriculumは、教材の深さ、安全性、アクセシビリティ、継続性を公開の証拠で維持します。役割は肩書きではなく、限定された権限と説明責任の組み合わせです。

## 役割

### Contributor

ContributorはIssue、教材、コード、出典、翻訳、レビューfinding、Errataを提出するすべての参加者です。変更理由、受け入れ条件、検証証拠を示し、指摘へ応答し、自分の変更を修正する責任を持ちます。merge権限は前提ではありません。

### Reviewer

Reviewerは、技術的正確性、学習設計・証拠、アクセシビリティ、編集・出典のうち、明示された観点を評価します。別のReviewerが担当した場合だけ独立reviewと呼び、承認は観点とcommitを限定し、未確認領域を承認したことにしません。各記録で`reviewerKind`を開示し、AI支援または自動結果をhuman approvalとして扱いません。

継続的にReviewerとなる候補は、少なくとも3件の受理済み貢献と、finding、author fix、再確認を含む1件の文書化されたレビューを示します。Maintainerは公開Issueで対象観点、根拠、権限範囲を記録して任命します。

### Maintainer

Maintainerはscope、security、release、governance、役割付与、最終的なmerge判断に責任を持ちます。CI成功だけで公開を決めず、4つのreview dimensions、残余risk、ライセンス、出典、対象commitを確認し、決定理由をPull Requestまたはdecision recordへ残します。

初期運営は単独Maintainerの**Model B**です。別の適格なhuman reviewerを確保できない場合、authenticated Maintainerは自分の変更についても、対象commit、4観点、`reviewerKind`、独立human approvalがない事実、残余risk、未解決threadの解消を公開記録したうえで最終判断できます。存在しない独立承認を偽装しません。複数の適格なMaintainerまたはReviewerが継続参加できる状態になったら、著者以外が最終承認するModel Aへの移行を公開Issueで決定します。

## 意思決定

通常の変更はIssueで問題と制約を合意し、Pull Requestで実装と証拠をレビューします。軽微な編集はPull Requestだけで扱えます。互換性、schema、依存、公開方針、評価基準、フレームワーク版、ガバナンスを変える提案は、実装前にIssueとdecision recordを必要とします。

議論は合理的な期間のlazy consensusを目指します。合意できない場合、担当Maintainerが利用者影響、可逆性、証拠、代替案、反対意見を要約して決定します。決定は将来の証拠で再検討でき、権威だけを根拠に固定しません。

Releaseには、全検証、決定的build、security/accessibility確認、変更履歴、authenticated Maintainerのcommit単位の公開判断が必要です。Model Bでは独立human approvalの有無と`reviewerKind`を正直に開示し、構造上の`complete`や`automated`結果だけでは公開できません。

## 利益相反

金銭、雇用、所属、著作者関係、個人的関係、競合関係など、判断へ合理的な疑いを生じさせる利益相反は、IssueまたはPull Requestで開示します。該当者は最終承認、異議申立ての裁定、役割任命から退き、利益相反のないMaintainerまたはReviewerへ引き継ぎます。

全Maintainerが利益相反を持つ場合、影響を受けないReviewerを公開で募り、少なくとも2名の一致を必要とします。適切な独立判断者がいない場合はmergeまたはreleaseを保留します。

## 異議申立て

技術、教材、役割、運営の決定への異議申立ては、元の記録へリンクした新しい公開Issueで行います。申立てには、争点、見落とされた証拠、求める変更、利用者影響を記載します。個人情報や非公開の行動規範報告を公開Issueへ移しません。

元の決定者と利益相反のある人は裁定から外れます。別のMaintainerが記録と新証拠を確認し、維持、修正、撤回のいずれかと理由を公開します。別のMaintainerがいない場合は、対象観点のReviewer 2名が判断し、それも満たせなければ現状を変更せず保留します。

## framework update

CS2023、SWEBOK、SFIAの版は自動置換しません。framework updateには、次の順序を要求します。

1. 公式資料の新しい版、変更範囲、移行理由を示すIssue。
2. 30レッスン、90 mapping、3 Capstone、用語、rubricへの影響を列挙するimpact matrix。
3. 旧版との対応、追加・削除・意味変更、根拠を示すmapping PR。
4. 対象観点のReviewerによる再評価とMaintainerの明示的判断。
5. 利用者に互換性と再学習範囲を伝えるrelease note。

四半期ごとに公式公開情報を確認できますが、確認日だけを更新成果にせず、版変更がある場合は上記の専用手続きを行います。

## 後継と継続性

Maintainerが90日以上活動できない見込みの場合、可能な限り30日前までに公開Issueで権限、未完了判断、release状態、後継候補を引き継ぎます。後継候補はReviewer要件を満たし、少なくとも2名の既存Maintainerまたは利益相反のないReviewerから公開承認を得ます。

最後のMaintainerが応答不能の場合、Reviewer要件を満たすContributorが後継提案を作成し、異なる観点を担当できるReviewer 2名の承認を得ます。必要な承認者がいない間は、新release、権限拡大、ガバナンス変更を行わず、再現可能な保守と安全上の縮小だけを許可します。

権限を離れるMaintainerは、可能な範囲でrepository accessを返却し、未公開情報を保持せず、後継の判断へ拒否権を残しません。役割の変更は公開のgovernance記録へ追記します。
