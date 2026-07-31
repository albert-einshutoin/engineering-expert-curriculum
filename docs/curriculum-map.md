# Engineering Expert Curriculum Map

この文書は、30レッスンの順序、依存関係、世界標準との対応、統合Capstoneでの
実践責任を一か所でレビューするための地図である。データ表はsource of truthから
機械生成し、学び方と解釈上の注意は人が保守する。

## 地図の読み方

レッスン番号は難易度の順位ではなく、前提関係をレビューするための安定した順序で
ある。Prerequisitesを先に満たし、各5レッスン後のmastery gateで複数領域を結ぶ
成果物を作る。Primary Capstoneはそのレッスンの能力を最終的に説明する責任を持ち、
Supporting Capstoneは別文脈で同じ能力を再利用する。

Framework欄はCS2023、SWEBOK、SFIAの語彙との関係を示す。資格、職位、SFIA責任level
の認定ではない。`direct`、`foundational`、`partial`は重なりの強さであり、mappingの
rationaleと制限は公開コンピテンシー表で確認する。

<!-- BEGIN GENERATED CURRICULUM MAP -->
### リリース集計

| 項目 | 件数・固定値 |
|---|---|
| 保存カタログ | 1,140 items |
| カタログ SHA-256 | `4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473` |
| コアレッスン | 30 complete lessons |
| コンピテンシー対応 | 90 mappings |
| 統合 Capstone | 3 projects |
| Primary exercise coverage | 30/30 |

### Framework baseline

