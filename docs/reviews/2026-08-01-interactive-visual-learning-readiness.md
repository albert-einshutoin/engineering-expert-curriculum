# Interactive Visual Learning release readiness

status: **READY / maintainer release decision pending**
reviewed implementation parent SHA: `4a8ac5982b33729a564777c269278ec837f6e712`
checked at JST: `2026-08-02T19:57:20+0900`
reviewerKind: ai-assisted

この記録は、Safari WebDriverの実capabilityに合わせたreviewed contract amendmentと、そのimplementation parent上で完了したclean release gateをまとめる。自動検証はREADYだが、push、hosted CI、公開artifact検証、releaseの最終判断を済ませたことは意味しない。

## 結論

- clean implementation parentでcompile、931 unit tests、curriculum map、2 fresh builds、site checks、browser provisioning、166/166 real-browser matrix、release manifestを検証した。
- browser reportはtop-level `status=passed`、166 passed、failed 0、blocked 0、not-run 0である。
- Safari必須2件はPages形式のloopback HTTPでdesktop `1440×900`と390px narrow `390×844`を実行し、両方でrequested `crossover`、100 reset、violations 0、runtime error 0、baseline復帰を確認した。
- Safariの`file://`成功は主張しない。Safari WebDriver 26.5は外部file main resourceをWebKit sandbox外として拒否することを実観測したため、reviewed contractをHTTP desktop/narrowへ変更した。Chromium・Firefoxのfile+HTTP、静的no-JS/file contractは維持している。
- この文書の親commitをreviewed implementation SHAとして固定し、readiness記録以外の変更を混ぜない。

## レビュー集計

引き継ぎ済みレビューとamendment re-reviewはいずれも指摘0件（表記値 `0/0/0`）である。

| Task | Review | 結果 |
| --- | --- | --- |
| Task12 | spec | `0/0/0` |
| Task12 | JavaScript | `0/0/0` |
| Task12 | Python-security | `0/0/0` |
| Task13 | Python-security | `0/0/0` |
| Task13 | spec-CI | `0/0/0` |
| Safari sandbox amendment | spec / accessibility-repository / Python-security | `0/0/0` |
| Hosted gate remediation | Gitleaks / Linux provisioning / shallow-clone / Python-security | `0/0/0` |

レビュー指摘0件は実browser evidenceの代替ではないため、amendment後にfocused Safari 2件とfull 166件を新規evidence directoryで実行した。

## Capability amendment

Safari通常起動後のbounded WebDriver診断ではsession作成に成功した一方、instrumented `file://` targetは次のWebKitエラーページへ置換された。

```text
Ignoring request to load this main resource because it is outside the sandbox
```

診断時はlocationが`safari-resource:`、instrumented harness markerなし、scriptなし、simulationなし、result nodeなしだった。したがって原因はCSP、load event、product runtimeではなく、document load前のSafari WebDriver/WebKit sandbox境界である。

amendment commit `04411a2` は次をclosed contractとして固定する。

- matrix: Safari `smokeTransport=loopback-http`、`smokeProfiles=[desktop,mobile]`
- required runs: `core-02-http-desktop` / `core-02-http-mobile`
- navigation前にpre-product harnessを埋め込み、実inner viewportを確認
- requested `crossover`、100 resets、violations/runtime errors 0、DOM/listener/timer baseline復帰
- Safari file authority、query、fragment、userinfo、non-loopback hostをfail-closed
- Chromium/Firefoxの`core-02-file` + `core-02-http` 4件と静的no-JS/file checksは変更しない

390px runで観測したdevice pixel ratioは1であり、mobile device emulationではない。ここでの`mobile` profileはmatrix名を維持したnarrow desktop-browser viewportを表す。

## Hosted gate remediation

PRの最初のhosted runで、Gitleaksが過去2 commitのvisual checksum fixtureをsecretとして検出し、Linux full-validationがhost依存のarchive fixture 7件で失敗し、browser-contractがChromium sandboxとFirefox内部binaryのpermissionで停止した。implementation parent `4a8ac59` は、次のclosed remediationをlocal gates greenの1 commitとして持つ。

- Gitleaksは検出済み2 fingerprintだけをignoreし、広域allowlistとinline suppressionを禁止する。現行checksumは値を変えずsecret-shapedな同一行を避ける。
- archive構造testは従来のDarwin挙動へ明示固定し、Linux operational installはbrowser名欠落を拒否し、positive preflight dispatchも検証する。
- Chromiumの`--no-sandbox`は固定digest・UID 1001のValidate/Pages OCI jobだけが明示opt-inし、通常Linuxはbrowser sandboxを維持し、Linux以外はcore APIを含め拒否する。
- Firefox tarは通常`rwx`だけを復元し、setuid、setgid、sticky、ownership、link、special entryを持ち込まない。

CIと同じ固定OCI digest、`linux/amd64`、UID 1001でbuild、Chromium/Firefox provisioning、実Chromium smokeを実行し、exit 0、`passed=true`、requested state reached、simulation count 1を確認した。さらにdepth-1 cloneでfocused 101/101、最終commitの独立review 2件で`0/0/0`を確認した。hosted CIそのものの再成功はpush後に別途確認する。

