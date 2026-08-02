# Engineering Expert Curriculum

[English summary](README.en.md)

1,140項目の知識地図と30のコアレッスンを使い、世界で通用するエンジニアリング判断を成果物で身につける、日本語中心の静的OSS教材です。知識の列挙ではなく、制約を理解し、手を動かし、自分の言葉で説明し、証拠で判断し、別条件へ転用できる状態を目指します。

> Learn → Practice → Explain → Prove → Transfer → Review

## 教材の構成

- 既存の知識領域を失わない1,140項目の静的カタログ
- 基礎から技術リーダーシップまでを横断する30のコアレッスン
- 学習成果を第三者が確認する6つの習熟ゲート
- 複数分野の判断を統合する3つのCapstone
- CS2023、SWEBOK V4.0a、SFIA 9への根拠付き対応表
- 前提関係、ラボ、assessment、transfer、rubric、1/7/30/90日後の復習

30レッスンは「基礎」「信頼できるソフトウェア」「データとスケール」「人とプロダクト」「継続と運用」「リードと貢献」の6領域を進みます。各領域の終わりで、未知システムの診断記録、テストと脅威モデルを持つサービス、障害実験とSLO、アクセシブルな改善、移行・運用・費用計画、他者が実行可能な技術方針という6つの習熟ゲートを通過します。

Capstoneでは、グローバルサービスの設計と運用、レガシーシステムの安全な進化、OSSプロダクトの公開と継続運営に取り組みます。提出物の存在だけでなく、入力、操作、観測、判断、反証条件、第三者レビュー後の修正までを証拠にします。

## 静的配信の契約

v0.1.0はHTML/CSS-onlyの不変なリリースです。v0.2.0では、HTMLとCSSだけで全内容を理解できるno-JS baselineを保ったまま、simulationを持つ承認済みレッスンだけがrepository-ownedの`static/visualization.js`をprogressive enhancementとして読み込みます。ビルド後の`site/index.html`を直接開く`file://`環境とGitHub Pagesの双方で、JavaScriptが無効・失敗・遮断された場合も同じ学習情報へ到達できます。

runtimeはdependency-freeで、network、storage、analytics、URL stateを使いません。アカウント、server API、databaseはなく、学習者データを収集・保存・送信しません。

ブラウザ組み込み検索、意味のあるHTML、印刷可能なレイアウトを基準にしています。CSSを無効にしても読み順と依存関係が残り、色や接続線だけに意味を委ねません。

承認済み12ページでは10種の図解を提供し、keyboard、reduced motion、forced colorsでも同じ因果関係と状態を追跡できます。公開候補はversion固定されたChromium・Firefoxとinstalled Safariで検証し、browserのcache、screenshot、raw performance reportは`outputs/`だけに置いて配布物へ含めません。ChromiumとFirefoxは`file://`とPages形式のloopback HTTPを検証します。Safari WebDriverは外部file main resourceをWebKit sandboxで拒否するため、同じpre-product harnessをloopback HTTPのdesktop幅と390px narrow viewportで実行します。これはmobile device emulationの主張ではなく、静的no-JS/file契約は別のbrowser/checker証拠で維持します。

公開時はcommit、各HTML/CSS/JavaScriptのbyte数とSHA-256をrootのrelease manifestへ記録し、GitHub Pages配信後に同じbytesを再検証します。manifestは署名やpublisherの真正性を単独で証明するものではありません。またmeta CSPでは`frame-ancestors`を強制できず、GitHub Pagesで任意response headerを設定できないため、clickjacking防止は保証しません。

## ローカルで読む

Python 3.12以降を用意し、リポジトリのルートで次を実行します。ビルド時のPython以外に実行時依存はありません。

```sh
python3 tools/build.py
open site/index.html
```

`open`がない環境では、ブラウザから`site/index.html`を開いてください。`site/`は再生成可能な成果物なのでGit管理しません。

## 検証

変更前に対象契約を失敗させ、最小の修正で通した後、全テストを実行します。

```sh
python3 -m unittest discover -s tests -v
python3 tools/build.py
```

ビルドは入力を検証してから決定的な静的成果物を生成します。ネットワークへ接続せず、同一入力から同一出力を作る設計です。

## 学習を始める

1. ロードマップで前提レッスンと次の習熟ゲートを確認します。
2. レッスンの到達目標と出典を読み、ラボの停止条件を確認します。
3. Learn → Practice → Explain → Prove → Transfer → Reviewを順に実行します。
4. 成果物、説明、判断根拠、条件変更後の結果を保存します。
5. rubricの`proficient`境界を使い、第三者に証拠をレビューしてもらいます。
6. 1/7/30/90日後に再現し、誤解があればLearnへ戻って証拠を更新します。

教材の`status: complete`はmachine-validated structural completenessだけを表します。技術的正確性、公開承認、human review、学習者の習得を自動的に証明しません。レビュー記録の`reviewerKind`は`human`、`ai-assisted`、`automated`のいずれかを明示し、AI支援または自動レビューをhuman approvalとして扱いません。

## リポジトリ

| パス | 役割 |
|---|---|
| `content/catalog.json` | 1,140項目の正規カタログ |
| `content/lessons/` | 30レッスンのmetadataと本文 |
| `content/roadmap.json` | 前提グラフと習熟ゲート |
| `content/competencies.json` | コンピテンシー対応と根拠 |
| `content/capstones/` | 3つの統合課題 |
| `curriculum_builder/` | 標準ライブラリだけを使う検証・生成処理 |
| `templates/`, `static/` | HTML template、CSS、任意のfirst-party progressive runtime |
| `tests/` | 内容、構造、安全性、決定性の契約 |
| `site/` | ローカル生成物。Git管理対象外 |

## 貢献・訂正・安全性

コード、教材、出典、アクセシビリティの改善は[CONTRIBUTING.md](CONTRIBUTING.md)に従ってください。公開済み教材の誤りと訂正履歴は[ERRATA.md](ERRATA.md)、意思決定と役割は[GOVERNANCE.md](GOVERNANCE.md)に記録します。

脆弱性を疑う情報は公開Issueへ書かず、[SECURITY.md](SECURITY.md)に記載したGitHubの非公開報告経路を使ってください。コミュニティで期待する行動は[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)に定めています。

## コンピテンシー対応について

CS2023、SWEBOK、SFIAの名称と資料は、それぞれの権利者に帰属します。本プロジェクトの対応表は学習目標との関係を説明するもので、各団体による認定、承認、資格付与を意味しません。版の更新は自動置換せず、影響分析とレビューを伴う変更として扱います。

## Licenseと引用

コードと教材は[MIT License](LICENSE)で提供します。研究、研修、教材比較で参照する場合は[CITATION.cff](CITATION.cff)のmetadataを利用できます。変更履歴は[CHANGELOG.md](CHANGELOG.md)を参照してください。
