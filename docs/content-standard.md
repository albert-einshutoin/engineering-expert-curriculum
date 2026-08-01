# Engineering Expert Curriculum コンテンツ品質標準

本書は、コアレッスンを単なる読み物ではなく、理解・実践・説明・判断・
転用・復習の証拠を提出できる教科書として維持するための規範である。

## 1. 適用範囲と規範語

この標準は30のコアレッスン、ロードマップ、コンピテンシー対応、統合
Capstone、およびそれらから生成する静的HTMLへ適用する。

`MUST` は例外なく満たす要件、`SHOULD` は理由と代替証拠が必要な要件、`MAY` は任意の改善として解釈することをMUSTとする。

読了、ページ表示、コマンドの終了コードだけを習得の証拠にしてはならない。

## 2. `complete` の定義

`status: complete` はmachine-validated structural completenessだけを示し、内容の正確性、human review、公開承認、学習者のmasteryを証明しないことをMUSTとする。

レッスンは、次のすべてを機械検証できる場合だけ `complete` を名乗ることができる。

1. 必須metadataと6つの著者執筆sectionが揃っている。
2. 全objectiveと5段階能力進行が、提出可能なevidenceへ追跡できる。
3. 成果物、説明、reasoning、transferの4種の証拠がある。
4. ラボ、assessment、rubric、source、1/7/30/90日後のreview構造が検証済みである。

公開commitは、全レッスンの構造的完全性に加え、release-level test、2回の決定的build、link検査、安全性検査、accessibility検査、review approvalを満たすことをMUSTとする。構造が一つでも欠ける場合はdraftへ戻すが、
`complete` だけを根拠に公開または習得済みと扱ってはならない。

## 3. 六段階 evidence loop

Evidence loopは Learn → Practice → Explain → Prove → Transfer → Review の順序をMUSTとする。

| 段階 | 学習者の行動 | MUSTとなる証拠 |
|---|---|---|
| Learn | 機構、境界、制約、失敗モードを理解する | objective、メンタルモデル、出典 |
| Practice | 固定条件で手を動かし結果を観測する | 3手順以上のlabと提出成果物 |
| Explain | 自分の言葉で因果関係と代替案を説明する | teach-backとexplanation evidence |
| Prove | もっともらしい誤診を反証して判断する | 問いとexpected evidenceを持つassessment |
| Transfer | 一つの重要制約を変え、判断を再実行する | transfer taskと更新された証拠 |
| Review | 時間を空けて再現・説明・修正する | 1/7/30/90日後のpromptとrubric再評価 |

Reviewで見つかった誤解はLearnへ戻し、成果物、説明、判断根拠を更新する。
同じ回答を再読するだけではReviewの証拠にならない。

## 4. 著者執筆と構造化データの責任分離

`body.html` の著者執筆sectionと `lesson.json` の構造化データは責任境界を分離することをMUSTとする。

`body.html` は次の6 sectionをこの順序でMUSTとして持つ。

1. なぜ重要か
2. メンタルモデル
3. 動く例で考える
4. トレードオフと失敗モード
5. 知識チェック
6. 出典と次の学習

一方、到達目標、能力進行、実践ラボ、teach-back、assessment、transfer、
review schedule、rubric、sourcesは`lesson.json`から共通templateが生成する。
著者は生成sectionを`body.html`へ複製してはならない。rendererは構造化値を
escapeし、body fragmentは安全性検査を通したものだけを挿入する。

## 5. Objective・能力・evidenceの追跡

すべてのobjectiveと能力段階は既知のevidence IDへ追跡でき、すべてのevidenceはobjectiveまたは能力段階から参照されることをMUSTとする。

各objectiveは観測可能な動詞を使い、一つ以上のevidence IDを参照する。
Recognize、Explain、Apply、Diagnose、Leadの5段階は順序を保ち、各段階が
一つ以上のevidenceを参照する。全evidence IDはobjectiveと能力進行の双方から
MUSTとして参照され、件数合わせの孤立evidenceを置いてはならない。