| Framework | Version | Official source | Verified |
|---|---|---|---|
| CS2023 | Final Report | [CS2023](https://csed.acm.org/final-report/) | 2026-07-31 |
| SWEBOK | V4.0a | [SWEBOK](https://www.computer.org/education/bodies-of-knowledge/software-engineering) | 2026-07-31 |
| SFIA | 9 | [SFIA](https://sfia-online.org/en/sfia-9/skills/all-skills-a-z?set_language=en) | 2026-07-31 |

### Mastery gates

| Order | Gate | After | Artifact | Review evidence |
|---:|---|---:|---|---|
| 1 | `foundation` | 5 | 未知システムの診断記録 | 機構と証拠を説明できる |
| 2 | `builder` | 10 | 契約・テスト・脅威モデル付きサービス | 信頼性を設計へ埋め込める |
| 3 | `scaler` | 15 | 負荷・障害・SLO実験 | 分散失敗を測定し判断できる |
| 4 | `human` | 20 | アクセシブルな検証済み改善 | 人と社会への影響を説明できる |
| 5 | `operator` | 25 | 移行・運用・費用計画 | 変更を安全かつ経済的に進められる |
| 6 | `leader` | 30 | 他者が実行可能な技術方針 | 不確実性の中で組織を前進させられる |

### 30-lesson release map

| # | Lesson | Track / Stage | Prerequisites | Mastery gate | CS2023 | SWEBOK | SFIA | Primary / Supporting Capstone |
|---:|---|---|---|---|---|---|---|---|
| 1 | `core-01-systems-tradeoffs`<br>システム思考とエンジニアリングのトレードオフ | foundations / 1 | — | `foundation` | `SF` Systems Fundamentals (direct) | `CHAPTER 18` Engineering Foundations (direct) | `DESN` Systems design (direct) | Primary: `global-service`<br>Supporting: `legacy-evolution`, `oss-launch` |
| 2 | `core-02-algorithms-measurement`<br>アルゴリズム選択を計算量と測定で検証する | foundations / 1 | `core-01-systems-tradeoffs` | `foundation` | `AL` Algorithmic Foundations (direct) | `CHAPTER 17` Mathematical Foundations (foundational) | `PROG` Programming/software development (foundational) | Primary: `global-service`<br>Supporting: `legacy-evolution`, `oss-launch` |
| 3 | `core-03-architecture-memory-caches`<br>CPU・メモリ経路とアクセス局所性 | foundations / 1 | `core-01-systems-tradeoffs` | `foundation` | `AR` Architecture and Organization (direct) | `CHAPTER 16` Computing Foundations (foundational) | `IFDN` Infrastructure design (foundational) | Primary: `global-service`<br>Supporting: `legacy-evolution` |
| 4 | `core-04-os-processes-concurrency`<br>プロセス・スレッド・並行性の不変条件 | foundations / 1 | `core-02-algorithms-measurement`<br>`core-03-architecture-memory-caches` | `foundation` | `OS` Operating Systems (direct) | `CHAPTER 16` Computing Foundations (foundational) | `PROG` Programming/software development (direct) | Primary: `global-service`<br>Supporting: `legacy-evolution` |
| 5 | `core-05-networks-latency-failure`<br>ネットワーク遅延と部分失敗を層別に診断する | foundations / 1 | `core-04-os-processes-concurrency` | `foundation` | `NC` Networking and Communication (direct) | `CHAPTER 16` Computing Foundations (foundational) | `NTDS` Network design (direct) | Primary: `global-service`<br>Supporting: `legacy-evolution` |
| 6 | `core-06-requirements-domain-modeling`<br>要求を発見し、境界と例外をドメインモデルへ結ぶ | build / 2 | `core-01-systems-tradeoffs` | `builder` | `SE` Software Engineering (partial) | `CHAPTER 01` Software Requirements (direct) | `REQM` Requirements definition and management (direct) | Primary: `global-service`<br>Supporting: `legacy-evolution`, `oss-launch` |
| 7 | `core-07-api-contract-design`<br>API契約を失敗、再送、進化まで設計する | build / 2 | `core-06-requirements-domain-modeling` | `builder` | `SE` Software Engineering (partial) | `CHAPTER 03` Software Design (direct) | `SWDN` Software design (direct) | Primary: `global-service`<br>Supporting: `legacy-evolution`, `oss-launch` |
| 8 | `core-08-modularity-evolutionary-architecture`<br>変更理由でモジュール境界を設計しADRで更新する | build / 2 | `core-06-requirements-domain-modeling`<br>`core-07-api-contract-design` | `builder` | `SE` Software Engineering (partial) | `CHAPTER 02` Software Architecture (direct) | `ARCH` Solution architecture (direct) | Primary: `legacy-evolution`<br>Supporting: `global-service`, `oss-launch` |
| 9 | `core-09-test-strategy-tdd`<br>TDDとリスク別テスト戦略で変更を証明する | build / 2 | `core-02-algorithms-measurement`<br>`core-08-modularity-evolutionary-architecture` | `builder` | `SE` Software Engineering (partial) | `CHAPTER 05` Software Testing (direct) | `TEST` Functional testing (direct) | Primary: `legacy-evolution`<br>Supporting: `global-service`, `oss-launch` |
| 10 | `core-10-threat-modeling-secure-design`<br>脅威モデルを設計・検証・残余リスクへ接続する | build / 2 | `core-07-api-contract-design`<br>`core-09-test-strategy-tdd` | `builder` | `SEC` Security (direct) | `CHAPTER 13` Software Security (direct) | `SCTY` Information security (direct) | Primary: `oss-launch`<br>Supporting: `global-service`, `legacy-evolution` |
| 11 | `core-11-data-modeling-storage`<br>アクセスパターンと制約からストレージADRを再計算する | data-scale / 3 | `core-06-requirements-domain-modeling` | `scaler` | `DM` Data Management (direct) | `CHAPTER 16` Computing Foundations (foundational) | `DTAN` Data modelling and design (direct) | Primary: `global-service`<br>Supporting: `legacy-evolution` |
| 12 | `core-12-transactions-isolation-consistency`<br>分離異常を再現し、abortとretryまで設計する | data-scale / 3 | `core-11-data-modeling-storage` | `scaler` | `DM` Data Management (direct) | `CHAPTER 16` Computing Foundations (foundational) | `DBDS` Database design (direct) | Primary: `global-service`<br>Supporting: `legacy-evolution` |
| 13 | `core-13-distributed-coordination-failure`<br>重複・順序・分断を再現し復旧境界を設計する | data-scale / 3 | `core-05-networks-latency-failure`<br>`core-12-transactions-isolation-consistency` | `scaler` | `PDC` Parallel and Distributed Computing (direct) | `CHAPTER 16` Computing Foundations (foundational) | `DESN` Systems design (direct) | Primary: `global-service`<br>Supporting: `legacy-evolution` |
| 14 | `core-14-performance-capacity`<br>負荷曲線と実測profileから安全容量を判断する | data-scale / 3 | `core-02-algorithms-measurement`<br>`core-03-architecture-memory-caches`<br>`core-11-data-modeling-storage` | `scaler` | `SF` Systems Fundamentals (foundational) | `CHAPTER 06` Software Engineering Operations (direct) | `CPMG` Capacity management (direct) | Primary: `global-service`<br>Supporting: `legacy-evolution`, `oss-launch` |
| 15 | `core-15-reliability-observability-slo`<br>利用者journeyからSLI、SLO、alert、runbookを導く | data-scale / 3 | `core-05-networks-latency-failure`<br>`core-13-distributed-coordination-failure`<br>`core-14-performance-capacity` | `scaler` | `SE` Software Engineering (partial) | `CHAPTER 06` Software Engineering Operations (direct) | `SLMO` Service level management (direct) | Primary: `global-service`<br>Supporting: `legacy-evolution`, `oss-launch` |
| 16 | `core-16-hci-usability-accessibility`<br>人間中心設計で静的サイトの利用可能性を監査する | human-product / 3 | `core-06-requirements-domain-modeling` | `human` | `HCI` Human-Computer Interaction (direct) | `CHAPTER 05` Software Testing (partial) | `ACIN` Accessibility and inclusion (direct) | Primary: `oss-launch`<br>Supporting: `global-service` |
| 17 | `core-17-graphics-visual-information`<br>静的グラフィックスを同等の情報構造として設計する | human-product / 3 | `core-03-architecture-memory-caches`<br>`core-16-hci-usability-accessibility` | `human` | `GIT` Graphics and Interactive Techniques (direct) | `CHAPTER 03` Software Design (partial) | `VISL` Data visualisation (direct) | Primary: `oss-launch`<br>Supporting: `global-service` |
| 18 | `core-18-product-discovery-experiments`<br>反証可能な仮説から停止判断までを事前に設計する | human-product / 3 | `core-06-requirements-domain-modeling`<br>`core-16-hci-usability-accessibility` | `human` | `SE` Software Engineering (partial) | `CHAPTER 01` Software Requirements (direct) | `URCH` User research (direct) | Primary: `oss-launch`<br>Supporting: `global-service` |
| 19 | `core-19-technical-communication-design-docs`<br>読者の判断を支える設計文書とADRを構成する | human-product / 3 | `core-01-systems-tradeoffs`<br>`core-06-requirements-domain-modeling` | `human` | `SEP` Society, Ethics, and the Profession (direct) | `CHAPTER 14` Software Engineering Professional Practice (direct) | `INCA` Content design and authoring (direct) | Primary: `legacy-evolution`<br>Supporting: `global-service`, `oss-launch` |
| 20 | `core-20-ethics-privacy-societal-impact`<br>倫理・privacy・社会的影響を設計制約へ変える | human-product / 3 | `core-10-threat-modeling-secure-design`<br>`core-16-hci-usability-accessibility`<br>`core-19-technical-communication-design-docs` | `human` | `SEP` Society, Ethics, and the Profession (direct) | `CHAPTER 14` Software Engineering Professional Practice (direct) | `PEDP` Information and data compliance (partial) | Primary: `global-service`<br>Supporting: `legacy-evolution`, `oss-launch` |
| 21 | `core-21-maintenance-legacy-comprehension`<br>未知を残したままlegacy systemを安全に変更する | sustain / 4 | `core-08-modularity-evolutionary-architecture`<br>`core-09-test-strategy-tdd` | `operator` | `SE` Software Engineering (partial) | `CHAPTER 07` Software Maintenance (direct) | `ASUP` Application support (direct) | Primary: `legacy-evolution`<br>Supporting: `oss-launch` |
| 22 | `core-22-evolution-safe-migrations`<br>互換性を保つschema migrationを段階実行する | sustain / 4 | `core-08-modularity-evolutionary-architecture`<br>`core-12-transactions-isolation-consistency`<br>`core-21-maintenance-legacy-comprehension` | `operator` | `SE` Software Engineering (partial) | `CHAPTER 06` Software Engineering Operations (direct) | `CHMG` Change control (direct) | Primary: `legacy-evolution` |
| 23 | `core-23-incident-response-learning`<br>incident responseを検証可能な学習へ変える | sustain / 4 | `core-15-reliability-observability-slo`<br>`core-21-maintenance-legacy-comprehension` | `operator` | `SEC` Security (partial) | `CHAPTER 06` Software Engineering Operations (direct) | `USUP` Incident management (direct) | Primary: `legacy-evolution`<br>Supporting: `global-service`, `oss-launch` |
| 24 | `core-24-delivery-ci-release-safety`<br>CI・段階配信・supply chainを結果証拠で閉じる | sustain / 4 | `core-09-test-strategy-tdd`<br>`core-15-reliability-observability-slo` | `operator` | `SE` Software Engineering (partial) | `CHAPTER 08` Software Configuration Management (direct) | `RELM` Release management (direct) | Primary: `oss-launch`<br>Supporting: `global-service`, `legacy-evolution` |
| 25 | `core-25-engineering-economics-capacity`<br>engineering economicsで信頼性と容量へ投資する | sustain / 4 | `core-14-performance-capacity`<br>`core-15-reliability-observability-slo`<br>`core-24-delivery-ci-release-safety` | `operator` | `SE` Software Engineering (partial) | `CHAPTER 15` Software Engineering Economics (direct) | `INVA` Investment appraisal (direct) | Primary: `legacy-evolution`<br>Supporting: `global-service`, `oss-launch` |
| 26 | `core-26-code-review-collaborative-quality`<br>コードレビューを協働品質システムとして運営する | lead / 5 | `core-09-test-strategy-tdd`<br>`core-19-technical-communication-design-docs` | `leader` | `SE` Software Engineering (partial) | `CHAPTER 12` Software Quality (direct) | `QUAS` Quality assurance (direct) | Primary: `oss-launch`<br>Supporting: `global-service`, `legacy-evolution` |
| 27 | `core-27-team-interfaces-sociotechnical-architecture`<br>チームインターフェースで社会技術アーキテクチャを設計する | lead / 5 | `core-08-modularity-evolutionary-architecture`<br>`core-19-technical-communication-design-docs`<br>`core-26-code-review-collaborative-quality` | `leader` | `SE` Software Engineering (partial) | `CHAPTER 10` Software Engineering Process (direct) | `ORDI` Organisation design and implementation (direct) | Primary: `legacy-evolution`<br>Supporting: `global-service`, `oss-launch` |
| 28 | `core-28-oss-governance-stewardship`<br>OSS governanceで貢献とリリースを持続可能にする | lead / 5 | `core-10-threat-modeling-secure-design`<br>`core-19-technical-communication-design-docs`<br>`core-26-code-review-collaborative-quality` | `leader` | `SEP` Society, Ethics, and the Profession (direct) | `CHAPTER 14` Software Engineering Professional Practice (direct) | `GOVN` Governance (direct) | Primary: `oss-launch` |
| 29 | `core-29-cross-cultural-async-collaboration`<br>時差と言語を越える非同期RFCを設計する | lead / 5 | `core-19-technical-communication-design-docs`<br>`core-27-team-interfaces-sociotechnical-architecture` | `leader` | `SEP` Society, Ethics, and the Profession (direct) | `CHAPTER 14` Software Engineering Professional Practice (direct) | `OFCL` Organisational facilitation (direct) | Primary: `oss-launch`<br>Supporting: `global-service`, `legacy-evolution` |
| 30 | `core-30-evidence-based-technical-leadership`<br>証拠と撤退条件で技術方針を率いる | lead / 5 | `core-20-ethics-privacy-societal-impact`<br>`core-25-engineering-economics-capacity`<br>`core-27-team-interfaces-sociotechnical-architecture`<br>`core-28-oss-governance-stewardship`<br>`core-29-cross-cultural-async-collaboration` | `leader` | `SEP` Society, Ethics, and the Profession (partial) | `CHAPTER 09` Software Engineering Management (direct) | `ITSP` Strategic planning (direct) | Primary: `global-service`<br>Supporting: `legacy-evolution`, `oss-launch` |

### Capstone coverage

| Capstone | Lessons | Primary exercises | Evidence kinds |
|---|---:|---:|---|
| `global-service` — 多地域の医療予約サービスを設計・運用する | 27 | 14 | `build`, `operate`, `explain`, `review` |
| `legacy-evolution` — 請求legacy systemを止めずに進化させる | 26 | 8 | `build`, `operate`, `explain`, `review` |
| `oss-launch` — アクセシブルな静的レポート生成器をOSSとして公開・運営する | 23 | 8 | `build`, `operate`, `explain`, `review` |
<!-- END GENERATED CURRICULUM MAP -->

## 推奨する進み方

最初は番号順を基本にするが、既に提出可能な証拠を持つ領域はrubricで診断してよい。
診断で`proficient`へ届かない観点があれば、そのlessonと前提へ戻る。各trackを読み
終えるだけで先へ進まず、artifact、teach-back、assessment reasoning、transferを
揃えてからmastery gateへ進む。

Capstoneでは一度に全機能を作らない。Milestoneごとにbuild、operate、explain、review
の証拠を保存し、第三者findingとauthor fix後の独立再評価を行う。一つの重要制約を
変えて判断が更新されることまでを成長の証拠とする。

## 更新方法

生成表を直接編集してはならない。source contentを変更後、次を実行する。

```console
python3.13 tools/generate_curriculum_map.py
python3.13 tools/generate_curriculum_map.py --check
```

手書き部分の変更は、学習設計と編集reviewの対象である。生成部分の変更は、lesson、
roadmap、competency、capstone、catalogの差分と同じPRでレビューする。

