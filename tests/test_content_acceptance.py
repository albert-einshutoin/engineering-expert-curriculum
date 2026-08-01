from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
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
TASK7_STRUCTURE_IDS = {
    "core-02-algorithms-measurement": {
        "alternatives": ("linear-scan", "binary-search", "hash-lookup"),
        "criteria": ("best-case", "average-case", "worst-case"),
        "cells": ("linear-best", "linear-average", "linear-worst", "binary-best", "binary-average", "binary-worst", "hash-best", "hash-average", "hash-worst"),
    },
    "core-03-architecture-memory-caches": {
        "layers": ("instruction", "tlb", "page-table", "l1-cache", "lower-cache", "memory-controller", "reuse"),
        "transfers": ("instruction-to-tlb", "tlb-to-page-table", "page-table-to-l1", "l1-to-lower", "lower-to-memory", "memory-to-reuse"),
    },
    "core-11-data-modeling-storage": {
        "rows": ("relational", "document", "key-value"),
        "columns": ("access-fit", "constraint", "operations-recovery"),
        "cells": ("relational-access", "relational-constraint", "relational-ops", "document-access", "document-constraint", "document-ops", "key-value-access", "key-value-constraint", "key-value-ops"),
    },
    "core-16-hci-usability-accessibility": {
        "steps": ("scope", "target", "observe", "review", "claim"),
        "transitions": ("scope-to-target", "target-to-observe", "observe-to-review", "review-to-claim"),
    },
    "core-17-graphics-visual-information": {
        "steps": ("data", "transform", "visual", "equivalent", "verify"),
        "transitions": ("data-to-transform", "transform-to-visual", "visual-to-equivalent", "equivalent-to-verify"),
    },
    "core-19-technical-communication-design-docs": {
        "nodes": ("decision-record", "audience", "evidence", "executive-view", "implementation-view", "alternatives", "validation"),
    },
    "core-25-engineering-economics-capacity": {
        "rows": ("option-a", "option-b"),
        "columns": ("total-cost", "capacity", "decision"),
        "cells": ("a-cost", "a-capacity", "a-decision", "b-cost", "b-capacity", "b-decision"),
    },
    "core-28-oss-governance-stewardship": {
        "steps": ("discover", "prepare", "submit", "review", "maintainer-merge", "release-evidence"),
        "transitions": ("discover-to-prepare", "prepare-to-submit", "submit-to-review", "review-to-merge", "merge-to-release"),
    },
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


def _task5_visual_projection(document: dict[str, object]) -> dict[str, object]:
    visual = document["visualizations"][0]  # type: ignore[index]
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
    encoded = json.dumps(
        document["visualizations"][0],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _task6_visual_projection(document: dict[str, object]) -> dict[str, object]:
    """Project every authored field without using production model objects."""
    visual = document["visualizations"][0]
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
                self.assertNotIn("simulation", visual)
                rendered = str(render_visualization(
                    lesson_id,
                    load_lesson_bytes((root / "lesson.json").read_bytes(), "lesson.json").visualizations[0],
                ))
                for atom in legacy[lesson_id]["visibleAtoms"]:
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

    def test_task7_readable_contracts_freeze_every_structured_row_and_relation(self) -> None:
        for lesson_id, expected in TASK7_STRUCTURE_IDS.items():
            with self.subTest(lesson_id=lesson_id):
                path = REPOSITORY_ROOT / "content/lessons" / lesson_id / "lesson.json"
                visual = json.loads(path.read_bytes())["visualizations"][0]
                self.assertEqual(visual["afterSection"], "mentalModel")
                self.assertNotIn("simulation", visual)
                for field in ("id", "caption", "question", "expectedObservation"):
                    self.assertTrue(visual[field].strip())
                for field in ("objectiveIds", "evidenceIds", "sourceIds"):
                    self.assertTrue(visual[field])
                payload = visual["payload"]
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
        self.assertIn("固定latencyではない", memory["payload"]["layers"][4]["detail"])
        complexity = json.loads((REPOSITORY_ROOT / "content/lessons/core-02-algorithms-measurement/lesson.json").read_bytes())["visualizations"][0]
        self.assertEqual(tuple(item["label"] for item in complexity["payload"]["criteria"]), ("best case", "average case", "worst case"))
        hierarchy = json.loads((REPOSITORY_ROOT / "content/lessons/core-19-technical-communication-design-docs/lesson.json").read_bytes())["visualizations"][0]
        self.assertEqual(tuple(item["parentId"] for item in hierarchy["payload"]["nodes"]), (None, "decision-record", "decision-record", "audience", "audience", "evidence", "evidence"))

    def test_task7_readable_contract_detects_structure_and_detail_mutations(self) -> None:
        path = REPOSITORY_ROOT / "content/lessons/core-03-architecture-memory-caches/lesson.json"
        original = json.loads(path.read_bytes())["visualizations"][0]["payload"]
        expected_layers = TASK7_STRUCTURE_IDS["core-03-architecture-memory-caches"]["layers"]
        mutated = deepcopy(original)
        mutated["layers"][1]["detail"] = "translationとdata transferは常に同じlatency"
        self.assertNotEqual(mutated, original)
        swapped = deepcopy(original)
        swapped["layers"][0], swapped["layers"][1] = swapped["layers"][1], swapped["layers"][0]
        self.assertNotEqual(tuple(item["id"] for item in swapped["layers"]), expected_layers)

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
                self.assertEqual(len(document.get("visualizations", [])), 1)
                visual = document["visualizations"][0]
                self.assertEqual(visual["type"], expected_type)
                self.assertEqual(
                    visual["caption"], legacy_by_lesson[lesson_id]["caption"]
                )
                self.assertEqual(visual["afterSection"], "mentalModel")
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
        self.assertEqual(len(first), 41)
        self.assertEqual(sum(path.suffix.casefold() == ".html" for path in first), 39)
        self.assertEqual(sum(path.suffix.casefold() == ".css" for path in first), 2)
        self.assertEqual(sum(path.suffix.casefold() == ".js" for path in first), 0)
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