Evidenceは成果物の存在だけでなく、入力条件、操作、観測、結論、反証条件を
第三者が追跡できる記述にする。別名の同一成果物を複数種類として数えない。

## 6. ラボ成果物

各labは提出可能なartifact名、3手順以上、失敗時に保存する観測値、安全な停止条件を持つことをMUSTとする。

ラボは3手順以上をMUSTとし、提出成果物の名前と含める情報を明記する。
固定fixture、入力version、乱数seed、測定条件、実行commandなど、別の人が
再現するためのprovenanceをSHOULDとして残す。外部serviceや最新価格に依存する
場合は、教材fixtureと実環境の事実を明確に分離する。

破壊的操作、秘密情報、無制限の負荷、課金を伴う操作を前提にしてはならない。
成功終了だけでなく、失敗時に保存する観測値と停止条件を定義する。

## 7. Reasoning assessment

各assessmentは2問以上とし、reasoning、代替案、反証、結論を変える条件を問うことをMUSTとする。

Assessmentは少なくとも2問をMUSTとする。暗記した用語や正解の選択だけでなく、
制約、代替案、因果関係、反証、結論を変える条件のいずれかを説明させる。
`expectedEvidence` は模範解答の丸暗記ではなく、採点者が確認する観測可能な
証拠を示す。問いとexpected evidenceを同文にしてはならない。

少なくとも一問は、もっともらしい診断を別仮説と区別させる。自動keyword判定で
reasoningを証明したことにせず、学習設計reviewerが内容を判断する。

## 8. 評価rubric

各rubricはtechnical correctness、judgment、evidence、communicationの4観点×incomplete、developing、proficient、exemplaryの4段階を持つことをMUSTとする。

全レッスンはtechnical correctness、judgment、evidence、communicationの4観点を
持ち、各観点をincomplete、developing、proficient、exemplaryの4段階で記述する。
段階文は相互に異なり、採点者が成果物から観測できる振る舞いを表す。

`proficient` は支援なしで正しい成果を説明・再現できる合格境界として定義することをMUSTとする。
`exemplary` は量の多さではなく、不確実性、反例、他者review、system改善まで
扱えることを示す。学習者のrubric評価は構造的complete判定とは別に記録する。

## 9. Source hierarchy

各lessonはsource hierarchyに従い、異なる2件以上のHTTPS URLを持つことをMUSTとする。

主張に最も近い原典を優先する。

1. 規範、互換性、適合要件にはversionを特定した`standard`を使う。
2. 経験的効果や比較には方法と限界を確認した`peer-reviewed`研究を使う。
3. 実装機構、公式手順、原著者の判断には`primary`資料を使う。

各レッスンは異なるURLのHTTPS sourceを2件以上MUSTとして持つ。二次解説は本文の
補助としてMAYで紹介できるが、structured sourcesや必須2件へ算入しない。Sourceの
権威だけで主張を正当化せず、版、公開日、適用範囲、反対証拠を編集reviewで確認する。
到達不能URLを新しい版へ自動置換せず、専用PRで意味とmappingを再評価する。

## 10. Accessibilityと静的配信

公開成果物はHTMLとCSSのみで理解でき、JavaScriptなしで全情報へ到達できることをMUSTとする。v0.1.0はHTML/CSS-onlyとし、v0.2.0は承認済みsimulation lessonに限り、単一のrepository-owned `static/visualization.js`を任意のprogressive enhancementとしてMAYで読み込む。
runtimeはnetwork、storage、analytics、URL state、third-party dependencyを使用してはならない。JavaScriptの404、構文error、初期化error、無効化時にも完全なstatic oracleを保持することをMUSTとする。
CSSを無効にしても読み順と依存関係が残り、色や線だけへ意味を委ねない。

すべてのactive elementはkeyboardで到達・操作でき、visible focusと単独で理解できる名前を持つことをMUSTとする。

