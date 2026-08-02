# Security Policy

Engineering Expert Curriculumのv0.1.0はHTML/CSS-onlyです。v0.2.0は完全なsemantic HTMLをbaselineとし、simulation lessonだけで単一のdependency-free first-party runtimeを任意に読み込みます。このruntimeはnetwork、storage、analytics、URL state、third-party codeを使わず、learner dataを収集・保存・送信しません。つまりlearner dataを保存しません。ただし、build処理、JavaScript source/DOM境界、template escaping、リンク、GitHub Actions、配信設定には脆弱性が入り得ます。

exact meta CSPはruntimeとinline scriptを分離し、resourceより前に配置します。ただし`frame-ancestors`はmeta CSPで強制されず、GitHub Pagesではこのrepositoryが任意response headerを設定できないため、本projectはclickjacking防止を保証しません。

CIのbrowserはregistry-qualified OCI digestと公式HTTPS archive URL、version、SHA-256で固定します。checksum一致前の展開、platform間fallback、matrix外browserの自動探索を許しません。cacheと検証reportは`outputs/`へ限定し、release artifactへ混入させません。

固定digestかつnon-root OCIのbrowser jobは、既定seccompがChromiumの内側のuser-namespace sandboxを許可しないため、installerとrunnerの両方へ明示的に`--oci-container-no-sandbox`を渡します。このopt-inだけがChromiumへ`--no-sandbox`を追加し、通常のlocal Linuxではbrowser sandboxを維持し、macOSではopt-inを拒否します。CIでprocess-level sandboxを外しても、隔離された一時OCI container、固定browser archive、`file://`またはloopback HTTPだけに閉じたURL authorityは維持します。

Safari WebDriver 26.5では、外部`file://` main resourceがWebKit sandboxの外側として拒否されることを実機で確認しています。Safariの必須runtime smokeはmatrixで`loopback-http`へ閉じ、desktopと390px narrow viewportの2 profileをpre-product harnessで検証します。これはSafariのfile成功やmobile device emulationを意味しません。Chromium・Firefoxのfile/HTTP runtime contractと、静的no-JS/file checker contractは削除せず維持します。

rootのrelease manifestはcommitと配信対象byteの整合性を検査します。deployed verifierはHTTPSの同一Pages origin・同一subpathだけを、redirect、retry、時間、file数、byte数の上限内で取得します。ただしSHA-256 manifestは署名ではなく、publisherやworkflowの真正性を単独で保証しません。信頼の根はreview済みcommit、branch protection、digest固定workflow/action、GitHub Pages deploymentです。

## サポート対象

| 対象 | サポート |
|---|---|
| `main`の最新commit | 対象 |
| 最新リリース（存在する場合） | 対象 |
| 過去リリース、fork、変更済み配布物 | 原則対象外 |

報告時点の最新リリースと`main`を調査し、必要に応じて双方へ修正します。古い版だけに存在する問題は、影響と修正可能性を評価して対応を決めます。

## 非公開で報告する

脆弱性の疑いは、対象repositoryの**Security**タブから**Advisories**を開き、**Privately report a vulnerability**を選択してGitHub Security Advisoryを作成してください。これが本プロジェクトで指定する唯一の非公開脆弱性報告経路です。

この経路は、空のpublic repositoryを作成した直後、最初のcontent pushより前に有効化してAPIで確認します。有効化または確認に失敗した場合はcontentを公開しません。

公開Issueを作成しないでください。実証コード、秘密情報、攻撃可能なURL、未修正の詳細をDiscussion、Pull Request、commitへ投稿しないでください。非公開報告機能が表示されない場合は、公開の場へ詳細を移さず、機能が利用可能になるまで報告情報を保持してください。

報告には、安全に共有できる範囲で次を含めます。

- 影響を受けるcommit、release、file、処理。
- 前提条件と再現手順。破壊的な実証は避ける。
- 想定する機密性、完全性、可用性への影響。
- 既知の回避策と、既に第三者へ開示した範囲。
- 希望する公開時期や共同開示上の制約。

## 応答と修正

Maintainerは通常5営業日以内に受領を確認し、その後は通常10営業日以内を目安に、調査状況または次回更新予定を共有します。これらは状況共有の目標であり、安全性を損なう修正期限の約束ではありません。

影響、悪用可能性、修正risk、下流利用者を評価し、必要に応じて公開範囲の縮小、回避策、patch、release、advisoryを準備します。修正日は調査結果に基づいて報告者と調整し、検証前の期限を断定しません。報告者が望む場合は、GitHub Advisory上で謝辞の表記を確認します。

修正公開後は、影響範囲、修正版、回避策、credit、判断根拠を、悪用を不必要に容易にしない範囲でadvisoryへ記録します。

## Scopeの目安

次はsecurity reportの対象例です。

- path traversal、symlink race、生成先逸脱、任意file overwrite。
- authored HTMLやstructured contentからのscript実行、unsafe URL、escape回避。
- first-party runtimeのDOM allowlist逸脱、network/storage利用、timerや状態のfigure間漏洩。
- CI権限の過大付与、secret露出、untrusted contributionの危険な実行。
- 配布物の完全性を偽る決定性、検証、publication boundaryの欠陥。

単なる誤字、教材内容の通常の誤り、到達不能linkは[ERRATA.md](ERRATA.md)の公開訂正手順を使います。実際の悪用経路や安全上の重大な誤誘導を含む場合は、先に上記の非公開経路を使ってください。

## Safe harbor

善意の調査では、最小限のデータと操作で確認し、privacy侵害、service妨害、持続的access、第三者への拡散を避けてください。許可のないsystemやforkを試験対象に含めないでください。本プロジェクトは、これらの条件に従う善意の報告へ協力的に対応しますが、第三者のsystemや法的権限を代理して許可するものではありません。
