from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import string
from tempfile import TemporaryDirectory
import unicodedata
import unittest

from curriculum_builder.build import build_site
from curriculum_builder.capstones import parse_capstone_documents
from curriculum_builder.competencies import parse_competencies_bytes
from curriculum_builder.errors import CurriculumValidationError
from curriculum_builder.lessons import load_lesson_bytes
from curriculum_builder.visualizations import (
    parse_visualization_catalog_bytes,
    render_visualization,
    validate_visualization_assignments,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTENT_STANDARD = REPOSITORY_ROOT / "docs/content-standard.md"
CURRICULUM_MAP = REPOSITORY_ROOT / "docs/curriculum-map.md"
MIGRATION_ORACLE = (
    REPOSITORY_ROOT / "tests/fixtures/visualization-migration-v1.json"
)
BEGIN_GENERATED_MAP = "<!-- BEGIN GENERATED CURRICULUM MAP -->"
END_GENERATED_MAP = "<!-- END GENERATED CURRICULUM MAP -->"
LESSON_IDS = (
    "core-01-systems-tradeoffs",
    "core-02-algorithms-measurement",
    "core-03-architecture-memory-caches",
    "core-04-os-processes-concurrency",
    "core-05-networks-latency-failure",
    "core-06-requirements-domain-modeling",
    "core-07-api-contract-design",
    "core-08-modularity-evolutionary-architecture",
    "core-09-test-strategy-tdd",
    "core-10-threat-modeling-secure-design",
    "core-11-data-modeling-storage",
    "core-12-transactions-isolation-consistency",
    "core-13-distributed-coordination-failure",
    "core-14-performance-capacity",
    "core-15-reliability-observability-slo",
    "core-16-hci-usability-accessibility",
    "core-17-graphics-visual-information",
    "core-18-product-discovery-experiments",
    "core-19-technical-communication-design-docs",
    "core-20-ethics-privacy-societal-impact",
    "core-21-maintenance-legacy-comprehension",
    "core-22-evolution-safe-migrations",
    "core-23-incident-response-learning",
    "core-24-delivery-ci-release-safety",
    "core-25-engineering-economics-capacity",
    "core-26-code-review-collaborative-quality",
    "core-27-team-interfaces-sociotechnical-architecture",
    "core-28-oss-governance-stewardship",
    "core-29-cross-cultural-async-collaboration",
    "core-30-evidence-based-technical-leadership",
)
TASK5_VISUAL_TYPES = {
    "core-01-systems-tradeoffs": "causal",
    "core-06-requirements-domain-modeling": "network",
    "core-08-modularity-evolutionary-architecture": "network",
    "core-10-threat-modeling-secure-design": "network",
    "core-14-performance-capacity": "causal",
    "core-18-product-discovery-experiments": "causal",
    "core-20-ethics-privacy-societal-impact": "causal",
    "core-21-maintenance-legacy-comprehension": "network",
    "core-27-team-interfaces-sociotechnical-architecture": "network",
    "core-30-evidence-based-technical-leadership": "causal",
}
TASK6_VISUAL_TYPES = {
    "core-04-os-processes-concurrency": "timeline",
    "core-05-networks-latency-failure": "timeline",
    "core-07-api-contract-design": "state-machine",
    "core-09-test-strategy-tdd": "state-loop",
    "core-12-transactions-isolation-consistency": "timeline",
    "core-13-distributed-coordination-failure": "timeline",
    "core-15-reliability-observability-slo": "state-loop",
    "core-22-evolution-safe-migrations": "state-machine",
    "core-23-incident-response-learning": "timeline",
    "core-24-delivery-ci-release-safety": "state-machine",
    "core-26-code-review-collaborative-quality": "state-loop",
    "core-29-cross-cultural-async-collaboration": "timeline",
}
TASK7_VISUAL_TYPES = {
    "core-02-algorithms-measurement": "comparison",
    "core-03-architecture-memory-caches": "memory",
    "core-11-data-modeling-storage": "matrix",
    "core-16-hci-usability-accessibility": "flow",
    "core-17-graphics-visual-information": "flow",
    "core-19-technical-communication-design-docs": "hierarchy",
    "core-25-engineering-economics-capacity": "matrix",
    "core-28-oss-governance-stewardship": "flow",
}
TASK9_SIMULATION_CONTRACTS = {
    "core-02-algorithms-measurement": {
        "visual": "complexity-growth-static",
        "kind": "complexity-growth",
        "mode": "scenario",
        "parameters": ("input-size", "algorithm-family"),
        "states": (
            "small-input", "small-binary", "small-hash",
            "crossover-linear", "crossover", "crossover-hash",
            "large-linear", "large-binary", "large-input",
        ),
        "transitions": (),
        "outcomes": (
            "small-linear-result", "small-binary-result", "small-hash-result",
            "crossover-linear-result", "crossover-binary-result",
            "crossover-hash-result", "large-linear-result",
            "large-binary-result", "large-hash-result",
        ),
        "interval": None,
    },
    "core-03-architecture-memory-caches": {
        "visual": "memory-access-static",
        "kind": "memory-access",
        "mode": "hybrid",
        "parameters": ("working-set", "access-order"),
        "states": (
            "tlb-lookup", "l1-hit", "small-random-return",
            "large-sequential-return", "memory-return",
        ),
        "transitions": (
            "apply-small-sequential", "next-small-sequential",
            "timer-small-sequential", "previous-l1-hit", "reset-l1-hit",
            "apply-small-random", "next-small-random", "timer-small-random",
            "previous-small-random", "reset-small-random-return",
            "apply-large-sequential", "next-large-sequential",
            "timer-large-sequential", "previous-large-sequential",
            "reset-large-sequential-return", "apply-large-random",
            "next-large-random", "timer-large-random", "previous-memory-return",
            "reset-memory-return",
        ),
        "outcomes": (
            "small-sequential-outcome", "small-random-outcome",
            "large-sequential-outcome", "large-random-outcome",
        ),
        "interval": 1000,
    },
    "core-04-os-processes-concurrency": {
        "visual": "scheduler-interleaving-static",
        "kind": "scheduler-interleaving",
        "mode": "playback",
        "parameters": (),
        "states": (
            "read-old-value", "b-read-old-value", "a-compute", "b-compute",
            "a-write", "lost-update", "lock-acquired", "a-locked-write",
            "unlock", "b-lock-acquired", "b-locked-write", "locked-complete",
        ),
        "transitions": (
            "read-next", "read-timer", "b-read-next", "b-read-timer",
            "b-read-previous", "b-read-reset", "a-compute-next",
            "a-compute-timer", "a-compute-previous", "a-compute-reset",
            "b-compute-next", "b-compute-timer", "b-compute-previous",
            "b-compute-reset", "a-write-next", "a-write-timer",
            "a-write-previous", "a-write-reset", "lost-next", "lost-timer",
            "lost-previous", "lost-reset", "lock-next", "lock-timer",
            "lock-previous", "lock-reset", "a-locked-next", "a-locked-timer",
            "a-locked-previous", "a-locked-reset", "unlock-next", "unlock-timer",
            "unlock-previous", "unlock-reset", "b-lock-next", "b-lock-timer",
            "b-lock-previous", "b-lock-reset", "b-locked-next", "b-locked-timer",
            "b-locked-previous", "b-locked-reset", "complete-previous",
            "complete-reset",
        ),
        "outcomes": ("lost-update-outcome", "locked-outcome"),
        "interval": 1200,
    },
    "core-05-networks-latency-failure": {
        "visual": "request-path-static",
        "kind": "request-path",
        "mode": "hybrid",
        "parameters": ("fault", "budget"),
        "states": (
            "dns-lookup", "h-tcp", "tls-ready", "h-req", "h-ok",
            "h-retry-blocked", "d-fail", "d-retry", "d-retry-blocked",
            "t-fail", "t-retry", "t-retry-blocked", "l-tcp", "l-fail",
            "l-retry-blocked", "l-retry-blocked-tight", "q-tcp", "q-tls",
            "q-fail", "q-retry", "q-retry-blocked", "s-tcp", "s-tls",
            "s-req", "deadline-exceeded", "s-inquiry", "s-retry",
            "s-retry-blocked",
        ),
        "transitions": (),
        "outcomes": (
            "h-ok-outcome", "h-retry-blocked-outcome", "d-retry-outcome",
            "d-retry-blocked-outcome", "t-retry-outcome",
            "t-retry-blocked-outcome", "l-retry-blocked-outcome",
            "l-retry-blocked-tight-outcome", "q-retry-outcome",
            "q-retry-blocked-outcome", "s-retry-outcome",
            "s-retry-blocked-outcome",
        ),
        "interval": 1000,
    },
    "core-07-api-contract-design": {
        "visual": "retry-contract-static",
        "kind": "retry-contract",
        "mode": "playback",
        "parameters": (),
        "states": (
            "request-accepted", "side-effect-committed", "response-lost",
            "retry-replayed", "observed-success",
        ),
        "transitions": (
            "accepted-to-committed-next", "accepted-to-committed-timer",
            "committed-to-lost-next", "committed-to-lost-timer",
            "lost-to-replayed-next", "lost-to-replayed-timer",
            "replayed-to-observed-next", "replayed-to-observed-timer",
            "committed-to-accepted-previous", "lost-to-committed-previous",
            "replayed-to-lost-previous", "observed-to-replayed-previous",
            "reset-side-effect", "reset-response-lost", "reset-retry",
            "reset-observed",
        ),
        "outcomes": ("side-effect-once", "response-observed"),
        "interval": 1200,
    },
}
_CORE05_FAILURE_BRANCHES = (
    "healthy", "dns", "tcp", "tls", "request", "response",
)
_CORE05_NON_INITIAL_STATES = TASK9_SIMULATION_CONTRACTS[
    "core-05-networks-latency-failure"
]["states"][1:]
_CORE05_TERMINAL_STATES = frozenset(
    outcome_id.removesuffix("-outcome")
    for outcome_id in TASK9_SIMULATION_CONTRACTS[
        "core-05-networks-latency-failure"
    ]["outcomes"]
)
_CORE05_TERMINAL_TOKENS = {
    "h-ok": "healthy-end", "h-retry-blocked": "healthy-retry-blocked",
    "d-retry": "dns-retry", "d-retry-blocked": "dns-retry-blocked",
    "t-retry": "tcp-retry", "t-retry-blocked": "tcp-retry-blocked",
    "l-retry-blocked": "tls-retry-blocked",
    "l-retry-blocked-tight": "tls-retry-blocked-tight",
    "q-retry": "request-retry", "q-retry-blocked": "request-retry-blocked",
    "s-retry": "response-retry", "s-retry-blocked": "response-retry-blocked",
}
_CORE05_TRANSITION_TOKENS = {
    state_id: _CORE05_TERMINAL_TOKENS.get(state_id, f"s{index:02d}")
    for index, state_id in enumerate(_CORE05_NON_INITIAL_STATES, start=1)
}
TASK9_SIMULATION_CONTRACTS["core-05-networks-latency-failure"]["transitions"] = (
    *(f"apply-{branch}" for branch in _CORE05_FAILURE_BRANCHES),
    *(
        transition_id
        for state_id in _CORE05_NON_INITIAL_STATES
        for transition_id in (
            f"n-{_CORE05_TRANSITION_TOKENS[state_id]}",
            f"t-{_CORE05_TRANSITION_TOKENS[state_id]}",
            f"p-{_CORE05_TRANSITION_TOKENS[state_id]}",
            f"r-{_CORE05_TRANSITION_TOKENS[state_id]}",
        )
    ),
)
TASK10_SIMULATION_CONTRACTS = {
    "core-12-transactions-isolation-consistency": {
        "visual": "isolation-schedule-static",
        "kind": "isolation-schedule",
        "mode": "hybrid",
        "parameters": ("isolation",),
        "states": (
            "concurrent-read", "snapshot-local-decision", "write-skew",
            "serializable-validation", "transaction-aborted",
            "transaction-retried",
        ),
        "outcomes": ("write-skew-observed", "retry-preserves-invariant"),
        "interval": 1100,
    },
    "core-13-distributed-coordination-failure": {
        "visual": "distributed-failure-static",
        "kind": "distributed-failure",
        "mode": "hybrid",
        "parameters": ("event-case",),
        "states": (
            "event-log-start", "partition-detected", "partition-buffered",
            "duplicate-received", "reorder-gap-filled", "recovery-converged",
        ),
        "outcomes": (
            "duplicate-effect-once", "reorder-detected",
            "partition-buffers-three", "recovery-before-deadline",
        ),
        "interval": 1000,
    },
    "core-14-performance-capacity": {
        "visual": "queue-capacity-static",
        "kind": "queue-capacity",
        "mode": "scenario",
        "parameters": ("load-band", "workers"),
        "states": (
            "stable-load", "near-capacity", "saturation", "capacity-recovered",
            "write-stable-load", "write-near-capacity", "write-saturation",
            "write-capacity-recovered",
        ),
        "outcomes": (
            "baseline-low-result", "baseline-near-result",
            "baseline-overload-result", "baseline-recovery-result",
            "write-low-result", "write-near-result",
            "write-overload-result", "write-recovery-result",
        ),
        "interval": None,
    },
    "core-15-reliability-observability-slo": {
        "visual": "slo-burn-static",
        "kind": "slo-burn",
        "mode": "scenario",
        "parameters": ("error-window",),
        "states": ("budget-healthy", "fast-burn", "page-triggered"),
        "outcomes": (
            "healthy-no-action", "short-window-only", "multi-window-page",
        ),
        "interval": None,
    },
}
TASK7_COMMON_CONTRACTS = {
    "core-02-algorithms-measurement": ("complexity-growth-static", "comparison", "mentalModel", None, "アルゴリズム再選択の検証経路", "同じquery列への構築済みlookupで、入力特性・size・setup・space・query回数が選択をどう変えるか。", "best・average・worst caseを区別し、予測と反復実測の差から再選択条件を説明できる。", ("obj-predict", "obj-measure", "obj-reselect"), ("benchmark-report", "assessment"), ("src-01", "src-02", "src-03", "src-04"), ("操作モデル: 比較、hash計算、割り当てなど、支配的な操作を決める。", "成長率予測: 支配操作がΘ(n)ならnを2倍にしたとき約2倍、Θ(n²)なら約4倍と予測する。", "入力モデル: サイズだけでなく、順序、重複率、問い合わせ位置を固定する。", "測定設計: 準備と対象区間を分け、ウォームアップ後に複数回測る。", "統計要約: 全値、中央値、範囲を残し、除外規則を先に決める。", "差の診断: 定数項、キャッシュ、GC、処理系、外れ値を追加測定で反証する。", "再選択条件: 本番のn、分布、呼出回数の変化を監視する。")),
    "core-03-architecture-memory-caches": ("memory-access-static", "memory", "mentalModel", None, "一つのロードを診断する論理段階", "一つのloadでaddress translationとdata transferの待ちをどう切り分けるか。", "TLB・page tableの変換経路とcache・主記憶の転送経路を区別し、機種依存の階層を普遍的latencyとして扱わない。", ("obj-path", "obj-locality", "obj-transfer"), ("locality-report", "assessment"), ("src-01", "src-02", "src-03"), ("命令: 仮想アドレスAの値を要求する。", "TLB: Aのページ変換を検索する。missならページテーブルwalkが必要になる。", "L1 cache: Aを含むcache lineを検索する。hitなら近い階層で返る。", "L2と最終レベルcache: L1 miss後の候補を調べる。L2やLLCがcore-privateか複数coreでsharedかというprivate/shared範囲は機種依存である。", "memory controller: 全cacheでmissなら主記憶からline単位で転送する。", "再利用: 同じline内の次要素を使えば空間的局所性、短時間に同じ値を使えば時間的局所性を得る。", "このDAGはhit/missの診断依存を示し、VIPTではTLB変換とL1 index lookupが並行し得るため普遍的な逐次latencyではない。")),
    "core-11-data-modeling-storage": ("storage-decision-matrix", "matrix", "mentalModel", None, "workload証拠からstorage ADRを再計算するmechanism", "query frequencyだけを変え、固定したquery-fit ratingから何を再計算するか。", "changed inputはfrequencyだけで、query-fit ratingは固定され、導出されるaccess-fit rating、weighted score、winnerが順に変わり得ることを説明できる。", ("obj-workload", "obj-compare", "obj-recompute"), ("storage-adr", "assessment"), ("src-01", "src-02", "src-03", "src-04"), ("domain: 注文番号の一意性、合計額と明細合計の一致、注文状態遷移を不変条件にする。", "workload: 顧客履歴、注文detail、商品・期間検索、状態更新を一意なquery IDと時間当たり頻度で表す。", "growth: 現在件数と月間増加から12か月後を計算し、synthetic projectionである限界を残す。", "comparison: relational、document、key-valueをaccess fit、constraint、capacity、operations、recoveryの同じweightで採点する。", "ADR: winnerだけでなく、負の帰結、移行境界、confirmationを記録する。", "mutation: 商品・期間検索が主要queryになったらfrequencyだけを変える。query-fit ratingは固定し、access-fit rating、weighted score、winnerを再計算する。", "worked exampleでは全optionへ同じweight set 0.45/0.20/0.15/0.10/0.10を適用する。query-fit ratingは固定し、frequency変更からaccess-fit ratingを導出する。", "baseline total 4.288957; winner relational; changed total 3.668868; winner key-value")),
    "core-16-hci-usability-accessibility": ("accessible-ui-state-static", "flow", "mentalModel", None, "生成サイトの監査を適合主張と利用者タスクへ結ぶ証拠flow", "限定した監査scopeから、適合結果と利用者taskの結果を混同せずにどう報告するか。", "scope、規範target、観測、人手review、限定claimの順序と、WCAG 3.0 Working DraftをWCAG 2.2適合根拠にしない境界を説明できる。", ("obj-audit", "obj-usability", "obj-scope"), ("audit-record", "assessment"), ("src-01", "src-02", "src-03", "src-04"), ("Scope:", "Target:", "Observe:", "Review:", "Claim:")),
    "core-17-graphics-visual-information": ("semantic-rendering-flow", "flow", "mentalModel", None, "一つのdata modelから視覚と同等textへ分岐するrendering pipeline", "一つのdata modelから視覚表現と同等textを作り、どの不変条件を照合するか。", "Data、Transform、Visual、Equivalent、Verifyの順序を説明し、別目的の0–100% worked-example chartを二重計上しない。", ("obj-pipeline", "obj-equivalence", "obj-encoding"), ("semantic-visual", "assessment"), ("src-01", "src-02", "src-03", "src-04", "src-05"), ("Data:", "Transform:", "Visual:", "Equivalent:", "Verify:")),
    "core-19-technical-communication-design-docs": ("decision-evidence-hierarchy", "hierarchy", "mentalModel", None, "一つの決定証拠から読者別viewを導く構造", "同じdecision evidenceを読者別viewへどう入れ子にし、driftを防ぐか。", "共通decision recordの下にevidenceと読者別viewを置き、executiveとimplementationの詳細度だけを変えて同じdecisionを参照すると説明できる。", ("obj-audience", "obj-decision", "obj-transfer"), ("design-document", "assessment"), ("src-01", "src-02", "src-03", "src-04", "src-05"), ("Audience:", "Evidence:", "Decision:", "Executive view:", "Implementation view:", "Drift check: 要約、付録、ADRが同じdecisionを指すか検査する。")),
    "core-25-engineering-economics-capacity": ("investment-capacity-matrix", "matrix", "mentalModel", None, "入力からcapacity制約とunit economicsを経て投資判断へ至るchain", "投資候補ごとにcost構成とcapacity制約を同じ軸で比較し、どの順で判断するか。", "制約違反候補を先に除き、direct・opportunity・operations・reliabilityを合算したtotal costとunit costを比較し、一変数の感度境界を説明できる。", ("obj-economics", "obj-capacity", "obj-sensitivity"), ("investment-comparison", "assessment"), ("src-01", "src-02", "src-03", "src-04"), ("Direct: fixtureで与えた取得・実行費を置く。", "Opportunity: engineering hoursと一時間の代替価値を掛ける。", "Operations: operations hoursと運用単価を掛ける。", "Reliability: 障害確率、時間、時間当たり影響を掛ける。", "Capacity: 需要と供給からheadroomとbreachを導く。", "Decision: 制約違反を先に、unit costを次に比較する。")),
    "core-28-oss-governance-stewardship": ("contribution-governance-flow", "flow", "mentalModel", None, "第三者contributionをmaintainerのreview・merge・release evidenceへ安全に接続するgovernance chain", "第三者のopen contributionとmaintainerのwrite権限を分離したままrelease evidenceへどう接続するか。", "discoverからrelease evidenceまでの順序、第三者とmaintainerの権限境界、command successと公開artifactのsystem outcomeの差を説明できる。", ("obj-readiness", "obj-journey", "obj-transfer"), ("stewardship-repository", "repository-audit", "transfer"), ("src-01", "src-02", "src-03", "src-04", "src-05"), ("discover:", "prepare:", "submit:", "review:", "maintainer-merge:", "release-evidence:")),
}
TASK7_STRUCTURE_IDS = {
    "core-02-algorithms-measurement": {
        "alternatives": ("linear-scan", "binary-search", "hash-lookup"),
        "criteria": ("best-case", "average-case", "worst-case", "setup-cost", "space-cost", "query-crossover"),
        "cells": ("linear-best", "linear-average", "linear-worst", "linear-setup", "linear-space", "linear-crossover", "binary-best", "binary-average", "binary-worst", "binary-setup", "binary-space", "binary-crossover", "hash-best", "hash-average", "hash-worst", "hash-setup", "hash-space", "hash-crossover"),
    },
    "core-03-architecture-memory-caches": {
        "layers": ("instruction", "tlb", "page-table", "address-ready", "l1-cache", "lower-cache", "memory-controller", "return", "reuse"),
        "transfers": ("instruction-to-tlb", "instruction-to-l1", "tlb-hit", "tlb-miss", "walk-complete", "address-to-l1", "l1-hit-return", "l1-miss-lower", "lower-hit-return", "lower-miss-memory", "memory-return", "return-to-reuse"),
    },
    "core-11-data-modeling-storage": {
        "rows": ("relational", "document", "key-value"),
        "columns": ("access-fit", "constraint", "capacity", "operations", "recovery"),
        "cells": ("relational-access", "relational-constraint", "relational-capacity", "relational-operations", "relational-recovery", "document-access", "document-constraint", "document-capacity", "document-operations", "document-recovery", "key-value-access", "key-value-constraint", "key-value-capacity", "key-value-operations", "key-value-recovery"),
    },
    "core-16-hci-usability-accessibility": {
        "steps": ("scope", "target", "observe", "review", "claim"),
        "transitions": ("scope-to-target", "target-to-observe", "observe-to-review", "review-to-claim"),
    },
    "core-17-graphics-visual-information": {
        "steps": ("data", "transform", "visual", "equivalent", "verify"),
        "transitions": ("data-to-transform", "transform-to-visual", "transform-to-equivalent", "visual-to-verify", "equivalent-to-verify"),
    },
    "core-19-technical-communication-design-docs": {
        "nodes": ("decision-record", "audience", "evidence", "executive-view", "implementation-view", "alternatives", "validation"),
    },
    "core-25-engineering-economics-capacity": {
        "rows": ("scale-up", "automation"),
        "columns": ("direct", "opportunity", "operations", "reliability", "capacity-unit", "sensitivity"),
        "cells": ("scale-direct", "scale-opportunity", "scale-operations", "scale-reliability", "scale-total", "scale-sensitivity", "automation-direct", "automation-opportunity", "automation-operations", "automation-reliability", "automation-total", "automation-sensitivity"),
    },
    "core-28-oss-governance-stewardship": {
        "steps": ("discover", "prepare", "submit", "review", "maintainer-merge", "release-evidence"),
        "transitions": ("discover-to-prepare", "prepare-to-submit", "submit-to-review", "review-to-merge", "merge-to-release"),
    },
}

TASK7_PAYLOAD_CONTRACTS = {'core-02-algorithms-measurement': {'alternatives': [{'id': 'linear-scan',
                                                      'label': '線形走査',
                                                      'detail': '順序なし配列を先頭から探索する候補。'},
                                                     {'id': 'binary-search',
                                                      'label': '二分探索',
                                                      'detail': '整列済み配列を半分ずつ絞る候補。'},
                                                     {'id': 'hash-lookup',
                                                      'label': 'hash lookup',
                                                      'detail': 'hash tableを構築してkeyを探索する候補。'}],
                                    'criteria': [{'id': 'best-case',
                                                  'label': 'best case',
                                                  'detail': '最も有利な入力配置での支配操作。'},
                                                 {'id': 'average-case',
                                                  'label': 'average case',
                                                  'detail': '明示した入力分布の期待操作回数。'},
                                                 {'id': 'worst-case',
                                                  'label': 'worst case',
                                                  'detail': '最も不利な入力と衝突条件の上界。'},
                                                 {'id': 'setup-cost',
                                                  'label': 'setup / build cost',
                                                  'detail': 'worked exampleで分離測定するset構築または整列の費用。'},
                                                 {'id': 'space-cost',
                                                  'label': 'space cost',
                                                  'detail': '追加indexやcopyに必要なmemory。'},
                                                 {'id': 'query-crossover',
                                                  'label': 'query count / crossover',
                                                  'detail': 'setup費用をlookup短縮で償却できる環境固有のquery回数。'}],
                                    'cells': [{'id': 'linear-best',
                                               'alternativeId': 'linear-scan',
                                               'criterionId': 'best-case',
                                               'value': 'Θ(1): 先頭で一致'},
                                              {'id': 'linear-average',
                                               'alternativeId': 'linear-scan',
                                               'criterionId': 'average-case',
                                               'value': 'Θ(n): 平均で約n/2比較'},
                                              {'id': 'linear-worst',
                                               'alternativeId': 'linear-scan',
                                               'criterionId': 'worst-case',
                                               'value': 'Θ(n): 末尾または不在'},
                                              {'id': 'linear-setup',
                                               'alternativeId': 'linear-scan',
                                               'criterionId': 'setup-cost',
                                               'value': '追加構築なしΘ(1)'},
                                              {'id': 'linear-space',
                                               'alternativeId': 'linear-scan',
                                               'criterionId': 'space-cost',
                                               'value': '追加space Θ(1)'},
                                              {'id': 'linear-crossover',
                                               'alternativeId': 'linear-scan',
                                               'criterionId': 'query-crossover',
                                               'value': '少数queryではbuild費用がないため候補'},
                                              {'id': 'binary-best',
                                               'alternativeId': 'binary-search',
                                               'criterionId': 'best-case',
                                               'value': 'Θ(1): 中央で一致'},
                                              {'id': 'binary-average',
                                               'alternativeId': 'binary-search',
                                               'criterionId': 'average-case',
                                               'value': 'Θ(log n): 整列済み入力'},
                                              {'id': 'binary-worst',
                                               'alternativeId': 'binary-search',
                                               'criterionId': 'worst-case',
                                               'value': 'Θ(log n): 不在でも半減'},
                                              {'id': 'binary-setup',
                                               'alternativeId': 'binary-search',
                                               'criterionId': 'setup-cost',
                                               'value': '未整列ならsort Θ(n log n)'},
                                              {'id': 'binary-space',
                                               'alternativeId': 'binary-search',
                                               'criterionId': 'space-cost',
                                               'value': 'sort実装とcopy方針に依存'},
                                              {'id': 'binary-crossover',
                                               'alternativeId': 'binary-search',
                                               'criterionId': 'query-crossover',
                                               'value': 'sort費用を複数queryで償却'},
                                              {'id': 'hash-best',
                                               'alternativeId': 'hash-lookup',
                                               'criterionId': 'best-case',
                                               'value': 'Θ(1): 衝突なし'},
                                              {'id': 'hash-average',
                                               'alternativeId': 'hash-lookup',
                                               'criterionId': 'average-case',
                                               'value': '期待Θ(1): hash分布を仮定'},
                                              {'id': 'hash-worst',
                                               'alternativeId': 'hash-lookup',
                                               'criterionId': 'worst-case',
                                               'value': 'Θ(n): 全keyが衝突'},
                                              {'id': 'hash-setup',
                                               'alternativeId': 'hash-lookup',
                                               'criterionId': 'setup-cost',
                                               'value': 'set構築Θ(n)をlookupと分離測定'},
                                              {'id': 'hash-space',
                                               'alternativeId': 'hash-lookup',
                                               'criterionId': 'space-cost',
                                               'value': 'set tableの追加space Θ(n)'},
                                              {'id': 'hash-crossover',
                                               'alternativeId': 'hash-lookup',
                                               'criterionId': 'query-crossover',
                                               'value': 'set_build中央値 ÷ 1 query当たり短縮; query回数8と比較'}]},
 'core-03-architecture-memory-caches': {'layers': [{'id': 'instruction',
                                                    'label': '命令',
                                                    'detail': '仮想アドレスAの値を要求する。',
                                                    'group': 'request'},
                                                   {'id': 'tlb',
                                                    'label': 'TLB',
                                                    'detail': 'Aのページ変換を検索し、missならpage table walkを開始する。',
                                                    'group': 'translation'},
                                                   {'id': 'page-table',
                                                    'label': 'page table walk',
                                                    'detail': 'TLB miss branchだけで仮想pageから物理pageへの変換情報を取得する。',
                                                    'group': 'translation'},
                                                   {'id': 'address-ready',
                                                    'label': '物理address ready',
                                                    'detail': 'TLB hitまたはpage table walk完了が合流し、物理tag照合へ必要なaddressを渡す。',
                                                    'group': 'translation'},
                                                   {'id': 'l1-cache',
                                                    'label': 'L1 cache',
                                                    'detail': 'VIPTでは仮想addressのindex '
                                                              'lookupがTLBと並行し得るが、物理tag照合後にhit/missを判断する。',
                                                    'group': 'transfer'},
                                                   {'id': 'lower-cache',
                                                    'label': 'L2と最終レベルcache',
                                                    'detail': 'private/shared範囲と段数は機種依存で、固定latencyではない。',
                                                    'group': 'transfer'},
                                                   {'id': 'memory-controller',
                                                    'label': 'memory controller',
                                                    'detail': '全cache miss時に主記憶からline単位で転送する。',
                                                    'group': 'transfer'},
                                                   {'id': 'return',
                                                    'label': '値を命令へreturn',
                                                    'detail': 'L1 hit、lower cache hit、またはmemory転送完了が共通returnへ合流する。',
                                                    'group': 'return'},
                                                   {'id': 'reuse',
                                                    'label': '再利用',
                                                    'detail': 'return後、空間的局所性または時間的局所性で後続accessのhitを増やす。',
                                                    'group': 'reuse'}],
                                        'transfers': [{'id': 'instruction-to-tlb',
                                                       'from': 'instruction',
                                                       'to': 'tlb',
                                                       'label': '仮想アドレスAの変換を検索',
                                                       'kind': 'translation-request'},
                                                      {'id': 'instruction-to-l1',
                                                       'from': 'instruction',
                                                       'to': 'l1-cache',
                                                       'label': 'VIPT index lookupは変換と並行し得る',
                                                       'kind': 'vipt-parallel-index'},
                                                      {'id': 'tlb-hit',
                                                       'from': 'tlb',
                                                       'to': 'address-ready',
                                                       'label': 'TLB hitなら保持した変換を使う',
                                                       'kind': 'tlb-hit'},
                                                      {'id': 'tlb-miss',
                                                       'from': 'tlb',
                                                       'to': 'page-table',
                                                       'label': 'TLB miss時だけpage table walk',
                                                       'kind': 'tlb-miss'},
                                                      {'id': 'walk-complete',
                                                       'from': 'page-table',
                                                       'to': 'address-ready',
                                                       'label': 'walk完了で物理addressを得る',
                                                       'kind': 'translation-result'},
                                                      {'id': 'address-to-l1',
                                                       'from': 'address-ready',
                                                       'to': 'l1-cache',
                                                       'label': '物理tag照合でdata hit/missを確定',
                                                       'kind': 'tag-check'},
                                                      {'id': 'l1-hit-return',
                                                       'from': 'l1-cache',
                                                       'to': 'return',
                                                       'label': 'L1 hitなら値を返す',
                                                       'kind': 'l1-hit'},
                                                      {'id': 'l1-miss-lower',
                                                       'from': 'l1-cache',
                                                       'to': 'lower-cache',
                                                       'label': 'L1 miss時だけ下位cacheへ',
                                                       'kind': 'l1-miss'},
                                                      {'id': 'lower-hit-return',
                                                       'from': 'lower-cache',
                                                       'to': 'return',
                                                       'label': 'lower cache hitなら値を返す',
                                                       'kind': 'lower-hit'},
                                                      {'id': 'lower-miss-memory',
                                                       'from': 'lower-cache',
                                                       'to': 'memory-controller',
                                                       'label': '全cache miss時だけ主記憶へ',
                                                       'kind': 'lower-miss'},
                                                      {'id': 'memory-return',
                                                       'from': 'memory-controller',
                                                       'to': 'return',
                                                       'label': 'line転送完了後に値を返す',
                                                       'kind': 'memory-return'},
                                                      {'id': 'return-to-reuse',
                                                       'from': 'return',
                                                       'to': 'reuse',
                                                       'label': '返却後のlineを後続accessで再利用',
                                                       'kind': 'reuse'}]},
 'core-11-data-modeling-storage': {'rows': [{'id': 'relational',
                                             'label': 'relational',
                                             'detail': '関係・constraint・transactionを明示する候補。'},
                                            {'id': 'document',
                                             'label': 'document',
                                             'detail': 'aggregate単位で一緒に読むdataを保持する候補。'},
                                            {'id': 'key-value',
                                             'label': 'key-value',
                                             'detail': 'keyによるbounded lookupを中心にする候補。'}],
                                   'columns': [{'id': 'access-fit',
                                                'label': 'access fit × 0.45',
                                                'detail': 'query frequency×model別ratingの加重平均。baselineと変更後を同じ式で再計算する。'},
                                               {'id': 'constraint',
                                                'label': 'constraint × 0.20',
                                                'detail': '不変条件と更新競合のratingとscore contribution。'},
                                               {'id': 'capacity',
                                                'label': 'capacity × 0.15',
                                                'detail': '1.1M projected recordsへのtested pathのratingとcontribution。'},
                                               {'id': 'operations',
                                                'label': 'operations × 0.10',
                                                'detail': 'migration・observe・operateのratingとcontribution。'},
                                               {'id': 'recovery',
                                                'label': 'recovery × 0.10',
                                                'detail': 'backup・restore・reconstructionのratingとcontribution。'}],
                                   'cells': [{'id': 'relational-access',
                                              'rowId': 'relational',
                                              'columnId': 'access-fit',
                                              'value': 'baseline (480×5 + 360×3 + 48×1 + 90×4) / 978 = 3.975460; '
                                                       'changed (24×5 + 360×3 + 480×1 + 90×4) / 954 = 2.138365; weight '
                                                       '0.45',
                                              'status': 'value'},
                                             {'id': 'relational-constraint',
                                              'rowId': 'relational',
                                              'columnId': 'constraint',
                                              'value': 'rating 5 × 0.20 = 1.00',
                                              'status': 'value'},
                                             {'id': 'relational-capacity',
                                              'rowId': 'relational',
                                              'columnId': 'capacity',
                                              'value': 'rating 4 × 0.15 = 0.60',
                                              'status': 'value'},
                                             {'id': 'relational-operations',
                                              'rowId': 'relational',
                                              'columnId': 'operations',
                                              'value': 'rating 4 × 0.10 = 0.40',
                                              'status': 'value'},
                                             {'id': 'relational-recovery',
                                              'rowId': 'relational',
                                              'columnId': 'recovery',
                                              'value': 'rating 5 × 0.10 = 0.50; baseline total 4.288957; changed total '
                                                       '3.462264',
                                              'status': 'value'},
                                             {'id': 'document-access',
                                              'rowId': 'document',
                                              'columnId': 'access-fit',
                                              'value': 'baseline (480×4 + 360×5 + 48×2 + 90×4) / 978 = 4.269939; '
                                                       'changed (24×4 + 360×5 + 480×2 + 90×4) / 954 = 3.371069; weight '
                                                       '0.45',
                                              'status': 'value'},
                                             {'id': 'document-constraint',
                                              'rowId': 'document',
                                              'columnId': 'constraint',
                                              'value': 'rating 3 × 0.20 = 0.60',
                                              'status': 'value'},
                                             {'id': 'document-capacity',
                                              'rowId': 'document',
                                              'columnId': 'capacity',
                                              'value': 'rating 4 × 0.15 = 0.60',
                                              'status': 'value'},
                                             {'id': 'document-operations',
                                              'rowId': 'document',
                                              'columnId': 'operations',
                                              'value': 'rating 3 × 0.10 = 0.30',
                                              'status': 'value'},
                                             {'id': 'document-recovery',
                                              'rowId': 'document',
                                              'columnId': 'recovery',
                                              'value': 'rating 3 × 0.10 = 0.30; baseline total 3.721472; changed total '
                                                       '3.316981',
                                              'status': 'value'},
                                             {'id': 'key-value-access',
                                              'rowId': 'key-value',
                                              'columnId': 'access-fit',
                                              'value': 'baseline (480×2 + 360×4 + 48×5 + 90×2) / 978 = 2.883436; '
                                                       'changed (24×2 + 360×4 + 480×5 + 90×2) / 954 = 4.264151; weight '
                                                       '0.45',
                                              'status': 'value'},
                                             {'id': 'key-value-constraint',
                                              'rowId': 'key-value',
                                              'columnId': 'constraint',
                                              'value': 'rating 2 × 0.20 = 0.40',
                                              'status': 'value'},
                                             {'id': 'key-value-capacity',
                                              'rowId': 'key-value',
                                              'columnId': 'capacity',
                                              'value': 'rating 5 × 0.15 = 0.75',
                                              'status': 'value'},
                                             {'id': 'key-value-operations',
                                              'rowId': 'key-value',
                                              'columnId': 'operations',
                                              'value': 'rating 2 × 0.10 = 0.20',
                                              'status': 'value'},
                                             {'id': 'key-value-recovery',
                                              'rowId': 'key-value',
                                              'columnId': 'recovery',
                                              'value': 'rating 4 × 0.10 = 0.40; baseline total 3.047546; changed total '
                                                       '3.668868',
                                              'status': 'value'}]},
 'core-16-hci-usability-accessibility': {'steps': [{'id': 'scope',
                                                    'label': 'Scope',
                                                    'detail': 'ページfixture、利用者、入力方式、環境、除外を固定する。'},
                                                   {'id': 'target',
                                                    'label': 'Target',
                                                    'detail': 'WCAG 2.2 Level AAの規範的targetと版を記録する。'},
                                                   {'id': 'observe',
                                                    'label': 'Observe',
                                                    'detail': 'keyboard、200% zoom、reading order、usabilityを期待値と比較する。'},
                                                   {'id': 'review',
                                                    'label': 'Review',
                                                    'detail': '自動化で判定できない意味、順序、タスク成功を人が確認する。'},
                                                   {'id': 'claim',
                                                    'label': 'Claim',
                                                    'detail': '合否、未確認、残余リスクを分け、範囲を限定して報告する。'}],
                                         'transitions': [{'id': 'scope-to-target',
                                                          'from': 'scope',
                                                          'to': 'target',
                                                          'label': '対象を固定'},
                                                         {'id': 'target-to-observe',
                                                          'from': 'target',
                                                          'to': 'observe',
                                                          'label': '規範期待値を適用'},
                                                         {'id': 'observe-to-review',
                                                          'from': 'observe',
                                                          'to': 'review',
                                                          'label': '自動結果と手動観測を渡す'},
                                                         {'id': 'review-to-claim',
                                                          'from': 'review',
                                                          'to': 'claim',
                                                          'label': '証拠の限界を含める'}]},
 'core-17-graphics-visual-information': {'steps': [{'id': 'data',
                                                    'label': 'Data',
                                                    'detail': 'roadmapのnodeとedge、chartのlabelとvalueをID付きで定義する。'},
                                                   {'id': 'transform',
                                                    'label': 'Transform',
                                                    'detail': '並び、scale、minimum、maximumを決定的に計算する。'},
                                                   {'id': 'visual',
                                                    'label': 'Visual',
                                                    'detail': 'semantic HTMLとCSSでroadmapとquantitative chartを配置する。'},
                                                   {'id': 'equivalent',
                                                    'label': 'Equivalent',
                                                    'detail': 'node関係list、caption付きtable、summaryを同じdataから導出する。'},
                                                   {'id': 'verify',
                                                    'label': 'Verify',
                                                    'detail': 'ID、edge、row、値、集約、display modeの不変条件を照合する。'}],
                                         'transitions': [{'id': 'data-to-transform',
                                                          'from': 'data',
                                                          'to': 'transform',
                                                          'label': 'typed values'},
                                                         {'id': 'transform-to-visual',
                                                          'from': 'transform',
                                                          'to': 'visual',
                                                          'label': '同じtransformから決定的layout'},
                                                         {'id': 'transform-to-equivalent',
                                                          'from': 'transform',
                                                          'to': 'equivalent',
                                                          'label': '同じtransformから同等text'},
                                                         {'id': 'visual-to-verify',
                                                          'from': 'visual',
                                                          'to': 'verify',
                                                          'label': '視覚側のID・値を照合'},
                                                         {'id': 'equivalent-to-verify',
                                                          'from': 'equivalent',
                                                          'to': 'verify',
                                                          'label': 'text側のID・値を照合'}]},
 'core-19-technical-communication-design-docs': {'nodes': [{'id': 'decision-record',
                                                            'label': 'Decision record',
                                                            'detail': '選定結果、負うconsequence、再評価条件を明示する。',
                                                            'parentId': None},
                                                           {'id': 'audience',
                                                            'label': 'Audience',
                                                            'detail': '責務、判断、既知の用語、時間制約を定義する。',
                                                            'parentId': 'decision-record'},
                                                           {'id': 'evidence',
                                                            'label': 'Evidence',
                                                            'detail': '評価基準、入力、代替案、risk、検証結果を固定する。',
                                                            'parentId': 'decision-record'},
                                                           {'id': 'executive-view',
                                                            'label': 'Executive view',
                                                            'detail': '結論、価値、主要risk、承認依頼を一頁へ収める。',
                                                            'parentId': 'audience'},
                                                           {'id': 'implementation-view',
                                                            'label': 'Implementation view',
                                                            'detail': 'interface、migration、rollback、validationを付録へ置く。',
                                                            'parentId': 'audience'},
                                                           {'id': 'alternatives',
                                                            'label': '代替案と基準',
                                                            'detail': '採用案だけでなく比較対象と評価基準を保持する。',
                                                            'parentId': 'evidence'},
                                                           {'id': 'validation',
                                                            'label': '検証と再評価',
                                                            'detail': '結果の確認方法とdecisionを開き直す条件を保持する。',
                                                            'parentId': 'evidence'}]},
 'core-25-engineering-economics-capacity': {'rows': [{'id': 'scale-up',
                                                      'label': 'scale-up',
                                                      'detail': 'synthetic fixture: capacity 1000、direct '
                                                                '12000、engineering 40h、operations 20h、failure '
                                                                '0.05×8h。'},
                                                     {'id': 'automation',
                                                      'label': 'automation',
                                                      'detail': 'synthetic fixture: capacity 1600、direct '
                                                                '16000、engineering 120h、operations 5h、failure '
                                                                '0.01×2h。'}],
                                            'columns': [{'id': 'direct',
                                                         'label': 'direct cost',
                                                         'detail': 'lesson-defined取得・実行費。provider quoteではない。'},
                                                        {'id': 'opportunity',
                                                         'label': 'opportunity cost',
                                                         'detail': 'engineering hours × 100/hour。'},
                                                        {'id': 'operations',
                                                         'label': 'operations cost',
                                                         'detail': 'operations hours × 80/hour。'},
                                                        {'id': 'reliability',
                                                         'label': 'reliability loss',
                                                         'detail': 'failure probability × incident hours × '
                                                                   '10000/hour。'},
                                                        {'id': 'capacity-unit',
                                                         'label': 'total・capacity・unit cost',
                                                         'detail': '四cost合計、required capacity、served '
                                                                   'units、headroom、total/served units。'},
                                                        {'id': 'sensitivity',
                                                         'label': 'demand-growth sensitivity',
                                                         'detail': 'base demand 800でgrowthだけを変え、constraint breachをunit '
                                                                   'costより先に評価する。'}],
                                            'cells': [{'id': 'scale-direct',
                                                       'rowId': 'scale-up',
                                                       'columnId': 'direct',
                                                       'value': '12000',
                                                       'status': 'value'},
                                                      {'id': 'scale-opportunity',
                                                       'rowId': 'scale-up',
                                                       'columnId': 'opportunity',
                                                       'value': '40×100 = 4000',
                                                       'status': 'value'},
                                                      {'id': 'scale-operations',
                                                       'rowId': 'scale-up',
                                                       'columnId': 'operations',
                                                       'value': '20×80 = 1600',
                                                       'status': 'value'},
                                                      {'id': 'scale-reliability',
                                                       'rowId': 'scale-up',
                                                       'columnId': 'reliability',
                                                       'value': '0.05×8×10000 = 4000',
                                                       'status': 'value'},
                                                      {'id': 'scale-total',
                                                       'rowId': 'scale-up',
                                                       'columnId': 'capacity-unit',
                                                       'value': '12000 + 40×100 + 20×80 + 0.05×8×10000 = 21600; '
                                                                '21600/800 = 27.00/unit',
                                                       'status': 'value'},
                                                      {'id': 'scale-sensitivity',
                                                       'rowId': 'scale-up',
                                                       'columnId': 'sensitivity',
                                                       'value': 'growth 0.25でrequired capacity 1000、headroom 0; '
                                                                '0.25超でbreach',
                                                       'status': 'value'},
                                                      {'id': 'automation-direct',
                                                       'rowId': 'automation',
                                                       'columnId': 'direct',
                                                       'value': '16000',
                                                       'status': 'value'},
                                                      {'id': 'automation-opportunity',
                                                       'rowId': 'automation',
                                                       'columnId': 'opportunity',
                                                       'value': '120×100 = 12000',
                                                       'status': 'value'},
                                                      {'id': 'automation-operations',
                                                       'rowId': 'automation',
                                                       'columnId': 'operations',
                                                       'value': '5×80 = 400',
                                                       'status': 'value'},
                                                      {'id': 'automation-reliability',
                                                       'rowId': 'automation',
                                                       'columnId': 'reliability',
                                                       'value': '0.01×2×10000 = 200',
                                                       'status': 'value'},
                                                      {'id': 'automation-total',
                                                       'rowId': 'automation',
                                                       'columnId': 'capacity-unit',
                                                       'value': '16000 + 120×100 + 5×80 + 0.01×2×10000 = 28600; '
                                                                '28600/800 = 35.75/unit',
                                                       'status': 'value'},
                                                      {'id': 'automation-sensitivity',
                                                       'rowId': 'automation',
                                                       'columnId': 'sensitivity',
                                                       'value': 'growth 0.5でrequired capacity 1200、headroom '
                                                                '400、automationを選択',
                                                       'status': 'value'}]},
 'core-28-oss-governance-stewardship': {'steps': [{'id': 'discover',
                                                   'label': 'discover',
                                                   'detail': '第三者がlicense、community '
                                                             'rule、security窓口、contribution手順を見つける。'},
                                                  {'id': 'prepare',
                                                   'label': 'prepare',
                                                   'detail': 'forkまたは同等のread-only境界で変更と検証証拠を作る。'},
                                                  {'id': 'submit',
                                                   'label': 'submit',
                                                   'detail': '変更理由、scope、test結果をreview可能な単位で提示する。'},
                                                  {'id': 'review',
                                                   'label': 'review',
                                                   'detail': 'maintainerが品質、security、policy、互換性を証拠で判断する。'},
                                                  {'id': 'maintainer-merge',
                                                   'label': 'maintainer-merge',
                                                   'detail': 'write権限を第三者へ移さず、承認済み変更だけを統合する。'},
                                                  {'id': 'release-evidence',
                                                   'label': 'release-evidence',
                                                   'detail': 'CI結果、provenance、承認、公開artifactを対応付ける。'}],
                                        'transitions': [{'id': 'discover-to-prepare',
                                                         'from': 'discover',
                                                         'to': 'prepare',
                                                         'label': '公開policyを理解'},
                                                        {'id': 'prepare-to-submit',
                                                         'from': 'prepare',
                                                         'to': 'submit',
                                                         'label': '変更と検証証拠'},
                                                        {'id': 'submit-to-review',
                                                         'from': 'submit',
                                                         'to': 'review',
                                                         'label': 'review可能なscope'},
                                                        {'id': 'review-to-merge',
                                                         'from': 'review',
                                                         'to': 'maintainer-merge',
                                                         'label': 'maintainer承認'},
                                                        {'id': 'merge-to-release',
                                                         'from': 'maintainer-merge',
                                                         'to': 'release-evidence',
                                                         'label': '統合commitをartifactへ追跡'}]}}
TASK7_VISUAL_CONTRACT_SHA256 = {
    "core-02-algorithms-measurement": "d54ddfd1d57997d9ad22214a414cf97090f30758e104ab15c13bd5247d326db7",
    "core-03-architecture-memory-caches": "a4a48705ff0725ab6549e3554f88975574a6e5390ed925a042aecf02e4b76776",
    "core-11-data-modeling-storage": "d069bd0f046036b715c2083bc2b208a08da846d44a24a44e182d0ae044376ad4",
    "core-16-hci-usability-accessibility": "2479940e86a8e782f34887cd0951068c0e731bd9c2f5282e3fa5d3b1217a7e56",
    "core-17-graphics-visual-information": "b546551905fbe4d447c690209377666ac3cbc9b6f89254786cec919b22048a6a",
    "core-19-technical-communication-design-docs": "19c43b251a3be87d4e9285af961000ba676d4df9fdef06a8fb29e3e8dc9bad91",
    "core-25-engineering-economics-capacity": "c98dd7dfbdc4419478107a61c19a340f516ebc30bf16fabe67bf695bdee582c6",
    "core-28-oss-governance-stewardship": "53b530d4a257216d7f96d47404163f8bab72e8730909ea68df0dfc6fce223082",
}
TASK6_VISUAL_CONTRACT_SHA256 = {
    "core-04-os-processes-concurrency": "01e944d4d1847cc76b638183bdf58f4613eb55fb2da38d2d491ba30d8df6ae13",
    "core-05-networks-latency-failure": "6985c88dd048dd0bc6893a28ba3febfad7fff2a47648f4ae270a1f2eb4f3a5b2",
    "core-07-api-contract-design": "7fc89718157ef6118597c7ee5067fe2f0c0f03103a7b1bd2594eaf09f2e62807",
    "core-09-test-strategy-tdd": "e3cbfd0a85a97d968ae97031753676bae8c7f1264fb969e41dc5518450e991d4",
    "core-12-transactions-isolation-consistency": "5e2d513d61d6db8de805d84503e0ba7eb6335ca8b2e2bc8c2af2301919e6aaf3",
    "core-13-distributed-coordination-failure": "25531e2932f1358bdc26e15ecb3c9aac752f181aaea2a8ec9c55f859eb55fc8e",
    "core-15-reliability-observability-slo": "1963def9e97269e1ee86a6637b9311c13e9f442e4865800c90135b3716266e22",
    "core-22-evolution-safe-migrations": "aa04630c0005fb992238aca964bd09d0f95a11b8bacdaffeb79e13e2af868057",
    "core-23-incident-response-learning": "a8cf68469ee3358c5f6977e3cb58fd9d4648c0c2cf8194adb9c2022547368977",
    "core-24-delivery-ci-release-safety": "80557db3e04b3746228f3593862c94f1cf78abf0877fc0fb98334a46f2319352",
    "core-26-code-review-collaborative-quality": "228db9f1634d55d8fef51d184d29dc74b017468fb8f6b846ef70f1d8baadccb9",
    "core-29-cross-cultural-async-collaboration": "ad600a1d0755e79b755c6c0a6c08185cbf8ba349e415345a472d94b15519332e",
}
TASK6_VISUAL_CONTRACTS = {'core-04-os-processes-concurrency': {'common': ('concurrency-diagnostic-timeline',
                                                 'timeline',
                                                 'mentalModel',
                                                 None,
                                                 '共有境界から不変条件を守る診断経路',
                                                 '説明用のx=10で、Thread A/Bのどのinterleavingがlost updateを起こし、mutex後に何が変わるか。',
                                                 '両threadがx=10を読む最小trace、期待値x=8に対する違反点、mutex後のx=8を順に説明できる。',
                                                 ('obj-boundaries', 'obj-race'),
                                                 ('race-record',),
                                                 ('src-01', 'src-04'),
                                                 ('この注記は旧図の読み順を保持する補助です。',
                                                  '隔離単位: process A、process B、または同一process内thread AとBを置く。',
                                                  '共有対象: memory、file、socket、database row、queueを列挙する。',
                                                  '操作分解: read、compute、write、publishをイベントへ分ける。',
                                                  '不変条件: 在庫は0以上、合計減算数と最終値が一致、同じ注文を二度確定しない。',
                                                  '同期関係: mutex、atomic operation、message passingのどれが前後関係を作るか示す。',
                                                  '停止性: lock順、待機資源、timeout、cancel経路を観測する。',
                                                  '回帰: 同じstress条件で違反頻度と所要時間を再測定する。')),
                                      'phases': (('boundary',
                                                  '境界と説明用fixture',
                                                  '同一processのThread A/Bが共有整数xを1ずつ減算する説明用scenario。初期値x = 10は普遍値ではない。'),
                                                 ('lost-update-trace',
                                                  '同期なしのlost update',
                                                  '両threadが同じx = 10を読んで9を書き、二回減算の期待値x = 8を破る最小trace。'),
                                                 ('synchronized-trace',
                                                  'mutexによる比較trace',
                                                  '同じ説明用fixtureをmutexで直列化し、二回目のreadがx = 9を見る比較。'),
                                                 ('verification', '停止性と回帰', '安全性だけでなくlock順、timeout、同条件stressを再確認する。')),
                                      'events': (('isolation-unit',
                                                  '隔離単位・shared context',
                                                  'process A/Bまたは同一processのThread '
                                                  'A/Bを置く。この説明用traceは同一processの二threadを使う。',
                                                  'boundary',
                                                  0,
                                                  'shared-context'),
                                                 ('shared-target',
                                                  '共有対象・x',
                                                  'memory上の共有整数x = 10を説明用fixtureとし、実systemではfile、socket、database '
                                                  'row、queueも列挙する。',
                                                  'boundary',
                                                  1,
                                                  'shared-context'),
                                                 ('unsynchronized-start',
                                                  '同期なし開始',
                                                  '説明用の値は初期値x = 10。Thread AとThread Bがmutexなしで1ずつ減算する。',
                                                  'lost-update-trace',
                                                  2,
                                                  'shared-context'),
                                                 ('a-read',
                                                  'Thread A read',
                                                  'Thread Aが共有値x = 10を読む。',
                                                  'lost-update-trace',
                                                  3,
                                                  'thread-a'),
                                                 ('b-read',
                                                  'Thread B read',
                                                  'Thread BもAのwrite前に同じ共有値x = 10を読む。',
                                                  'lost-update-trace',
                                                  4,
                                                  'thread-b'),
                                                 ('a-compute',
                                                  'Thread A compute',
                                                  'Thread Aはlocalに10 - 1 = 9を計算する。',
                                                  'lost-update-trace',
                                                  5,
                                                  'thread-a'),
                                                 ('b-compute',
                                                  'Thread B compute',
                                                  'Thread Bもlocalに10 - 1 = 9を計算する。',
                                                  'lost-update-trace',
                                                  6,
                                                  'thread-b'),
                                                 ('a-write',
                                                  'Thread A write',
                                                  'Thread Aが共有値へx = 9を書き込む。',
                                                  'lost-update-trace',
                                                  7,
                                                  'thread-a'),
                                                 ('b-write',
                                                  'Thread B write',
                                                  'Thread Bが同じx = 9を上書きし、Thread Aの減算を失わせる。',
                                                  'lost-update-trace',
                                                  8,
                                                  'thread-b'),
                                                 ('lost-update-violation',
                                                  'lost update違反点',
                                                  '二回減算後の期待値 x = 8に対しactual x = 9。Thread B writeの完了時点でlost '
                                                  'updateが観測可能になる。',
                                                  'lost-update-trace',
                                                  9,
                                                  'shared-context'),
                                                 ('a-lock',
                                                  'Thread A mutex取得',
                                                  '同じ説明用fixtureをx = 10へ戻し、Thread Aがmutexを取得する。',
                                                  'synchronized-trace',
                                                  10,
                                                  'thread-a'),
                                                 ('a-locked-update',
                                                  'Thread A read/compute/write',
                                                  'mutex内でThread Aがx = 10を読み、9を計算してx = 9を書く。',
                                                  'synchronized-trace',
                                                  11,
                                                  'thread-a'),
                                                 ('a-unlock',
                                                  'Thread A mutex解放',
                                                  'Thread Aのwrite後にmutexを解放し、happens-beforeを作る。',
                                                  'synchronized-trace',
                                                  12,
                                                  'thread-a'),
                                                 ('b-lock',
                                                  'Thread B mutex取得',
                                                  'Thread BはAの解放後にmutexを取得する。',
                                                  'synchronized-trace',
                                                  13,
                                                  'thread-b'),
                                                 ('b-locked-update',
                                                  'Thread B read/compute/write',
                                                  'Thread Bは同期後のx = 9を読み、8を計算してx = 8を書く。',
                                                  'synchronized-trace',
                                                  14,
                                                  'thread-b'),
                                                 ('synchronized-invariant',
                                                  '同期後の不変条件',
                                                  '同期後の x = 8は二回減算後の期待値 x = 8と一致し、lost updateはない。',
                                                  'synchronized-trace',
                                                  15,
                                                  'shared-context'),
                                                 ('liveness',
                                                  '停止性',
                                                  'mutexのlock順、待機資源、timeout、cancel経路を観測する。',
                                                  'verification',
                                                  16,
                                                  'shared-context'),
                                                 ('regression',
                                                  '回帰',
                                                  '同期なしとmutexありを同じstress条件で反復し、違反頻度と所要時間を再測定する。',
                                                  'verification',
                                                  17,
                                                  'shared-context'))},
 'core-05-networks-latency-failure': {'common': ('request-path-timeline',
                                                 'timeline',
                                                 'mentalModel',
                                                 None,
                                                 'DNSから業務結果までの時系列',
                                                 '説明用の総deadline 300msで、どのeventが最初の超過点となり、残りbudgetはどう変化したか。',
                                                 '各eventのbudgetと累積observedを追い、first-byteの310msを最初の超過点として説明できる。これは普遍的なlatency値ではない。',
                                                 ('obj-timeline', 'obj-budget'),
                                                 ('trace-budget',),
                                                 ('src-01', 'src-02', 'src-04', 'src-05'),
                                                 ()),
                                      'phases': (('connection',
                                                  '接続準備 budget 120ms',
                                                  '説明用の総deadline 300msのうちDNS 30ms、TCP 40ms、TLS '
                                                  '50msを割り当てる。observed合計105ms。普遍値ではない。'),
                                                 ('exchange',
                                                  'HTTP交換 budget 160ms',
                                                  'request 10ms、server 100ms、first-byte 20ms、body 30ms。first-byte '
                                                  'observedで総deadlineを初めて超える。'),
                                                 ('business-result',
                                                  '業務結果 budget 20ms',
                                                  'transport完了後の結果永続化へ20msを割り当てる。数値はtraceの読み方を示す説明用。')),
                                      'events': (('dns',
                                                  '名前解決（説明用budget）',
                                                  'DNS queryを送り、候補addressとTTLを得る。budget 30ms、observed '
                                                  '25ms、累積25ms・残り275ms。',
                                                  'connection',
                                                  0,
                                                  None),
                                                 ('tcp',
                                                  '輸送接続（説明用budget）',
                                                  'TCP SYN、SYN-ACK、ACKで接続状態を確立する。budget 40ms、observed '
                                                  '35ms、累積60ms・残り240ms。',
                                                  'connection',
                                                  1,
                                                  None),
                                                 ('tls',
                                                  '暗号接続（説明用budget）',
                                                  'TLSでversion、鍵、相手のidentityを検証する。budget 50ms、observed '
                                                  '45ms、累積105ms・残り195ms。',
                                                  'connection',
                                                  2,
                                                  None),
                                                 ('request',
                                                  'request送信（説明用budget）',
                                                  'HTTP method、target、header、bodyを送る。budget 10ms、observed '
                                                  '10ms、累積115ms・残り185ms。',
                                                  'exchange',
                                                  3,
                                                  None),
                                                 ('server',
                                                  'server処理（説明用budget）',
                                                  'handlerと依存serviceが状態を読み書きする。budget 100ms、observed '
                                                  '120ms、累積235ms・残り65ms。',
                                                  'exchange',
                                                  4,
                                                  None),
                                                 ('first-byte',
                                                  '最初のbyte（説明用budget）',
                                                  'statusとheaderを受け始める。budget 20ms、observed '
                                                  '75ms、累積310ms。ここが最初のdeadline超過点（10ms超過）。',
                                                  'exchange',
                                                  5,
                                                  None),
                                                 ('body-complete',
                                                  '本文完了（説明用budget）',
                                                  'responseを読み終える。ただし業務結果はstatusとbodyの契約で判定する。budget 30ms、observed '
                                                  '25ms、累積335ms・残り-35ms。',
                                                  'exchange',
                                                  6,
                                                  None),
                                                 ('result',
                                                  '結果確定（説明用budget）',
                                                  'clientが結果を永続化し、必要なら冪等keyで後から照会できる。budget 20ms、observed '
                                                  '10ms、累積345ms・残り-45ms。',
                                                  'business-result',
                                                  7,
                                                  None))},
 'core-07-api-contract-design': {'common': ('offline-operation-state-machine',
                                            'state-machine',
                                            'mentalModel',
                                            None,
                                            'オフライン操作を副作用と観測へ分ける契約経路',
                                            'response喪失後のretryで、どの保存済み副作用を再利用し、何を再実行してはいけないか。',
                                            '冪等keyのscope、耐久化済み効果、試行ごとに変わるresponseを分け、安全なretryと拒否遷移を説明できる。',
                                            ('obj-contract', 'obj-replay', 'obj-evolution'),
                                            ('api-contract',),
                                            ('src-01', 'src-02', 'src-03'),
                                            ()),
                                 'states': (('created',
                                             '作成',
                                             'clientは操作ID、冪等key、対象version、tenantを永続化する。serverは認証済みprincipal、tenant、route、keyを保存scopeにする。'),
                                            ('sent', '送信', 'serverはschema、意味、認証、認可を順に検査する。'),
                                            ('applied', '適用', 'keyと操作結果を同じ耐久境界で記録し、状態を一度だけ進める。'),
                                            ('responded', '応答', '現在時刻やtrace IDを含むresponseは試行ごとに違ってよい。'),
                                            ('response-lost', '喪失', 'responseが届かなくても、clientは同じkeyで安全に再送する。'),
                                            ('queried', '照会', '保存済み効果を返し、同じ配送や同じresponseを保証したとは主張しない。'),
                                            ('evolved', '進化', '旧versionの利用状況を観測し、source、wire、意味の互換性を別々に判定する。')),
                                 'initialStateId': 'created',
                                 'transitions': (('created-to-sent', 'created', 'sent', 'next', 'allowed', None),
                                                 ('sent-to-applied', 'sent', 'applied', 'next', 'allowed', None),
                                                 ('applied-to-responded',
                                                  'applied',
                                                  'responded',
                                                  'next',
                                                  'allowed',
                                                  None),
                                                 ('applied-to-lost',
                                                  'applied',
                                                  'response-lost',
                                                  'timer',
                                                  'allowed',
                                                  None),
                                                 ('lost-to-query', 'response-lost', 'queried', 'next', 'allowed', None),
                                                 ('responded-to-evolved',
                                                  'responded',
                                                  'evolved',
                                                  'next',
                                                  'allowed',
                                                  None),
                                                 ('queried-to-evolved', 'queried', 'evolved', 'next', 'allowed', None),
                                                 ('lost-reapply',
                                                  'response-lost',
                                                  'applied',
                                                  'next',
                                                  'rejected',
                                                  '同じ冪等keyの保存済み効果を再適用してはならない。'))},
 'core-09-test-strategy-tdd': {'common': ('tdd-evidence-loop',
                                          'state-loop',
                                          'mentalModel',
                                          None,
                                          'riskから証拠へ進み、mutationで感度を反証するloop',
                                          'GREEN後のmutationでtestが誤りを検出しなかった時、どの期待へ戻るか。',
                                          'risk、RED、GREEN、refactor、mutationを循環させ、生存mutantから期待を改善して証拠成立へ到達できる。',
                                          ('obj-cycle', 'obj-strategy'),
                                          ('tdd-history',),
                                          ('src-01', 'src-02', 'src-03'),
                                          ()),
                               'states': (('risk', 'Step 1', '利用者影響と守る不変条件を一つ選ぶ。'),
                                          ('red', 'Step 2', '失敗する最小の期待を実行し、REDの理由を読む。'),
                                          ('green', 'Step 3', '最小実装でGREENにし、別の入力でも性質を確認する。'),
                                          ('refactor', 'Step 4', '振る舞いを保って構造を整理し、同じ観測を再実行する。'),
                                          ('mutation', 'Step 5', 'mutantまたは障害注入で、testが実際に誤りを検出するか確かめる。'),
                                          ('evidence-ready', '証拠成立', 'mutantを検出し、同じ観測を再実行できる。')),
                               'entryStateId': 'risk',
                               'exitStateId': 'evidence-ready',
                               'recoveryStateId': 'mutation',
                               'transitions': (('risk-to-red', 'risk', 'red', '次の証拠を得る', None),
                                               ('red-to-green', 'red', 'green', '次の証拠を得る', None),
                                               ('green-to-refactor', 'green', 'refactor', '次の証拠を得る', None),
                                               ('refactor-to-mutation', 'refactor', 'mutation', '次の証拠を得る', None),
                                               ('mutation-feedback', 'mutation', 'red', 'mutantが生存したら期待を改善する', None),
                                               ('mutation-exit',
                                                'mutation',
                                                'evidence-ready',
                                                'mutantを検出したら証拠を確定する',
                                                None)),
                               'feedbackTransitionIds': ('mutation-feedback',)},
 'core-12-transactions-isolation-consistency': {'common': ('isolation-schedule-timeline',
                                                           'timeline',
                                                           'mentalModel',
                                                           None,
                                                           'snapshotから依存関係、commit判定、retryへ進む分離異常の因果経路',
                                                           '同じsnapshotを読んだT1とT2のwrite skewを、どの依存検証とretryが防ぐか。',
                                                           '業務不変条件、並行read、局所判断、Serializableのabort、transaction全体の再読込を順に説明できる。',
                                                           ('obj-anomaly', 'obj-serializable'),
                                                           ('transaction-experiment',),
                                                           ('src-01', 'src-02', 'src-04'),
                                                           ()),
                                                'phases': (('contract', '不変条件', 'rowとは別に業務不変条件を固定する。'),
                                                           ('concurrent',
                                                            '並行schedule',
                                                            '二つのtransactionのreadと局所判断を並べる。'),
                                                           ('validation-phase', '検証と回復', 'commit可否を判断し、abort後は読み直す。')),
                                                'events': (('invariant',
                                                            '不変条件',
                                                            '「aliceまたはbobの少なくとも一人が当直」をdatabaseのrowとは別に明示する。',
                                                            'contract',
                                                            0,
                                                            None),
                                                           ('snapshot',
                                                            'snapshot',
                                                            'T1とT2が同じ開始状態 {alice: on, bob: on} を読む。',
                                                            'concurrent',
                                                            1,
                                                            None),
                                                           ('local-decision',
                                                            '局所判断',
                                                            'T1はbobが当直なのでaliceを外し、T2はaliceが当直なのでbobを外す。',
                                                            'concurrent',
                                                            2,
                                                            None),
                                                           ('validation',
                                                            '検証',
                                                            'Snapshot '
                                                            'Isolationでは別rowへのwriteが双方commitし得る。Serializableでは危険な依存を検出して一方をabortする。',
                                                            'validation-phase',
                                                            3,
                                                            None),
                                                           ('retry',
                                                            'retry',
                                                            'abortされたT2は古い判断を再利用せず、transaction開始から読み直す。aliceが外れているためbobを当直に残す。',
                                                            'validation-phase',
                                                            4,
                                                            None))},
 'core-13-distributed-coordination-failure': {'common': ('dedupe-recovery-timeline',
                                                         'timeline',
                                                         'mentalModel',
                                                         None,
                                                         'at-least-once commandを永続dedupeと回復へ接続するmechanism',
                                                         'response lossと再配送があっても副作用を一度だけ進めるdedupeの耐久境界はどこか。',
                                                         'stable keyとfingerprintの照合、stateとresultのatomic '
                                                         'commit、partition回復後の再評価を説明できる。',
                                                         ('obj-idempotency', 'obj-recovery'),
                                                         ('coordination-simulation',),
                                                         ('src-01', 'src-03', 'src-04'),
                                                         ()),
                                              'phases': (('dedupe', '重複排除', 'stable keyと入力fingerprintで再配送を識別する。'),
                                                         ('durability', '耐久化', '状態遷移と再利用resultを同じ境界で保存する。'),
                                                         ('recovery', '回復', 'partition後の順序差と期限超過を再評価する。')),
                                              'events': (('receive',
                                                          'receive',
                                                          'tenant、resource、operationを含むstable keyと入力fingerprintを受け取る。',
                                                          'dedupe',
                                                          0,
                                                          None),
                                                         ('lookup',
                                                          'lookup',
                                                          '永続dedupe '
                                                          'storeにkeyがあれば入力fingerprintを照合し、一致時だけ状態遷移を再実行せず最初のresultを再利用する。不一致はkey衝突として拒否する。',
                                                          'dedupe',
                                                          1,
                                                          None),
                                                         ('apply',
                                                          'apply',
                                                          'keyがなければ現在stateから許可された次stateへ一度だけ遷移する。',
                                                          'durability',
                                                          2,
                                                          None),
                                                         ('commit',
                                                          'commit',
                                                          'state、fingerprint、resultを同じdurability境界で保存する。response '
                                                          'lossはcommitを取り消さない。',
                                                          'durability',
                                                          3,
                                                          None),
                                                         ('recover',
                                                          'recover',
                                                          'partition中のmessageを再開後に処理し、logical sequenceとdelivery '
                                                          'orderの差を検査する。',
                                                          'recovery',
                                                          4,
                                                          None),
                                                         ('reevaluate',
                                                          're-evaluate',
                                                          'partitionがdeadlineを越えたら、queue、retention、stale '
                                                          'command、reconciliation、利用者結果を更新する。',
                                                          'recovery',
                                                          5,
                                                          None))},
 'core-15-reliability-observability-slo': {'common': ('slo-action-loop',
                                                      'state-loop',
                                                      'mentalModel',
                                                      None,
                                                      '利用者結果からon-call actionまでを閉じるflow',
                                                      'どのSLIとburn evidenceがpageを起動し、mitigation後の何を確認してloopを終了するか。',
                                                      'JourneyからSLI・SLO・telemetry・alert・runbookへ進み、復旧証拠が揃ったterminal '
                                                      'stateを示せる。',
                                                      ('obj-sli-slo', 'obj-alert', 'obj-telemetry'),
                                                      ('slo-runbook',),
                                                      ('src-01', 'src-02', 'src-04'),
                                                      ('この注記は旧図の読み順を保持する補助です。',
                                                       'Journey: 利用者が達成したい結果とvalidな試行を定める。',
                                                       'SLI: goodの結果とlatency境界をevent単位で計算する。',
                                                       'SLO: window、target、error budget、例外を合意する。',
                                                       'Alert: 短窓と長窓のburnをpageとticketへ分ける。',
                                                       'Runbook: impact確認、mitigation、rollback、escalationを結ぶ。',
                                                       'Telemetry: traceで原因へ相関し、意味とprivacyを検証する。')),
                                           'states': (('journey', 'Journey', '利用者が達成したい結果とvalidな試行を定める。'),
                                                      ('sli', 'SLI', 'goodの結果とlatency境界をevent単位で計算する。'),
                                                      ('slo', 'SLO', 'window、target、error budget、例外を合意する。'),
                                                      ('telemetry', 'Telemetry', 'traceで原因へ相関し、意味とprivacyを検証する。'),
                                                      ('alert', 'Alert', '短窓と長窓のburnをpageとticketへ分ける。'),
                                                      ('runbook',
                                                       'Runbook',
                                                       'impact確認、mitigation、rollback、escalationを結ぶ。'),
                                                      ('evidence-ready',
                                                       '復旧証拠成立',
                                                       '利用者結果、burn rate、mitigation後のservice状態を再観測し、pageを閉じられる。')),
                                           'entryStateId': 'journey',
                                           'exitStateId': 'evidence-ready',
                                           'recoveryStateId': 'alert',
                                           'transitions': (('journey-to-sli',
                                                            'journey',
                                                            'sli',
                                                            'valid eventからgoodを計算する',
                                                            None),
                                                           ('sli-to-slo', 'sli', 'slo', 'windowとtargetを合意する', None),
                                                           ('slo-to-telemetry',
                                                            'slo',
                                                            'telemetry',
                                                            'SLIを安定したsignalとして収集する',
                                                            None),
                                                           ('telemetry-to-alert',
                                                            'telemetry',
                                                            'alert',
                                                            '短窓と長窓のburnを評価する',
                                                            None),
                                                           ('alert-to-runbook',
                                                            'alert',
                                                            'runbook',
                                                            'pageからmitigationへ進む',
                                                            None),
                                                           ('runbook-feedback',
                                                            'runbook',
                                                            'telemetry',
                                                            'mitigation後の利用者結果を再観測する',
                                                            None),
                                                           ('runbook-to-evidence',
                                                            'runbook',
                                                            'evidence-ready',
                                                            '復旧とburn正常化を確認してpageを閉じる',
                                                            None)),
                                           'feedbackTransitionIds': ('runbook-feedback',)},
 'core-22-evolution-safe-migrations': {'common': ('expand-contract-state-machine',
                                                  'state-machine',
                                                  'mentalModel',
                                                  None,
                                                  '互換性と観測gateを持つexpand-contract state machine',
                                                  'dual write、backfill、dual readの各phaseで互換性gateが失敗した時、どの安全状態へ戻すか。',
                                                  'phase別の停止・rollback先、旧reader互換性、復旧観測、contractへの拒否条件を説明できる。',
                                                  ('obj-state-machine', 'obj-observation'),
                                                  ('migration-plan',),
                                                  ('src-01', 'src-02', 'src-03'),
                                                  ('この注記は旧図の読み順を保持する補助です。',
                                                   'expand: old readerを壊さないnullable構造を追加する。',
                                                   'dual write: 新旧fieldへ書き、成功率と値のparityを観測する。',
                                                   'backfill: bounded batchで既存rowを移しerror rateとlagを測る。',
                                                   'dual read: 新旧readerの結果差を比較しfallbackを保持する。',
                                                   'contract: 利用停止の証拠を確認してから旧構造を除く。',
                                                   'rollback: 各stateで戻す対象と回復確認を先に定義する。')),
                                       'states': (('expand', 'expand', 'old readerを壊さないnullable構造を追加する。'),
                                                  ('dual-write', 'dual write', '新旧fieldへ書き、成功率と値のparityを観測する。'),
                                                  ('backfill', 'backfill', 'bounded batchで既存rowを移しerror rateとlagを測る。'),
                                                  ('dual-read', 'dual read', '新旧readerの結果差を比較しfallbackを保持する。'),
                                                  ('contract', 'contract', '利用停止の証拠を確認してから旧構造を除く。'),
                                                  ('dual-write-compatible',
                                                   'dual write停止・旧構造互換',
                                                   '新fieldへのwriteを停止し、old readerが旧fieldから正しい値を読める状態へ戻す。'),
                                                  ('backfill-compatible',
                                                   'backfill停止・旧構造互換',
                                                   'bounded batchを停止し、dual writeと旧fieldを維持して未移行rowを安全に残す。'),
                                                  ('dual-read-compatible',
                                                   'old readへfallback',
                                                   '新readerを停止し、old readerの結果へfallbackして利用者結果を回復する。'),
                                                  ('restoration-verified',
                                                   '互換性回復を検証済み',
                                                   'old reader成功率、値のparity、error rate、利用者結果を再観測して安全状態を確認する。')),
                                       'initialStateId': 'expand',
                                       'transitions': (('expand-to-dual-write',
                                                        'expand',
                                                        'dual-write',
                                                        'next',
                                                        'allowed',
                                                        None),
                                                       ('dual-write-to-backfill',
                                                        'dual-write',
                                                        'backfill',
                                                        'next',
                                                        'allowed',
                                                        None),
                                                       ('backfill-to-dual-read',
                                                        'backfill',
                                                        'dual-read',
                                                        'next',
                                                        'allowed',
                                                        None),
                                                       ('dual-read-to-contract',
                                                        'dual-read',
                                                        'contract',
                                                        'next',
                                                        'allowed',
                                                        None),
                                                       ('dual-write-stop',
                                                        'dual-write',
                                                        'dual-write-compatible',
                                                        'reset',
                                                        'allowed',
                                                        None),
                                                       ('backfill-stop',
                                                        'backfill',
                                                        'backfill-compatible',
                                                        'reset',
                                                        'allowed',
                                                        None),
                                                       ('dual-read-rollback',
                                                        'dual-read',
                                                        'dual-read-compatible',
                                                        'reset',
                                                        'allowed',
                                                        None),
                                                       ('dual-write-verify',
                                                        'dual-write-compatible',
                                                        'restoration-verified',
                                                        'next',
                                                        'allowed',
                                                        None),
                                                       ('backfill-verify',
                                                        'backfill-compatible',
                                                        'restoration-verified',
                                                        'next',
                                                        'allowed',
                                                        None),
                                                       ('dual-read-verify',
                                                        'dual-read-compatible',
                                                        'restoration-verified',
                                                        'next',
                                                        'allowed',
                                                        None),
                                                       ('parity-forward-rejected',
                                                        'dual-write',
                                                        'backfill',
                                                        'timer',
                                                        'rejected',
                                                        '成功率または値のparityがgateを満たさない間はbackfillへ進まない。'),
                                                       ('backfill-forward-rejected',
                                                        'backfill',
                                                        'dual-read',
                                                        'timer',
                                                        'rejected',
                                                        'backfillのerror rateまたはlagがgateを満たさない間はdual readへ進まない。'),
                                                       ('contract-forward-rejected',
                                                        'dual-read',
                                                        'contract',
                                                        'timer',
                                                        'rejected',
                                                        '旧構造の利用停止証拠が揃うまでcontractを開始しない。'))},
 'core-23-incident-response-learning': {'common': ('incident-review-timeline',
                                                   'timeline',
                                                   'mentalModel',
                                                   None,
                                                   'incident evidenceを検証可能な学習へ変えるreview chain',
                                                   'incident当時利用可能だったevidenceから、検知遅延のimpactとdecisionをどう再構成するか。',
                                                   'clockを揃えたtimeline、影響計算、当時の判断、system factor、検証可能なactionを追跡できる。',
                                                   ('obj-evidence', 'obj-learning', 'obj-action'),
                                                   ('incident-review',),
                                                   ('src-01', 'src-02', 'src-03'),
                                                   ()),
                                        'phases': (('reconstruct', '再構成', '観測事実とclockを揃える。'),
                                                   ('analyze', '分析', '影響、当時の判断、system conditionを証拠へ結ぶ。'),
                                                   ('learn', '学習', '検証可能なactionとして完了条件を固定する。')),
                                        'events': (('evidence',
                                                    'Evidence',
                                                    'timestamp、source、観測値、evidence IDを固定する。',
                                                    'reconstruct',
                                                    0,
                                                    None),
                                                   ('timeline',
                                                    'Timeline',
                                                    'clockを揃えて観測事実を時刻順に並べる。',
                                                    'reconstruct',
                                                    1,
                                                    None),
                                                   ('impact',
                                                    'Impact',
                                                    'incident startからdetectionまでの未緩和時間とaffected rateから検知遅延の影響を導く。',
                                                    'analyze',
                                                    2,
                                                    None),
                                                   ('decision',
                                                    'Decision',
                                                    '当時利用可能だったevidenceと判断を結ぶ。',
                                                    'analyze',
                                                    3,
                                                    None),
                                                   ('factor',
                                                    'Factor',
                                                    '複数のsystem conditionと反証可能な仮説を残す。',
                                                    'analyze',
                                                    4,
                                                    None),
                                                   ('action',
                                                    'Action',
                                                    'owner、due、verification、evidenceで完了を定義する。',
                                                    'learn',
                                                    5,
                                                    None))},
 'core-24-delivery-ci-release-safety': {'common': ('release-evidence-state-machine',
                                                   'state-machine',
                                                   'mentalModel',
                                                   None,
                                                   'source変更からrollback outcomeまでを結ぶdelivery evidence chain',
                                                   'required '
                                                   'check不足でstopした後、原因解消から全gateを再実行し、canaryでpromoteとrollbackのどちらを選ぶか。',
                                                   'stopを未配信の安全な中断としてCIへ戻し、promoteまたはrollback復旧だけを完了outcomeへ結べる。',
                                                   ('obj-ci', 'obj-provenance', 'obj-outcome'),
                                                   ('delivery-evidence',),
                                                   ('src-01', 'src-03', 'src-04'),
                                                   ('この注記は旧図の読み順を保持する補助です。',
                                                    '現行modelではstopはCI evidence '
                                                    'missing/unknown、promote/rollbackはpost-canary判断です。',
                                                    'CI: required check集合がすべて観測され成功したか検査する。',
                                                    'Artifact: 配信対象bytesからdigestを計算して固定する。',
                                                    'Provenance: subject digestとtrusted builderを独立に検証する。',
                                                    'Canary: 利用者可視のerror rateを閾値と比較する。',
                                                    'Decision: advance、stop、rollbackを入力から導く。',
                                                    'Outcome: command完了後にservice restorationを再観測する。')),
                                        'states': (('ci', 'CI', 'required check集合がすべて観測され成功したか検査する。'),
                                                   ('artifact', 'Artifact', '配信対象bytesからdigestを計算して固定する。'),
                                                   ('provenance',
                                                    'Provenance',
                                                    'subject digestとtrusted builderを独立に検証する。'),
                                                   ('canary', 'Canary', '利用者可視のerror rateを閾値と比較する。'),
                                                   ('decision', 'Decision', 'canary thresholdからpromoteまたはrollbackを導く。'),
                                                   ('promoted',
                                                    'promote実行',
                                                    'canaryが閾値内なら同一digestのartifactを次の配信段階へ進める。'),
                                                   ('stopped',
                                                    'required check不足でstop',
                                                    'required '
                                                    'checkがmissing、unknown、failedなら配信せず現行serviceを維持し、原因を解消してCIから全gateを再実行する。'),
                                                   ('rolling-back',
                                                    'rollback実行',
                                                    '検証済みの直前artifactへ戻し、command成功だけを復旧とは扱わない。'),
                                                   ('restoration-verified',
                                                    'service restoration再観測',
                                                    'rollback後の利用者可視error rate、health、artifact digestを再観測して復旧を確認する。'),
                                                   ('outcome', 'Outcome', 'command完了後にservice restorationを再観測する。')),
                                        'initialStateId': 'ci',
                                        'transitions': (('checks-known-pass',
                                                         'ci',
                                                         'artifact',
                                                         'next',
                                                         'allowed',
                                                         None),
                                                        ('checks-missing-unknown-stop',
                                                         'ci',
                                                         'stopped',
                                                         'reset',
                                                         'allowed',
                                                         None),
                                                        ('artifact-to-provenance',
                                                         'artifact',
                                                         'provenance',
                                                         'next',
                                                         'allowed',
                                                         None),
                                                        ('provenance-to-canary',
                                                         'provenance',
                                                         'canary',
                                                         'next',
                                                         'allowed',
                                                         None),
                                                        ('canary-to-decision',
                                                         'canary',
                                                         'decision',
                                                         'next',
                                                         'allowed',
                                                         None),
                                                        ('threshold-within-promote',
                                                         'decision',
                                                         'promoted',
                                                         'next',
                                                         'allowed',
                                                         None),
                                                        ('threshold-exceeded-rollback',
                                                         'decision',
                                                         'rolling-back',
                                                         'previous',
                                                         'allowed',
                                                         None),
                                                        ('promote-outcome',
                                                         'promoted',
                                                         'outcome',
                                                         'next',
                                                         'allowed',
                                                         None),
                                                        ('stop-cause-resolved-rerun',
                                                         'stopped',
                                                         'ci',
                                                         'reset',
                                                         'allowed',
                                                         None),
                                                        ('rollback-restoration',
                                                         'rolling-back',
                                                         'restoration-verified',
                                                         'next',
                                                         'allowed',
                                                         None),
                                                        ('restoration-outcome',
                                                         'restoration-verified',
                                                         'outcome',
                                                         'next',
                                                         'allowed',
                                                         None),
                                                        ('checks-not-passed',
                                                         'ci',
                                                         'artifact',
                                                         'timer',
                                                         'rejected',
                                                         'required '
                                                         'checkがmissing、unknown、failedの時はartifact確定へ進まずstopする。'),
                                                        ('digest-mismatch',
                                                         'artifact',
                                                         'provenance',
                                                         'timer',
                                                         'rejected',
                                                         'subject digestが配信対象bytesと一致しない時はprovenanceを受理しない。'),
                                                        ('builder-mismatch',
                                                         'provenance',
                                                         'canary',
                                                         'timer',
                                                         'rejected',
                                                         'trusted builderと一致しないprovenanceではcanaryへ進まない。'),
                                                        ('skip-decision',
                                                         'canary',
                                                         'outcome',
                                                         'next',
                                                         'rejected',
                                                         'canary thresholdからpromoteまたはrollbackを決める前にoutcomeへ進まない。'))},
 'core-26-code-review-collaborative-quality': {'common': ('collaborative-review-loop',
                                                          'state-loop',
                                                          'mentalModel',
                                                          None,
                                                          'sample changeから共同で品質を改善し独立再評価するreview loop',
                                                          'author fix後に別reviewerがどのprobeを再実行し、blocking '
                                                          'findingの解消を判断するか。',
                                                          'riskとfinding IDからpatchを追跡し、feedback '
                                                          'cycleを保ちながら独立再評価の証拠をterminalへ確定できる。',
                                                          ('obj-review-priority',
                                                           'obj-author-enablement',
                                                           'obj-independent-review'),
                                                          ('review-cycle',),
                                                          ('src-01', 'src-02', 'src-04'),
                                                          ()),
                                               'states': (('scope', 'Scope', 'changeとrisk kind、review budgetを固定する。'),
                                                          ('initial-review',
                                                           'Initial review',
                                                           'priority、evidence、actionable fixを同じ入力から導く。'),
                                                          ('author-fix',
                                                           'Author fix',
                                                           '指摘IDに対応するpatchをactual artifactへ適用し、patch IDを残す。'),
                                                          ('independent-review',
                                                           'Independent re-evaluation',
                                                           '初回とは別のreviewerがprobeを再実行し、actualとexpectedからblocking '
                                                           'findingとsystem outcomeを確認する。'),
                                                          ('enablement',
                                                           'Enablement',
                                                           '判断根拠を残し、他のcontributorが再利用できるようにする。'),
                                                          ('evidence-ready',
                                                           'Review evidence ready',
                                                           '別reviewerのprobe、blocking finding解消、system '
                                                           'outcome、再利用可能な判断根拠を一つの完了証拠として確定する。')),
                                               'entryStateId': 'scope',
                                               'exitStateId': 'evidence-ready',
                                               'recoveryStateId': 'author-fix',
                                               'transitions': (('scope-to-initial-review',
                                                                'scope',
                                                                'initial-review',
                                                                '次の証拠を得る',
                                                                None),
                                                               ('initial-review-to-author-fix',
                                                                'initial-review',
                                                                'author-fix',
                                                                '次の証拠を得る',
                                                                None),
                                                               ('author-fix-to-independent-review',
                                                                'author-fix',
                                                                'independent-review',
                                                                '次の証拠を得る',
                                                                None),
                                                               ('independent-review-to-enablement',
                                                                'independent-review',
                                                                'enablement',
                                                                '次の証拠を得る',
                                                                None),
                                                               ('independent-feedback',
                                                                'independent-review',
                                                                'author-fix',
                                                                'blocking findingが残れば再修正する',
                                                                None),
                                                               ('enablement-feedback',
                                                                'enablement',
                                                                'scope',
                                                                '次のchangeでriskを再評価する',
                                                                None),
                                                               ('enablement-to-evidence-ready',
                                                                'enablement',
                                                                'evidence-ready',
                                                                '独立再評価とsystem outcomeの証拠を確定する',
                                                                None)),
                                               'feedbackTransitionIds': ('independent-feedback',
                                                                         'enablement-feedback')},
 'core-29-cross-cultural-async-collaboration': {'common': ('async-review-timeline',
                                                           'timeline',
                                                           'mentalModel',
                                                           None,
                                                           'proposal contextからreasoned decisionへ進む非同期review chain',
                                                           'timezone overlapがなくてもdissentと採否理由を第三者が再評価できる記録は何か。',
                                                           'decision rights、evidence、参加条件、response '
                                                           'window、異論への応答を再生可能なdecision logへ結べる。',
                                                           ('obj-async-context', 'obj-dissent', 'obj-zero-overlap'),
                                                           ('async-rfc', 'decision-log'),
                                                           ('src-01', 'src-02', 'src-03'),
                                                           ()),
                                                'phases': (('context', '文脈', '判断範囲、代替案、参加条件を文書へ揃える。'),
                                                           ('review', 'レビュー', '安全なresponse windowで異論と応答を追跡する。'),
                                                           ('decision-phase', '決定', '第三者がmeetingなしで再評価できる形にする。')),
                                                'events': (('frame',
                                                            'Frame',
                                                            'problem、decision rights、対象外を固定する。',
                                                            'context',
                                                            0,
                                                            None),
                                                           ('expose',
                                                            'Expose',
                                                            'alternatives、evidence、uncertaintyを同じ文書に置く。',
                                                            'context',
                                                            1,
                                                            None),
                                                           ('include',
                                                            'Include',
                                                            'timezone、working language、用語、UTC期限を示す。',
                                                            'context',
                                                            2,
                                                            None),
                                                           ('invite',
                                                            'Invite',
                                                            'dissentを安全に記録するresponse-windowを開く。',
                                                            'review',
                                                            3,
                                                            None),
                                                           ('resolve',
                                                            'Resolve',
                                                            '異論ごとのresponseと採否理由を残す。',
                                                            'review',
                                                            4,
                                                            None),
                                                           ('replay',
                                                            'Replay',
                                                            'meeting unnecessaryな状態で第三者が判断を再評価する。',
                                                            'decision-phase',
                                                            5,
                                                            None))}}
TASK6_LESSON_JUDGMENT_TEXT = {
    "core-04-os-processes-concurrency": (
        "説明用のx=10で、Thread A/Bのどのinterleavingがlost updateを起こし、mutex後に何が変わるか。",
        "両threadがx=10を読む最小trace、期待値x=8に対する違反点、mutex後のx=8を順に説明できる。",
    ),
    "core-05-networks-latency-failure": (
        "説明用の総deadline 300msで、どのeventが最初の超過点となり、残りbudgetはどう変化したか。",
        "各eventのbudgetと累積observedを追い、first-byteの310msを最初の超過点として説明できる。これは普遍的なlatency値ではない。",
    ),
    "core-07-api-contract-design": (
        "response喪失後のretryで、どの保存済み副作用を再利用し、何を再実行してはいけないか。",
        "冪等keyのscope、耐久化済み効果、試行ごとに変わるresponseを分け、安全なretryと拒否遷移を説明できる。",
    ),
    "core-09-test-strategy-tdd": (
        "GREEN後のmutationでtestが誤りを検出しなかった時、どの期待へ戻るか。",
        "risk、RED、GREEN、refactor、mutationを循環させ、生存mutantから期待を改善して証拠成立へ到達できる。",
    ),
    "core-12-transactions-isolation-consistency": (
        "同じsnapshotを読んだT1とT2のwrite skewを、どの依存検証とretryが防ぐか。",
        "業務不変条件、並行read、局所判断、Serializableのabort、transaction全体の再読込を順に説明できる。",
    ),
    "core-13-distributed-coordination-failure": (
        "response lossと再配送があっても副作用を一度だけ進めるdedupeの耐久境界はどこか。",
        "stable keyとfingerprintの照合、stateとresultのatomic commit、partition回復後の再評価を説明できる。",
    ),
    "core-15-reliability-observability-slo": (
        "どのSLIとburn evidenceがpageを起動し、mitigation後の何を確認してloopを終了するか。",
        "JourneyからSLI・SLO・telemetry・alert・runbookへ進み、復旧証拠が揃ったterminal stateを示せる。",
    ),
    "core-22-evolution-safe-migrations": (
        "dual write、backfill、dual readの各phaseで互換性gateが失敗した時、どの安全状態へ戻すか。",
        "phase別の停止・rollback先、旧reader互換性、復旧観測、contractへの拒否条件を説明できる。",
    ),
    "core-23-incident-response-learning": (
        "incident当時利用可能だったevidenceから、検知遅延のimpactとdecisionをどう再構成するか。",
        "clockを揃えたtimeline、影響計算、当時の判断、system factor、検証可能なactionを追跡できる。",
    ),
    "core-24-delivery-ci-release-safety": (
        "required check不足でstopした後、原因解消から全gateを再実行し、canaryでpromoteとrollbackのどちらを選ぶか。",
        "stopを未配信の安全な中断としてCIへ戻し、promoteまたはrollback復旧だけを完了outcomeへ結べる。",
    ),
    "core-26-code-review-collaborative-quality": (
        "author fix後に別reviewerがどのprobeを再実行し、blocking findingの解消を判断するか。",
        "riskとfinding IDからpatchを追跡し、feedback cycleを保ちながら独立再評価の証拠をterminalへ確定できる。",
    ),
    "core-29-cross-cultural-async-collaboration": (
        "timezone overlapがなくてもdissentと採否理由を第三者が再評価できる記録は何か。",
        "decision rights、evidence、参加条件、response window、異論への応答を再生可能なdecision logへ結べる。",
    ),
}
TASK5_READING_ORDER_MARKER = "この注記は旧図の読み順を保持する補助です。"
TASK5_VISUAL_IDENTITIES = {
    "core-01-systems-tradeoffs": "decision-causal-loop",
    "core-06-requirements-domain-modeling": "domain-model-network",
    "core-08-modularity-evolutionary-architecture": "module-dependency-network",
    "core-10-threat-modeling-secure-design": "threat-trace-network",
    "core-14-performance-capacity": "capacity-causal-cycle",
    "core-18-product-discovery-experiments": "experiment-decision-causal",
    "core-20-ethics-privacy-societal-impact": "impact-causal-chain",
    "core-21-maintenance-legacy-comprehension": "legacy-comprehension-network",
    "core-27-team-interfaces-sociotechnical-architecture": "team-interface-network",
    "core-30-evidence-based-technical-leadership": "leadership-decision-causal",
}
TASK5_COMPANION_NOTES = {
    "core-01-systems-tradeoffs": (
        "目的: 利用者が二秒以内に受付結果を知る。",
        "境界: Web、受付API、永続ストア、worker、通知を含め、決済事業者は外部契約とする。",
        "制約: 重複確定は0件、受付データ損失は0件、運用当番は一名。",
        "代替案: 同期完了、永続化後に非同期実行、負荷時だけ非同期化を比較する。",
        "観測: p95受付時間、成果完了時間、重複率、最古滞留時間、復旧時間を測る。",
        "反証: 観測が閾値を越えたら、境界または選択案を見直す。",
    ),
    "core-06-requirements-domain-modeling": (
        "発言: 利害関係者の目的、困り事、制約を発言者と状況付きで記録する。",
        "用語: 語ごとに定義、具体例、反例、所有する文脈を置く。",
        "境界: 同じ語と不変条件が一貫する範囲を決め、境界間の翻訳を示す。",
        "振る舞い: 意図をコマンド、起きた事実をイベント、許される状態変化を不変条件で表す。",
        "例外: 時間切れ、在庫不足、権限不足、外部決済失敗を通常経路と同じ粒度で置く。",
        "検証: 要求から観測までを追跡し、空欄と矛盾を次の質問へ戻す。",
    ),
    "core-08-modularity-evolutionary-architecture": (
        "pricing-domain: 料金規則と不変条件。UIやDB形式を知らない。",
        "pricing-application: use caseを順序付け、domainのportを使う。",
        "pricing-adapters: HTTP、DB、batch形式をdomainの語彙へ変換する。",
        "reporting: 料金計算の変更対象外となる独立module。impact計算のfalse positiveを検出する基準にする。",
        "source dependencyはadaptersからapplication、applicationからdomainへ向ける。",
        "運用viewでは逆向きのrequest flowを別の矢印として記述し、意味を混ぜない。",
    ),
    "core-10-threat-modeling-secure-design": (
        "asset: customer data、deployment credential、audit logの価値と安全性目標を定義する。",
        "actorとboundary: external customer、operations contractor、platform adminをID・type・scopeを持つentityとして定義し、flowの起点と越境点へ参照させる。",
        "threat: 意図ではなく、credential再利用、誤ったbulk export、audit停止など観測可能な行為で表す。",
        "control: prevent、detect、recoverを型として区別し、各threatへ三種類すべてを重ねる。",
        "verification: 具体的なtest ID、control ID、resultをthreatへ接続する。",
        "residual risk: threat ID、decision、uncertainty、owner、期限を付け、未解決を隠さない。",
    ),
    "core-14-performance-capacity": (
        "Fixture: request mix、payload、依存、処理上限、環境を固定する。",
        "Curve: 低負荷、限界付近、超過、回復を同じ列で記録する。",
        "Diagnose: plateau、tail、error、queue、resource、downstreamを結ぶ。",
        "Profile: 仮説に合う実processの局所証拠を別に採取する。",
        "Capacity: observed kneeからheadroomを引き、再測定条件を残す。",
    ),
    "core-18-product-discovery-experiments": (
        "Problem: 利用者の行動と制約を観察し、solutionから独立した問題を記述する。",
        "Hypothesis: 介入、success metricの期待差、反証条件を宣言する。",
        "Plan: primary metric、guardrail、stop condition、always-valid解析を観測前に固定する。",
        "Simulate: controlとtreatmentの固定集計からrateと差分を導出する。",
        "Decide: successとguardrailを同時評価し、continue、stop、learnを記録する。",
    ),
    "core-20-ethics-privacy-societal-impact": (
        "People: 利益、害、権力、退出可能性が異なる集団を列挙する。",
        "Lifecycle: collect、use、share、retain、deleteの目的とownerを追う。",
        "Harm: privacy、security、accessibility、人権、労働への害を具体化する。",
        "Inherent risk: likelihood、severity、exposureを軽減前に評価する。",
        "Mitigation: 回避、最小化、検知、救済、退出を設計する。",
        "Residual risk: 残る害、uneven harm、owner、期限、停止条件を記録する。",
    ),
    "core-21-maintenance-legacy-comprehension": (
        "Reason: 誰のどの結果を変える要求かを一文で固定する。",
        "Trace: entry pointから実際のexecution pathを入力付きで追う。",
        "Map: component、data、side effect、ownerを経路へ結ぶ。",
        "Unknown: 未観測、未所有、仕様不明を仮説から分離する。",
        "Characterize: 現在のexpected、actual、observed pathをtestへ残す。",
        "Decide: 証拠が足りなければ編集せず調査または停止を選ぶ。",
    ),
    "core-27-team-interfaces-sociotechnical-architecture": (
        "Ownership: checkout teamがcheckout capabilityのdecision rightを持つ。",
        "Dependency: checkoutはplatform capabilityへ依存する。",
        "Cognitive load: assigned領域をcapacityと比較し、過負荷を個人努力へ隠さない。",
        "SLO: dependency latencyのtargetとobservedを同じ単位で評価する。",
        "Enablement: 各interface snapshotから判断を再計算し、healthyならmonitor、breachedならescalateとしてcheckoutの自律判断を増やす。",
    ),
    "core-30-evidence-based-technical-leadership": (
        "Frame: system outcome、非目標、decision rightsを合意する。",
        "Measure: five metrics、risk、cost、利用者影響を別々に観測する。",
        "Challenge: uncertaintyとdissentから反証条件を作る。",
        "Order: 制約を守るoptionを投資順へ置く。",
        "Act: reversible first stepだけにtimeboxしたbudgetを与える。",
        "Review: withdrawal conditionsでstop、adapt、expandを判断する。",
    ),
}
TASK5_VISUAL_CONTRACTS = {
    "core-01-systems-tradeoffs": {
        "trace": (
            ("obj-boundary", "obj-falsification"),
            ("assessment",),
            ("src-01", "src-03"),
        ),
        "structure": {
            "causes": (("constraints", "制約"),),
            "mechanisms": (("boundary", "境界"), ("alternatives", "代替案")),
            "outcomes": (("purpose", "目的"), ("observations", "観測")),
            "mitigations": (("falsification", "反証"),),
        },
        "relations": (
            ("constraints-bound-boundary", "constraints", "boundary", "制約を守る評価境界を定める"),
            ("boundary-shapes-options", "boundary", "alternatives", "境界内で成立する選択肢を比較する"),
            ("options-seek-purpose", "alternatives", "purpose", "選択肢を利用者目的に照合する"),
            ("options-produce-signals", "alternatives", "observations", "選択の結果を測定する"),
            ("signals-trigger-review", "observations", "falsification", "閾値超過で境界または選択案を見直す"),
        ),
    },
    "core-06-requirements-domain-modeling": {
        "trace": (
            ("obj-language", "obj-boundary"),
            ("domain-model",),
            ("src-01", "src-03"),
        ),
        "components": (("requirements-model", "要求とドメインモデル"),),
        "nodes": (
            ("statement", "発言", "requirements-model"),
            ("language", "用語", "requirements-model"),
            ("boundary", "境界", "requirements-model"),
            ("behavior", "振る舞い", "requirements-model"),
            ("exceptions", "例外", "requirements-model"),
            ("verification", "検証", "requirements-model"),
        ),
        "relations": (
            ("statement-defines-language", "statement", "language", "例と反例で語を定義する"),
            ("language-locates-boundary", "language", "boundary", "用語の一貫する範囲を決める"),
            ("boundary-owns-behavior", "boundary", "behavior", "状態変化の責任を置く"),
            ("behavior-exposes-exceptions", "behavior", "exceptions", "通常経路と失敗経路を揃える"),
            ("exceptions-drive-verification", "exceptions", "verification", "観測と確認質問へ接続する"),
        ),
    },
    "core-08-modularity-evolutionary-architecture": {
        "trace": (
            ("obj-boundary", "obj-direction"),
            ("module-adr",),
            ("src-01", "src-02"),
        ),
        "components": (
            ("source-dependency-view", "source dependency view"),
            ("runtime-request-flow-view", "runtime request flow view"),
            ("independent-reporting", "変更対象外のreporting境界"),
        ),
        "nodes": (
            ("source-domain", "pricing-domain", "source-dependency-view"),
            ("source-application", "pricing-application", "source-dependency-view"),
            ("source-adapters", "pricing-adapters", "source-dependency-view"),
            ("runtime-domain", "pricing-domain", "runtime-request-flow-view"),
            ("runtime-application", "pricing-application", "runtime-request-flow-view"),
            ("runtime-adapters", "pricing-adapters", "runtime-request-flow-view"),
            ("reporting", "reporting", "independent-reporting"),
        ),
        "relations": (
            ("source-adapters-to-application", "source-adapters", "source-application", "source dependency: adaptersからapplicationへ向ける"),
            ("source-application-to-domain", "source-application", "source-domain", "source dependency: applicationからdomain portへ向ける"),
            ("runtime-domain-to-application", "runtime-domain", "runtime-application", "runtime request flow: domain portからapplicationへ戻る"),
            ("runtime-application-to-adapters", "runtime-application", "runtime-adapters", "runtime request flow: applicationからadapter実装を呼ぶ"),
        ),
    },
    "core-10-threat-modeling-secure-design": {
        "trace": (
            ("obj-model", "obj-control"),
            ("threat-model",),
            ("src-01", "src-04"),
        ),
        "components": (("threat-trace", "threat trace"),),
        "nodes": (
            ("asset", "asset", "threat-trace"),
            ("actor-boundary", "actorとboundary", "threat-trace"),
            ("threat", "threat", "threat-trace"),
            ("control", "control", "threat-trace"),
            ("verification", "verification", "threat-trace"),
            ("residual-risk", "residual risk", "threat-trace"),
        ),
        "relations": (
            ("asset-crosses-boundary", "asset", "actor-boundary", "価値ある対象と越境点を対応付ける"),
            ("boundary-exposes-threat", "actor-boundary", "threat", "actorの行為として脅威を具体化する"),
            ("threat-covered-by-control", "threat", "control", "予防・検知・回復を重ねる"),
            ("control-tested-by-verification", "control", "verification", "test結果で有効性を確かめる"),
            ("verification-informs-risk", "verification", "residual-risk", "未解決riskの判断根拠にする"),
        ),
    },
    "core-14-performance-capacity": {
        "trace": (
            ("obj-load-curve", "obj-profile"),
            ("performance-report",),
            ("src-01", "src-02", "src-03"),
        ),
        "structure": {
            "causes": (("fixture", "Fixture（負荷条件）"),),
            "mechanisms": (("bottleneck-mechanism", "Bottleneck mechanism"),),
            "outcomes": (("curve", "Curve"), ("profile", "Profile")),
            "mitigations": (("capacity", "Capacity"),),
        },
        "relations": (
            ("fixture-exposes-mechanism", "fixture", "bottleneck-mechanism", "固定条件でresource、queue、downstreamの飽和を起こす"),
            ("mechanism-shapes-curve", "bottleneck-mechanism", "curve", "plateau、tail、error、queueとして現れる"),
            ("mechanism-guides-profile", "bottleneck-mechanism", "profile", "仮説に合う局所証拠を採る"),
            ("curve-bounds-capacity", "curve", "capacity", "observed kneeからheadroomを引く"),
            ("profile-bounds-capacity", "profile", "capacity", "局所証拠を再測定条件へ反映する"),
        ),
    },
    "core-18-product-discovery-experiments": {
        "trace": (
            ("obj-falsifiable-hypothesis", "obj-analysis-plan"),
            ("experiment-plan",),
            ("src-02", "src-04"),
        ),
        "structure": {
            "causes": (("problem", "Problem"),),
            "mechanisms": (("hypothesis", "Hypothesis"), ("plan", "Plan"), ("simulate", "Simulate")),
            "outcomes": (("decide", "Decide"),),
            "mitigations": (("guardrail-response", "Guardrail response"),),
        },
        "relations": (
            ("problem-forms-hypothesis", "problem", "hypothesis", "問題から反証可能な介入を定める"),
            ("hypothesis-fixes-plan", "hypothesis", "plan", "観測前に評価契約を固定する"),
            ("plan-governs-simulation", "plan", "simulate", "固定集計からrateと差分を計算する"),
            ("simulation-informs-decision", "simulate", "decide", "successとguardrailを同時評価する"),
            ("decision-triggers-response", "decide", "guardrail-response", "stopまたはlearnで追加被害を抑える"),
        ),
    },
    "core-20-ethics-privacy-societal-impact": {
        "trace": (
            ("obj-impact", "obj-residual"),
            ("assessment",),
            ("src-01", "src-02", "src-04"),
        ),
        "structure": {
            "causes": (("lifecycle", "Lifecycle"),),
            "mechanisms": (("exposure-mechanism", "Exposure mechanism"),),
            "outcomes": (("harm", "Harm"), ("residual-risk", "Residual risk")),
            "mitigations": (("mitigation", "Mitigation"),),
        },
        "relations": (
            ("lifecycle-creates-exposure", "lifecycle", "exposure-mechanism", "collect、use、share、retainが人とdataを害へ曝露する"),
            ("exposure-produces-harm", "exposure-mechanism", "harm", "権力差と退出困難を通じ具体的な害として現れる"),
            ("harm-leaves-residual", "harm", "residual-risk", "軽減後も残る害を明示する"),
            ("mitigation-reduces-residual", "mitigation", "residual-risk", "回避、最小化、検知、救済、退出で低減する"),
        ),
    },
    "core-21-maintenance-legacy-comprehension": {
        "trace": (
            ("obj-comprehension", "obj-characterization"),
            ("system-map",),
            ("src-01", "src-02"),
        ),
        "components": (("change-evidence", "変更前証拠"),),
        "nodes": (
            ("reason", "Reason", "change-evidence"),
            ("trace", "Trace", "change-evidence"),
            ("map", "Map", "change-evidence"),
            ("unknown", "Unknown", "change-evidence"),
            ("characterize", "Characterize", "change-evidence"),
            ("decide", "Decide", "change-evidence"),
        ),
        "relations": (
            ("reason-selects-trace", "reason", "trace", "変更対象の実行経路を選ぶ"),
            ("trace-builds-map", "trace", "map", "観測したcomponentと副作用を結ぶ"),
            ("map-exposes-unknown", "map", "unknown", "未観測と仮説を分離する"),
            ("unknown-bounds-characterization", "unknown", "characterize", "現行挙動をtestへ固定する"),
            ("characterization-gates-decision", "characterize", "decide", "証拠量で編集開始を判断する"),
        ),
    },
    "core-27-team-interfaces-sociotechnical-architecture": {
        "trace": (
            ("obj-team-interface", "obj-cognitive-load"),
            ("team-interface",),
            ("src-01", "src-02", "src-03"),
        ),
        "components": (("delivery-interface", "delivery interface"),),
        "nodes": (
            ("ownership", "Ownership", "delivery-interface"),
            ("dependency", "Dependency", "delivery-interface"),
            ("cognitive-load", "Cognitive load", "delivery-interface"),
            ("slo", "SLO", "delivery-interface"),
            ("enablement", "Enablement", "delivery-interface"),
        ),
        "relations": (
            ("ownership-declares-dependency", "ownership", "dependency", "checkout capabilityのdecision rightとplatform依存を分ける"),
            ("ownership-bounds-cognitive-load", "ownership", "cognitive-load", "assigned領域をcapacityと比較する"),
            ("dependency-defines-slo", "dependency", "slo", "dependency latencyのtargetとobservedを比較する"),
            ("cognitive-load-guides-enablement", "cognitive-load", "enablement", "capacity内かをenablement判断へ渡す"),
            ("slo-guides-enablement", "slo", "enablement", "dependency SLO statusをenablement判断へ渡す"),
        ),
    },
    "core-30-evidence-based-technical-leadership": {
        "trace": (
            ("obj-strategy-evidence", "obj-reversible-leadership"),
            ("technical-strategy",),
            ("src-01", "src-02", "src-03", "src-04"),
        ),
        "structure": {
            "causes": (("frame", "Frame"),),
            "mechanisms": (("measure", "Measure"), ("challenge", "Challenge"), ("order", "Order"), ("act", "Act")),
            "outcomes": (("review", "Review"),),
            "mitigations": (("withdrawal-conditions", "Withdrawal conditions"),),
        },
        "relations": (
            ("frame-selects-measures", "frame", "measure", "outcomeに必要な証拠を分ける"),
            ("measures-enable-challenge", "measure", "challenge", "不確実性とdissentで反証する"),
            ("challenge-orders-options", "challenge", "order", "制約を守る投資順を作る"),
            ("order-bounds-action", "order", "act", "可逆なfirst stepだけを実行する"),
            ("action-enters-review", "act", "review", "観測結果からstop、adapt、expandを判断する"),
            ("withdrawal-guides-review", "withdrawal-conditions", "review", "撤退条件で害と埋没費用を抑える"),
        ),
    },
}
TASK5_COMMON_TEXT = {
    "core-01-systems-tradeoffs": ("判断を更新可能にする因果ループ", "目的と制約から、どの観測が判断の再評価を起動するか。", "境界と制約を起点に、代替案、観測、反証条件までの因果経路を指し示せる。"),
    "core-06-requirements-domain-modeling": ("発言を検証可能なドメインモデルへ変換する循環", "利害関係者の発言は、どの境界と関係を経て検証可能になるか。", "発言から用語、境界、振る舞い、例外、検証までの接続と、次の確認質問が生まれる位置を説明できる。"),
    "core-08-modularity-evolutionary-architecture": ("変更理由を内側へ隠蔽する三層の依存graph", "変更理由を守る source dependency と運用時の request flow をどう区別するか。", "source dependencyはadapterからdomainへ、runtime request flowはdomain portからadapter実装へ進む逆向きのviewとして区別し、独立したreporting境界も指し示せる。"),
    "core-10-threat-modeling-secure-design": ("assetから攻撃経路、control、verification、残余riskを結ぶtrace", "各 threat をどの control、verification、残余 risk の判断まで追跡できるか。", "assetと境界から観測可能なthreatをたどり、予防・検知・回復、test結果、残余riskの所有者まで説明できる。"),
    "core-14-performance-capacity": ("負荷を証拠へ変えて安全容量を更新する循環", "固定した負荷条件から、どの証拠を経て安全容量を決めるか。", "負荷曲線のknee、tail、queue、局所profileを結び、headroomを引いた容量と再測定条件を示せる。"),
    "core-18-product-discovery-experiments": ("問題発見から事前固定した停止判断までの因果flow", "観測後に基準を変えず、どの条件で継続または停止を判断するか。", "問題、反証可能な仮説、事前固定した解析、固定集計、guardrailを含む判断を順に説明できる。"),
    "core-20-ethics-privacy-societal-impact": ("affected peopleから残余riskの意思決定へ至るimpact chain", "誰にどの害が残り、誰がどの条件で停止を判断するか。", "affected peopleとdata lifecycleから害を具体化し、軽減前risk、軽減策、unevenな残余riskまで追跡できる。"),
    "core-21-maintenance-legacy-comprehension": ("change requestから変更前証拠を作るlegacy comprehension loop", "編集前に、要求からexecution pathと未知領域をどこまで証拠化できているか。", "change requestから実行経路、component、side effect、未知領域、characterization test、停止判断までを指し示せる。"),
    "core-27-team-interfaces-sociotechnical-architecture": ("team ownershipからdependency SLOとcontributor enablementへ至る社会技術interface", "ownershipとdependencyの設計は、認知負荷とdelivery SLOへどう現れるか。", "checkoutとplatformの依存を、decision right、認知負荷、dependency latency、enablement判断まで結んで説明できる。"),
    "core-30-evidence-based-technical-leadership": ("多面的evidenceから可逆な投資と撤退判断へ進むleadership loop", "対立する指標と不確実性を、どの撤退条件を持つ投資判断へ変えるか。", "system outcome、複数metric、反証条件、投資順、可逆なfirst step、withdrawal conditionを一つの判断経路として説明できる。"),
}
TASK5_ITEM_DETAILS = {
    "core-01-systems-tradeoffs": {"constraints": "重複確定は0件、受付データ損失は0件、運用当番は一名。", "boundary": "Web、受付API、永続ストア、worker、通知を含め、決済事業者は外部契約とする。", "alternatives": "同期完了、永続化後に非同期実行、負荷時だけ非同期化を比較する。", "purpose": "利用者が二秒以内に受付結果を知る。", "observations": "p95受付時間、成果完了時間、重複率、最古滞留時間、復旧時間を測る。", "falsification": "観測が閾値を越えたら、境界または選択案を見直す。"},
    "core-06-requirements-domain-modeling": {"requirements-model": "発言を追跡可能なモデルと観測へ接続する範囲。", "statement": "利害関係者の目的、困り事、制約を発言者と状況付きで記録する。", "language": "語ごとに定義、具体例、反例、所有する文脈を置く。", "boundary": "同じ語と不変条件が一貫する範囲を決め、境界間の翻訳を示す。", "behavior": "意図をコマンド、起きた事実をイベント、許される状態変化を不変条件で表す。", "exceptions": "時間切れ、在庫不足、権限不足、外部決済失敗を通常経路と同じ粒度で置く。", "verification": "要求から観測までを追跡し、空欄と矛盾を次の質問へ戻す。"},
    "core-08-modularity-evolutionary-architecture": {"source-dependency-view": "source dependencyはadaptersからapplication、applicationからdomainへ向ける。", "runtime-request-flow-view": "運用viewでは逆向きのrequest flowを別の矢印として記述し、意味を混ぜない。", "independent-reporting": "pricingの依存graphから隔離し、impact計算のfalse positiveを検出する基準にする。", "source-domain": "料金規則と不変条件。UIやDB形式を知らない。", "source-application": "use caseを順序付け、domainのportを使う。", "source-adapters": "HTTP、DB、batch形式をdomainの語彙へ変換する。", "runtime-domain": "runtime viewでdomain portから外側の実装を呼び出す起点。", "runtime-application": "runtime viewでuse caseとdomain portの呼出しを中継する。", "runtime-adapters": "runtime viewでHTTP、DB、batchのadapter実装を実行する。", "reporting": "料金計算の変更対象外となる独立module。impact計算のfalse positiveを検出する基準にする。"},
    "core-10-threat-modeling-secure-design": {"threat-trace": "資産から残余riskの意思決定までをIDで追跡する安全設計モデル。", "asset": "customer data、deployment credential、audit logの価値と安全性目標を定義する。", "actor-boundary": "external customer、operations contractor、platform adminをID・type・scopeを持つentityとして定義し、flowの起点と越境点へ参照させる。", "threat": "意図ではなく、credential再利用、誤ったbulk export、audit停止など観測可能な行為で表す。", "control": "prevent、detect、recoverを型として区別し、各threatへ三種類すべてを重ねる。", "verification": "具体的なtest ID、control ID、resultをthreatへ接続する。", "residual-risk": "threat ID、decision、uncertainty、owner、期限を付け、未解決を隠さない。"},
    "core-14-performance-capacity": {"fixture": "request mix、payload、依存、処理上限、環境を固定する。", "bottleneck-mechanism": "resource上限、queue蓄積、downstream待機が処理率を制限し、tail latencyとerrorを増幅する。", "curve": "低負荷、限界付近、超過、回復を同じ列で記録する。", "profile": "仮説に合う実processの局所証拠を別に採取する。", "capacity": "observed kneeからheadroomを引き、再測定条件を残す。"},
    "core-18-product-discovery-experiments": {"problem": "利用者の行動と制約を観察し、solutionから独立した問題を記述する。", "hypothesis": "介入、success metricの期待差、反証条件を宣言する。", "plan": "primary metric、guardrail、stop condition、always-valid解析を観測前に固定する。", "simulate": "controlとtreatmentの固定集計からrateと差分を導出する。", "decide": "successとguardrailを同時評価し、continue、stop、learnを記録する。", "guardrail-response": "停止条件に達したらstopまたはlearnを選び、追加被害と無駄な投資を抑える。"},
    "core-20-ethics-privacy-societal-impact": {"lifecycle": "collect、use、share、retain、deleteの目的とownerを追う。", "exposure-mechanism": "収集、利用、共有、保持が、権力差や退出困難を通じて人とdataを害へ曝露する。", "harm": "privacy、security、accessibility、人権、労働への害を具体化する。", "residual-risk": "残る害、uneven harm、owner、期限、停止条件を記録する。", "mitigation": "回避、最小化、検知、救済、退出を設計する。"},
    "core-21-maintenance-legacy-comprehension": {"change-evidence": "編集せずに要求と現行挙動を結ぶcomprehension範囲。", "reason": "誰のどの結果を変える要求かを一文で固定する。", "trace": "entry pointから実際のexecution pathを入力付きで追う。", "map": "component、data、side effect、ownerを経路へ結ぶ。", "unknown": "未観測、未所有、仕様不明を仮説から分離する。", "characterize": "現在のexpected、actual、observed pathをtestへ残す。", "decide": "証拠が足りなければ編集せず調査または停止を選ぶ。"},
    "core-27-team-interfaces-sociotechnical-architecture": {"delivery-interface": "team境界とsoftware dependencyを同じsnapshotで評価する社会技術範囲。", "ownership": "checkout teamがcheckout capabilityのdecision rightを持つ。", "dependency": "checkoutはplatform capabilityへ依存する。", "cognitive-load": "assigned領域をcapacityと比較し、過負荷を個人努力へ隠さない。", "slo": "dependency latencyのtargetとobservedを同じ単位で評価する。", "enablement": "各interface snapshotから判断を再計算し、healthyならmonitor、breachedならescalateとしてcheckoutの自律判断を増やす。"},
    "core-30-evidence-based-technical-leadership": {"frame": "system outcome、非目標、decision rightsを合意する。", "measure": "five metrics、risk、cost、利用者影響を別々に観測する。", "challenge": "uncertaintyとdissentから反証条件を作る。", "order": "制約を守るoptionを投資順へ置く。", "act": "reversible first stepだけにtimeboxしたbudgetを与える。", "review": "withdrawal conditionsでstop、adapt、expandを判断する。", "withdrawal-conditions": "害や埋没費用が増える前にstop、adapt、expandを判断する境界を固定する。"},
}


def _complete_task5_contracts() -> None:
    """Expand hand-authored Task 5 facts into the exact projection shape."""
    for lesson_id, contract in TASK5_VISUAL_CONTRACTS.items():
        objective_ids, evidence_ids, source_ids = contract["trace"]
        contract["common"] = (
            TASK5_VISUAL_IDENTITIES[lesson_id],
            TASK5_VISUAL_TYPES[lesson_id],
            "mentalModel",
            *TASK5_COMMON_TEXT[lesson_id],
            objective_ids,
            evidence_ids,
            source_ids,
            (TASK5_READING_ORDER_MARKER, *TASK5_COMPANION_NOTES[lesson_id]),
            None,
        )
        details = TASK5_ITEM_DETAILS[lesson_id]
        if "structure" in contract:
            contract["structure"] = {
                group: tuple((*item, details[item[0]]) for item in items)
                for group, items in contract["structure"].items()
            }
        else:
            contract["components"] = tuple(
                (*item, details[item[0]], "component")
                for item in contract["components"]
            )
            contract["nodes"] = tuple(
                (item[0], item[1], details[item[0]], "node", item[2])
                for item in contract["nodes"]
            )


_complete_task5_contracts()
CAPSTONE_IDS = ("global-service", "legacy-evolution", "oss-launch")
CATALOG_SHA256 = (
    "4f38b5f63931a7f06e13f90f5d9ef90a0a435f30dae5d4fe70720d730a057473"
)
FRAMEWORKS = ("CS2023", "SWEBOK", "SFIA")
FRAMEWORK_VERSIONS = {
    "CS2023": "Final Report",
    "SWEBOK": "V4.0a",
    "SFIA": "9",
}
FRAMEWORK_SOURCES = {
    "CS2023": {
        "version": "Final Report",
        "officialUrl": "https://csed.acm.org/final-report/",
        "verifiedAt": "2026-07-31",
    },
    "SWEBOK": {
        "version": "V4.0a",
        "officialUrl": (
            "https://www.computer.org/education/bodies-of-knowledge/"
            "software-engineering"
        ),
        "verifiedAt": "2026-07-31",
    },
    "SFIA": {
        "version": "9",
        "officialUrl": (
            "https://sfia-online.org/en/sfia-9/skills/"
            "all-skills-a-z?set_language=en"
        ),
        "verifiedAt": "2026-07-31",
    },
}
EXPECTED_PREREQUISITES = {
    "core-01-systems-tradeoffs": (),
    "core-02-algorithms-measurement": ("core-01-systems-tradeoffs",),
    "core-03-architecture-memory-caches": ("core-01-systems-tradeoffs",),
    "core-04-os-processes-concurrency": (
        "core-02-algorithms-measurement",
        "core-03-architecture-memory-caches",
    ),
    "core-05-networks-latency-failure": (
        "core-04-os-processes-concurrency",
    ),
    "core-06-requirements-domain-modeling": (
        "core-01-systems-tradeoffs",
    ),
    "core-07-api-contract-design": (
        "core-06-requirements-domain-modeling",
    ),
    "core-08-modularity-evolutionary-architecture": (
        "core-06-requirements-domain-modeling",
        "core-07-api-contract-design",
    ),
    "core-09-test-strategy-tdd": (
        "core-02-algorithms-measurement",
        "core-08-modularity-evolutionary-architecture",
    ),
    "core-10-threat-modeling-secure-design": (
        "core-07-api-contract-design",
        "core-09-test-strategy-tdd",
    ),
    "core-11-data-modeling-storage": (
        "core-06-requirements-domain-modeling",
    ),
    "core-12-transactions-isolation-consistency": (
        "core-11-data-modeling-storage",
    ),
    "core-13-distributed-coordination-failure": (
        "core-05-networks-latency-failure",
        "core-12-transactions-isolation-consistency",
    ),
    "core-14-performance-capacity": (
        "core-02-algorithms-measurement",
        "core-03-architecture-memory-caches",
        "core-11-data-modeling-storage",
    ),
    "core-15-reliability-observability-slo": (
        "core-05-networks-latency-failure",
        "core-13-distributed-coordination-failure",
        "core-14-performance-capacity",
    ),
    "core-16-hci-usability-accessibility": (
        "core-06-requirements-domain-modeling",
    ),
    "core-17-graphics-visual-information": (
        "core-03-architecture-memory-caches",
        "core-16-hci-usability-accessibility",
    ),
    "core-18-product-discovery-experiments": (
        "core-06-requirements-domain-modeling",
        "core-16-hci-usability-accessibility",
    ),
    "core-19-technical-communication-design-docs": (
        "core-01-systems-tradeoffs",
        "core-06-requirements-domain-modeling",
    ),
    "core-20-ethics-privacy-societal-impact": (
        "core-10-threat-modeling-secure-design",
        "core-16-hci-usability-accessibility",
        "core-19-technical-communication-design-docs",
    ),
    "core-21-maintenance-legacy-comprehension": (
        "core-08-modularity-evolutionary-architecture",
        "core-09-test-strategy-tdd",
    ),
    "core-22-evolution-safe-migrations": (
        "core-08-modularity-evolutionary-architecture",
        "core-12-transactions-isolation-consistency",
        "core-21-maintenance-legacy-comprehension",
    ),
    "core-23-incident-response-learning": (
        "core-15-reliability-observability-slo",
        "core-21-maintenance-legacy-comprehension",
    ),
    "core-24-delivery-ci-release-safety": (
        "core-09-test-strategy-tdd",
        "core-15-reliability-observability-slo",
    ),
    "core-25-engineering-economics-capacity": (
        "core-14-performance-capacity",
        "core-15-reliability-observability-slo",
        "core-24-delivery-ci-release-safety",
    ),
    "core-26-code-review-collaborative-quality": (
        "core-09-test-strategy-tdd",
        "core-19-technical-communication-design-docs",
    ),
    "core-27-team-interfaces-sociotechnical-architecture": (
        "core-08-modularity-evolutionary-architecture",
        "core-19-technical-communication-design-docs",
        "core-26-code-review-collaborative-quality",
    ),
    "core-28-oss-governance-stewardship": (
        "core-10-threat-modeling-secure-design",
        "core-19-technical-communication-design-docs",
        "core-26-code-review-collaborative-quality",
    ),
    "core-29-cross-cultural-async-collaboration": (
        "core-19-technical-communication-design-docs",
        "core-27-team-interfaces-sociotechnical-architecture",
    ),
    "core-30-evidence-based-technical-leadership": (
        "core-20-ethics-privacy-societal-impact",
        "core-25-engineering-economics-capacity",
        "core-27-team-interfaces-sociotechnical-architecture",
        "core-28-oss-governance-stewardship",
        "core-29-cross-cultural-async-collaboration",
    ),
}
EXPECTED_MASTERY_GATES = (
    {
        "id": "foundation",
        "after": 5,
        "artifact": "未知システムの診断記録",
        "review": "機構と証拠を説明できる",
    },
    {
        "id": "builder",
        "after": 10,
        "artifact": "契約・テスト・脅威モデル付きサービス",
        "review": "信頼性を設計へ埋め込める",
    },
    {
        "id": "scaler",
        "after": 15,
        "artifact": "負荷・障害・SLO実験",
        "review": "分散失敗を測定し判断できる",
    },
    {
        "id": "human",
        "after": 20,
        "artifact": "アクセシブルな検証済み改善",
        "review": "人と社会への影響を説明できる",
    },
    {
        "id": "operator",
        "after": 25,
        "artifact": "移行・運用・費用計画",
        "review": "変更を安全かつ経済的に進められる",
    },
    {
        "id": "leader",
        "after": 30,
        "artifact": "他者が実行可能な技術方針",
        "review": "不確実性の中で組織を前進させられる",
    },
)
EXPECTED_PRIMARY_OWNER = {
    "core-01-systems-tradeoffs": "global-service",
    "core-02-algorithms-measurement": "global-service",
    "core-03-architecture-memory-caches": "global-service",
    "core-04-os-processes-concurrency": "global-service",
    "core-05-networks-latency-failure": "global-service",
    "core-06-requirements-domain-modeling": "global-service",
    "core-07-api-contract-design": "global-service",
    "core-08-modularity-evolutionary-architecture": "legacy-evolution",
    "core-09-test-strategy-tdd": "legacy-evolution",
    "core-10-threat-modeling-secure-design": "oss-launch",
    "core-11-data-modeling-storage": "global-service",
    "core-12-transactions-isolation-consistency": "global-service",
    "core-13-distributed-coordination-failure": "global-service",
    "core-14-performance-capacity": "global-service",
    "core-15-reliability-observability-slo": "global-service",
    "core-16-hci-usability-accessibility": "oss-launch",
    "core-17-graphics-visual-information": "oss-launch",
    "core-18-product-discovery-experiments": "oss-launch",
    "core-19-technical-communication-design-docs": "legacy-evolution",
    "core-20-ethics-privacy-societal-impact": "global-service",
    "core-21-maintenance-legacy-comprehension": "legacy-evolution",
    "core-22-evolution-safe-migrations": "legacy-evolution",
    "core-23-incident-response-learning": "legacy-evolution",
    "core-24-delivery-ci-release-safety": "oss-launch",
    "core-25-engineering-economics-capacity": "legacy-evolution",
    "core-26-code-review-collaborative-quality": "oss-launch",
    "core-27-team-interfaces-sociotechnical-architecture": "legacy-evolution",
    "core-28-oss-governance-stewardship": "oss-launch",
    "core-29-cross-cultural-async-collaboration": "oss-launch",
    "core-30-evidence-based-technical-leadership": "global-service",
}
CAPSTONE_EVIDENCE_KINDS = ("build", "operate", "explain", "review")
_LESSON_MAP_ROW = re.compile(
    r"^\| (?P<ordinal>[1-9]|[12][0-9]|30) \| "
    r"`(?P<lesson>core-(?:0[1-9]|[12][0-9]|30)-[a-z0-9-]+)`<br>"
)
REVIEW_ROLES = (
    "技術的正確性",
    "学習設計・証拠",
    "アクセシビリティ",
    "編集・出典",
)
EVIDENCE_LOOP = ("Learn", "Practice", "Explain", "Prove", "Transfer", "Review")
AUTHORED_HEADINGS = (
    "なぜ重要か",
    "メンタルモデル",
    "動く例で考える",
    "トレードオフと失敗モード",
    "知識チェック",
    "出典と次の学習",
)
EVIDENCE_KINDS = frozenset(
    {"artifact", "explanation", "reasoning", "transfer"}
)
CAPABILITY_LEVELS = ("recognize", "explain", "apply", "diagnose", "lead")
RUBRIC_DIMENSIONS = (
    "technical-correctness",
    "judgment",
    "evidence",
    "communication",
)
RUBRIC_LEVELS = frozenset(
    {"incomplete", "developing", "proficient", "exemplary"}
)


@dataclass(frozen=True, slots=True)
class _ParsedSection:
    heading: str
    body: str


@dataclass(frozen=True, slots=True)
class _EvidenceItem:
    id: str
    kind: str


@dataclass(frozen=True, slots=True)
class _EvidenceContract:
    lesson_id: str
    evidence: tuple[_EvidenceItem, ...]
    objective_references: frozenset[str]
    capability_references: frozenset[str]


class _AuthoredBodyParser(HTMLParser):
    """Read authored semantics without sharing the production HTML validator."""

    _HIDDEN_ELEMENTS = frozenset({"script", "style", "template", "noscript"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[_ParsedSection] = []
        self.visible_parts: list[str] = []
        self._hidden_depth = 0
        self._heading_depth = 0
        self._heading_seen = False
        self._heading_parts: list[str] = []
        self._body_parts: list[str] = []
        self._section_depth = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        tag = tag.casefold()
        if tag in self._HIDDEN_ELEMENTS:
            self._hidden_depth += 1
            return
        if self._hidden_depth:
            return
        if tag == "section":
            if self._section_depth == 0:
                self._heading_seen = False
                self._heading_parts = []
                self._body_parts = []
            self._section_depth += 1
        elif tag == "h2" and self._section_depth == 1:
            if self._heading_depth:
                raise AssertionError("authored h2 elements must not be nested")
            if self._heading_seen:
                raise AssertionError("each authored section must contain one h2")
            self._heading_seen = True
            self._heading_depth = 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in self._HIDDEN_ELEMENTS:
            if self._hidden_depth:
                self._hidden_depth -= 1
            return
        if self._hidden_depth:
            return
        if tag == "h2" and self._heading_depth:
            self._heading_depth = 0
        elif tag == "section":
            if not self._section_depth:
                raise AssertionError("unexpected authored section close")
            self._section_depth -= 1
            if self._section_depth == 0:
                self.sections.append(
                    _ParsedSection(
                        heading=_normalize_visible_text(self._heading_parts),
                        body=_normalize_visible_text(self._body_parts),
                    )
                )

    def handle_data(self, data: str) -> None:
        if self._hidden_depth:
            return
        self.visible_parts.append(data)
        if not self._section_depth:
            return
        if self._heading_depth:
            self._heading_parts.append(data)
        else:
            self._body_parts.append(data)

    def finish(self) -> tuple[tuple[_ParsedSection, ...], str]:
        self.close()
        if self._section_depth or self._heading_depth:
            raise AssertionError("authored section markup is incomplete")
        return tuple(self.sections), _normalize_visible_text(self.visible_parts)


class _FigureOracleParser(HTMLParser):
    """Project authored figure facts without importing production parsing."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.caption_depth = 0
        self.cell_depth = 0
        self.caption: list[str] = []
        self.visible_atoms: list[str] = []
        self.table_cells: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        if tag == "figcaption":
            self.caption_depth += 1
        elif tag in {"th", "td"}:
            self.cell_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "figcaption":
            self.caption_depth -= 1
        elif tag in {"th", "td"}:
            self.cell_depth -= 1

    def handle_data(self, data: str) -> None:
        atom = " ".join(data.split())
        if not atom:
            return
        if self.caption_depth:
            self.caption.append(atom)
        elif self.cell_depth:
            self.table_cells.append(atom)
        else:
            self.visible_atoms.append(atom)


def _section_role(section_id: str) -> str:
    roles = (
        ("mental-model", "mentalModel"),
        ("worked-example", "workedExample"),
        ("knowledge-check", "knowledgeCheck"),
        ("tradeoffs", "tradeoffs"),
        ("sources-next", "sourcesNext"),
        ("why", "why"),
    )
    for suffix, role in roles:
        if section_id == suffix or section_id.endswith(f"-{suffix}"):
            return role
    raise AssertionError(f"unknown authored section role: {section_id}")


def _legacy_figure_projection(
    lesson_id: str,
    body: str,
) -> tuple[list[dict[str, object]], str]:
    section_tokens = tuple(
        re.finditer(r'<section id="([^"]+)">|</section>', body)
    )
    figure_matches = tuple(
        re.finditer(
            r"^[ \t]*<figure(?: [^>]*)?>.*?^[ \t]*</figure>\n?",
            body,
            re.DOTALL | re.MULTILINE,
        )
    )
    occurrences: dict[str, int] = {}
    projection: list[dict[str, object]] = []
    primary_span: tuple[int, int] | None = None
    for figure_index, match in enumerate(figure_matches):
        stack: list[str] = []
        for token in section_tokens:
            if token.start() >= match.start():
                break
            section_id = token.group(1)
            if section_id is not None:
                stack.append(section_id)
            elif stack:
                stack.pop()
        if not stack:
            raise AssertionError(f"{lesson_id}: figure is outside a section")
        role = _section_role(stack[-1])
        occurrences[role] = occurrences.get(role, 0) + 1
        parser = _FigureOracleParser()
        parser.feed(match.group(0))
        parser.close()
        disposition = (
            "retain"
            if lesson_id == "core-17-graphics-visual-information"
            and figure_index == 1
            else "migrate"
        )
        projection.append(
            {
                "lessonId": lesson_id,
                "sectionRole": role,
                "occurrence": occurrences[role],
                "caption": " ".join(parser.caption),
                "visibleAtoms": parser.visible_atoms,
                "tableCells": parser.table_cells,
                "disposition": disposition,
            }
        )
        if disposition == "migrate":
            if primary_span is not None:
                raise AssertionError(f"{lesson_id}: multiple primary figures")
            primary_span = match.span()
    if primary_span is None:
        raise AssertionError(f"{lesson_id}: missing primary figure")
    residual = body[: primary_span[0]] + body[primary_span[1] :]
    return projection, hashlib.sha256(residual.encode("utf-8")).hexdigest()


def _normalize_visible_text(parts: list[str] | tuple[str, ...]) -> str:
    joined = " ".join(parts)
    return " ".join(unicodedata.normalize("NFKC", joined).casefold().split())


def _parse_authored_body(source: str) -> tuple[tuple[_ParsedSection, ...], str]:
    parser = _AuthoredBodyParser()
    parser.feed(source)
    return parser.finish()


def _assert_unique_visible_bodies(bodies: dict[str, str]) -> set[str]:
    owners: dict[str, str] = {}
    for lesson_id, body in bodies.items():
        normalized = _normalize_visible_text([body])
        if not normalized:
            raise AssertionError(f"{lesson_id}: visible body must not be empty")
        if normalized in owners:
            raise AssertionError(
                f"duplicate visible body: {owners[normalized]} and {lesson_id}"
            )
        owners[normalized] = lesson_id
    return set(owners)


def _evidence_contract(document: dict[str, object]) -> _EvidenceContract:
    evidence = tuple(
        _EvidenceItem(item["id"], item["kind"])
        for item in document["evidence"]  # type: ignore[index,union-attr]
    )
    objective_references = frozenset(
        evidence_id
        for objective in document["objectives"]  # type: ignore[union-attr]
        for evidence_id in objective["evidenceIds"]
    )
    capability_references = frozenset(
        evidence_id
        for level in document["capabilityProgression"]  # type: ignore[union-attr]
        for evidence_id in level["evidenceIds"]
    )
    return _EvidenceContract(
        lesson_id=document["id"],  # type: ignore[arg-type]
        evidence=evidence,
        objective_references=objective_references,
        capability_references=capability_references,
    )


def _assert_evidence_references(contract: _EvidenceContract) -> None:
    evidence_ids = [item.id for item in contract.evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise AssertionError(f"{contract.lesson_id}: evidence IDs must be unique")
    if {item.kind for item in contract.evidence} != EVIDENCE_KINDS:
        raise AssertionError(
            f"{contract.lesson_id}: evidence kinds must match the contract"
        )
    expected = frozenset(evidence_ids)
    if contract.objective_references != expected:
        raise AssertionError(
            f"{contract.lesson_id}: orphan or unknown objective evidence"
        )
    if contract.capability_references != expected:
        raise AssertionError(
            f"{contract.lesson_id}: orphan or unknown capability evidence"
        )


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _expected_artifacts() -> frozenset[PurePosixPath]:
    paths = {
        PurePosixPath("index.html"),
        PurePosixPath("styles.css"),
        PurePosixPath("static/visualizations.css"),
        PurePosixPath("static/visualization.js"),
        PurePosixPath("catalog/index.html"),
        PurePosixPath("roadmap/index.html"),
        PurePosixPath("competencies/index.html"),
        PurePosixPath("lessons/index.html"),
        PurePosixPath("capstones/index.html"),
    }
    paths.update(
        PurePosixPath("lessons") / lesson_id / "index.html"
        for lesson_id in LESSON_IDS
    )
    paths.update(
        PurePosixPath("capstones") / capstone_id / "index.html"
        for capstone_id in CAPSTONE_IDS
    )
    return frozenset(paths)


_TASK10_PRIOR_VISUAL_IDS = {
    "core-12-transactions-isolation-consistency": "isolation-schedule-timeline",
    "core-13-distributed-coordination-failure": "dedupe-recovery-timeline",
    "core-14-performance-capacity": "capacity-causal-cycle",
    "core-15-reliability-observability-slo": "slo-action-loop",
}


def _prior_task_static_visual(
    document: dict[str, object], visual: dict[str, object]
) -> dict[str, object]:
    """Keep Task 5/6 semantic oracles independent from later simulations."""
    lesson_id = document["id"]
    if lesson_id not in _TASK10_PRIOR_VISUAL_IDS:
        return visual
    normalized = deepcopy(visual)
    normalized["id"] = _TASK10_PRIOR_VISUAL_IDS[lesson_id]
    normalized.pop("simulation", None)
    if lesson_id == "core-13-distributed-coordination-failure":
        payload = normalized["payload"]
        payload["phases"] = [
            item for item in payload["phases"]
            if item["id"] != "fixture-log"
        ]
        payload["events"] = [
            item for item in payload["events"]
            if not item["id"].startswith("e")
        ]
    return normalized


def _task5_visual_projection(document: dict[str, object]) -> dict[str, object]:
    visual = _prior_task_static_visual(
        document, document["visualizations"][0]  # type: ignore[index]
    )
    payload = visual["payload"]  # type: ignore[index]
    projection: dict[str, object] = {
        "common": (
            visual["id"],  # type: ignore[index]
            visual["type"],  # type: ignore[index]
            visual["afterSection"],  # type: ignore[index]
            visual["caption"],  # type: ignore[index]
            visual["question"],  # type: ignore[index]
            visual["expectedObservation"],  # type: ignore[index]
            tuple(visual["objectiveIds"]),  # type: ignore[index]
            tuple(visual["evidenceIds"]),  # type: ignore[index]
            tuple(visual["sourceIds"]),  # type: ignore[index]
            tuple(visual.get("notes", ())),  # type: ignore[union-attr]
            visual.get("simulation"),  # type: ignore[union-attr]
        ),
        "trace": (
            tuple(visual["objectiveIds"]),  # type: ignore[index]
            tuple(visual["evidenceIds"]),  # type: ignore[index]
            tuple(visual["sourceIds"]),  # type: ignore[index]
        ),
    }
    if visual["type"] == "causal":  # type: ignore[index]
        projection["structure"] = {
            group: tuple(
                (item["id"], item["label"], item["detail"])
                for item in payload[group]  # type: ignore[index]
            )
            for group in ("causes", "mechanisms", "outcomes", "mitigations")
        }
        relations = payload["relations"]  # type: ignore[index]
    else:
        projection["components"] = tuple(
            (item["id"], item["label"], item["detail"], "component")
            for item in payload["components"]  # type: ignore[index]
        )
        projection["nodes"] = tuple(
            (
                item["id"],
                item["label"],
                item["detail"],
                "node",
                item["componentId"],
            )
            for item in payload["nodes"]  # type: ignore[index]
        )
        relations = payload["connections"]  # type: ignore[index]
    projection["relations"] = tuple(
        (item["id"], item["from"], item["to"], item["label"])
        for item in relations
    )
    return projection


def _task6_visual_contract_sha256(document: dict[str, object]) -> str:
    """Provide a compact secondary corruption signal for the readable oracle."""
    visual = _prior_task_static_visual(
        document, document["visualizations"][0]  # type: ignore[index]
    )
    encoded = json.dumps(
        visual,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _task6_visual_projection(document: dict[str, object]) -> dict[str, object]:
    """Project every authored field without using production model objects."""
    visual = _prior_task_static_visual(
        document, document["visualizations"][0]  # type: ignore[index]
    )
    payload = visual["payload"]
    projection: dict[str, object] = {
        "common": (
            visual["id"], visual["type"], visual["afterSection"],
            visual.get("simulation"), visual["caption"], visual["question"],
            visual["expectedObservation"], tuple(visual["objectiveIds"]),
            tuple(visual["evidenceIds"]), tuple(visual["sourceIds"]),
            tuple(visual.get("notes", ())),
        )
    }
    if visual["type"] == "timeline":
        projection["phases"] = tuple(
            (item["id"], item["label"], item["detail"])
            for item in payload["phases"]
        )
        projection["events"] = tuple(
            (
                item["id"], item["label"], item["detail"], item["phaseId"],
                item["order"], item.get("lane"),
            )
            for item in payload["events"]
        )
    elif visual["type"] == "state-machine":
        projection["states"] = tuple(
            (item["id"], item["label"], item["detail"])
            for item in payload["states"]
        )
        projection["initialStateId"] = payload["initialStateId"]
        projection["transitions"] = tuple(
            (
                item["id"], item["from"], item["to"], item["event"],
                item["status"], item.get("reason"),
            )
            for item in payload["transitions"]
        )
    else:
        states = payload["states"]
        projection["states"] = tuple(
            (item["id"], item["label"], item["detail"])
            for item in states
        )
        projection["entryStateId"] = states[0]["id"]
        projection["exitStateId"] = payload["exitStateId"]
        projection["recoveryStateId"] = payload["recoveryStateId"]
        projection["transitions"] = tuple(
            (
                item["id"], item["from"], item["to"], item["label"],
                item.get("kind"),
            )
            for item in payload["transitions"]
        )
        state_order = {item["id"]: index for index, item in enumerate(states)}
        projection["feedbackTransitionIds"] = tuple(
            item["id"]
            for item in payload["transitions"]
            if state_order[item["to"]] <= state_order[item["from"]]
        )
    return projection


def _snapshot(root: Path) -> dict[PurePosixPath, bytes]:
    return {
        PurePosixPath(path.relative_to(root).as_posix()): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _json_bytes(document: object) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _extract_generated_map(document: str) -> str:
    if document.count(BEGIN_GENERATED_MAP) != 1:
        raise AssertionError("curriculum map needs exactly one start marker")
    if document.count(END_GENERATED_MAP) != 1:
        raise AssertionError("curriculum map needs exactly one end marker")
    start = document.index(BEGIN_GENERATED_MAP)
    end = document.index(END_GENERATED_MAP)
    if start >= end:
        raise AssertionError("curriculum map markers are out of order")
    return document[start : end + len(END_GENERATED_MAP)]


_MAP_H1 = "Engineering Expert Curriculum Map"
_MAP_H2 = ("地図の読み方", "推奨する進み方", "更新方法")
_MAP_REQUIRED_GUIDANCE = {
    None: (
        "データ表はsource of truthから "
        "機械生成し、学び方と解釈上の注意は人が保守する。"
    ),
    _MAP_H2[0]: "資格、職位、SFIA責任level の認定ではない。",
    _MAP_H2[1]: (
        "artifact、teach-back、assessment reasoning、transferを "
        "揃えてからmastery gateへ進む。"
    ),
    _MAP_H2[2]: "生成表を直接編集してはならない。",
}
_MAP_ATX_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_MAP_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_MAP_SETEXT_UNDERLINE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
_MAP_RAW_HTML = re.compile(
    r"</?(?:pre|code|template|h[1-6])(?:[ \t][^>]*)?>",
    re.IGNORECASE,
)


def _visible_handwritten_map_lines(document: str) -> tuple[str, ...]:
    """Return only reviewable handwritten prose outside the generated sentinels."""
    generated = _extract_generated_map(document)
    start = document.index(generated)
    handwritten = document[:start] + "\n" + document[start + len(generated) :]
    # Normative prose must never rely on renderer-dependent HTML comment rules.
    if "<!--" in handwritten or "-->" in handwritten:
        raise AssertionError("curriculum map handwritten comments are forbidden")

    visible: list[str] = []
    fence_character: str | None = None
    fence_width = 0
    for line in handwritten.splitlines():
        if fence_character is not None:
            if re.fullmatch(
                rf" {{0,3}}{re.escape(fence_character)}{{{fence_width},}}[ \t]*",
                line,
            ):
                fence_character = None
                fence_width = 0
            continue

        opening = _MAP_FENCE_OPEN.fullmatch(line)
        if opening is not None:
            delimiter, info = opening.groups()
            if delimiter[0] == "`" and "`" in info:
                raise AssertionError(
                    "curriculum map has an invalid backtick fence info string"
                )
            fence_character = delimiter[0]
            fence_width = len(delimiter)
            continue
        if re.match(r"^(?: {4}|\t)", line) or re.match(r"^ {0,3}>", line):
            continue
        if _MAP_RAW_HTML.search(line):
            raise AssertionError("curriculum map contains forbidden raw HTML")
        visible.append(line)

    if fence_character is not None:
        raise AssertionError("curriculum map contains an unclosed code fence")
    return tuple(visible)


_CANONICAL_DECIMAL_ENTITY = re.compile(r"&#([0-9]{1,3});")
_ENTITY_PUNCTUATION = frozenset(string.punctuation) - {"\\", "|"}


def _split_markdown_table_row(line: str) -> tuple[str, ...]:
    """Split only the two backslash escapes production can generate."""
    if not line.startswith("|") or not line.endswith("|"):
        raise AssertionError("generated map row must start and end with a pipe")
    cells: list[str] = []
    current: list[str] = []
    index = 1
    while index < len(line) - 1:
        character = line[index]
        if character == "\\":
            if index + 1 >= len(line) - 1:
                raise AssertionError("generated map row has a dangling escape")
            escaped = line[index + 1]
            if escaped not in {"\\", "|"}:
                raise AssertionError("generated map row has an unsupported escape")
            current.extend(("\\", escaped))
            index += 2
            continue
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
        index += 1
    cells.append("".join(current).strip())
    return tuple(cells)


def _decode_generated_cell(value: str) -> str:
    decoded: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character == "\\":
            if index + 1 >= len(value) or value[index + 1] not in {"\\", "|"}:
                raise AssertionError("generated map row has an unsupported escape")
            decoded.append(value[index + 1])
            index += 2
            continue
        if character == "&":
            match = _CANONICAL_DECIMAL_ENTITY.match(value, index)
            if match is None:
                raise AssertionError("generated map row has an unsupported entity")
            codepoint = int(match.group(1))
            if (
                match.group(1) != str(codepoint)
                or chr(codepoint) not in _ENTITY_PUNCTUATION
            ):
                raise AssertionError("generated map row has a noncanonical entity")
            decoded.append(chr(codepoint))
            index = match.end()
            continue
        decoded.append(character)
        index += 1
    return "".join(decoded)


def _parse_markdown_table_row(line: str) -> tuple[str, ...]:
    """Parse one canonical generated row without production rendering code."""
    return tuple(
        _decode_generated_cell(cell)
        for cell in _split_markdown_table_row(line)
    )


def _encode_expected_markdown_text(value: str) -> str:
    """Independently specify the only plain-text spelling accepted by the map."""
    encoded: list[str] = []
    for character in value:
        if character == "\\":
            encoded.append("\\\\")
        elif character == "|":
            encoded.append("\\|")
        elif character in string.punctuation:
            encoded.append(f"&#{ord(character)};")
        else:
            encoded.append(character)
    return "".join(encoded)


def _encode_expected_mapping_cell(mapping: dict[str, str]) -> str:
    return (
        f"`{_encode_expected_markdown_text(mapping['competencyId'])}` "
        f"{_encode_expected_markdown_text(mapping['competencyName'])} "
        f"({_encode_expected_markdown_text(mapping['alignment'])})"
    )


def _encode_expected_table_row(cells: tuple[str, ...]) -> str:
    return "| " + " | ".join(cells) + " |"


def _assert_handwritten_learning_contract(document: str) -> None:
    """Keep learning guidance independently reviewable from generated data."""
    lines = _visible_handwritten_map_lines(document)
    for index, line in enumerate(lines):
        if (
            index > 0
            and lines[index - 1].strip()
            and _MAP_SETEXT_UNDERLINE.fullmatch(line)
        ):
            raise AssertionError("curriculum map headings must use ATX Markdown")

    first_content = next((line for line in lines if line.strip()), "")
    if first_content != f"# {_MAP_H1}":
        raise AssertionError("curriculum map must begin with the exact H1")

    h1: list[str] = []
    h2: list[str] = []
    sections: dict[str | None, list[str]] = {None: []}
    active_section: str | None = None
    for line in lines:
        heading = _MAP_ATX_HEADING.fullmatch(line)
        if heading is not None:
            level = len(heading.group(1))
            title = re.sub(r"[ \t]+#+[ \t]*$", "", heading.group(2)).strip()
            if level == 1:
                h1.append(title)
                active_section = None
            elif level == 2:
                h2.append(title)
                sections.setdefault(title, [])
                active_section = title
            else:
                raise AssertionError("curriculum map has an unexpected heading")
            continue
        sections.setdefault(active_section, []).append(line)

    if tuple(h1) != (_MAP_H1,):
        raise AssertionError("curriculum map must have one exact H1")
    if tuple(h2) != _MAP_H2:
        raise AssertionError("curriculum map H2 order must be exact")
    if set(sections) != {None, *_MAP_H2}:
        raise AssertionError("curriculum map sections must be exact")

    for section, guidance in _MAP_REQUIRED_GUIDANCE.items():
        prose = " ".join(" ".join(sections[section]).split())
        if prose.count(guidance) != 1:
            raise AssertionError(
                "curriculum map handwritten learning guidance drifted"
            )


def _map_section(
    block: str,
    heading: str,
    next_heading: str | None,
) -> tuple[str, ...]:
    start_marker = f"### {heading}\n"
    if block.count(start_marker) != 1:
        raise AssertionError(f"generated map needs one {heading} section")
    section = block.split(start_marker, maxsplit=1)[1]
    if next_heading is not None:
        end_marker = f"\n### {next_heading}\n"
        if section.count(end_marker) != 1:
            raise AssertionError(
                f"generated map needs one {next_heading} section boundary"
            )
        section = section.split(end_marker, maxsplit=1)[0]
    return tuple(section.splitlines())


def _map_table_rows(
    block: str,
    heading: str,
    next_heading: str | None,
    header: str,
    separator: str,
    expected_rows: int,
) -> tuple[str, ...]:
    """Consume every nonblank line so injected content cannot hide in a section."""
    content = tuple(
        line
        for line in _map_section(block, heading, next_heading)
        if line
    )
    if next_heading is None:
        if not content or content[-1] != END_GENERATED_MAP:
            raise AssertionError("generated map must end after its final table")
        content = content[:-1]
    if any(not line.startswith("|") or not line.endswith("|") for line in content):
        raise AssertionError(f"generated map {heading} contains unexpected content")
    if content[:2] != (header, separator):
        raise AssertionError(f"generated map {heading} table header drifted")
    rows = content[2:]
    if len(rows) != expected_rows:
        raise AssertionError(f"generated map {heading} row count drifted")
    return rows


def _assert_generated_map_contract(
    document: str,
    repository_root: Path = REPOSITORY_ROOT,
) -> None:
    _assert_handwritten_learning_contract(document)
    block = _extract_generated_map(document)
    expected_release_rows = (
        "| 保存カタログ | 1,140 items |",
        f"| カタログ SHA-256 | `{CATALOG_SHA256}` |",
        "| コアレッスン | 30 structurally complete lessons |",
        "| コンピテンシー対応 | 90 mappings |",
        "| 統合 Capstone | 3 projects |",
        "| Primary exercise coverage | 30/30 |",
    )
    release_rows = _map_table_rows(
        block,
        "リリース集計",
        "Framework baseline",
        "| 項目 | 件数・固定値 |",
        "|---|---|",
        len(expected_release_rows),
    )
    if release_rows != expected_release_rows:
        raise AssertionError("generated map release rows are not canonical")

    framework_lines = _map_table_rows(
        block,
        "Framework baseline",
        "Mastery gates",
        "| Framework | Version | Official source | Verified |",
        "|---|---|---|---|",
        len(FRAMEWORKS),
    )
    framework_rows = tuple(
        _parse_markdown_table_row(line)
        for line in framework_lines
    )
    expected_framework_rows = tuple(
        (
            framework,
            FRAMEWORK_SOURCES[framework]["version"],
            f"[{framework}]({FRAMEWORK_SOURCES[framework]['officialUrl']})",
            FRAMEWORK_SOURCES[framework]["verifiedAt"],
        )
        for framework in FRAMEWORKS
    )
    if framework_rows != expected_framework_rows:
        raise AssertionError("generated map framework baseline is not canonical")
    expected_framework_raw_rows = tuple(
        (
            framework,
            _encode_expected_markdown_text(
                FRAMEWORK_SOURCES[framework]["version"]
            ),
            f"[{framework}]({FRAMEWORK_SOURCES[framework]['officialUrl']})",
            FRAMEWORK_SOURCES[framework]["verifiedAt"],
        )
        for framework in FRAMEWORKS
    )
    if framework_lines != tuple(
        _encode_expected_table_row(row)
        for row in expected_framework_raw_rows
    ):
        raise AssertionError("generated map framework encoding is not canonical")

    gate_lines = _map_table_rows(
        block,
        "Mastery gates",
        "30-lesson release map",
        "| Order | Gate | After | Artifact | Review evidence |",
        "|---:|---|---:|---|---|",
        len(EXPECTED_MASTERY_GATES),
    )
    gate_rows = tuple(
        _parse_markdown_table_row(line)
        for line in gate_lines
    )
    expected_gate_rows = tuple(
        (
            str(order),
            f"`{gate['id']}`",
            str(gate["after"]),
            gate["artifact"],
            gate["review"],
        )
        for order, gate in enumerate(EXPECTED_MASTERY_GATES, start=1)
    )
    if gate_rows != expected_gate_rows:
        raise AssertionError("generated map mastery gates are not canonical")
    expected_gate_raw_rows = tuple(
        (
            str(order),
            f"`{gate['id']}`",
            str(gate["after"]),
            _encode_expected_markdown_text(gate["artifact"]),
            _encode_expected_markdown_text(gate["review"]),
        )
        for order, gate in enumerate(EXPECTED_MASTERY_GATES, start=1)
    )
    if gate_lines != tuple(
        _encode_expected_table_row(row) for row in expected_gate_raw_rows
    ):
        raise AssertionError("generated map mastery gate encoding drifted")

    lesson_documents = {
        lesson_id: json.loads(
            (
                repository_root
                / "content/lessons"
                / lesson_id
                / "lesson.json"
            ).read_bytes()
        )
        for lesson_id in LESSON_IDS
    }
    competency_document = json.loads(
        (repository_root / "content/competencies.json").read_bytes()
    )
    mappings = {
        (mapping["targetId"], mapping["framework"]): mapping
        for mapping in competency_document["mappings"]
    }
    capstone_documents = {
        capstone_id: json.loads(
            (
                repository_root
                / "content/capstones"
                / f"{capstone_id}.json"
            ).read_bytes()
        )
        for capstone_id in CAPSTONE_IDS
    }

    lesson_lines = _map_table_rows(
        block,
        "30-lesson release map",
        "Capstone coverage",
        "| # | Lesson | Track / Stage | Prerequisites | Mastery gate | "
        "CS2023 | SWEBOK | SFIA | Primary / Supporting Capstone |",
        "|---:|---|---|---|---|---|---|---|---|",
        len(LESSON_IDS),
    )
    parsed_lesson_rows = []
    for line in lesson_lines:
        match = _LESSON_MAP_ROW.match(line)
        if match is None:
            raise AssertionError("generated map contains an invalid lesson row")
        parsed_lesson_rows.append(
            (match, line, _parse_markdown_table_row(line))
        )
    lesson_rows = tuple(parsed_lesson_rows)
    if len(lesson_rows) != 30:
        raise AssertionError("generated map must contain exactly 30 lesson rows")
    if tuple(
        match.group("lesson") for match, _line, _cells in lesson_rows
    ) != LESSON_IDS:
        raise AssertionError("generated map lesson IDs do not match the release")
    if tuple(
        int(match.group("ordinal"))
        for match, _line, _cells in lesson_rows
    ) != tuple(range(1, 31)):
        raise AssertionError("generated map lesson ordinals are not canonical")

    mapping_cells: list[str] = []
    for match, _line, cells in lesson_rows:
        if len(cells) != 9:
            raise AssertionError("lesson rows must contain exactly nine cells")
        lesson_id = match.group("lesson")
        ordinal = int(match.group("ordinal"))
        lesson = lesson_documents[lesson_id]
        expected_prerequisites = EXPECTED_PREREQUISITES[lesson_id]
        expected_prerequisite_cell = "<br>".join(
            f"`{value}`" for value in expected_prerequisites
        ) or "—"
        expected_gate = next(
            gate["id"]
            for gate in EXPECTED_MASTERY_GATES
            if ordinal <= gate["after"]
        )
        if cells[:5] != (
            str(ordinal),
            f"`{lesson_id}`<br>{lesson['title']}",
            f"{lesson['track']} / {lesson['stage']}",
            expected_prerequisite_cell,
            f"`{expected_gate}`",
        ):
            raise AssertionError(
                f"generated map lesson identity, prerequisite, or gate drifted: "
                f"{lesson_id}"
            )
        framework_cells = cells[5:8]
        expected_framework_cells = tuple(
            (
                f"`{mappings[(lesson_id, framework)]['competencyId']}` "
                f"{mappings[(lesson_id, framework)]['competencyName']} "
                f"({mappings[(lesson_id, framework)]['alignment']})"
            )
            for framework in FRAMEWORKS
        )
        if framework_cells != expected_framework_cells:
            raise AssertionError(
                f"generated map framework mapping drifted: {lesson_id}"
            )
        mapping_cells.extend(framework_cells)
        expected_owner = EXPECTED_PRIMARY_OWNER[lesson_id]
        supporting = tuple(
            capstone_id
            for capstone_id in CAPSTONE_IDS
            if lesson_id in capstone_documents[capstone_id]["lessonIds"]
            and capstone_id != expected_owner
        )
        expected_capstone_cell = f"Primary: `{expected_owner}`"
        if supporting:
            expected_capstone_cell += "<br>Supporting: " + ", ".join(
                f"`{value}`" for value in supporting
            )
        if cells[8] != expected_capstone_cell:
            raise AssertionError(
                f"generated map capstone ownership drifted: {lesson_id}"
            )
        expected_framework_raw_cells = tuple(
            _encode_expected_mapping_cell(mappings[(lesson_id, framework)])
            for framework in FRAMEWORKS
        )
        expected_raw_cells = (
            str(ordinal),
            f"`{lesson_id}`<br>"
            f"{_encode_expected_markdown_text(lesson['title'])}",
            f"{_encode_expected_markdown_text(lesson['track'])} / "
            f"{lesson['stage']}",
            expected_prerequisite_cell,
            f"`{expected_gate}`",
            *expected_framework_raw_cells,
            expected_capstone_cell,
        )
        if _line != _encode_expected_table_row(expected_raw_cells):
            raise AssertionError(
                f"generated map lesson encoding drifted: {lesson_id}"
            )
    if len(mapping_cells) != 90:
        raise AssertionError("generated map must expose exactly 90 mapping cells")

    capstone_lines = _map_table_rows(
        block,
        "Capstone coverage",
        None,
        "| Capstone | Lessons | Primary exercises | Evidence kinds |",
        "|---|---:|---:|---|",
        len(CAPSTONE_IDS),
    )
    if any(
        re.match(
            r"^\| `(?:global-service|legacy-evolution|oss-launch)` — ",
            line,
        )
        is None
        for line in capstone_lines
    ):
        raise AssertionError("generated map contains an invalid capstone row")
    capstone_rows = tuple(
        _parse_markdown_table_row(line) for line in capstone_lines
    )
    expected_capstone_rows = tuple(
        (
            f"`{capstone_id}` — {capstone_documents[capstone_id]['title']}",
            str(len(capstone_documents[capstone_id]["lessonIds"])),
            str(len(capstone_documents[capstone_id]["primaryExercises"])),
            ", ".join(f"`{kind}`" for kind in CAPSTONE_EVIDENCE_KINDS),
        )
        for capstone_id in CAPSTONE_IDS
    )
    if capstone_rows != expected_capstone_rows:
        raise AssertionError("generated map capstone coverage drifted")
    expected_capstone_raw_rows = tuple(
        (
            f"`{capstone_id}` — "
            f"{_encode_expected_markdown_text(capstone_documents[capstone_id]['title'])}",
            str(len(capstone_documents[capstone_id]["lessonIds"])),
            str(len(capstone_documents[capstone_id]["primaryExercises"])),
            ", ".join(f"`{kind}`" for kind in CAPSTONE_EVIDENCE_KINDS),
        )
        for capstone_id in CAPSTONE_IDS
    )
    if capstone_lines != tuple(
        _encode_expected_table_row(row)
        for row in expected_capstone_raw_rows
    ):
        raise AssertionError("generated map capstone encoding drifted")


class ContentAcceptanceTests(unittest.TestCase):
    def test_task9_foundational_simulations_have_exact_finite_contracts(self) -> None:
        catalog = {
            item["lessonId"]: item["simulation"]
            for item in json.loads(
                (REPOSITORY_ROOT / "content/visualization-catalog.json").read_bytes()
            )["lessons"]
            if item["lessonId"] in TASK9_SIMULATION_CONTRACTS
        }
        self.assertEqual(set(catalog), set(TASK9_SIMULATION_CONTRACTS))

        for lesson_id, expected in TASK9_SIMULATION_CONTRACTS.items():
            with self.subTest(lesson_id=lesson_id):
                document = json.loads(
                    (REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json")
                    .read_bytes()
                )
                simulations = [
                    visual for visual in document["visualizations"]
                    if "simulation" in visual
                ]
                self.assertEqual(len(simulations), 1)
                visual = simulations[0]
                simulation = visual["simulation"]
                approved = catalog[lesson_id]

                self.assertEqual(visual["id"], expected["visual"])
                self.assertEqual(simulation["kind"], expected["kind"])
                self.assertEqual(simulation["interactionMode"], expected["mode"])
                self.assertEqual(approved["staticEquivalentId"], visual["id"])
                self.assertEqual(approved["kind"], simulation["kind"])
                self.assertEqual(approved["interactionMode"], simulation["interactionMode"])
                self.assertEqual(
                    tuple(item["id"] for item in simulation["parameters"]),
                    expected["parameters"],
                )
                self.assertEqual(
                    tuple(item["id"] for item in simulation["states"]),
                    expected["states"],
                )
                self.assertEqual(
                    tuple(item["id"] for item in simulation["transitions"]),
                    expected["transitions"],
                )
                self.assertEqual(
                    tuple(item["id"] for item in simulation["outcomes"]),
                    expected["outcomes"],
                )
                self.assertEqual(
                    simulation.get("defaultIntervalMs"), expected["interval"]
                )
                if expected["mode"] in {"playback", "hybrid"}:
                    interval = simulation["defaultIntervalMs"]
                    self.assertTrue(250 <= interval <= 5000)
                    self.assertEqual(interval % 50, 0)
                else:
                    self.assertNotIn("defaultIntervalMs", simulation)

                state_ids = set(expected["states"])
                self.assertIn(simulation["initialStateId"], state_ids)
                self.assertTrue(
                    set(approved["visualRegressionStateIds"]) <= state_ids
                )
                self.assertTrue(simulation["outcomes"])
                self.assertTrue(
                    all(item["stateId"] in state_ids for item in simulation["outcomes"])
                )

    def test_task9_review_contracts_preserve_measurement_and_trace_boundaries(self) -> None:
        documents = {
            lesson_id: json.loads(
                (REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json")
                .read_bytes()
            )
            for lesson_id in TASK9_SIMULATION_CONTRACTS
        }
        simulations = {
            lesson_id: next(
                visual["simulation"] for visual in document["visualizations"]
                if "simulation" in visual
            )
            for lesson_id, document in documents.items()
        }

        core02 = json.dumps(simulations["core-02-algorithms-measurement"], ensure_ascii=False)
        for atom in (
            "n=1000: 線形1000・二分10・hash期待1",
            "n=10000: 線形10000・二分14・hash期待1",
            "n=100000: 線形100000・二分17・hash期待1",
            "median_ns/range_ns", "理論操作数", "普遍的な時間",
        ):
            self.assertIn(atom, core02)

        core03 = json.dumps(simulations["core-03-architecture-memory-caches"], ensure_ascii=False)
        for atom in (
            "固定sample trace", "原因候補", "観測値だけでは証明できない",
            "hardware counter", "translationとtransferを独立",
        ):
            self.assertIn(atom, core03)

        self.assertEqual(
            tuple(item["id"] for item in simulations["core-04-os-processes-concurrency"]["states"]),
            (
                "read-old-value", "b-read-old-value", "a-compute", "b-compute",
                "a-write", "lost-update", "lock-acquired", "a-locked-write",
                "unlock", "b-lock-acquired", "b-locked-write", "locked-complete",
            ),
        )
        core04 = json.dumps(simulations["core-04-os-processes-concurrency"], ensure_ascii=False)
        for atom in ("期待値x=8", "actual x=9", "read/compute/write", "lock/unlock"):
            self.assertIn(atom, core04)
        core04_visual = next(
            visual for visual in documents["core-04-os-processes-concurrency"]["visualizations"]
            if visual["id"] == "scheduler-interleaving-static"
        )
        static_step = next(
            edge for edge in core04_visual["payload"]["transitions"]
            if edge["id"] == "step-06"
        )
        simulation_step = next(
            edge for edge in core04_visual["simulation"]["transitions"]
            if edge["id"] == "lost-next"
        )
        self.assertEqual(
            (static_step["from"], static_step["to"], static_step["event"]),
            ("lost-update", "lock-acquired", "next"),
        )
        self.assertEqual(
            (simulation_step["from"], simulation_step["to"], simulation_step["event"]),
            (static_step["from"], static_step["to"], static_step["event"]),
        )
        reset_step = next(
            edge for edge in core04_visual["simulation"]["transitions"]
            if edge["id"] == "lost-reset"
        )
        self.assertEqual(
            (reset_step["from"], reset_step["to"], reset_step["event"]),
            ("lost-update", "read-old-value", "reset"),
        )

        core05_simulation = simulations["core-05-networks-latency-failure"]
        self.assertEqual(
            tuple(item["id"] for item in core05_simulation["parameters"]),
            ("fault", "budget"),
        )
        core05 = json.dumps(core05_simulation, ensure_ascii=False)
        for atom in (
            "DNS→TCP→TLS→request", "retry decision", "設定不整合なのでretry禁止",
            "side effectは不明", "normal-budget", "tight-budget",
        ):
            self.assertIn(atom, core05)

        core05_visual = next(
            visual for visual in documents["core-05-networks-latency-failure"]["visualizations"]
            if visual["id"] == "request-path-static"
        )
        completed_paths = {
            cell["alternativeId"]: cell["value"]
            for cell in core05_visual["payload"]["cells"]
            if cell["criterionId"] == "completed-path"
        }
        self.assertEqual(completed_paths, {
            "healthy": "DNS→TCP→TLS→request→response",
            "dns-point": "DNS→failure observation→retry decision/recovery",
            "tcp-point": "DNS→TCP→failure observation→retry decision/recovery",
            "tls-point": "DNS→TCP→TLS failure→retry blocked/config repair",
            "request-point": "DNS→TCP→TLS→request timeout→retry decision/recovery",
            "response-point": (
                "DNS→TCP→TLS→request sent→response unobserved→"
                "side-effect inquiry→retry decision"
            ),
        })

    def test_task9_core05_each_selection_has_an_exact_causal_navigation_path(self) -> None:
        document = json.loads(
            (REPOSITORY_ROOT / "content/lessons/core-05-networks-latency-failure/lesson.json")
            .read_bytes()
        )
        simulation = next(
            visual["simulation"] for visual in document["visualizations"]
            if visual["id"] == "request-path-static"
        )
        paths = {
            ("ok", "n"): (
                "dns-lookup", "h-tcp", "tls-ready", "h-req", "h-ok",
            ),
            ("ok", "t"): (
                "dns-lookup", "h-tcp", "tls-ready", "h-req", "h-retry-blocked",
            ),
            ("dns", "n"): (
                "dns-lookup", "d-fail", "d-retry",
            ),
            ("dns", "t"): (
                "dns-lookup", "d-fail", "d-retry-blocked",
            ),
            ("tcp", "n"): (
                "dns-lookup", "t-fail", "t-retry",
            ),
            ("tcp", "t"): (
                "dns-lookup", "t-fail", "t-retry-blocked",
            ),
            ("tls", "n"): (
                "dns-lookup", "l-tcp", "l-fail", "l-retry-blocked",
            ),
            ("tls", "t"): (
                "dns-lookup", "l-tcp", "l-fail", "l-retry-blocked-tight",
            ),
            ("req", "n"): (
                "dns-lookup", "q-tcp", "q-tls", "q-fail", "q-retry",
            ),
            ("req", "t"): (
                "dns-lookup", "q-tcp", "q-tls", "q-fail", "q-retry-blocked",
            ),
            ("resp", "n"): (
                "dns-lookup", "s-tcp", "s-tls", "s-req", "deadline-exceeded",
                "s-inquiry", "s-retry",
            ),
            ("resp", "t"): (
                "dns-lookup", "s-tcp", "s-tls", "s-req", "deadline-exceeded",
                "s-inquiry", "s-retry-blocked",
            ),
        }
        states = {state["id"]: state for state in simulation["states"]}
        transitions = simulation["transitions"]

        for selection_values, path in paths.items():
            selection = dict(zip(("fault", "budget"), selection_values))
            active_states = {
                state_id for state_id, state in states.items()
                if all(selection[key] == value for key, value in state.get("when", {}).items())
            }
            active_edges = [
                edge for edge in transitions
                if all(selection[key] == value for key, value in edge.get("when", {}).items())
            ]
            with self.subTest(selection=selection_values):
                self.assertEqual(active_states, set(path))
                self.assertEqual(
                    [
                        (edge["from"], edge["to"])
                        for edge in active_edges if edge["event"] == "next"
                    ],
                    list(zip(path, path[1:])),
                )
                self.assertEqual(
                    [
                        (edge["from"], edge["to"])
                        for edge in active_edges if edge["event"] == "timer"
                    ],
                    list(zip(path, path[1:])),
                )
                self.assertEqual(
                    {
                        (edge["from"], edge["to"])
                        for edge in active_edges if edge["event"] == "previous"
                    },
                    set(zip(path[1:], path)),
                )
                self.assertEqual(
                    {
                        (edge["from"], edge["to"])
                        for edge in active_edges if edge["event"] == "reset"
                    },
                    {(state_id, "dns-lookup") for state_id in path[1:]},
                )

    def test_task9_core05_retry_budget_has_exact_arithmetic_boundaries(self) -> None:
        document = json.loads(
            (REPOSITORY_ROOT / "content/lessons/core-05-networks-latency-failure/lesson.json")
            .read_bytes()
        )
        visual = next(
            item for item in document["visualizations"]
            if item["id"] == "request-path-static"
        )
        simulation = visual["simulation"]
        components = {
            "first": 800, "backoff": 100, "second": 700,
            "post": 200, "cancel": 100,
        }
        self.assertEqual(sum(components.values()), 1900)
        rendered = json.dumps(visual, ensure_ascii=False)
        for atom in (
            "total=2000ms", "first=800ms", "backoff=100ms",
            "second=700ms", "post=200ms", "cancel=100ms",
            "planned=1900ms", "retry開始条件 remaining>=100ms",
            "primaryの300ms phase breakdown fixtureとは別",
        ):
            self.assertIn(atom, rendered)

        options = {
            option["id"]: option["label"]
            for parameter in simulation["parameters"]
            if parameter["id"] == "budget"
            for option in parameter["options"]
        }
        self.assertEqual(options, {
            "n": "normal-budget: elapsed=1900ms, remaining=100ms",
            "t": "tight-budget(+1ms overhead): elapsed=1901ms, remaining=99ms",
        })

        outcomes = {item["stateId"]: item["label"] for item in simulation["outcomes"]}
        states = {item["id"]: item for item in simulation["states"]}
        self.assertEqual(len(outcomes), 12)
        for state_id, label in outcomes.items():
            profile = states[state_id]["when"]["budget"]
            expected_elapsed, expected_remaining, expected_decision = (
                (1900, 100, "allowed")
                if profile == "n"
                else (1901, 99, "blocked")
            )
            with self.subTest(state_id=state_id):
                self.assertIn(f"elapsed={expected_elapsed}ms", label)
                self.assertIn(f"remaining={expected_remaining}ms", label)
                self.assertIn(f"budget-gate={expected_decision}", label)
                self.assertEqual(2000 - expected_elapsed, expected_remaining)
                self.assertEqual(expected_remaining >= 100, expected_decision == "allowed")
                self.assertIn(f"elapsed={expected_elapsed}ms", states[state_id]["status"])
                self.assertIn(f"remaining={expected_remaining}ms", states[state_id]["status"])

    def test_task10_simulations_have_exact_independent_finite_contracts(self) -> None:
        catalog_document = json.loads(
            (REPOSITORY_ROOT / "content/visualization-catalog.json").read_bytes()
        )
        catalog = {
            item["lessonId"]: item["simulation"]
            for item in catalog_document["lessons"]
            if item["lessonId"] in TASK10_SIMULATION_CONTRACTS
        }
        self.assertEqual(set(catalog), set(TASK10_SIMULATION_CONTRACTS))

        authored_simulations = {}
        for lesson_id in LESSON_IDS:
            document = json.loads(
                (REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json")
                .read_bytes()
            )
            for visual in document["visualizations"]:
                if "simulation" in visual:
                    authored_simulations[lesson_id] = visual

        # This is intentionally independent from the catalog projection: Task 10
        # advances the implemented boundary from five to exactly nine lessons.
        self.assertEqual(
            set(authored_simulations),
            set(TASK9_SIMULATION_CONTRACTS) | set(TASK10_SIMULATION_CONTRACTS),
        )
        self.assertEqual(len(authored_simulations), 9)

        for lesson_id, expected in TASK10_SIMULATION_CONTRACTS.items():
            with self.subTest(lesson_id=lesson_id):
                visual = authored_simulations[lesson_id]
                simulation = visual["simulation"]
                approved = catalog[lesson_id]
                self.assertEqual(visual["id"], expected["visual"])
                self.assertEqual(simulation["kind"], expected["kind"])
                self.assertEqual(simulation["interactionMode"], expected["mode"])
                self.assertEqual(approved["staticEquivalentId"], visual["id"])
                self.assertEqual(approved["kind"], simulation["kind"])
                self.assertEqual(approved["interactionMode"], expected["mode"])
                self.assertEqual(
                    tuple(item["id"] for item in simulation["parameters"]),
                    expected["parameters"],
                )
                self.assertEqual(
                    tuple(item["id"] for item in simulation["states"]),
                    expected["states"],
                )
                self.assertEqual(
                    tuple(item["id"] for item in simulation["outcomes"]),
                    expected["outcomes"],
                )
                self.assertEqual(
                    simulation.get("defaultIntervalMs"), expected["interval"]
                )
                state_ids = set(expected["states"])
                self.assertIn(simulation["initialStateId"], state_ids)
                self.assertTrue(
                    set(approved["visualRegressionStateIds"]) <= state_ids
                )

    def test_task10_static_oracles_preserve_exact_lesson_fixture_results(self) -> None:
        rendered = {}
        for lesson_id, expected in TASK10_SIMULATION_CONTRACTS.items():
            document = json.loads(
                (REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json")
                .read_bytes()
            )
            matching_visuals = [
                item for item in document["visualizations"]
                if item["id"] == expected["visual"]
            ]
            self.assertEqual(len(matching_visuals), 1)
            visual = matching_visuals[0]
            lesson = load_lesson_bytes(
                (REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json")
                .read_bytes(), lesson_id,
            )
            model = next(item for item in lesson.visualizations if item.id == expected["visual"])
            rendered[lesson_id] = str(render_visualization(lesson_id, model))
            self.assertIn("パラメータと選択肢", rendered[lesson_id])
            self.assertIn("完全な遷移", rendered[lesson_id])
            self.assertIn("観測結果", rendered[lesson_id])
            for state in visual["simulation"]["states"]:
                self.assertIn(state["status"], rendered[lesson_id])
            for outcome in visual["simulation"]["outcomes"]:
                self.assertIn(outcome["label"], rendered[lesson_id])
            self.assertLessEqual(len(visual["simulation"]["states"]), 64)
            self.assertLessEqual(len(visual["simulation"]["transitions"]), 128)

        exact_atoms = {
            "core-12-transactions-isolation-consistency": (
                "開始状態 {alice: on, bob: on}", "Snapshot Isolation",
                "2件ともcommit", "当直者0人", "1件をabort",
                "合計3 attempt", "当直者1人",
            ),
            "core-13-distributed-coordination-failure": (
                "seed 20260731", "6 event", "3 message", "tick 6",
                "deadline 8", "state transitionは1回", "resultを1回再利用",
            ),
            "core-14-performance-capacity": (
                "arrivals=150req", "admitted=130req", "completed=100req",
                "Qend=30req", "rejected=20req", "p99=450ms",
                "safe capacityは20% headroom後の80 RPS",
                "arrivals=120req", "admitted=110req", "rejected=10req",
                "safe capacityは20% headroom後の64 RPS",
            ),
            "core-15-reliability-observability-slo": (
                "28日", "target=90%", "error budget=10%", "5分",
                "60分", "short burn=2", "long burn=0.1667",
                "short burn=10", "long burn=2", "page=true",
            ),
        }
        for lesson_id, atoms in exact_atoms.items():
            for atom in atoms:
                with self.subTest(lesson_id=lesson_id, atom=atom):
                    self.assertIn(atom, rendered[lesson_id])

    def test_task10_core14_states_expose_exact_queue_conservation_records(self) -> None:
        lesson_id = "core-14-performance-capacity"
        path = REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json"
        document = json.loads(path.read_bytes())
        states = document["visualizations"][0]["simulation"]["states"]
        expected_statuses = {
            "stable-load": "Δt=1s;Qstart=0req;arrivals=40req;admitted=40req;immediate=40req;backlogDone=0req;completed=40req;Qend=0req;rejected=0req;failed=0req;p99=70ms.",
            "near-capacity": "Δt=1s;Qstart=0req;arrivals=100req;admitted=100req;immediate=100req;backlogDone=0req;completed=100req;Qend=0req;rejected=0req;failed=0req;p99=100ms.",
            "saturation": "Δt=1s;Qstart=0req;arrivals=150req;admitted=130req;immediate=100req;backlogDone=0req;completed=100req;Qend=30req;rejected=20req;failed=20req;p99=450ms.",
            "capacity-recovered": "Δt=1s;Qstart=30req;arrivals=50req;admitted=50req;immediate=50req;backlogDone=30req;completed=80req;Qend=0req;rejected=0req;failed=0req;p99=180ms.",
            "write-stable-load": "Δt=1s;Qstart=0req;arrivals=40req;admitted=40req;immediate=40req;backlogDone=0req;completed=40req;Qend=0req;rejected=0req;failed=0req;p99=90ms.",
            "write-near-capacity": "Δt=1s;Qstart=0req;arrivals=80req;admitted=80req;immediate=80req;backlogDone=0req;completed=80req;Qend=0req;rejected=0req;failed=0req;p99=190ms.",
            "write-saturation": "Δt=1s;Qstart=0req;arrivals=120req;admitted=110req;immediate=80req;backlogDone=0req;completed=80req;Qend=30req;rejected=10req;failed=10req;p99=900ms.",
            "write-capacity-recovered": "Δt=1s;Qstart=30req;arrivals=50req;admitted=50req;immediate=50req;backlogDone=30req;completed=80req;Qend=0req;rejected=0req;failed=0req;p99=360ms.",
        }
        self.assertEqual(
            {state["id"]: state["status"] for state in states},
            expected_statuses,
        )

    def test_task10_core13_static_equivalent_is_the_complete_six_event_log(self) -> None:
        lesson_id = "core-13-distributed-coordination-failure"
        path = REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json"
        document = json.loads(path.read_bytes())
        self.assertEqual(
            tuple(item["id"] for item in document["visualizations"]),
            ("distributed-failure-static",),
        )
        visual = document["visualizations"][0]
        self.assertEqual(visual["type"], "timeline")
        expected_events = (
            (
                "e1-confirm",
                "tick=1、kind=deliver、logical_sequence=2、delivery_priority=0。immediateにpending→confirmedを1回applyし、state・fingerprint・result=confirmed-onceをatomic commitする。",
            ),
            (
                "e2-partition-start",
                "tick=2、kind=partition_start。partitionをactiveにし、e1の永続commitを保持したまま以後のmessageをbufferする。",
            ),
            (
                "e3-status-read",
                "tick=3、kind=deliver、logical_sequence=4、delivery_priority=1。partition中なのでstatus readはapplyせずbufferし、利用者結果を未確定のまま保つ。",
            ),
            (
                "e4-confirm-retry",
                "tick=4、kind=duplicate、logical_sequence=2、delivery_priority=2。同じkeyとfingerprintのretryをbufferし、回復時もeffectを再applyせず保存済みresultを再利用する。",
            ),
            (
                "e5-reconcile-read",
                "tick=5、kind=deliver、logical_sequence=3、delivery_priority=0。partition中にbufferし、回復時はe3のsequence=4より先にgapを埋めるread-only resultを得る。",
            ),
            (
                "e6-partition-end",
                "tick=6、kind=partition_end。deadline=8以内にrecoveryし、priority順e5→e3→e4で解放する。最終state=confirmed、apply=1、result reuse=1として順序差と残留messageを再評価する。",
            ),
        )
        self.assertEqual(
            tuple(
                (item["id"], item["detail"])
                for item in visual["payload"]["events"]
                if item["id"].startswith("e")
            ),
            expected_events,
        )
        simulation = visual["simulation"]
        self.assertEqual(
            tuple(item["activeNodeIds"] for item in simulation["states"]),
            tuple([event_id] for event_id, _detail in expected_events),
        )
        model = load_lesson_bytes(path.read_bytes(), path.name).visualizations[0]
        no_js = str(render_visualization(lesson_id, model))
        for event_id, detail in expected_events:
            self.assertIn(event_id, no_js)
            self.assertIn(detail, no_js)

    def test_task10_hybrid_paths_have_complete_manual_timer_and_reset_edges(self) -> None:
        expected_paths = {
            "core-12-transactions-isolation-consistency": {
                "snapshot": (
                    "concurrent-read", "snapshot-local-decision", "write-skew",
                ),
                "serializable": (
                    "concurrent-read", "serializable-validation",
                    "transaction-aborted", "transaction-retried",
                ),
            },
            "core-13-distributed-coordination-failure": {
                "duplicate": (
                    "event-log-start", "partition-detected", "partition-buffered",
                    "duplicate-received", "reorder-gap-filled", "recovery-converged",
                ),
                "reorder": (
                    "event-log-start", "partition-detected", "partition-buffered",
                    "duplicate-received", "reorder-gap-filled", "recovery-converged",
                ),
                "partition": (
                    "event-log-start", "partition-detected", "partition-buffered",
                    "duplicate-received", "reorder-gap-filled", "recovery-converged",
                ),
                "recovery": (
                    "event-log-start", "partition-detected", "partition-buffered",
                    "duplicate-received", "reorder-gap-filled", "recovery-converged",
                ),
            },
        }
        for lesson_id, lesson_paths in expected_paths.items():
            document = json.loads(
                (REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json")
                .read_bytes()
            )
            matching_simulations = [
                item["simulation"] for item in document["visualizations"]
                if "simulation" in item
            ]
            self.assertEqual(len(matching_simulations), 1)
            simulation = matching_simulations[0]
            parameter = simulation["parameters"][0]
            states = {state["id"]: state for state in simulation["states"]}
            transitions = simulation["transitions"]
            initial = simulation["initialStateId"]
            for option in parameter["options"]:
                selection = {parameter["id"]: option["id"]}
                active_states = {
                    state_id for state_id, state in states.items()
                    if all(selection[key] == value for key, value in state.get("when", {}).items())
                }
                active_edges = [
                    edge for edge in transitions
                    if all(selection[key] == value for key, value in edge.get("when", {}).items())
                ]
                with self.subTest(lesson_id=lesson_id, option=option["id"]):
                    path = lesson_paths[option["id"]]
                    self.assertEqual(active_states, set(path))
                    parameter_changes = [
                        edge for edge in active_edges
                        if edge["event"] == "parameter-change"
                    ]
                    self.assertEqual(len(parameter_changes), 1)
                    self.assertEqual(
                        (parameter_changes[0]["from"], parameter_changes[0]["to"]),
                        (initial, initial),
                    )
                    forward = {
                        (edge["from"], edge["to"])
                        for edge in active_edges if edge["event"] == "next"
                    }
                    self.assertEqual(forward, set(zip(path, path[1:])))
                    self.assertEqual(forward, {
                        (edge["from"], edge["to"])
                        for edge in active_edges if edge["event"] == "timer"
                    })
                    self.assertEqual({(to_id, from_id) for from_id, to_id in forward}, {
                        (edge["from"], edge["to"])
                        for edge in active_edges if edge["event"] == "previous"
                    })
                    self.assertEqual(
                        {(edge["from"], edge["to"]) for edge in active_edges if edge["event"] == "reset"},
                        {(state_id, initial) for state_id in active_states - {initial}},
                    )

    def test_catalog_bytes_and_identity_are_bound_to_the_preserved_release(
        self,
    ) -> None:
        raw = (REPOSITORY_ROOT / "content/catalog.json").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), CATALOG_SHA256)

        document = json.loads(raw)
        items = document["items"]
        item_ids = tuple(item["id"] for item in items)
        self.assertEqual(len(item_ids), 1_140)
        self.assertEqual(len(set(item_ids)), 1_140)
        self.assertTrue(
            {
                item["coreLessonId"]
                for item in items
                if item["coreLessonId"] is not None
            }.issubset(frozenset(LESSON_IDS))
        )

    def test_roadmap_matches_fixed_prerequisites_and_six_mastery_gates(
        self,
    ) -> None:
        document = json.loads(
            (REPOSITORY_ROOT / "content/roadmap.json").read_text(
                encoding="utf-8"
            )
        )
        nodes = document["nodes"]
        self.assertEqual(tuple(node["id"] for node in nodes), LESSON_IDS)
        self.assertEqual(
            {
                node["id"]: tuple(node["prerequisiteIds"])
                for node in nodes
            },
            EXPECTED_PREREQUISITES,
        )
        self.assertEqual(
            tuple(document["masteryGates"]),
            EXPECTED_MASTERY_GATES,
        )

    def test_competency_matrix_is_one_pinned_official_triple_per_lesson(
        self,
    ) -> None:
        path = REPOSITORY_ROOT / "content/competencies.json"
        document = json.loads(path.read_bytes())
        self.assertEqual(document["frameworkVersions"], FRAMEWORK_VERSIONS)
        self.assertEqual(document["frameworkSources"], FRAMEWORK_SOURCES)

        mappings = document["mappings"]
        self.assertEqual(len(mappings), 90)
        pairs = tuple(
            (mapping["targetId"], mapping["framework"])
            for mapping in mappings
        )
        self.assertEqual(len(set(pairs)), 90)
        self.assertEqual(
            frozenset(pairs),
            frozenset(
                (lesson_id, framework)
                for lesson_id in LESSON_IDS
                for framework in FRAMEWORKS
            ),
        )

    def test_competency_parser_rejects_count_preserving_duplicate_and_drift(
        self,
    ) -> None:
        path = REPOSITORY_ROOT / "content/competencies.json"
        original = json.loads(path.read_bytes())

        duplicated = json.loads(json.dumps(original))
        duplicated["mappings"][-1] = dict(duplicated["mappings"][0])
        self.assertEqual(len(duplicated["mappings"]), 90)
        with self.assertRaises(CurriculumValidationError):
            parse_competencies_bytes(
                _json_bytes(duplicated),
                expected_target_ids=frozenset(LESSON_IDS),
                source_name="competencies.json",
            )

        drifted = json.loads(json.dumps(original))
        drifted["frameworkVersions"]["CS2023"] = "Draft"
        with self.assertRaises(CurriculumValidationError):
            parse_competencies_bytes(
                _json_bytes(drifted),
                expected_target_ids=frozenset(LESSON_IDS),
                source_name="competencies.json",
            )

    def test_capstones_have_fixed_primary_owners_and_four_evidence_kinds(
        self,
    ) -> None:
        root = REPOSITORY_ROOT / "content/capstones"
        documents = tuple(
            json.loads((root / f"{capstone_id}.json").read_bytes())
            for capstone_id in CAPSTONE_IDS
        )
        self.assertEqual(tuple(item["id"] for item in documents), CAPSTONE_IDS)

        primary_owners: dict[str, str] = {}
        for document in documents:
            with self.subTest(capstone=document["id"]):
                self.assertEqual(tuple(document["evidence"]), CAPSTONE_EVIDENCE_KINDS)
                self.assertTrue(
                    all(
                        _nonempty(document["evidence"][kind])
                        for kind in CAPSTONE_EVIDENCE_KINDS
                    )
                )
                self.assertTrue(set(document["lessonIds"]) <= set(LESSON_IDS))
                for lesson_id, exercise in document["primaryExercises"].items():
                    self.assertNotIn(lesson_id, primary_owners)
                    self.assertTrue(_nonempty(exercise))
                    primary_owners[lesson_id] = document["id"]

        self.assertEqual(primary_owners, EXPECTED_PRIMARY_OWNER)
        self.assertEqual(len(primary_owners), 30)

    def test_capstone_parser_rejects_one_owner_for_all_primary_exercises(
        self,
    ) -> None:
        root = REPOSITORY_ROOT / "content/capstones"
        mutated = {
            capstone_id: json.loads(
                (root / f"{capstone_id}.json").read_bytes()
            )
            for capstone_id in CAPSTONE_IDS
        }
        all_exercises = {
            lesson_id: document["primaryExercises"][lesson_id]
            for document in mutated.values()
            for lesson_id in document["primaryExercises"]
        }
        self.assertEqual(frozenset(all_exercises), frozenset(LESSON_IDS))
        for capstone_id, document in mutated.items():
            document["primaryExercises"] = (
                all_exercises if capstone_id == "global-service" else {}
            )
        mutated["global-service"]["lessonIds"] = list(LESSON_IDS)

        with self.assertRaises(CurriculumValidationError):
            parse_capstone_documents(
                {
                    f"{capstone_id}.json": _json_bytes(mutated[capstone_id])
                    for capstone_id in CAPSTONE_IDS
                },
                expected_lesson_ids=frozenset(LESSON_IDS),
            )

    def test_canonical_lessons_are_complete_regular_file_pairs(self) -> None:
        lessons_root = REPOSITORY_ROOT / "content/lessons"
        self.assertTrue(stat.S_ISDIR(lessons_root.lstat().st_mode))

        lesson_directories = tuple(sorted(lessons_root.iterdir()))
        self.assertEqual(
            tuple(path.name for path in lesson_directories),
            LESSON_IDS,
        )
        for ordinal, (lesson_id, directory) in enumerate(
            zip(LESSON_IDS, lesson_directories, strict=True), start=1
        ):
            with self.subTest(lesson_id=lesson_id):
                self.assertTrue(stat.S_ISDIR(directory.lstat().st_mode))
                self.assertFalse(directory.is_symlink())
                self.assertTrue(lesson_id.startswith(f"core-{ordinal:02d}-"))

                entries = tuple(sorted(directory.iterdir()))
                self.assertEqual(
                    tuple(path.name for path in entries),
                    ("body.html", "lesson.json"),
                )
                for path in entries:
                    self.assertTrue(
                        stat.S_ISREG(path.lstat().st_mode),
                        f"{path}: must be a regular file",
                    )
                    self.assertFalse(path.is_symlink())

                document = json.loads(
                    (directory / "lesson.json").read_text(encoding="utf-8")
                )
                self.assertEqual(document["id"], lesson_id)
                self.assertEqual(document["status"], "complete")

    def test_v01_migration_oracle_freezes_figures_residuals_and_sources(self) -> None:
        oracle = json.loads(MIGRATION_ORACLE.read_bytes())
        self.assertEqual(
            set(oracle),
            {
                "version",
                "baselineCommit",
                "figures",
                "residualBodies",
                "sourceProjections",
            },
        )
        self.assertEqual(oracle["version"], 1)
        self.assertEqual(
            oracle["baselineCommit"],
            "267c3233a70b5f6541db175c2295c44df6f39ca9",
        )

        actual_figures: list[dict[str, object]] = []
        actual_residuals: list[dict[str, str]] = []
        actual_sources: list[dict[str, object]] = []
        for lesson_id in LESSON_IDS:
            lesson_root = REPOSITORY_ROOT / "content/lessons" / lesson_id
            body = (lesson_root / "body.html").read_text(encoding="utf-8")
            if lesson_id in TASK5_VISUAL_TYPES or lesson_id in TASK6_VISUAL_TYPES or lesson_id in TASK7_VISUAL_TYPES:
                if lesson_id == "core-17-graphics-visual-information":
                    self.assertEqual(body.count("<figure"), 1)
                else:
                    self.assertNotIn("<figure", body)
                residual_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
            else:
                figures, residual_sha256 = _legacy_figure_projection(
                    lesson_id, body
                )
                actual_figures.extend(figures)
            actual_residuals.append(
                {"lessonId": lesson_id, "sha256": residual_sha256}
            )
            sources = json.loads(
                (lesson_root / "lesson.json").read_bytes()
            )["sources"]
            self.assertEqual(
                tuple(source["id"] for source in sources),
                tuple(f"src-{index:02d}" for index in range(1, len(sources) + 1)),
            )
            self.assertTrue(
                all(set(source) == {"id", "title", "url", "kind"} for source in sources)
            )
            actual_sources.append(
                {
                    "lessonId": lesson_id,
                    "sources": [
                        {
                            "title": source["title"],
                            "url": source["url"],
                            "kind": source["kind"],
                        }
                        for source in sources
                    ],
                }
            )

        expected_remaining_figures = [
            item
            for item in oracle["figures"]
            if item["lessonId"] not in TASK5_VISUAL_TYPES
            and item["lessonId"] not in TASK6_VISUAL_TYPES
            and item["lessonId"] not in TASK7_VISUAL_TYPES
        ]
        self.assertEqual(len(actual_figures), 0)
        self.assertEqual(
            [
                (item["lessonId"], item["sectionRole"], item["caption"])
                for item in actual_figures
                if item["disposition"] == "retain"
            ],
            [],
        )
        self.assertEqual(actual_figures, expected_remaining_figures)
        self.assertEqual(actual_residuals, oracle["residualBodies"])
        self.assertEqual(actual_sources, oracle["sourceProjections"])
        self.assertEqual(
            sum(len(item["sources"]) for item in actual_sources),
            126,
        )

    def test_task7_remaining_lessons_have_exact_primary_types_and_preserve_legacy_facts(self) -> None:
        oracle = json.loads(MIGRATION_ORACLE.read_bytes())
        legacy = {
            item["lessonId"]: item
            for item in oracle["figures"]
            if item["lessonId"] in TASK7_VISUAL_TYPES and item["disposition"] == "migrate"
        }
        for lesson_id, expected_type in TASK7_VISUAL_TYPES.items():
            with self.subTest(lesson_id=lesson_id):
                root = REPOSITORY_ROOT / "content/lessons" / lesson_id
                document = json.loads((root / "lesson.json").read_bytes())
                visual = document["visualizations"][0]
                self.assertEqual(visual["type"], expected_type)
                self.assertEqual(visual["caption"], legacy[lesson_id]["caption"])
                if lesson_id not in TASK9_SIMULATION_CONTRACTS:
                    self.assertNotIn("simulation", visual)
                rendered = str(render_visualization(
                    lesson_id,
                    load_lesson_bytes((root / "lesson.json").read_bytes(), "lesson.json").visualizations[0],
                ))
                for atom in legacy[lesson_id]["visibleAtoms"]:
                    if (
                        lesson_id == "core-11-data-modeling-storage"
                        and atom == "商品・期間検索が主要queryになったらfrequencyとratingを変え、scoreとwinnerを再計算する。"
                    ):
                        # The legacy wording incorrectly treated query-fit
                        # rating as a changed input. The exact Task 7 contract
                        # above freezes the corrected input/derived boundary.
                        self.assertNotIn(escape(atom), rendered)
                        continue
                    self.assertIn(escape(atom), rendered)

    def test_complete_lesson_set_matches_every_catalog_assignment_exactly(self) -> None:
        catalog_path = REPOSITORY_ROOT / "content/visualization-catalog.json"
        catalog = parse_visualization_catalog_bytes(catalog_path.read_bytes(), catalog_path.name)
        visuals = {}
        for lesson_id in LESSON_IDS:
            path = REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json"
            visuals[lesson_id] = load_lesson_bytes(path.read_bytes(), path.name).visualizations

        validate_visualization_assignments(catalog, visuals)

        swapped = json.loads(catalog_path.read_bytes())
        swapped["lessons"][0]["primaryType"], swapped["lessons"][1]["primaryType"] = (
            swapped["lessons"][1]["primaryType"], swapped["lessons"][0]["primaryType"]
        )
        mutated = parse_visualization_catalog_bytes(_json_bytes(swapped), "swapped.json")
        with self.assertRaisesRegex(CurriculumValidationError, "primary visualization type"):
            validate_visualization_assignments(mutated, visuals)

    def test_visualization_catalog_rejects_coverage_secondary_and_simulation_mutations(self) -> None:
        catalog_path = REPOSITORY_ROOT / "content/visualization-catalog.json"
        catalog = parse_visualization_catalog_bytes(
            catalog_path.read_bytes(), catalog_path.name
        )
        visuals = {}
        for lesson_id in LESSON_IDS:
            path = REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json"
            visuals[lesson_id] = load_lesson_bytes(
                path.read_bytes(), path.name
            ).visualizations

        missing = dict(visuals)
        missing.pop("core-30-evidence-based-technical-leadership")
        with self.assertRaisesRegex(CurriculumValidationError, "exact catalog lesson IDs"):
            validate_visualization_assignments(catalog, missing)

        extra = dict(visuals)
        extra["core-31-unapproved"] = visuals["core-30-evidence-based-technical-leadership"]
        with self.assertRaisesRegex(CurriculumValidationError, "exact catalog lesson IDs"):
            validate_visualization_assignments(catalog, extra)

        wrong_secondary = dict(visuals)
        wrong_secondary["core-01-systems-tradeoffs"] = (
            visuals["core-01-systems-tradeoffs"][0],
            visuals["core-16-hci-usability-accessibility"][0],
        )
        with self.assertRaisesRegex(CurriculumValidationError, "unapproved secondary"):
            validate_visualization_assignments(catalog, wrong_secondary)

        accepted_secondary = dict(visuals)
        accepted_secondary["core-01-systems-tradeoffs"] = (
            visuals["core-01-systems-tradeoffs"][0],
            visuals["core-11-data-modeling-storage"][0],
        )
        validate_visualization_assignments(catalog, accepted_secondary)
        swapped_document = json.loads(catalog_path.read_bytes())
        swapped_document["lessons"][0]["optionalSecondaryType"] = "flow"
        swapped_catalog = parse_visualization_catalog_bytes(
            _json_bytes(swapped_document), "optional-swap.json"
        )
        with self.assertRaisesRegex(CurriculumValidationError, "unapproved secondary"):
            validate_visualization_assignments(swapped_catalog, accepted_secondary)

        unapproved_static = dict(visuals)
        unapproved_static["core-01-systems-tradeoffs"] = (
            replace(visuals["core-01-systems-tradeoffs"][0], simulation=object()),
        )
        with self.assertRaisesRegex(CurriculumValidationError, "unapproved simulation"):
            validate_visualization_assignments(catalog, unapproved_static)

        broken_dynamic_relation = dict(visuals)
        broken_dynamic_relation["core-02-algorithms-measurement"] = (
            replace(
                visuals["core-02-algorithms-measurement"][0],
                id="wrong-static-equivalent",
                simulation=object(),
            ),
        )
        with self.assertRaisesRegex(CurriculumValidationError, "unapproved simulation"):
            validate_visualization_assignments(catalog, broken_dynamic_relation)

    def test_production_build_rejects_a_catalog_assignment_mutation(self) -> None:
        with TemporaryDirectory(
            prefix=".catalog-assignment-",
            dir=REPOSITORY_ROOT.parent,
        ) as temporary:
            root = Path(temporary)
            content = root / "content"
            shutil.copytree(REPOSITORY_ROOT / "content", content)
            catalog_path = content / "visualization-catalog.json"
            document = json.loads(catalog_path.read_bytes())
            document["lessons"][0]["primaryType"] = "network"
            catalog_path.write_bytes(_json_bytes(document))
            # The catalog remains schema-valid; failure must come from the
            # production build's release-wide assignment validation.
            parse_visualization_catalog_bytes(
                catalog_path.read_bytes(), catalog_path.name
            )
            with self.assertRaisesRegex(
                CurriculumValidationError, "wrong primary visualization type"
            ):
                build_site(
                    content,
                    REPOSITORY_ROOT / "templates",
                    REPOSITORY_ROOT / "static",
                    root / "site",
                    require_complete_curriculum=True,
                )

    def test_task7_readable_contracts_freeze_every_structured_row_and_relation(self) -> None:
        self.assertEqual(set(TASK7_COMMON_CONTRACTS), set(TASK7_VISUAL_TYPES))
        self.assertEqual(set(TASK7_PAYLOAD_CONTRACTS), set(TASK7_VISUAL_TYPES))
        self.assertEqual(set(TASK7_VISUAL_CONTRACT_SHA256), set(TASK7_VISUAL_TYPES))
        for lesson_id, expected in TASK7_STRUCTURE_IDS.items():
            with self.subTest(lesson_id=lesson_id):
                path = REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json"
                visual = json.loads(path.read_bytes())["visualizations"][0]
                static_visual = dict(visual)
                static_visual.pop("simulation", None)
                self.assertEqual(
                    (
                        static_visual["id"], static_visual["type"], static_visual["afterSection"],
                        static_visual.get("simulation"), static_visual["caption"],
                        static_visual["question"], static_visual["expectedObservation"],
                        tuple(static_visual["objectiveIds"]), tuple(static_visual["evidenceIds"]),
                        tuple(static_visual["sourceIds"]), tuple(static_visual.get("notes", ())),
                    ),
                    TASK7_COMMON_CONTRACTS[lesson_id],
                )
                payload = visual["payload"]
                self.assertEqual(payload, TASK7_PAYLOAD_CONTRACTS[lesson_id])
                encoded = json.dumps(
                    static_visual, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                self.assertEqual(
                    hashlib.sha256(encoded).hexdigest(),
                    TASK7_VISUAL_CONTRACT_SHA256[lesson_id],
                )
                for group, expected_ids in expected.items():
                    items = payload[group]
                    self.assertEqual(tuple(item["id"] for item in items), expected_ids)
                    for item in items:
                        if group in {"transitions", "transfers"}:
                            self.assertTrue(item["from"])
                            self.assertTrue(item["to"])
                            self.assertTrue(item["label"])
                        elif group == "cells":
                            self.assertTrue(item["value"])
                        else:
                            self.assertTrue(item["label"])
                            self.assertTrue(item["detail"])

        memory = json.loads((REPOSITORY_ROOT / "content/lessons/core-03-architecture-memory-caches/lesson.json").read_bytes())["visualizations"][0]
        self.assertIn("translation", memory["question"])
        lower = next(
            item for item in memory["payload"]["layers"]
            if item["id"] == "lower-cache"
        )
        self.assertIn("固定latencyではない", lower["detail"])
        complexity = json.loads((REPOSITORY_ROOT / "content/lessons/core-02-algorithms-measurement/lesson.json").read_bytes())["visualizations"][0]
        self.assertEqual(
            tuple(item["label"] for item in complexity["payload"]["criteria"]),
            (
                "best case", "average case", "worst case",
                "setup / build cost", "space cost", "query count / crossover",
            ),
        )
        hierarchy = json.loads((REPOSITORY_ROOT / "content/lessons/core-19-technical-communication-design-docs/lesson.json").read_bytes())["visualizations"][0]
        self.assertEqual(tuple(item["parentId"] for item in hierarchy["payload"]["nodes"]), (None, "decision-record", "decision-record", "audience", "audience", "evidence", "evidence"))

    def test_task7_readable_contract_detects_structure_and_detail_mutations(self) -> None:
        def load_visual(lesson_id: str) -> dict[str, object]:
            path = REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json"
            return json.loads(path.read_bytes())["visualizations"][0]

        def assert_contract(lesson_id: str, visual: dict[str, object]) -> None:
            self.assertEqual(
                (
                    visual["id"], visual["type"], visual["afterSection"],
                    visual.get("simulation"), visual["caption"], visual["question"],
                    visual["expectedObservation"], tuple(visual["objectiveIds"]),
                    tuple(visual["evidenceIds"]), tuple(visual["sourceIds"]),
                    tuple(visual.get("notes", ())),
                ),
                TASK7_COMMON_CONTRACTS[lesson_id],
            )
            self.assertEqual(visual["payload"], TASK7_PAYLOAD_CONTRACTS[lesson_id])

        mutations: list[tuple[str, dict[str, object]]] = []

        memory = load_visual("core-03-architecture-memory-caches")
        memory["payload"]["transfers"][2]["label"] = "TLB結果を常に無視する"
        mutations.append(("core-03-architecture-memory-caches", memory))

        matrix = load_visual("core-11-data-modeling-storage")
        matrix["payload"]["cells"][0]["value"] = "baseline total 5.0"
        mutations.append(("core-11-data-modeling-storage", matrix))

        hierarchy = load_visual("core-19-technical-communication-design-docs")
        hierarchy["payload"]["nodes"][3]["detail"] = "実装詳細を意思決定から切り離す。"
        mutations.append(("core-19-technical-communication-design-docs", hierarchy))

        sources = load_visual("core-28-oss-governance-stewardship")
        sources["sourceIds"] = ["src-02", "src-01", "src-03", "src-04", "src-05"]
        mutations.append(("core-28-oss-governance-stewardship", sources))

        placement = load_visual("core-02-algorithms-measurement")
        placement["afterSection"] = "workedExample"
        mutations.append(("core-02-algorithms-measurement", placement))

        for lesson_id, mutated in mutations:
            with self.subTest(lesson_id=lesson_id), self.assertRaises(AssertionError):
                assert_contract(lesson_id, mutated)

    def test_task7_core11_matrix_reproduces_the_worked_example_calculations(self) -> None:
        path = REPOSITORY_ROOT / "content/lessons/core-11-data-modeling-storage/lesson.json"
        visual = json.loads(path.read_bytes())["visualizations"][0]
        payload = visual["payload"]
        self.assertEqual(
            tuple(column["id"] for column in payload["columns"]),
            ("access-fit", "constraint", "capacity", "operations", "recovery"),
        )
        values = {cell["id"]: cell["value"] for cell in payload["cells"]}
        expected = {
            "relational-access": "baseline (480×5 + 360×3 + 48×1 + 90×4) / 978 = 3.975460; changed (24×5 + 360×3 + 480×1 + 90×4) / 954 = 2.138365; weight 0.45",
            "relational-constraint": "rating 5 × 0.20 = 1.00",
            "relational-capacity": "rating 4 × 0.15 = 0.60",
            "relational-operations": "rating 4 × 0.10 = 0.40",
            "relational-recovery": "rating 5 × 0.10 = 0.50; baseline total 4.288957; changed total 3.462264",
            "document-access": "baseline (480×4 + 360×5 + 48×2 + 90×4) / 978 = 4.269939; changed (24×4 + 360×5 + 480×2 + 90×4) / 954 = 3.371069; weight 0.45",
            "document-constraint": "rating 3 × 0.20 = 0.60",
            "document-capacity": "rating 4 × 0.15 = 0.60",
            "document-operations": "rating 3 × 0.10 = 0.30",
            "document-recovery": "rating 3 × 0.10 = 0.30; baseline total 3.721472; changed total 3.316981",
            "key-value-access": "baseline (480×2 + 360×4 + 48×5 + 90×2) / 978 = 2.883436; changed (24×2 + 360×4 + 480×5 + 90×2) / 954 = 4.264151; weight 0.45",
            "key-value-constraint": "rating 2 × 0.20 = 0.40",
            "key-value-capacity": "rating 5 × 0.15 = 0.75",
            "key-value-operations": "rating 2 × 0.10 = 0.20",
            "key-value-recovery": "rating 4 × 0.10 = 0.40; baseline total 3.047546; changed total 3.668868",
        }
        self.assertEqual(values, expected)
        self.assertTrue(any("baseline total 4.288957" in note for note in visual["notes"]))
        self.assertTrue(any("changed total 3.668868" in note for note in visual["notes"]))

    def test_task7_core11_distinguishes_changed_input_from_derived_rating(self) -> None:
        path = REPOSITORY_ROOT / "content/lessons/core-11-data-modeling-storage/lesson.json"
        visual = json.loads(path.read_bytes())["visualizations"][0]
        self.assertEqual(
            visual["question"],
            "query frequencyだけを変え、固定したquery-fit ratingから何を再計算するか。",
        )
        self.assertEqual(
            visual["expectedObservation"],
            "changed inputはfrequencyだけで、query-fit ratingは固定され、導出されるaccess-fit rating、weighted score、winnerが順に変わり得ることを説明できる。",
        )
        self.assertIn(
            "mutation: 商品・期間検索が主要queryになったらfrequencyだけを変える。query-fit ratingは固定し、access-fit rating、weighted score、winnerを再計算する。",
            visual["notes"],
        )
        semantic_text = " ".join(
            (visual["question"], visual["expectedObservation"], *visual["notes"])
        )
        self.assertNotIn("frequencyとratingを変", semantic_text)
        self.assertNotIn("ratingを変更", semantic_text)

    def test_task7_core25_matrix_reproduces_cost_and_sensitivity_arithmetic(self) -> None:
        path = REPOSITORY_ROOT / "content/lessons/core-25-engineering-economics-capacity/lesson.json"
        visual = json.loads(path.read_bytes())["visualizations"][0]
        payload = visual["payload"]
        self.assertEqual(tuple(row["id"] for row in payload["rows"]), ("scale-up", "automation"))
        self.assertEqual(
            tuple(column["id"] for column in payload["columns"]),
            ("direct", "opportunity", "operations", "reliability", "capacity-unit", "sensitivity"),
        )
        values = {cell["id"]: cell["value"] for cell in payload["cells"]}
        self.assertEqual(values, {
            "scale-direct": "12000",
            "scale-opportunity": "40×100 = 4000",
            "scale-operations": "20×80 = 1600",
            "scale-reliability": "0.05×8×10000 = 4000",
            "scale-total": "12000 + 40×100 + 20×80 + 0.05×8×10000 = 21600; 21600/800 = 27.00/unit",
            "scale-sensitivity": "growth 0.25でrequired capacity 1000、headroom 0; 0.25超でbreach",
            "automation-direct": "16000",
            "automation-opportunity": "120×100 = 12000",
            "automation-operations": "5×80 = 400",
            "automation-reliability": "0.01×2×10000 = 200",
            "automation-total": "16000 + 120×100 + 5×80 + 0.01×2×10000 = 28600; 28600/800 = 35.75/unit",
            "automation-sensitivity": "growth 0.5でrequired capacity 1200、headroom 400、automationを選択",
        })

    def test_task7_core17_branches_visual_and_text_from_transform_before_verify(self) -> None:
        path = REPOSITORY_ROOT / "content/lessons/core-17-graphics-visual-information/lesson.json"
        transitions = json.loads(path.read_bytes())["visualizations"][0]["payload"]["transitions"]
        edges = {(edge["from"], edge["to"]) for edge in transitions}
        self.assertEqual(edges, {("data", "transform"), ("transform", "visual"), ("transform", "equivalent"), ("visual", "verify"), ("equivalent", "verify")})
        self.assertNotIn(("visual", "equivalent"), edges)

    def test_task7_core03_models_translation_and_data_hit_miss_branches(self) -> None:
        path = REPOSITORY_ROOT / "content/lessons/core-03-architecture-memory-caches/lesson.json"
        visual = json.loads(path.read_bytes())["visualizations"][0]
        edges = {(edge["from"], edge["to"], edge["kind"]) for edge in visual["payload"]["transfers"]}
        for required in {
            ("tlb", "address-ready", "tlb-hit"),
            ("tlb", "page-table", "tlb-miss"),
            ("l1-cache", "return", "l1-hit"),
            ("l1-cache", "lower-cache", "l1-miss"),
            ("lower-cache", "return", "lower-hit"),
            ("lower-cache", "memory-controller", "lower-miss"),
        }:
            self.assertIn(required, edges)
        self.assertIn(("instruction", "l1-cache", "vipt-parallel-index"), edges)
        self.assertNotIn(("memory-controller", "reuse", "data-transfer"), edges)
        self.assertTrue(
            any("普遍的な逐次latencyではない" in note for note in visual["notes"])
        )

    def test_task7_core02_includes_build_space_query_count_and_crossover(self) -> None:
        path = REPOSITORY_ROOT / "content/lessons/core-02-algorithms-measurement/lesson.json"
        visual = json.loads(path.read_bytes())["visualizations"][0]
        criteria = tuple(item["id"] for item in visual["payload"]["criteria"])
        self.assertEqual(criteria, ("best-case", "average-case", "worst-case", "setup-cost", "space-cost", "query-crossover"))
        self.assertIn("構築済みlookup", visual["question"])
        values = {cell["id"]: cell["value"] for cell in visual["payload"]["cells"]}
        self.assertIn("set構築Θ(n)", values["hash-setup"])
        self.assertIn("query回数", values["hash-crossover"])

    def test_core17_retains_distinct_worked_example_chart_byte_exact(self) -> None:
        lesson_id = "core-17-graphics-visual-information"
        body = (REPOSITORY_ROOT / "content/lessons" / lesson_id / "body.html").read_text(encoding="utf-8")
        retained = re.search(
            r'^  <figure class="quantitative-chart-artifact">.*?^  </figure>\n',
            body,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(retained)
        self.assertEqual(
            hashlib.sha256(retained.group(0).encode("utf-8")).hexdigest(),
            "a25cdd9fd76cdc729127062d50373851a39a0b14000aa6d3640bcd93f6fa13da",
        )

    def test_task5_causal_and_network_visuals_preserve_ordered_legacy_facts(self) -> None:
        oracle = json.loads(MIGRATION_ORACLE.read_bytes())
        legacy_by_lesson = {
            item["lessonId"]: item
            for item in oracle["figures"]
            if item["lessonId"] in TASK5_VISUAL_TYPES
        }

        for lesson_id, expected_type in TASK5_VISUAL_TYPES.items():
            with self.subTest(lesson_id=lesson_id):
                lesson_root = REPOSITORY_ROOT / "content/lessons" / lesson_id
                document = json.loads((lesson_root / "lesson.json").read_bytes())
                lesson = load_lesson_bytes(
                    (lesson_root / "lesson.json").read_bytes(), "lesson.json"
                )
                self.assertEqual(len(lesson.visualizations), 1)
                visual = document["visualizations"][0]
                self.assertEqual(visual["type"], expected_type)
                self.assertEqual(
                    visual["caption"], legacy_by_lesson[lesson_id]["caption"]
                )
                if lesson_id not in TASK10_SIMULATION_CONTRACTS:
                    self.assertNotIn("simulation", visual)
                self.assertTrue(visual["objectiveIds"])
                self.assertTrue(visual["evidenceIds"])
                self.assertTrue(visual["sourceIds"])
                self.assertTrue(visual["expectedObservation"].strip())

                objectives = {
                    item["id"]: set(item["evidenceIds"])
                    for item in document["objectives"]
                }
                reachable = set().union(
                    *(objectives[item] for item in visual["objectiveIds"])
                )
                self.assertLessEqual(set(visual["evidenceIds"]), reachable)

                payload = visual["payload"]
                if expected_type == "causal":
                    items = [
                        item
                        for group in (
                            "causes",
                            "mechanisms",
                            "outcomes",
                            "mitigations",
                        )
                        for item in payload[group]
                    ]
                    relations = payload["relations"]
                else:
                    items = payload["nodes"]
                    relations = payload["connections"]
                semantic_values = [
                    visual["caption"],
                    visual["question"],
                    visual["expectedObservation"],
                    *visual.get("notes", []),
                    *(
                        value
                        for component in payload.get("components", [])
                        for value in (component["label"], component["detail"])
                    ),
                    *(
                        value
                        for relation in relations
                        for value in (relation["label"],)
                    ),
                    *(
                        value
                        for item in items
                        for value in (item["label"], item["detail"])
                    ),
                ]
                expected_atoms = [
                    atom[:-1] if atom.endswith(":") else atom
                    for atom in legacy_by_lesson[lesson_id]["visibleAtoms"]
                ]
                for atom in expected_atoms:
                    self.assertTrue(
                        any(atom in value for value in semantic_values),
                        f"{lesson_id}: missing legacy fact atom {atom!r}",
                    )
                self.assertTrue(relations)
                self.assertTrue(
                    all(relation["label"].strip() for relation in relations)
                )

    def test_task6_timeline_and_state_assignments_are_static_and_preserve_legacy_facts(
        self,
    ) -> None:
        legacy_by_lesson = {
            entry["lessonId"]: entry
            for entry in json.loads(MIGRATION_ORACLE.read_bytes())["figures"]
        }
        for lesson_id, expected_type in TASK6_VISUAL_TYPES.items():
            with self.subTest(lesson_id=lesson_id):
                path = (
                    REPOSITORY_ROOT
                    / "content/lessons"
                    / lesson_id
                    / "lesson.json"
                )
                document = json.loads(path.read_bytes())
                expected_count = 2 if lesson_id in TASK9_SIMULATION_CONTRACTS else 1
                self.assertEqual(len(document.get("visualizations", [])), expected_count)
                visual = document["visualizations"][0]
                self.assertEqual(visual["type"], expected_type)
                self.assertEqual(
                    visual["caption"], legacy_by_lesson[lesson_id]["caption"]
                )
                self.assertEqual(visual["afterSection"], "mentalModel")
                if lesson_id not in TASK10_SIMULATION_CONTRACTS:
                    self.assertNotIn("simulation", visual)
                semantic_text = json.dumps(visual, ensure_ascii=False)
                for atom in legacy_by_lesson[lesson_id]["visibleAtoms"]:
                    normalized = atom[:-1] if atom.endswith(":") else atom
                    self.assertIn(normalized, semantic_text)
                load_lesson_bytes(path.read_bytes(), "lesson.json")

    def test_task6_visual_contracts_freeze_every_ordered_authored_field(self) -> None:
        self.assertEqual(set(TASK6_VISUAL_CONTRACTS), set(TASK6_VISUAL_TYPES))
        self.assertEqual(set(TASK6_VISUAL_CONTRACT_SHA256), set(TASK6_VISUAL_TYPES))
        for lesson_id, expected in TASK6_VISUAL_CONTRACTS.items():
            with self.subTest(lesson_id=lesson_id):
                path = REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json"
                document = json.loads(path.read_bytes())
                self.assertEqual(_task6_visual_projection(document), expected)
                self.assertEqual(
                    _task6_visual_contract_sha256(document),
                    TASK6_VISUAL_CONTRACT_SHA256[lesson_id],
                )

    def test_task6_readable_contract_rejects_semantic_mutations_even_with_a_new_hash(
        self,
    ) -> None:
        def document(lesson_id: str) -> dict[str, object]:
            path = REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json"
            return json.loads(path.read_bytes())

        reversed_timeline = document("core-05-networks-latency-failure")
        reversed_timeline["visualizations"][0]["payload"]["events"].reverse()
        self.assertNotEqual(
            _task6_visual_projection(reversed_timeline),
            TASK6_VISUAL_CONTRACTS["core-05-networks-latency-failure"],
        )
        self.assertNotEqual(
            _task6_visual_contract_sha256(reversed_timeline),
            TASK6_VISUAL_CONTRACT_SHA256["core-05-networks-latency-failure"],
        )

        status_flip = document("core-24-delivery-ci-release-safety")
        builder = next(
            edge
            for edge in status_flip["visualizations"][0]["payload"]["transitions"]
            if edge["id"] == "builder-mismatch"
        )
        builder["status"] = "allowed"
        builder.pop("reason")
        self.assertNotEqual(
            _task6_visual_projection(status_flip),
            TASK6_VISUAL_CONTRACTS["core-24-delivery-ci-release-safety"],
        )

        source_swap = document("core-13-distributed-coordination-failure")
        source_swap["visualizations"][0]["sourceIds"] = ["src-01", "src-02"]
        self.assertNotEqual(
            _task6_visual_projection(source_swap),
            TASK6_VISUAL_CONTRACTS["core-13-distributed-coordination-failure"],
        )

        detail_swap = document("core-04-os-processes-concurrency")
        events = detail_swap["visualizations"][0]["payload"]["events"]
        events[3]["detail"], events[4]["detail"] = (
            events[4]["detail"], events[3]["detail"]
        )
        self.assertNotEqual(
            _task6_visual_projection(detail_swap),
            TASK6_VISUAL_CONTRACTS["core-04-os-processes-concurrency"],
        )

        exit_outgoing = document("core-26-code-review-collaborative-quality")
        exit_outgoing["visualizations"][0]["payload"]["transitions"].append(
            {
                "id": "incorrect-exit-feedback",
                "from": "evidence-ready",
                "to": "scope",
                "label": "誤ったexit outgoing",
            }
        )
        self.assertNotEqual(
            _task6_visual_projection(exit_outgoing),
            TASK6_VISUAL_CONTRACTS["core-26-code-review-collaborative-quality"],
        )

    def test_task6_questions_and_observations_name_lesson_specific_judgments(
        self,
    ) -> None:
        self.assertEqual(set(TASK6_LESSON_JUDGMENT_TEXT), set(TASK6_VISUAL_TYPES))
        forbidden = {
            "どの順序と境界が、途中の観測を最終判断へ結ぶか。",
            "どのfeedbackと回復経路が、証拠の揃ったexitへ導くか。",
            "どの証拠で遷移を許可または拒否し、安全な回復へ進むか。",
        }
        for lesson_id, expected in TASK6_LESSON_JUDGMENT_TEXT.items():
            with self.subTest(lesson_id=lesson_id):
                path = REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json"
                visual = json.loads(path.read_bytes())["visualizations"][0]
                actual = (visual["question"], visual["expectedObservation"])
                self.assertEqual(actual, expected)
                self.assertNotIn(actual[0], forbidden)

    def test_task6_release_migration_and_slo_models_have_safe_terminal_semantics(
        self,
    ) -> None:
        def payload(lesson_id: str) -> dict[str, object]:
            path = REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json"
            return json.loads(path.read_bytes())["visualizations"][0]["payload"]

        release = payload("core-24-delivery-ci-release-safety")
        self.assertEqual(
            tuple(state["id"] for state in release["states"]),
            (
                "ci", "artifact", "provenance", "canary", "decision",
                "promoted", "stopped", "rolling-back",
                "restoration-verified", "outcome",
            ),
        )
        release_edges = tuple(
            (
                edge["id"], edge["from"], edge["to"],
                edge["event"], edge["status"], edge.get("reason"),
            )
            for edge in release["transitions"]
        )
        self.assertEqual(
            release_edges,
            (
                ("checks-known-pass", "ci", "artifact", "next", "allowed", None),
                ("checks-missing-unknown-stop", "ci", "stopped", "reset", "allowed", None),
                ("artifact-to-provenance", "artifact", "provenance", "next", "allowed", None),
                ("provenance-to-canary", "provenance", "canary", "next", "allowed", None),
                ("canary-to-decision", "canary", "decision", "next", "allowed", None),
                ("threshold-within-promote", "decision", "promoted", "next", "allowed", None),
                ("threshold-exceeded-rollback", "decision", "rolling-back", "previous", "allowed", None),
                ("promote-outcome", "promoted", "outcome", "next", "allowed", None),
                ("stop-cause-resolved-rerun", "stopped", "ci", "reset", "allowed", None),
                ("rollback-restoration", "rolling-back", "restoration-verified", "next", "allowed", None),
                ("restoration-outcome", "restoration-verified", "outcome", "next", "allowed", None),
                ("checks-not-passed", "ci", "artifact", "timer", "rejected", "required checkがmissing、unknown、failedの時はartifact確定へ進まずstopする。"),
                ("digest-mismatch", "artifact", "provenance", "timer", "rejected", "subject digestが配信対象bytesと一致しない時はprovenanceを受理しない。"),
                ("builder-mismatch", "provenance", "canary", "timer", "rejected", "trusted builderと一致しないprovenanceではcanaryへ進まない。"),
                ("skip-decision", "canary", "outcome", "next", "rejected", "canary thresholdからpromoteまたはrollbackを決める前にoutcomeへ進まない。"),
            ),
        )
        self.assertFalse(
            any(
                edge["from"] == "decision" and edge["to"] == "stopped"
                for edge in release["transitions"]
            )
        )
        self.assertFalse(
            any(
                edge["from"] == "stopped" and edge["to"] == "outcome"
                for edge in release["transitions"]
            )
        )
        stopped = next(state for state in release["states"] if state["id"] == "stopped")
        self.assertIn("required check", stopped["label"])
        self.assertIn("missing、unknown", stopped["detail"])
        self.assertIn("原因を解消", stopped["detail"])
        self.assertIn("全gate", stopped["detail"])
        current_model_text = json.dumps(
            {
                "states": release["states"],
                "transitions": release["transitions"],
            },
            ensure_ascii=False,
        )
        self.assertNotIn("advance", current_model_text)
        self.assertIn("promote", current_model_text)

        migration = payload("core-22-evolution-safe-migrations")
        self.assertEqual(
            tuple(state["id"] for state in migration["states"]),
            (
                "expand", "dual-write", "backfill", "dual-read", "contract",
                "dual-write-compatible", "backfill-compatible",
                "dual-read-compatible", "restoration-verified",
            ),
        )
        migration_edges = tuple(
            (edge["from"], edge["to"], edge["event"], edge["status"])
            for edge in migration["transitions"]
        )
        self.assertEqual(
            migration_edges,
            (
                ("expand", "dual-write", "next", "allowed"),
                ("dual-write", "backfill", "next", "allowed"),
                ("backfill", "dual-read", "next", "allowed"),
                ("dual-read", "contract", "next", "allowed"),
                ("dual-write", "dual-write-compatible", "reset", "allowed"),
                ("backfill", "backfill-compatible", "reset", "allowed"),
                ("dual-read", "dual-read-compatible", "reset", "allowed"),
                ("dual-write-compatible", "restoration-verified", "next", "allowed"),
                ("backfill-compatible", "restoration-verified", "next", "allowed"),
                ("dual-read-compatible", "restoration-verified", "next", "allowed"),
                ("dual-write", "backfill", "timer", "rejected"),
                ("backfill", "dual-read", "timer", "rejected"),
                ("dual-read", "contract", "timer", "rejected"),
            ),
        )

        slo = payload("core-15-reliability-observability-slo")
        slo_path = (
            REPOSITORY_ROOT
            / "content/lessons/core-15-reliability-observability-slo/lesson.json"
        )
        slo_visual = json.loads(slo_path.read_bytes())["visualizations"][0]
        self.assertEqual(
            tuple(slo_visual["notes"]),
            (
                TASK5_READING_ORDER_MARKER,
                "Journey: 利用者が達成したい結果とvalidな試行を定める。",
                "SLI: goodの結果とlatency境界をevent単位で計算する。",
                "SLO: window、target、error budget、例外を合意する。",
                "Alert: 短窓と長窓のburnをpageとticketへ分ける。",
                "Runbook: impact確認、mitigation、rollback、escalationを結ぶ。",
                "Telemetry: traceで原因へ相関し、意味とprivacyを検証する。",
            ),
        )
        self.assertEqual(
            tuple(state["id"] for state in slo["states"]),
            ("journey", "sli", "slo", "telemetry", "alert", "runbook", "evidence-ready"),
        )
        self.assertEqual(slo["exitStateId"], "evidence-ready")
        self.assertEqual(
            tuple((edge["from"], edge["to"]) for edge in slo["transitions"]),
            (
                ("journey", "sli"), ("sli", "slo"),
                ("slo", "telemetry"), ("telemetry", "alert"),
                ("alert", "runbook"), ("runbook", "telemetry"),
                ("runbook", "evidence-ready"),
            ),
        )
        self.assertFalse(
            any(
                edge["from"] == slo["exitStateId"]
                for edge in slo["transitions"]
            )
        )
        state_order = [state["id"] for state in slo["states"]]
        self.assertLess(state_order.index("telemetry"), state_order.index("alert"))
        self.assertLess(state_order.index("runbook"), state_order.index("evidence-ready"))

    def test_task6_core04_has_an_exact_illustrative_lost_update_and_synchronized_trace(
        self,
    ) -> None:
        path = REPOSITORY_ROOT / "content/lessons/core-04-os-processes-concurrency/lesson.json"
        visual = json.loads(path.read_bytes())["visualizations"][0]
        events = visual["payload"]["events"]
        self.assertEqual(
            tuple((item["id"], item["phaseId"], item["order"], item.get("lane")) for item in events),
            (
                ("isolation-unit", "boundary", 0, "shared-context"),
                ("shared-target", "boundary", 1, "shared-context"),
                ("unsynchronized-start", "lost-update-trace", 2, "shared-context"),
                ("a-read", "lost-update-trace", 3, "thread-a"),
                ("b-read", "lost-update-trace", 4, "thread-b"),
                ("a-compute", "lost-update-trace", 5, "thread-a"),
                ("b-compute", "lost-update-trace", 6, "thread-b"),
                ("a-write", "lost-update-trace", 7, "thread-a"),
                ("b-write", "lost-update-trace", 8, "thread-b"),
                ("lost-update-violation", "lost-update-trace", 9, "shared-context"),
                ("a-lock", "synchronized-trace", 10, "thread-a"),
                ("a-locked-update", "synchronized-trace", 11, "thread-a"),
                ("a-unlock", "synchronized-trace", 12, "thread-a"),
                ("b-lock", "synchronized-trace", 13, "thread-b"),
                ("b-locked-update", "synchronized-trace", 14, "thread-b"),
                ("synchronized-invariant", "synchronized-trace", 15, "shared-context"),
                ("liveness", "verification", 16, "shared-context"),
                ("regression", "verification", 17, "shared-context"),
            ),
        )
        trace = json.dumps(events, ensure_ascii=False)
        for atom in (
            "説明用の値", "x = 10", "Thread A", "Thread B", "x = 9",
            "期待値 x = 8", "lost update", "mutex", "同期後の x = 8",
        ):
            self.assertIn(atom, trace)

    def test_task6_core05_has_an_exact_illustrative_deadline_budget_trace(self) -> None:
        path = REPOSITORY_ROOT / "content/lessons/core-05-networks-latency-failure/lesson.json"
        visual = json.loads(path.read_bytes())["visualizations"][0]
        events = visual["payload"]["events"]
        self.assertEqual(
            tuple((item["id"], item["order"]) for item in events),
            (("dns", 0), ("tcp", 1), ("tls", 2), ("request", 3),
             ("server", 4), ("first-byte", 5), ("body-complete", 6), ("result", 7)),
        )
        self.assertIn("説明用の総deadline 300ms", visual["payload"]["phases"][0]["detail"])
        observed = {item["id"]: item["detail"] for item in events}
        self.assertIn("累積235ms・残り65ms", observed["server"])
        self.assertIn("累積310ms", observed["first-byte"])
        self.assertIn("最初のdeadline超過点（10ms超過）", observed["first-byte"])
        self.assertIn("普遍的なlatency値ではない", visual["expectedObservation"])

    def test_task6_core24_clarifies_legacy_decision_wording_before_the_model(self) -> None:
        path = REPOSITORY_ROOT / "content/lessons/core-24-delivery-ci-release-safety/lesson.json"
        document = json.loads(path.read_bytes())
        notes = document["visualizations"][0]["notes"]
        clarification = (
            "現行modelではstopはCI evidence missing/unknown、"
            "promote/rollbackはpost-canary判断です。"
        )
        legacy = "Decision: advance、stop、rollbackを入力から導く。"
        self.assertEqual(notes[1], clarification)
        self.assertEqual(notes[6], legacy)
        lesson = load_lesson_bytes(path.read_bytes(), "lesson.json")
        rendered = render_visualization(
            document["id"], lesson.visualizations[0]
        ).value
        self.assertLess(rendered.index(clarification), rendered.index(legacy))
        self.assertLess(
            rendered.index(legacy), rendered.index("visualization__states")
        )

    def test_task6_state_loop_exit_states_are_terminal_and_core26_keeps_feedback(
        self,
    ) -> None:
        for lesson_id, visual_type in TASK6_VISUAL_TYPES.items():
            if visual_type != "state-loop":
                continue
            with self.subTest(lesson_id=lesson_id):
                path = REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json"
                payload = json.loads(path.read_bytes())["visualizations"][0]["payload"]
                self.assertFalse(
                    any(edge["from"] == payload["exitStateId"] for edge in payload["transitions"])
                )
        path = REPOSITORY_ROOT / "content/lessons/core-26-code-review-collaborative-quality/lesson.json"
        payload = json.loads(path.read_bytes())["visualizations"][0]["payload"]
        self.assertEqual(payload["exitStateId"], "evidence-ready")
        edges = {(edge["from"], edge["to"], edge["label"]) for edge in payload["transitions"]}
        self.assertIn(("enablement", "scope", "次のchangeでriskを再評価する"), edges)
        self.assertIn(("enablement", "evidence-ready", "独立再評価とsystem outcomeの証拠を確定する"), edges)

    def test_task6_contract_rejects_order_transition_text_source_note_and_placement_mutations(
        self,
    ) -> None:
        def document(lesson_id: str) -> dict[str, object]:
            path = REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json"
            return json.loads(path.read_bytes())

        timeline = document("core-05-networks-latency-failure")
        expected = TASK6_VISUAL_CONTRACT_SHA256[
            "core-05-networks-latency-failure"
        ]
        reversed_events = deepcopy(timeline)
        reversed_events["visualizations"][0]["payload"]["events"].reverse()
        with self.assertRaises(CurriculumValidationError):
            load_lesson_bytes(
                json.dumps(reversed_events, ensure_ascii=False).encode("utf-8"),
                "lesson.json",
            )
        self.assertNotEqual(_task6_visual_contract_sha256(reversed_events), expected)

        wrong_detail = deepcopy(timeline)
        wrong_detail["visualizations"][0]["payload"]["events"][0]["detail"] += " altered"
        load_lesson_bytes(
            json.dumps(wrong_detail, ensure_ascii=False).encode("utf-8"),
            "lesson.json",
        )
        self.assertNotEqual(_task6_visual_contract_sha256(wrong_detail), expected)

        machine = document("core-24-delivery-ci-release-safety")
        machine_expected = TASK6_VISUAL_CONTRACT_SHA256[
            "core-24-delivery-ci-release-safety"
        ]
        wrong_transition = deepcopy(machine)
        wrong_transition["visualizations"][0]["payload"]["transitions"][0][
            "to"
        ] = "provenance"
        with self.assertRaises(CurriculumValidationError):
            load_lesson_bytes(
                json.dumps(wrong_transition, ensure_ascii=False).encode("utf-8"),
                "lesson.json",
            )
        self.assertNotEqual(
            _task6_visual_contract_sha256(wrong_transition), machine_expected
        )

        for field, value in (
            ("caption", "誤ったcaption"),
            ("question", "どの証拠で遷移を許可または拒否し、安全な回復へ進むか。"),
            (
                "expectedObservation",
                "初期stateからの許可遷移と拒否理由を説明できる。",
            ),
            ("sourceIds", ["src-02"]),
            ("notes", ["誤った注記"]),
            ("afterSection", "workedExample"),
        ):
            with self.subTest(field=field):
                mutated = deepcopy(machine)
                mutated["visualizations"][0][field] = value
                load_lesson_bytes(
                    json.dumps(mutated, ensure_ascii=False).encode("utf-8"),
                    "lesson.json",
                )
                self.assertNotEqual(
                    _task6_visual_contract_sha256(mutated), machine_expected
                )

    def test_task5_visual_contracts_are_independently_exact(self) -> None:
        self.assertEqual(
            set(TASK5_VISUAL_CONTRACTS),
            set(TASK5_VISUAL_TYPES),
        )
        for lesson_id, expected in TASK5_VISUAL_CONTRACTS.items():
            with self.subTest(lesson_id=lesson_id):
                path = (
                    REPOSITORY_ROOT
                    / "content/lessons"
                    / lesson_id
                    / "lesson.json"
                )
                document = json.loads(path.read_bytes())
                self.assertEqual(
                    _task5_visual_projection(document),
                    expected,
                )

    def test_task5_companion_notes_preserve_legacy_first_occurrence_order(
        self,
    ) -> None:
        legacy_by_lesson = {
            entry["lessonId"]: entry
            for entry in json.loads(MIGRATION_ORACLE.read_bytes())["figures"]
        }
        self.assertEqual(set(TASK5_COMPANION_NOTES), set(TASK5_VISUAL_TYPES))
        for lesson_id, expected_notes in TASK5_COMPANION_NOTES.items():
            with self.subTest(lesson_id=lesson_id):
                path = (
                    REPOSITORY_ROOT
                    / "content/lessons"
                    / lesson_id
                    / "lesson.json"
                )
                document = json.loads(path.read_bytes())
                visual_document = document["visualizations"][0]
                self.assertEqual(
                    tuple(visual_document["notes"]),
                    (TASK5_READING_ORDER_MARKER, *expected_notes),
                )
                self.assertLessEqual(len(visual_document["notes"]), 8)
                self.assertEqual(
                    visual_document["afterSection"],
                    legacy_by_lesson[lesson_id]["sectionRole"],
                )
                lesson = load_lesson_bytes(path.read_bytes(), "lesson.json")
                rendered = render_visualization(
                    lesson_id, lesson.visualizations[0]
                ).value
                offsets = [
                    rendered.index(escape(atom))
                    for atom in legacy_by_lesson[lesson_id]["visibleAtoms"]
                ]
                self.assertEqual(offsets, sorted(offsets))
                self.assertEqual(len(offsets), len(set(offsets)))
                marker = rendered.index(TASK5_READING_ORDER_MARKER)
                model_class = (
                    "visualization__causal-model"
                    if TASK5_VISUAL_TYPES[lesson_id] == "causal"
                    else "visualization__components"
                )
                self.assertLess(marker, offsets[0])
                self.assertLess(offsets[-1], rendered.index(model_class))

    def test_task5_exact_contract_rejects_semantic_relationship_and_source_mutations(
        self,
    ) -> None:
        documents = {
            lesson_id: json.loads(
                (
                    REPOSITORY_ROOT
                    / "content/lessons"
                    / lesson_id
                    / "lesson.json"
                ).read_bytes()
            )
            for lesson_id in TASK5_VISUAL_CONTRACTS
        }

        reversed_edge = deepcopy(
            documents["core-06-requirements-domain-modeling"]
        )
        edge = reversed_edge["visualizations"][0]["payload"]["connections"][0]
        edge["from"], edge["to"] = edge["to"], edge["from"]
        load_lesson_bytes(
            json.dumps(reversed_edge, ensure_ascii=False).encode("utf-8"),
            "lesson.json",
        )
        self.assertNotEqual(
            _task5_visual_projection(reversed_edge),
            TASK5_VISUAL_CONTRACTS["core-06-requirements-domain-modeling"],
        )

        swapped_labels = deepcopy(
            documents["core-10-threat-modeling-secure-design"]
        )
        relations = swapped_labels["visualizations"][0]["payload"]["connections"]
        relations[0]["label"], relations[1]["label"] = (
            relations[1]["label"],
            relations[0]["label"],
        )
        load_lesson_bytes(
            json.dumps(swapped_labels, ensure_ascii=False).encode("utf-8"),
            "lesson.json",
        )
        self.assertNotEqual(
            _task5_visual_projection(swapped_labels),
            TASK5_VISUAL_CONTRACTS["core-10-threat-modeling-secure-design"],
        )

        unsuitable_source = deepcopy(
            documents["core-08-modularity-evolutionary-architecture"]
        )
        unsuitable_source["visualizations"][0]["sourceIds"] = [
            "src-03",
            "src-04",
        ]
        load_lesson_bytes(
            json.dumps(unsuitable_source, ensure_ascii=False).encode("utf-8"),
            "lesson.json",
        )
        self.assertNotEqual(
            _task5_visual_projection(unsuitable_source),
            TASK5_VISUAL_CONTRACTS[
                "core-08-modularity-evolutionary-architecture"
            ],
        )

        swapped_details = deepcopy(
            documents["core-06-requirements-domain-modeling"]
        )
        nodes = swapped_details["visualizations"][0]["payload"]["nodes"]
        nodes[0]["detail"], nodes[1]["detail"] = (
            nodes[1]["detail"],
            nodes[0]["detail"],
        )
        load_lesson_bytes(
            json.dumps(swapped_details, ensure_ascii=False).encode("utf-8"),
            "lesson.json",
        )
        self.assertNotEqual(
            _task5_visual_projection(swapped_details),
            TASK5_VISUAL_CONTRACTS["core-06-requirements-domain-modeling"],
        )

        relocated_notes = deepcopy(documents["core-01-systems-tradeoffs"])
        notes = relocated_notes["visualizations"][0]["notes"]
        notes[0], notes[1] = notes[1], notes[0]
        load_lesson_bytes(
            json.dumps(relocated_notes, ensure_ascii=False).encode("utf-8"),
            "lesson.json",
        )
        self.assertNotEqual(
            _task5_visual_projection(relocated_notes),
            TASK5_VISUAL_CONTRACTS["core-01-systems-tradeoffs"],
        )

        misinformation = deepcopy(
            documents["core-08-modularity-evolutionary-architecture"]
        )
        misinformation["visualizations"][0]["payload"]["components"][2][
            "detail"
        ] += " reportingはpricing-adaptersへ依存する。"
        load_lesson_bytes(
            json.dumps(misinformation, ensure_ascii=False).encode("utf-8"),
            "lesson.json",
        )
        self.assertNotEqual(
            _task5_visual_projection(misinformation),
            TASK5_VISUAL_CONTRACTS[
                "core-08-modularity-evolutionary-architecture"
            ],
        )

    def test_task5_exact_contract_rejects_identity_placement_and_simulation_mutations(
        self,
    ) -> None:
        path = (
            REPOSITORY_ROOT
            / "content/lessons/core-01-systems-tradeoffs/lesson.json"
        )
        document = json.loads(path.read_bytes())
        expected = TASK5_VISUAL_CONTRACTS["core-01-systems-tradeoffs"]

        renamed = deepcopy(document)
        renamed["visualizations"][0]["id"] = "renamed-causal-loop"
        load_lesson_bytes(
            json.dumps(renamed, ensure_ascii=False).encode("utf-8"),
            "lesson.json",
        )
        self.assertNotEqual(_task5_visual_projection(renamed), expected)

        relocated = deepcopy(document)
        relocated["visualizations"][0]["afterSection"] = "workedExample"
        load_lesson_bytes(
            json.dumps(relocated, ensure_ascii=False).encode("utf-8"),
            "lesson.json",
        )
        self.assertNotEqual(_task5_visual_projection(relocated), expected)

        with_simulation = deepcopy(document)
        with_simulation["visualizations"][0]["simulation"] = {
            "kind": "request-path",
            "interactionMode": "scenario",
            "parameters": [],
            "initialStateId": "inserted-state",
            "states": [
                {
                    "id": "inserted-state",
                    "label": "挿入状態",
                    "status": "観測可能",
                    "activeNodeIds": ["constraints"],
                    "activeEdgeIds": [],
                }
            ],
            "transitions": [],
            "outcomes": [
                {
                    "id": "inserted-outcome",
                    "stateId": "inserted-state",
                    "label": "挿入結果",
                }
            ],
        }
        load_lesson_bytes(
            json.dumps(with_simulation, ensure_ascii=False).encode("utf-8"),
            "lesson.json",
        )
        self.assertNotEqual(_task5_visual_projection(with_simulation), expected)

    def test_causal_no_js_oracles_place_items_under_semantic_headings(self) -> None:
        heading_by_group = {
            "causes": "原因",
            "mechanisms": "機構",
            "outcomes": "結果",
            "mitigations": "対策",
        }
        for lesson_id, expected in TASK5_VISUAL_CONTRACTS.items():
            if TASK5_VISUAL_TYPES[lesson_id] != "causal":
                continue
            with self.subTest(lesson_id=lesson_id):
                path = (
                    REPOSITORY_ROOT
                    / "content/lessons"
                    / lesson_id
                    / "lesson.json"
                )
                lesson = load_lesson_bytes(path.read_bytes(), "lesson.json")
                html = render_visualization(
                    lesson_id, lesson.visualizations[0]
                ).value
                for group, items in expected["structure"].items():
                    start = html.index(
                        f"<dt>{heading_by_group[group]}</dt><dd><dl>"
                    )
                    end = html.index("</dl></dd>", start)
                    section = html[start:end]
                    for _, label, _ in items:
                        self.assertIn(f"<dt>{label}</dt>", section)

    def test_core08_network_compares_source_and_runtime_views_without_linking_reporting(
        self,
    ) -> None:
        lesson_root = (
            REPOSITORY_ROOT
            / "content/lessons/core-08-modularity-evolutionary-architecture"
        )
        document = json.loads((lesson_root / "lesson.json").read_bytes())
        payload = document["visualizations"][0]["payload"]

        component_ids = {
            component["id"] for component in payload["components"]
        }
        self.assertEqual(
            component_ids,
            {
                "source-dependency-view",
                "runtime-request-flow-view",
                "independent-reporting",
            },
        )
        labels = tuple(edge["label"] for edge in payload["connections"])
        self.assertEqual(
            sum(label.startswith("source dependency:") for label in labels),
            2,
        )
        self.assertEqual(
            sum(label.startswith("runtime request flow:") for label in labels),
            2,
        )
        self.assertFalse(
            any(
                "reporting" in {edge["from"], edge["to"]}
                for edge in payload["connections"]
            )
        )

    def test_core27_network_keeps_cognitive_load_and_slo_as_independent_inputs(self) -> None:
        lesson_root = (
            REPOSITORY_ROOT
            / "content/lessons/core-27-team-interfaces-sociotechnical-architecture"
        )
        document = json.loads((lesson_root / "lesson.json").read_bytes())
        connections = document["visualizations"][0]["payload"]["connections"]
        actual = tuple(
            (edge["from"], edge["to"], edge["label"])
            for edge in connections
        )

        self.assertEqual(
            actual,
            (
                (
                    "ownership",
                    "dependency",
                    "checkout capabilityのdecision rightとplatform依存を分ける",
                ),
                (
                    "ownership",
                    "cognitive-load",
                    "assigned領域をcapacityと比較する",
                ),
                (
                    "dependency",
                    "slo",
                    "dependency latencyのtargetとobservedを比較する",
                ),
                (
                    "cognitive-load",
                    "enablement",
                    "capacity内かをenablement判断へ渡す",
                ),
                (
                    "slo",
                    "enablement",
                    "dependency SLO statusをenablement判断へ渡す",
                ),
            ),
        )
        endpoints = {
            (source, target) for source, target, _ in actual
        }
        self.assertNotIn(("cognitive-load", "slo"), endpoints)
        self.assertNotIn(("dependency", "cognitive-load"), endpoints)

    def test_authored_bodies_have_six_sections_and_unique_visible_text(self) -> None:
        visible_bodies: dict[str, str] = {}
        for lesson_id in LESSON_IDS:
            with self.subTest(lesson_id=lesson_id):
                source = (
                    REPOSITORY_ROOT
                    / "content/lessons"
                    / lesson_id
                    / "body.html"
                ).read_text(encoding="utf-8")
                sections, visible_text = _parse_authored_body(source)
                self.assertEqual(
                    tuple(section.heading for section in sections),
                    AUTHORED_HEADINGS,
                )
                self.assertEqual(len(sections), len(AUTHORED_HEADINGS))
                self.assertTrue(all(section.body for section in sections))
                visible_bodies[lesson_id] = visible_text

        normalized = _assert_unique_visible_bodies(visible_bodies)
        self.assertEqual(len(normalized), len(LESSON_IDS))

        duplicated = dict(visible_bodies)
        duplicated[LESSON_IDS[1]] = visible_bodies[LESSON_IDS[0]]
        with self.assertRaisesRegex(AssertionError, "duplicate visible body"):
            _assert_unique_visible_bodies(duplicated)

    def test_every_lesson_closes_the_evidence_learning_loop(self) -> None:
        first_contract: _EvidenceContract | None = None
        for lesson_id in LESSON_IDS:
            with self.subTest(lesson_id=lesson_id):
                document = json.loads(
                    (
                        REPOSITORY_ROOT
                        / "content/lessons"
                        / lesson_id
                        / "lesson.json"
                    ).read_text(encoding="utf-8")
                )
                contract = _evidence_contract(document)
                _assert_evidence_references(contract)
                if first_contract is None:
                    first_contract = contract

                self.assertEqual(
                    tuple(
                        level["level"]
                        for level in document["capabilityProgression"]
                    ),
                    CAPABILITY_LEVELS,
                )

                lab = document["lab"]
                self.assertTrue(_nonempty(lab["artifact"]))
                self.assertGreaterEqual(len(lab["steps"]), 3)
                self.assertTrue(all(_nonempty(step) for step in lab["steps"]))
                self.assertTrue(_nonempty(document["teachBack"]))

                assessments = document["assessment"]
                self.assertGreaterEqual(len(assessments), 2)
                for assessment in assessments:
                    self.assertTrue(_nonempty(assessment["prompt"]))
                    self.assertTrue(_nonempty(assessment["expectedEvidence"]))
                self.assertTrue(_nonempty(document["transferTask"]))

                review = document["review"]
                self.assertEqual(review["intervalDays"], [1, 7, 30, 90])
                self.assertTrue(review["prompts"])
                self.assertTrue(
                    all(_nonempty(prompt) for prompt in review["prompts"])
                )

                rubric = document["rubric"]
                self.assertEqual(
                    tuple(item["dimension"] for item in rubric),
                    RUBRIC_DIMENSIONS,
                )
                self.assertEqual(len(rubric), 4)
                for item in rubric:
                    self.assertEqual(frozenset(item["levels"]), RUBRIC_LEVELS)
                    self.assertEqual(len(item["levels"]), 4)
                    self.assertTrue(
                        all(_nonempty(value) for value in item["levels"].values())
                    )

        self.assertIsNotNone(first_contract)
        assert first_contract is not None
        orphaned = replace(
            first_contract,
            evidence=first_contract.evidence
            + (_EvidenceItem("orphan-evidence", "artifact"),),
        )
        with self.assertRaisesRegex(
            AssertionError, "orphan or unknown objective evidence"
        ):
            _assert_evidence_references(orphaned)

    def test_content_standard_names_evidence_loop_and_four_review_roles(self) -> None:
        standard = CONTENT_STANDARD.read_text(encoding="utf-8")

        for stage in EVIDENCE_LOOP:
            self.assertIn(stage, standard)
        for role in REVIEW_ROLES:
            self.assertIn(role, standard)
        self.assertIn("4 review dimensions", standard)
        for reviewer_kind in ("human", "ai-assisted", "automated"):
            self.assertIn(f"`{reviewer_kind}`", standard)
        self.assertIn("正直に開示", standard)

    def test_curriculum_map_generated_block_matches_expected_bytes(self) -> None:
        from curriculum_builder.curriculum_map import (
            render_generated_curriculum_map,
        )

        document = CURRICULUM_MAP.read_text(encoding="utf-8")
        self.assertEqual(document.count(BEGIN_GENERATED_MAP), 1)
        self.assertEqual(document.count(END_GENERATED_MAP), 1)
        start = document.index(BEGIN_GENERATED_MAP)
        end = document.index(END_GENERATED_MAP) + len(END_GENERATED_MAP)
        self.assertEqual(
            document[start:end],
            render_generated_curriculum_map(REPOSITORY_ROOT),
        )

    def test_curriculum_map_independently_proves_release_totals_and_graph(
        self,
    ) -> None:
        document = CURRICULUM_MAP.read_text(encoding="utf-8")
        _assert_generated_map_contract(document)

        duplicated_marker = BEGIN_GENERATED_MAP + "\n" + document
        with self.assertRaisesRegex(AssertionError, "one start marker"):
            _assert_generated_map_contract(duplicated_marker)

        tampered_total = document.replace(
            "| コンピテンシー対応 | 90 mappings |",
            "| コンピテンシー対応 | 89 mappings |",
        )
        self.assertNotEqual(tampered_total, document)
        with self.assertRaisesRegex(AssertionError, "release row"):
            _assert_generated_map_contract(tampered_total)

        mutations = (
            ("V4&#46;0a", r"V4\.0a"),
            ("V4&#46;0a", "V4&period;0a"),
            ("V4&#46;0a", "V4&#x2e;0a"),
            ("| CS2023 | Final Report |", "|CS2023 | Final Report |"),
            ("| CS2023 | Final Report |", "|  CS2023 | Final Report |"),
            ("| CS2023 | Final Report |", "| CS2023| Final Report |"),
            (
                "`core-01-systems-tradeoffs`<br>システム思考",
                "`core-01-systems-tradeoffs`<br>\\システム思考",
            ),
            (
                "`core-01-systems-tradeoffs` | `foundation`",
                "`core-30-evidence-based-technical-leadership` | `foundation`",
            ),
            ("| 1 | `foundation` | 5 |", "| 1 | `foundation` | 4 |"),
            ("| CS2023 | Final Report |", "| CS2023 | Draft Report |"),
            (
                "`SF` Systems Fundamentals (direct)",
                "`AL` Systems Fundamentals (direct)",
            ),
            (
                "Primary: `global-service`<br>Supporting: "
                "`legacy-evolution`, `oss-launch`",
                "Primary: `global-service`<br>Supporting: `legacy-evolution`",
            ),
            (
                "`global-service` — 多地域の医療予約サービスを設計・運用する | 27 |",
                "`global-service` — 多地域の医療予約サービスを設計・運用する | 26 |",
            ),
            (
                "`build`, `operate`, `explain`, `review` |",
                "`build`, `operate`, `explain`, `audit` |",
            ),
        )
        for original, replacement in mutations:
            tampered = document.replace(original, replacement, 1)
            self.assertNotEqual(tampered, document)
            with self.assertRaises(AssertionError):
                _assert_generated_map_contract(tampered)

    def test_curriculum_map_requires_the_handwritten_learning_contract(self) -> None:
        document = CURRICULUM_MAP.read_text(encoding="utf-8")
        generated_only = _extract_generated_map(document)
        with self.assertRaises(AssertionError):
            _assert_generated_map_contract(generated_only)

        mutations = (
            ("# Engineering Expert Curriculum Map", "# Generated Data"),
            ("## 地図の読み方", "## 表の読み方"),
            ("## 推奨する進み方", "## 進み方"),
            ("## 更新方法", "## 再生成"),
            (
                "データ表はsource of truthから\n機械生成し、学び方と解釈上の注意は人が保守する。",
                "データ表は機械生成する。",
            ),
            (
                "資格、職位、SFIA責任level\nの認定ではない。",
                "SFIAの認定として利用できる。",
            ),
            (
                "artifact、teach-back、assessment reasoning、transferを\n"
                "揃えてからmastery gateへ進む。",
                "読了後すぐmastery gateへ進む。",
            ),
            (
                "生成表を直接編集してはならない。",
                "生成表を直接編集する。",
            ),
        )
        for original, replacement in mutations:
            with self.subTest(original=original):
                tampered = document.replace(original, replacement, 1)
                self.assertNotEqual(tampered, document)
                with self.assertRaises(AssertionError):
                    _assert_generated_map_contract(tampered)

        visibility_mutations = {
            "HTML comment": f"<!--\n{document}\n-->",
            "code fence": f"````markdown\n{document}\n````",
            "extra H2": document.replace(
                "## 地図の読み方",
                "## 追加方針\n\nこの節は許可されない。\n\n## 地図の読み方",
                1,
            ),
            "raw HTML heading": document.replace(
                "## 地図の読み方",
                "<h3>隠れた方針</h3>\n\n## 地図の読み方",
                1,
            ),
            "reordered H2": document.replace(
                "## 地図の読み方",
                "## SWAP",
                1,
            )
            .replace("## 推奨する進み方", "## 地図の読み方", 1)
            .replace("## SWAP", "## 推奨する進み方", 1),
            "clause moved to the wrong section": document.replace(
                "データ表はsource of truthから\n"
                "機械生成し、学び方と解釈上の注意は人が保守する。",
                "",
                1,
            ).replace(
                "## 地図の読み方",
                "## 地図の読み方\n\n"
                "データ表はsource of truthから\n"
                "機械生成し、学び方と解釈上の注意は人が保守する。",
                1,
            ),
        }
        for label, tampered in visibility_mutations.items():
            with self.subTest(label=label), self.assertRaises(AssertionError):
                _assert_generated_map_contract(tampered)

        for injected in (
            "| unexpected | generated | row |",
            '<img src="https://example.invalid/tracker">',
        ):
            tampered = document.replace(
                END_GENERATED_MAP,
                f"{injected}\n{END_GENERATED_MAP}",
                1,
            )
            with self.assertRaises(AssertionError):
                _assert_generated_map_contract(tampered)

    def test_independent_markdown_parser_accepts_an_escaped_pipe(self) -> None:
        self.assertEqual(
            _parse_markdown_table_row(r"| 1 | boundary a\|b | final |"),
            ("1", "boundary a|b", "final"),
        )
        with self.assertRaisesRegex(AssertionError, "unsupported escape"):
            _parse_markdown_table_row(r"| \literal |")

    def test_two_fresh_builds_have_exact_deterministic_static_inventory(self) -> None:
        with TemporaryDirectory(
            prefix=".content-acceptance-",
            dir=REPOSITORY_ROOT.parent,
        ) as temporary:
            parent = Path(temporary)
            outputs = (parent / "site-a", parent / "site-b")
            for output in outputs:
                build_site(
                    REPOSITORY_ROOT / "content",
                    REPOSITORY_ROOT / "templates",
                    REPOSITORY_ROOT / "static",
                    output,
                    require_complete_curriculum=True,
                )

            first = _snapshot(outputs[0])
            second = _snapshot(outputs[1])

        self.assertEqual(first, second)
        self.assertEqual(frozenset(first), _expected_artifacts())
        self.assertEqual(len(first), 42)
        self.assertEqual(sum(path.suffix.casefold() == ".html" for path in first), 39)
        self.assertEqual(sum(path.suffix.casefold() == ".css" for path in first), 2)
        self.assertEqual(sum(path.suffix.casefold() == ".js" for path in first), 1)
        self.assertEqual(
            sum(
                b"<script " in source
                for path, source in first.items()
                if path.suffix.casefold() == ".html"
            ),
            9,
        )
        legacy_by_lesson = {
            entry["lessonId"]: entry
            for entry in json.loads(MIGRATION_ORACLE.read_bytes())["figures"]
        }
        for lesson_id, visual_type in TASK5_VISUAL_TYPES.items():
            generated = first[
                PurePosixPath("lessons") / lesson_id / "index.html"
            ].decode("utf-8")
            offsets = [
                generated.index(escape(atom))
                for atom in legacy_by_lesson[lesson_id]["visibleAtoms"]
            ]
            model_class = (
                "visualization__causal-model"
                if visual_type == "causal"
                else "visualization__components"
            )
            marker = generated.index(TASK5_READING_ORDER_MARKER)
            self.assertLess(generated.index("注記"), marker)
            self.assertNotIn("旧図の読み順（補助）", generated)
            self.assertLess(marker, offsets[0])
            self.assertEqual(offsets, sorted(offsets))
            self.assertLess(offsets[-1], generated.index(model_class))


if __name__ == "__main__":
    unittest.main()