全ページは日本語の文書言語、固有title、一つの`main`と`h1`、skip link、論理的な
heading、visible focusを持つ。Tableにはcaptionとscope、figureにはfigcaption、
linkには単独で理解できる名前を付ける。200% zoom、狭い画面、high contrast、printで
情報を失わない。承認済みのdeferred classic runtime以外のscript、iframe、object、embed、form、inline event handler、remote
font/image、unsafe URL schemeは禁止する。meta CSPはexact v0.2 policyを持ちresourceより前に置く。`frame-ancestors`はmeta CSPでは強制されず、GitHub Pagesで任意response headerを設定できないため、clickjacking防止を主張しない。

## 11. Review roles

技術的正確性、学習設計・証拠、アクセシビリティ、編集・出典の4 review dimensionsを独立して記録することをMUSTとする。

| 役割 | 独立して確認する責任 |
|---|---|
| 技術的正確性 | 機構、code、測定、制約、failure mode、sourceとの一致 |
| 学習設計・証拠 | objective、六段階loop、assessment、transfer、rubricの採点可能性 |
| アクセシビリティ | semantic HTML、keyboard、読み順、zoom、contrast、print |
| 編集・出典 | 用語、断定範囲、version、引用、link、Errata履歴 |

各review記録は `reviewerKind` を `human`、`ai-assisted`、`automated` のいずれかとして正直に開示することをMUSTとする。

AI支援または自動生成のreviewを `human` approvalとして扱わないことをMUSTとする。

著者のself-reviewは必須だが、4 dimensionsすべての代わりにはならない。同一人物が
複数dimensionを担当する場合も各観点のfindingと再確認結果を別々に記録する。重大な
修正後はauthor fix後のsnapshotを再評価し、最初のレビュー結果を流用しない。

## 12. 完了、更新、Errata、例外

公開可能性はcommit単位のPR・release evidenceと、認証済みmaintainerによる明示的decisionで判定することをMUSTとする。

`v0.1.0` から発効するこの開示方針を、既存contentへ遡及してhuman approvalを推定または付与するために使わないことをMUSTとする。

承認は将来の変更にのみ効力を持ち、過去または後続のcommitへ自動継承しないことをMUSTとする。

Completeへの構造変更は、対象lesson、提出成果物、実行した検証、review結果、残る
制限をPRへ記録する。Framework version、主要source、prerequisite、primary Capstoneを
変える場合は、30-lesson mapと全90 mappingを再生成・再検証する。

公開後の誤りはErrataとして影響範囲、旧記述、新記述、修正理由、検証日を残す。
技術的誤り、安全性、accessibility阻害はstatusをdraftへ戻す理由になる。

SHOULD要件への例外は、対象、必要性、期限、代替証拠、ownerを記録する。MUST要件、
JavaScriptなしのbaseline、catalog保存には例外を認めない。

## 13. Contributor・reviewerチェックリスト

- Contributorとreviewerは公開前に次のチェックリストを上から順に確認することをMUSTとする。

- [ ] 構造的completeとcommit単位の公開可能性を別々に判定した。
- [ ] 6 authored sectionsが順序どおりで、重複本文やplaceholderがない。
- [ ] 全objectiveと5能力段階が4種evidenceへ追跡できる。
- [ ] Labを第三者が安全に再現でき、artifactと失敗証拠を提出できる。
- [ ] 2問以上のassessmentがreasoning、代替案、反証を要求する。
- [ ] Transferが重要制約を変え、同じ判断のコピーになっていない。
- [ ] Rubricの4観点×4段階が観測可能で、proficient境界が明確である。
- [ ] Source hierarchy、version、関連性、断定範囲、異なる2件以上のHTTPS URLを確認した。
- [ ] Semantic HTML、keyboard、zoom、contrast、print、JavaScript無効時の完全性を確認した。
- [ ] 4 review dimensions、reviewerKind、author fix、再確認結果を記録した。
- [ ] v0.1.0以後のreviewerKindを開示し、AI reviewをhuman approvalに数えていない。
- [ ] Generated map、full tests、2回build、local link、安全性、accessibility検査と認証済みmaintainer decisionが揃った。