## Clean gate

開始時のtracked差分はなく、readiness draftだけをuntrackedで保持した。対象はreviewed implementation parent SHAである。

| Gate | 結果 |
| --- | --- |
| `python3.13 -m compileall -q curriculum_builder tools tests` | PASS |
| `python3.13 -m unittest discover -s tests` | PASS — 931 tests、74.246s |
| `python3.13 tools/generate_curriculum_map.py --check` | PASS — generated block current |
| Fresh build 1 + current-release site check | PASS |
| Fresh build 2 + current-release site check | PASS |
| 42-file相対path + SHA-256 diff | PASS — diff 0 |
| Pinned browser provisioning | PASS — Chromium、Firefox、Safari |
| Full real-browser closed plan | PASS — 166/166 |
| Release manifest create / expected-commit verify | PASS |
| Manifest-required site check | PASS |
| `git diff --check` | PASS |

2つのfresh build SHA一覧は完全一致した。

```text
3f35cf9ed4af0d4196ff8f556b414071b357043e17f8a143c48c1d0ee379b4d3
```

release manifestは42 filesとreviewed implementation parent SHAを記録した。

```text
manifest SHA-256: fe0524372c5b9aa906337ee259c8a75db9dafbf5c2ec83c7373544ab65624036
commit: 4a8ac5982b33729a564777c269278ec837f6e712
```

## Full browser evidence

```text
outputs/task14-final-browser-evidence.2esaXl/report.json
SHA-256: 41de052f9cd4c6e6a98faca4f74a764883761db452430d104490acb2d6de2104
```

| 項目 | 結果 |
| --- | --- |
| top-level status | `passed` |
| terminal runs | 166 |
| passed / failed / blocked / not-run | `166 / 0 / 0 / 0` |
| inventory | dynamic lessons 12、diagram types 10、regression states 36、profiles 4 |
| performance | 6/6 passed、各100 reset cycles |
| Chromium / Firefox transport | `file://` + Pages-style HTTPを維持 |
| Safari transport | exact loopback HTTPのみ |

provenance:

```text
matrix:  029cff63b74a18a5f914201d4548d102226f79da9dfbf57ac624d93ed9eeaa1a
fixture: 3636bd328a914309d0f2f5fb1037f5285d9db40686f97c688adee9e972972686
harness: ece8196bb17559f61e85ad0808ef5564ed473b4e382aac2a685a32b56274896d
platform: macos / arm64
Chromium: 151.0.7922.71 verified
Firefox: 153.0.1 verified
Safari: 26.5 / 21624.2.5.11.4 verified
```

performanceはmaximum desktop/mobileで全sampleのmutation count 6144、memory/distributed desktop/mobileで32を記録し、6件すべてPASSした。

## Safari evidence

| Run | observed viewport | requested state | reset | violations / runtime errors | baseline復帰 |
| --- | --- | --- | --- | --- | --- |
| `core-02-http-desktop` | `1440×900`、DPR 1 | `crossover` reached | 100 | `0 / 0` | DOM 446、listeners 4、timers 0 |
| `core-02-http-mobile` | `390×844`、DPR 1 | `crossover` reached | 100 | `0 / 0` | DOM 446、listeners 4、timers 0 |

Safariではexplicit GCが利用できずheap evidenceは`-1`であるため、heap保持量の成功は主張しない。DOM/listener/timer復帰とharness violations 0をSafari契約とし、explicit GCを含む性能・leak gateはChromiumの6 performance runsで検証した。

## 実行注記と残余リスク

1. Linux固定OCIではprovisioningと実Chromium smokeまでを再現し、full 166件はlocal macOS hostで実行した。hosted CI成功はpush後に同一HEADで確認する。
2. local browser report schemaはcommitやsite tree hashを内包せず、reportを置く`outputs/`もversion control対象外である。したがってこのreport hash、Docker smoke、shallow-clone、AI reviewはlocal診断証拠であり、単独の第三者監査可能なrelease証明とは扱わない。最終判断はexact HEADに結び付くhosted GitHub checksと、commit・全公開byteを結ぶdeployed release manifestで行う。
3. amendment前のblocked reportと、commit前に誤って開始して即時中断したreportは採用しない。中断reportは`browser-contract-aborted`、166 not-runとしてfail-closedしている。
4. full evidenceはlocal macOS hostの証拠であり、hosted CI成功、push、公開Pages bytes、release完了を証明しない。
5. Safari WebDriverのfile成功を将来推論しない。capabilityが変わる場合はmatrix/spec変更としてREDテストとreviewを再度要求する。

## Maintainer decision

local release gateはREADYである。maintainerはこのreadiness commitをreviewし、hosted CIを同一HEADで成功させ、公開artifactとmanifestのbytesを検証した後にpush/release可否を決定する。未解決thread、branch protection、実際のmerge/publish状態は別途live確認する。
