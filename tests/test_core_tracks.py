from __future__ import annotations

import ast
from datetime import date
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from curriculum_builder.lessons import load_lesson


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BODY_HEADINGS = (
    "なぜ重要か",
    "メンタルモデル",
    "動く例で考える",
    "トレードオフと失敗モード",
    "知識チェック",
    "出典と次の学習",
)
FOUNDATION_SOURCES = {
    "core-01-systems-tradeoffs": (
        (
            "NASA Systems Engineering Handbook",
            "https://www.nasa.gov/reference/systems-engineering-handbook/",
            "primary",
        ),
        (
            "NIST SP 800-160 Vol. 1 Rev. 1: "
            "Engineering Trustworthy Secure Systems",
            "https://doi.org/10.6028/NIST.SP.800-160v1r1",
            "standard",
        ),
        (
            "The Architecture Tradeoff Analysis Method",
            "https://www.sei.cmu.edu/library/"
            "the-architecture-tradeoff-analysis-method/",
            "primary",
        ),
    ),
    "core-02-algorithms-measurement": (
        (
            "big-O notation",
            "https://www.nist.gov/dads/HTML/bigOnotation.html",
            "primary",
        ),
        (
            "SPEC CPU®2017 Run and Reporting Rules",
            "https://www.spec.org/cpu2017/Docs/runrules.html",
            "standard",
        ),
        (
            "timeit — Measure execution time of small code snippets",
            "https://docs.python.org/3/library/timeit.html",
            "primary",
        ),
        (
            "Quicksort",
            "https://www.cs.princeton.edu/courses/archive/"
            "spr18/cos226/lectures/23Quicksort.pdf",
            "primary",
        ),
    ),
    "core-03-architecture-memory-caches": (
        (
            "Intel® 64 and IA-32 Architectures Optimization",
            "https://www.intel.com/content/www/us/en/developer/articles/"
            "technical/intel64-and-ia32-architectures-optimization.html",
            "primary",
        ),
        (
            "Armv8-A memory model",
            "https://developer.arm.com/-/media/Arm%20Developer%20Community/"
            "PDF/Learn%20the%20Architecture/"
            "Armv8-A%20memory%20model%20guide.pdf"
            "?revision=58b1dd0a-3800-4218-b21a-f95a0332034c",
            "primary",
        ),
        (
            "The TLB",
            "https://docs.kernel.org/arch/x86/tlb.html",
            "primary",
        ),
    ),
    "core-04-os-processes-concurrency": (
        (
            "Chapter 17. Threads and Locks",
            "https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html",
            "standard",
        ),
        (
            "pthread_create — thread creation",
            "https://pubs.opengroup.org/onlinepubs/"
            "9799919799.2024edition/functions/pthread_create.html",
            "standard",
        ),
        (
            "fork — create a new process",
            "https://pubs.opengroup.org/onlinepubs/"
            "9799919799.2024edition/functions/fork.html",
            "standard",
        ),
        (
            "Linux kernel memory barriers",
            "https://docs.kernel.org/core-api/wrappers/memory-barriers.html",
            "primary",
        ),
        (
            "About Processes and Threads",
            "https://learn.microsoft.com/en-us/windows/win32/"
            "procthread/about-processes-and-threads",
            "primary",
        ),
    ),
    "core-05-networks-latency-failure": (
        (
            "RFC 1035: Domain Names - Implementation and Specification",
            "https://www.rfc-editor.org/rfc/rfc1035.html",
            "standard",
        ),
        (
            "RFC 9293: Transmission Control Protocol (TCP)",
            "https://www.rfc-editor.org/rfc/rfc9293.html",
            "standard",
        ),
        (
            "RFC 6298: Computing TCP's Retransmission Timer",
            "https://www.rfc-editor.org/rfc/rfc6298.html",
            "standard",
        ),
        (
            "RFC 8446: The Transport Layer Security (TLS) Protocol "
            "Version 1.3",
            "https://www.rfc-editor.org/rfc/rfc8446.html",
            "standard",
        ),
        (
            "RFC 9110: HTTP Semantics",
            "https://www.rfc-editor.org/rfc/rfc9110.html",
            "standard",
        ),
    ),
}
BUILD_SOURCES = {
    "core-06-requirements-domain-modeling": (
        (
            "ISO/IEC/IEEE 29148:2018 - Systems and software engineering — "
            "Life cycle processes — Requirements engineering",
            "https://www.iso.org/standard/72089.html",
            "standard",
        ),
        (
            "Appendix C: How to Write a Good Requirement",
            "https://www.nasa.gov/reference/"
            "appendix-c-how-to-write-a-good-requirement/",
            "primary",
        ),
        (
            "Domain-Driven Design Reference: Definitions and Pattern "
            "Summaries",
            "https://www.domainlanguage.com/wp-content/uploads/2016/05/"
            "DDD_Reference_2015-03.pdf",
            "primary",
        ),
    ),
    "core-07-api-contract-design": (
        (
            "RFC 9110: HTTP Semantics",
            "https://www.rfc-editor.org/rfc/rfc9110.html",
            "standard",
        ),
        (
            "OpenAPI Specification v3.2.0",
            "https://spec.openapis.org/oas/v3.2.0.html",
            "standard",
        ),
        (
            "JSON Schema Validation: A Vocabulary for Structural "
            "Validation of JSON",
            "https://json-schema.org/draft/2020-12/"
            "json-schema-validation",
            "standard",
        ),
        (
            "AIP-180: Backwards compatibility",
            "https://google.aip.dev/180",
            "primary",
        ),
        (
            "RFC 9457: Problem Details for HTTP APIs",
            "https://www.rfc-editor.org/rfc/rfc9457.html",
            "standard",
        ),
    ),
    "core-08-modularity-evolutionary-architecture": (
        (
            "On the Criteria To Be Used in Decomposing Systems into "
            "Modules",
            "https://doi.org/10.1145/361598.361623",
            "primary",
        ),
        (
            "ISO/IEC/IEEE 42010:2022 - Software, systems and enterprise — "
            "Architecture description",
            "https://www.iso.org/standard/74393.html",
            "standard",
        ),
        (
            "Documenting Software Architectures: Views and Beyond, "
            "Second Edition",
            "https://www.sei.cmu.edu/library/"
            "documenting-software-architectures-views-and-beyond-"
            "second-edition/",
            "primary",
        ),
        (
            "MADR 4.0.0 — The Markdown Architectural Decision Records",
            "https://adr.github.io/madr/",
            "primary",
        ),
    ),
    "core-09-test-strategy-tdd": (
        (
            "ISTQB Certified Tester Foundation Level Syllabus v4.0.1",
            "https://istqb.org/wp-content/uploads/2024/11/"
            "ISTQB_CTFL_Syllabus_v4.0.1.pdf",
            "standard",
        ),
        (
            "Test Driven Development: By Example",
            "https://www.informit.com/store/"
            "test-driven-development-by-example-9780321146533",
            "primary",
        ),
        (
            "An Empirical Analysis of Flaky Tests",
            "https://doi.org/10.1145/2635868.2635920",
            "peer-reviewed",
        ),
        (
            "Metamorphic Testing: A New Approach for Generating Next "
            "Test Cases",
            "https://www.cse.ust.hk/~scc/publ/"
            "CS98-01-metamorphictesting.pdf",
            "primary",
        ),
        (
            "Pact Specification",
            "https://docs.pact.io/getting_started/specification",
            "primary",
        ),
    ),
    "core-10-threat-modeling-secure-design": (
        (
            "Secure Software Development Framework (SSDF) Version 1.1: "
            "Recommendations for Mitigating the Risk of Software "
            "Vulnerabilities",
            "https://csrc.nist.gov/pubs/sp/800/218/final",
            "standard",
        ),
        (
            "Shifting the Balance of Cybersecurity Risk: Principles and "
            "Approaches for Secure by Design Software",
            "https://www.cisa.gov/sites/default/files/2023-10/"
            "Shifting-the-Balance-of-Cybersecurity-Risk-Principles-and-"
            "Approaches-for-Secure-by-Design-Software.pdf",
            "primary",
        ),
        (
            "Threat Modeling Cheat Sheet",
            "https://cheatsheetseries.owasp.org/cheatsheets/"
            "Threat_Modeling_Cheat_Sheet.html",
            "primary",
        ),
        (
            "OWASP Application Security Verification Standard 5.0.0",
            "https://github.com/OWASP/ASVS/releases/tag/v5.0.0_release",
            "standard",
        ),
        (
            "Insider Threat Mitigation Guide",
            "https://www.cisa.gov/sites/default/files/2022-11/"
            "Insider%20Threat%20Mitigation%20Guide_Final_508.pdf",
            "primary",
        ),
    ),
}
DATA_SCALE_SOURCES = {
    "core-11-data-modeling-storage": (
        (
            "A Relational Model of Data for Large Shared Data Banks",
            "https://doi.org/10.1145/362384.362685",
            "peer-reviewed",
        ),
        (
            "Chapter 5. Data Definition",
            "https://www.postgresql.org/docs/18/ddl.html",
            "primary",
        ),
        (
            "Data Modeling in MongoDB",
            "https://www.mongodb.com/docs/v8.0/data-modeling/",
            "primary",
        ),
        (
            "Dynamo: Amazon’s Highly Available Key-value Store",
            "https://doi.org/10.1145/1294261.1294281",
            "peer-reviewed",
        ),
    ),
    "core-12-transactions-isolation-consistency": (
        (
            "Principles of Transaction-Oriented Database Recovery",
            "https://doi.org/10.1145/289.291",
            "peer-reviewed",
        ),
        (
            "A Critique of ANSI SQL Isolation Levels",
            "https://sigmodrecord.org/1995/06/06/"
            "a-critique-of-ansi-sql-isolation-levels/",
            "peer-reviewed",
        ),
        (
            "13.2. Transaction Isolation",
            "https://www.postgresql.org/docs/18/transaction-iso.html",
            "primary",
        ),
        (
            "Serializable Snapshot Isolation in PostgreSQL",
            "https://doi.org/10.14778/2367502.2367523",
            "peer-reviewed",
        ),
    ),
    "core-13-distributed-coordination-failure": (
        (
            "Impossibility of Distributed Consensus with One Faulty "
            "Process",
            "https://doi.org/10.1145/3149.214121",
            "peer-reviewed",
        ),
        (
            "In Search of an Understandable Consensus Algorithm",
            "https://raft.github.io/raft.pdf",
            "primary",
        ),
        (
            "RFC 9110: HTTP Semantics",
            "https://www.rfc-editor.org/rfc/rfc9110.html",
            "standard",
        ),
        (
            "FoundationDB: A Distributed Unbundled Transactional Key "
            "Value Store",
            "https://doi.org/10.1145/3448016.3457559",
            "peer-reviewed",
        ),
    ),
    "core-14-performance-capacity": (
        (
            "Diagnostics",
            "https://go.dev/doc/diagnostics",
            "primary",
        ),
        (
            "Handling Overload",
            "https://sre.google/sre-book/handling-overload/",
            "primary",
        ),
        (
            "A Proof for the Queuing Formula: L = λW",
            "https://doi.org/10.1287/opre.9.3.383",
            "peer-reviewed",
        ),
        (
            "The Tail at Scale",
            "https://doi.org/10.1145/2408776.2408794",
            "peer-reviewed",
        ),
        (
            "The Python Profilers",
            "https://docs.python.org/3.13/library/profile.html",
            "primary",
        ),
    ),
    "core-15-reliability-observability-slo": (
        (
            "Service Level Objectives",
            "https://sre.google/sre-book/service-level-objectives/",
            "primary",
        ),
        (
            "Alerting on SLOs",
            "https://sre.google/workbook/alerting-on-slos/",
            "primary",
        ),
        (
            "On-Call",
            "https://sre.google/workbook/on-call/",
            "primary",
        ),
        (
            "OpenTelemetry Specification 1.59.0",
            "https://opentelemetry.io/docs/specs/otel/",
            "standard",
        ),
        (
            "OpenTelemetry semantic conventions 1.43.0",
            "https://opentelemetry.io/docs/specs/semconv/",
            "standard",
        ),
    ),
}
HUMAN_PRODUCT_SOURCES = {
    "core-16-hci-usability-accessibility": (
        (
            "Web Content Accessibility Guidelines (WCAG) 2.2",
            "https://www.w3.org/TR/WCAG22/",
            "standard",
        ),
        (
            "Website Accessibility Conformance Evaluation Methodology "
            "(WCAG-EM) 1.0",
            "https://www.w3.org/TR/WCAG-EM/",
            "standard",
        ),
        (
            "ISO 9241-210:2019 - Ergonomics of human-system interaction "
            "— Part 210: Human-centred design for interactive systems",
            "https://www.iso.org/standard/77520.html",
            "standard",
        ),
        (
            "W3C Accessibility Guidelines (WCAG) 3.0 Working Draft "
            "03 March 2026",
            "https://www.w3.org/TR/wcag-3.0/",
            "primary",
        ),
    ),
    "core-17-graphics-visual-information": (
        (
            "The OpenGL Graphics System: A Specification, Version 4.6 "
            "(Core Profile), May 5, 2022",
            "https://registry.khronos.org/OpenGL/specs/gl/"
            "glspec46.core.pdf",
            "standard",
        ),
        (
            "Scalable Vector Graphics (SVG) 2",
            "https://www.w3.org/TR/SVG2/",
            "standard",
        ),
        (
            "Graphical Perception: Theory, Experimentation, and "
            "Application to the Development of Graphical Methods",
            "https://doi.org/10.1080/01621459.1984.10478080",
            "peer-reviewed",
        ),
        (
            "Visualization Analysis and Design",
            "https://www.routledge.com/Visualization-Analysis-and-Design/"
            "Munzner/p/book/9781466508910",
            "primary",
        ),
        (
            "Complex Images",
            "https://www.w3.org/WAI/tutorials/images/complex/",
            "primary",
        ),
    ),
    "core-18-product-discovery-experiments": (
        (
            "How the discovery phase works",
            "https://www.gov.uk/service-manual/agile-delivery/"
            "how-the-discovery-phase-works",
            "primary",
        ),
        (
            "Trustworthy Online Controlled Experiments: A Practical "
            "Guide to A/B Testing",
            "https://doi.org/10.1017/9781108653985",
            "primary",
        ),
        (
            "Online Experimentation at Microsoft",
            "https://www.microsoft.com/en-us/research/publication/"
            "online-experimentation-at-microsoft/",
            "primary",
        ),
        (
            "Always Valid Inference: Continuous Monitoring of A/B Tests",
            "https://doi.org/10.1287/opre.2021.2135",
            "peer-reviewed",
        ),
    ),
    "core-19-technical-communication-design-docs": (
        (
            "ISO/IEC/IEEE 42010:2022 - Software, systems and enterprise "
            "— Architecture description",
            "https://www.iso.org/standard/74393.html",
            "standard",
        ),
        (
            "NASA Systems Engineering Handbook, NASA/SP-2016-6105 Rev2",
            "https://www.nasa.gov/reference/systems-engineering-handbook/",
            "primary",
        ),
        (
            "RFC 7322: RFC Style Guide",
            "https://www.rfc-editor.org/info/rfc7322/",
            "standard",
        ),
        (
            "Markdown Architectural Decision Records 4.0.0",
            "https://adr.github.io/madr/",
            "primary",
        ),
        (
            "Plain language guide series",
            "https://digital.gov/guides/plain-language",
            "primary",
        ),
    ),
    "core-20-ethics-privacy-societal-impact": (
        (
            "ACM Code of Ethics and Professional Conduct (2018)",
            "https://www.acm.org/code-of-ethics",
            "standard",
        ),
        (
            "NIST Privacy Framework: A Tool for Improving Privacy "
            "through Enterprise Risk Management, Version 1.0",
            "https://doi.org/10.6028/NIST.CSWP.01162020",
            "standard",
        ),
        (
            "RFC 6973: Privacy Considerations for Internet Protocols",
            "https://www.rfc-editor.org/info/rfc6973/",
            "standard",
        ),
        (
            "RFC 9620: Guidelines for Human Rights Protocol and "
            "Architecture Considerations",
            "https://www.rfc-editor.org/rfc/rfc9620.html",
            "primary",
        ),
        (
            "Artificial Intelligence Risk Management Framework "
            "(AI RMF 1.0)",
            "https://doi.org/10.6028/NIST.AI.100-1",
            "standard",
        ),
    ),
}
SUSTAIN_SOURCES = {
    "core-21-maintenance-legacy-comprehension": (
        (
            "Guide to the Software Engineering Body of Knowledge "
            "(SWEBOK Guide), Version 4.0a, September 2025",
            "https://ieeecs-media.computer.org/media/education/"
            "swebok/swebok-v4.pdf",
            "standard",
        ),
        (
            "ISO/IEC/IEEE 14764:2022 - Software engineering — "
            "Software life cycle processes — Maintenance",
            "https://www.iso.org/standard/80710.html",
            "standard",
        ),
        (
            "Software maintenance and evolution: a roadmap (2000)",
            "https://doi.org/10.1145/336512.336534",
            "peer-reviewed",
        ),
        (
            "Comprehension strategies and difficulties in maintaining "
            "object-oriented systems: An explorative study (2007)",
            "https://doi.org/10.1016/j.jss.2006.10.041",
            "peer-reviewed",
        ),
    ),
    "core-22-evolution-safe-migrations": (
        (
            "DORA Capability: Database change management "
            "(accessed 2026-07-31)",
            "https://dora.dev/capabilities/database-change-management/",
            "primary",
        ),
        (
            "PostgreSQL 18 Documentation: ALTER TABLE",
            "https://www.postgresql.org/docs/18/sql-altertable.html",
            "primary",
        ),
        (
            "PostgreSQL 18 Documentation: Restrictions",
            "https://www.postgresql.org/docs/18/"
            "logical-replication-restrictions.html",
            "primary",
        ),
    ),
    "core-23-incident-response-learning": (
        (
            "NIST SP 800-61 Rev. 3: Incident Response Recommendations "
            "and Considerations for Cybersecurity Risk Management "
            "(April 2025)",
            "https://doi.org/10.6028/NIST.SP.800-61r3",
            "standard",
        ),
        (
            "Google SRE Workbook: Incident Response",
            "https://sre.google/workbook/incident-response/",
            "primary",
        ),
        (
            "Google SRE Workbook: Postmortem Culture — "
            "Learning from Failure",
            "https://sre.google/workbook/postmortem-culture/",
            "primary",
        ),
    ),
    "core-24-delivery-ci-release-safety": (
        (
            "SLSA Specification Version 1.2 (Approved)",
            "https://slsa.dev/spec/v1.2/",
            "standard",
        ),
        (
            "DORA's software delivery performance metrics "
            "(updated January 5, 2026)",
            "https://dora.dev/guides/dora-metrics/",
            "primary",
        ),
        (
            "DORA Capability: Continuous delivery "
            "(accessed 2026-07-31)",
            "https://dora.dev/capabilities/continuous-delivery/",
            "primary",
        ),
        (
            "NIST SP 800-218: Secure Software Development Framework "
            "Version 1.1 (February 2022)",
            "https://doi.org/10.6028/NIST.SP.800-218",
            "standard",
        ),
    ),
    "core-25-engineering-economics-capacity": (
        (
            "FinOps Framework Capability: Unit Economics "
            "(accessed 2026-07-31)",
            "https://www.finops.org/framework/capabilities/"
            "unit-economics/",
            "primary",
        ),
        (
            "FinOps Framework Capability: Architecting & Workload "
            "Placement (accessed 2026-07-31)",
            "https://www.finops.org/framework/capabilities/"
            "architecting-workload-placement/",
            "primary",
        ),
        (
            "AWS Well-Architected Framework: Cost Optimization Pillar "
            "(June 27, 2024)",
            "https://docs.aws.amazon.com/wellarchitected/latest/"
            "cost-optimization-pillar/welcome.html",
            "primary",
        ),
        (
            "Google Cloud Well-Architected Framework: "
            "Cost optimization pillar (accessed 2026-07-31)",
            "https://docs.cloud.google.com/architecture/framework/"
            "cost-optimization",
            "primary",
        ),
    ),
}
FOUNDATIONS = {
    "core-01-systems-tradeoffs": {
        "prerequisites": (),
        "artifact": "制約、代替案、反証条件を含む意思決定記録",
        "transfer": "医療予約システムで同じ判断を再実施",
    },
    "core-02-algorithms-measurement": {
        "prerequisites": ("core-01-systems-tradeoffs",),
        "artifact": "計算量予測と実測値の差を説明するベンチマーク報告",
        "transfer": "データ分布が変わる場合のアルゴリズム再選択",
    },
    "core-03-architecture-memory-caches": {
        "prerequisites": ("core-01-systems-tradeoffs",),
        "artifact": "アクセス局所性を変えた測定とCPU・メモリ経路図",
        "transfer": "データ指向設計を別の処理系へ適用",
    },
    "core-04-os-processes-concurrency": {
        "prerequisites": (
            "core-02-algorithms-measurement",
            "core-03-architecture-memory-caches",
        ),
        "artifact": "競合を再現し不変条件で修正した実験記録",
        "transfer": "プロセス分離とスレッド共有の再比較",
    },
    "core-05-networks-latency-failure": {
        "prerequisites": ("core-04-os-processes-concurrency",),
        "artifact": "DNSからHTTPまでの時系列トレースとタイムアウト予算",
        "transfer": "パケット損失と依存遅延を区別する診断",
    },
}
BUILD = {
    "core-06-requirements-domain-modeling": {
        "prerequisites": ("core-01-systems-tradeoffs",),
        "artifact": "用語集、境界、例外を含むドメインモデル",
        "transfer": (
            "未知のレンタル事業で用語の衝突と未宣言ルールを発見し、"
            "境界と例外を再構成する"
        ),
    },
    "core-07-api-contract-design": {
        "prerequisites": ("core-06-requirements-domain-modeling",),
        "artifact": "互換性、冪等性、失敗形式を含むAPI契約",
        "transfer": (
            "長時間オフラインになる現場端末へ互換な再送・同期API契約を"
            "設計する"
        ),
    },
    "core-08-modularity-evolutionary-architecture": {
        "prerequisites": (
            "core-06-requirements-domain-modeling",
            "core-07-api-contract-design",
        ),
        "artifact": "変更理由と依存方向を説明するモジュール図とADR",
        "transfer": (
            "変更頻度が高い料金計算モジュールの依存方向を再設計し、"
            "ADRで判断を更新する"
        ),
    },
    "core-09-test-strategy-tdd": {
        "prerequisites": (
            "core-02-algorithms-measurement",
            "core-08-modularity-evolutionary-architecture",
        ),
        "artifact": "RED-GREEN-REFACTOR履歴とリスク別テスト戦略",
        "transfer": (
            "順序と時刻に依存する非決定的障害を再現し、"
            "リスク別テスト戦略で診断する"
        ),
    },
    "core-10-threat-modeling-secure-design": {
        "prerequisites": (
            "core-07-api-contract-design",
            "core-09-test-strategy-tdd",
        ),
        "artifact": "資産、境界、攻撃経路、検証を結ぶ脅威モデル",
        "transfer": (
            "正規権限を持つ委託運用者の誤操作・資格情報悪用を含む"
            "内部者脅威へモデルを移す"
        ),
    },
}
DATA_SCALE = {
    "core-11-data-modeling-storage": {
        "prerequisites": ("core-06-requirements-domain-modeling",),
        "artifact": "アクセスパターン、整合性、成長予測を含むストレージADR",
        "transfer": (
            "注文検索が顧客中心から商品・期間中心へ変わるアクセスパターン"
            "変更でストレージADRを再評価する"
        ),
    },
    "core-12-transactions-isolation-consistency": {
        "prerequisites": ("core-11-data-modeling-storage",),
        "artifact": "二つの分離異常を再現するトランザクション実験",
        "transfer": (
            "同時購入者数が増える在庫引当の並行性変更で分離レベルと"
            "retry境界を再評価する"
        ),
    },
    "core-13-distributed-coordination-failure": {
        "prerequisites": (
            "core-05-networks-latency-failure",
            "core-12-transactions-isolation-consistency",
        ),
        "artifact": "重複、順序、部分障害を再現する決定的シミュレーション",
        "transfer": (
            "拠点間ネットワーク分断が長期化する条件へ変え、重複排除と"
            "復旧結果を再評価する"
        ),
    },
    "core-14-performance-capacity": {
        "prerequisites": (
            "core-02-algorithms-measurement",
            "core-03-architecture-memory-caches",
            "core-11-data-modeling-storage",
        ),
        "artifact": "ボトルネック証拠、負荷曲線、容量限界を含む性能報告",
        "transfer": (
            "参照中心から書込み中心へ変わるrequest mixでbottleneckと"
            "安全容量を再測定する"
        ),
    },
    "core-15-reliability-observability-slo": {
        "prerequisites": (
            "core-05-networks-latency-failure",
            "core-13-distributed-coordination-failure",
            "core-14-performance-capacity",
        ),
        "artifact": "利用者ジャーニーから導いたSLI、SLO、アラート、ランブック",
        "transfer": (
            "検索成功率から購入完了までへ利用者可視の信頼性境界を変え、"
            "SLIとSLOを再設計する"
        ),
    },
}
DATA_SCALE_ASSUMPTIONS = {
    "core-11-data-modeling-storage": "access-pattern",
    "core-12-transactions-isolation-consistency": "concurrency",
    "core-13-distributed-coordination-failure": "network-partition",
    "core-14-performance-capacity": "request-mix",
    "core-15-reliability-observability-slo": "user-visible-reliability",
}
HUMAN_PRODUCT = {
    "core-16-hci-usability-accessibility": {
        "prerequisites": ("core-06-requirements-domain-modeling",),
        "artifact": "キーボード、ズーム、読み上げ、ユーザビリティの監査記録",
        "transfer": (
            "pointer操作中心からkeyboard-only利用へ入力方式だけを変え、"
            "生成サイト監査を再評価する"
        ),
    },
    "core-17-graphics-visual-information": {
        "prerequisites": (
            "core-03-architecture-memory-caches",
            "core-16-hci-usability-accessibility",
        ),
        "artifact": "視覚表現と同等のテキスト構造を持つ静的データ図",
        "transfer": (
            "color表示からmonochrome表示へ変え、roadmapとchartの"
            "同等情報を再検証する"
        ),
    },
    "core-18-product-discovery-experiments": {
        "prerequisites": (
            "core-06-requirements-domain-modeling",
            "core-16-hci-usability-accessibility",
        ),
        "artifact": "反証可能な仮説、成功指標、停止条件を持つ実験計画",
        "transfer": (
            "guardrail上限だけを厳しくし、同じ実験結果の継続・停止判断を"
            "再評価する"
        ),
    },
    "core-19-technical-communication-design-docs": {
        "prerequisites": (
            "core-01-systems-tradeoffs",
            "core-06-requirements-domain-modeling",
        ),
        "artifact": "読者別の要約、代替案、リスク、決定を含む設計文書",
        "transfer": (
            "経営読者から実装読者へaudienceだけを変え、同じ決定証拠を"
            "再構成する"
        ),
    },
    "core-20-ethics-privacy-societal-impact": {
        "prerequisites": (
            "core-10-threat-modeling-secure-design",
            "core-16-hci-usability-accessibility",
            "core-19-technical-communication-design-docs",
        ),
        "artifact": "影響を受ける人、データライフサイクル、軽減策を含む影響評価",
        "transfer": (
            "平均的利用者から高リスク集団を含むaffected populationへ"
            "変え、残余riskを再評価する"
        ),
    },
}
HUMAN_PRODUCT_ASSUMPTIONS = {
    "core-16-hci-usability-accessibility": "input-mode",
    "core-17-graphics-visual-information": "display-mode",
    "core-18-product-discovery-experiments": "guardrail-threshold",
    "core-19-technical-communication-design-docs": "audience",
    "core-20-ethics-privacy-societal-impact": "affected-population",
}
SUSTAIN = {
    "core-21-maintenance-legacy-comprehension": {
        "prerequisites": (
            "core-08-modularity-evolutionary-architecture",
            "core-09-test-strategy-tdd",
        ),
        "artifact": (
            "実行経路、変更理由、未知領域を示すシステム地図と特性テスト"
        ),
        "transfer": (
            "割引率変更から税丸め変更へchange requestだけを変え、"
            "同じlegacy fixtureの影響経路、未知領域、特性テストを再構成する"
        ),
    },
    "core-22-evolution-safe-migrations": {
        "prerequisites": (
            "core-08-modularity-evolutionary-architecture",
            "core-12-transactions-isolation-consistency",
            "core-21-maintenance-legacy-comprehension",
        ),
        "artifact": (
            "expand-contract段階、観測、停止、ロールバックを含む移行計画"
        ),
        "transfer": (
            "backfill error rateだけを変え、同じ移行計画の継続・停止・"
            "ロールバック判断を再評価する"
        ),
    },
    "core-23-incident-response-learning": {
        "prerequisites": (
            "core-15-reliability-observability-slo",
            "core-21-maintenance-legacy-comprehension",
        ),
        "artifact": (
            "影響、意思決定、証拠、寄与要因、検証可能な対策を含むレビュー"
        ),
        "transfer": (
            "検知遅延だけを変え、同じincident evidenceから影響時間と"
            "学習行動を再評価する"
        ),
    },
    "core-24-delivery-ci-release-safety": {
        "prerequisites": (
            "core-09-test-strategy-tdd",
            "core-15-reliability-observability-slo",
        ),
        "artifact": (
            "失敗を閉じるCI、段階配信、来歴、ロールバックの実行証拠"
        ),
        "transfer": (
            "canary error rateだけを変え、同じartifactとprovenanceで"
            "段階配信のadvance・rollback判断を再評価する"
        ),
    },
    "core-25-engineering-economics-capacity": {
        "prerequisites": (
            "core-14-performance-capacity",
            "core-15-reliability-observability-slo",
            "core-24-delivery-ci-release-safety",
        ),
        "artifact": (
            "機会費用、運用時間、信頼性、容量を含む投資比較"
        ),
        "transfer": (
            "demand growthだけを変え、同じ投資候補のunit economicsと"
            "選択を感度分析で再評価する"
        ),
    },
}
SUSTAIN_ASSUMPTIONS = {
    "core-21-maintenance-legacy-comprehension": "change-request",
    "core-22-evolution-safe-migrations": "backfill-error-rate",
    "core-23-incident-response-learning": "detection-delay",
    "core-24-delivery-ci-release-safety": "canary-error-rate",
    "core-25-engineering-economics-capacity": "demand-growth",
}
SUSTAIN_HARNESSES = {
    "core-21-maintenance-legacy-comprehension": (
        "legacy_comprehension_lab_v1",
        "synthetic",
    ),
    "core-22-evolution-safe-migrations": (
        "migration_state_machine_lab_v1",
        "simulated",
    ),
    "core-23-incident-response-learning": (
        "incident_learning_review_lab_v1",
        "simulated",
    ),
    "core-24-delivery-ci-release-safety": (
        "delivery_safety_lab_v1",
        "simulated",
    ),
    "core-25-engineering-economics-capacity": (
        "engineering_economics_lab_v1",
        "synthetic",
    ),
}
DEPRECATED_SUSTAIN_IDS = (
    "core-21-legacy-systems-maintenance",
    "core-22-database-schema-migration",
    "core-24-delivery-ci-supply-chain",
    "core-25-engineering-economics",
)


class _BodyContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.section_depth = 0
        self.headings: list[str] = []
        self.definition_terms: list[str] = []
        self.table_captions: list[str] = []
        self.figure_count = 0
        self.figure_captions: list[str] = []
        self.table_count = 0
        self.table_headers_without_scope: list[str] = []
        self.misdiagnosis_items: list[str] = []
        self.worked_example_text: list[str] = []
        self.worked_example_code: list[str] = []
        self.dangerous_elements: list[str] = []
        self.unsafe_attributes: list[tuple[str, str]] = []
        self._heading_text: list[str] | None = None
        self._definition_text: list[str] | None = None
        self._caption_text: list[str] | None = None
        self._figure_caption_text: list[str] | None = None
        self._list_item_text: list[str] | None = None
        self._worked_code_text: list[str] | None = None
        self._in_worked_example = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        parent = self.stack[-1] if self.stack else None
        values = {
            name.casefold(): value or ""
            for name, value in attrs
        }
        if normalized_tag == "section":
            self.section_depth += 1
            if values.get("id") == "worked-example":
                self._in_worked_example = True
        if normalized_tag == "figure":
            self.figure_count += 1
        if normalized_tag == "table":
            self.table_count += 1
        if normalized_tag in {"script", "style"}:
            self.dangerous_elements.append(normalized_tag)
        if normalized_tag == "figcaption" and parent == "figure":
            self._figure_caption_text = []
        if normalized_tag == "th" and values.get("scope") not in {
            "col",
            "row",
            "colgroup",
            "rowgroup",
        }:
            self.table_headers_without_scope.append(values.get("scope", ""))
        if normalized_tag == "li":
            self._list_item_text = []
        if (
            normalized_tag == "code"
            and parent == "pre"
            and self._in_worked_example
        ):
            self._worked_code_text = []
        if (
            normalized_tag == "h2"
            and parent == "section"
            and self.section_depth == 1
        ):
            self._heading_text = []
        elif normalized_tag == "dt":
            self._definition_text = []
        elif normalized_tag == "caption" and parent == "table":
            self._caption_text = []

        for name, value in attrs:
            normalized_name = name.casefold()
            candidate = value or ""
            if (
                normalized_name == "style"
                or normalized_name.startswith("on")
            ):
                self.unsafe_attributes.append(
                    (normalized_name, candidate)
                )
            if normalized_name in {
                "href",
                "src",
                "action",
                "formaction",
            } and (
                "://" in candidate
                or candidate.startswith(("//", "\\"))
                or candidate.casefold().startswith(
                    ("data:", "javascript:", "vbscript:")
                )
            ):
                self.unsafe_attributes.append(
                    (normalized_name, candidate)
                )
        self.stack.append(normalized_tag)

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag == "h2" and self._heading_text is not None:
            self.headings.append(self._normalized(self._heading_text))
            self._heading_text = None
        elif normalized_tag == "dt" and self._definition_text is not None:
            self.definition_terms.append(
                self._normalized(self._definition_text)
            )
            self._definition_text = None
        elif normalized_tag == "caption" and self._caption_text is not None:
            self.table_captions.append(
                self._normalized(self._caption_text)
            )
            self._caption_text = None
        elif (
            normalized_tag == "figcaption"
            and self._figure_caption_text is not None
        ):
            self.figure_captions.append(
                self._normalized(self._figure_caption_text)
            )
            self._figure_caption_text = None
        elif normalized_tag == "li" and self._list_item_text is not None:
            item = self._normalized(self._list_item_text)
            if "誤診:" in item:
                self.misdiagnosis_items.append(item)
            self._list_item_text = None
        elif (
            normalized_tag == "code"
            and self._worked_code_text is not None
        ):
            self.worked_example_code.append(
                self._normalized(self._worked_code_text)
            )
            self._worked_code_text = None
        if normalized_tag == "section":
            self.section_depth -= 1
            if self._in_worked_example:
                self._in_worked_example = False
        if self.stack:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        for buffer in (
            self._heading_text,
            self._definition_text,
            self._caption_text,
            self._figure_caption_text,
            self._list_item_text,
            self._worked_code_text,
        ):
            if buffer is not None:
                buffer.append(data)
        if self._in_worked_example:
            self.worked_example_text.append(data)

    @staticmethod
    def _normalized(parts: list[str]) -> str:
        return " ".join("".join(parts).split())


class _PreCodeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._in_pre = False
        self._code_text: list[str] | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.casefold() == "pre":
            self._in_pre = True
        elif tag.casefold() == "code" and self._in_pre:
            self._code_text = []

    def handle_data(self, data: str) -> None:
        if self._code_text is not None:
            self._code_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "code" and self._code_text is not None:
            self.blocks.append("".join(self._code_text))
            self._code_text = None
        elif tag.casefold() == "pre":
            self._in_pre = False


class _StaticArtifactParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.ids: list[str] = []
        self.edge_pairs: list[list[str]] = []
        self.meter_values: list[dict[str, int | str]] = []
        self.table_header_scopes: list[str] = []
        self.unsafe: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        values = {
            name.casefold(): value or ""
            for name, value in attrs
        }
        self.tags.append(normalized_tag)
        if values.get("id"):
            self.ids.append(values["id"])
        if normalized_tag == "li" and {
            "data-from",
            "data-to",
        }.issubset(values):
            self.edge_pairs.append(
                [values["data-from"], values["data-to"]]
            )
        if normalized_tag == "th":
            self.table_header_scopes.append(values.get("scope", ""))
        if normalized_tag == "meter":
            self.meter_values.append(
                {
                    "id": values.get("data-id", ""),
                    "min": int(values.get("min", "-1")),
                    "max": int(values.get("max", "-1")),
                    "value": int(values.get("value", "-1")),
                    "raw_value": int(
                        values.get("data-raw-value", "-1")
                    ),
                }
            )
        if normalized_tag in {
            "script",
            "style",
            "iframe",
            "object",
            "embed",
        }:
            self.unsafe.append(normalized_tag)
        for name, value in attrs:
            normalized_name = name.casefold()
            candidate = value or ""
            if (
                normalized_name == "style"
                or normalized_name.startswith("on")
                or "://" in candidate
            ):
                self.unsafe.append(normalized_name)


class CoreTrackTests(unittest.TestCase):
    def body_path(self, lesson_id: str) -> Path:
        return (
            REPOSITORY_ROOT
            / "content"
            / "lessons"
            / lesson_id
            / "body.html"
        )

    def run_python_harness(
        self,
        lesson_id: str,
        marker: str,
        *,
        environment: dict[str, str] | None = None,
    ) -> dict[str, object]:
        body = self.body_path(lesson_id).read_text(encoding="utf-8")
        parser = _PreCodeParser()
        parser.feed(body)
        parser.close()
        matching = [block for block in parser.blocks if marker in block]
        self.assertEqual(len(matching), 1, f"{lesson_id}: {marker}")
        command, separator, remainder = matching[0].partition("\n")
        self.assertTrue(separator, f"{lesson_id}: harness command")
        self.assertTrue(
            command.startswith("python3.13 - "),
            f"{lesson_id}: Python 3.13 harness",
        )
        payload, terminator, _ = remainder.partition("\nPY")
        self.assertTrue(terminator, f"{lesson_id}: heredoc terminator")
        with TemporaryDirectory() as directory:
            script = Path(directory) / "harness.py"
            script.write_text(payload, encoding="utf-8")
            process_environment = os.environ.copy()
            if environment is not None:
                process_environment.update(environment)
            result = subprocess.run(
                [sys.executable, script],
                cwd=directory,
                env=process_environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            document = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            self.fail(f"{lesson_id}: invalid JSON output: {error}")
        self.assertIs(type(document), dict)
        return document

    def pre_code_blocks(self, lesson_id: str) -> list[str]:
        body = self.body_path(lesson_id).read_text(encoding="utf-8")
        parser = _PreCodeParser()
        parser.feed(body)
        parser.close()
        return parser.blocks

    def python_harness_source(
        self,
        lesson_id: str,
        marker: str,
    ) -> str:
        matching = [
            block
            for block in self.pre_code_blocks(lesson_id)
            if marker in block
        ]
        self.assertEqual(len(matching), 1, f"{lesson_id}: {marker}")
        command, separator, remainder = matching[0].partition("\n")
        self.assertTrue(separator, f"{lesson_id}: harness command")
        self.assertTrue(
            command.startswith("python3.13 - "),
            f"{lesson_id}: Python 3.13 harness",
        )
        payload, terminator, _ = remainder.partition("\nPY")
        self.assertTrue(terminator, f"{lesson_id}: heredoc terminator")
        return payload

    def execute_python_harness_source(
        self,
        payload: str,
    ) -> subprocess.CompletedProcess[str]:
        with TemporaryDirectory() as directory:
            script = Path(directory) / "harness.py"
            script.write_text(payload, encoding="utf-8")
            return subprocess.run(
                [sys.executable, script],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

    def assert_data_scale_mastery_evidence(
        self,
        report: dict[str, object],
        lesson_id: str,
    ) -> None:
        metadata_path = self.body_path(lesson_id).with_name("lesson.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        mastery = report["mastery_evidence"]

        lab_steps = mastery["lab_steps"]
        self.assertEqual(
            [item["step"] for item in lab_steps],
            list(range(1, len(metadata["lab"]["steps"]) + 1)),
        )
        self.assertTrue(all(item["evidence"] for item in lab_steps))

        assessments = mastery["assessments"]
        self.assertEqual(
            [item["assessment"] for item in assessments],
            list(range(1, len(metadata["assessment"]) + 1)),
        )
        self.assertTrue(all(item["evidence"] for item in assessments))

        self.assertEqual(
            set(mastery["rubric_dimensions"]),
            {
                item["dimension"]
                for item in metadata["rubric"]
            },
        )
        transfer = mastery["transfer"]
        self.assertEqual(transfer["task"], metadata["transferTask"])
        self.assertEqual(
            transfer["changed_assumption"],
            DATA_SCALE_ASSUMPTIONS[lesson_id],
        )
        self.assertTrue(transfer["evidence"])

    def assert_human_product_mastery_evidence(
        self,
        report: dict[str, object],
        lesson_id: str,
    ) -> None:
        metadata_path = self.body_path(lesson_id).with_name("lesson.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        mastery = report["mastery_evidence"]

        self.assertEqual(
            [item["step"] for item in mastery["lab_steps"]],
            list(range(1, len(metadata["lab"]["steps"]) + 1)),
        )
        self.assertTrue(
            all(item["evidence"] for item in mastery["lab_steps"]),
        )
        self.assertEqual(
            [item["assessment"] for item in mastery["assessments"]],
            list(range(1, len(metadata["assessment"]) + 1)),
        )
        self.assertTrue(
            all(item["evidence"] for item in mastery["assessments"]),
        )
        self.assertEqual(
            set(mastery["rubric_dimensions"]),
            {item["dimension"] for item in metadata["rubric"]},
        )
        transfer = mastery["transfer"]
        self.assertEqual(transfer["task"], metadata["transferTask"])
        self.assertEqual(
            transfer["changed_assumption"],
            HUMAN_PRODUCT_ASSUMPTIONS[lesson_id],
        )
        self.assertTrue(transfer["evidence"])

    def assert_human_product_harness_contract(
        self,
        report: dict[str, object],
        lesson_id: str,
        expected_kind: str,
    ) -> None:
        metadata = report["fixture_metadata"]
        self.assertEqual(metadata["kind"], expected_kind)
        self.assertTrue(metadata["provenance"])
        self.assertTrue(metadata["limitations"])
        runtime_bound = report["runtime_bound"]
        self.assertGreater(runtime_bound["records"], 0)
        self.assertLessEqual(runtime_bound["records"], 1_000)
        self.assertEqual(runtime_bound["subprocesses"], 0)
        self.assertFalse(report["external_network_used"])
        self.assert_human_product_mastery_evidence(report, lesson_id)

    def assert_sustain_mastery_evidence(
        self,
        report: dict[str, object],
        lesson_id: str,
    ) -> None:
        metadata_path = self.body_path(lesson_id).with_name("lesson.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        mastery = report["mastery_evidence"]

        self.assertEqual(
            [item["step"] for item in mastery["lab_steps"]],
            list(range(1, len(metadata["lab"]["steps"]) + 1)),
        )
        self.assertTrue(
            all(item["evidence"] for item in mastery["lab_steps"]),
        )
        self.assertEqual(
            [item["assessment"] for item in mastery["assessments"]],
            list(range(1, len(metadata["assessment"]) + 1)),
        )
        self.assertTrue(
            all(item["evidence"] for item in mastery["assessments"]),
        )
        self.assertEqual(
            set(mastery["rubric_dimensions"]),
            {item["dimension"] for item in metadata["rubric"]},
        )
        transfer = mastery["transfer"]
        self.assertEqual(transfer["task"], metadata["transferTask"])
        self.assertEqual(
            transfer["changed_assumption"],
            SUSTAIN_ASSUMPTIONS[lesson_id],
        )
        self.assertTrue(transfer["evidence"])

    def assert_sustain_harness_contract(
        self,
        report: dict[str, object],
        lesson_id: str,
        expected_kind: str,
    ) -> None:
        metadata = report["fixture_metadata"]
        self.assertEqual(metadata["kind"], expected_kind)
        self.assertTrue(metadata["provenance"])
        self.assertTrue(metadata["limitations"])
        self.assertTrue(metadata["synthetic_or_observed_explicit"])

        runtime_bound = report["runtime_bound"]
        self.assertGreater(runtime_bound["records"], 0)
        self.assertLessEqual(runtime_bound["records"], 1_000)
        self.assertEqual(runtime_bound["subprocesses"], 0)
        self.assertLessEqual(runtime_bound["maximum_iterations"], 1_000)
        self.assertFalse(report["external_network_used"])

        distinction = report["command_success_distinction"]
        self.assertTrue(distinction["command_completed"])
        self.assertTrue(distinction["system_outcome_checked"])
        self.assertFalse(
            distinction["command_success_equals_system_outcome"],
        )
        self.assertTrue(distinction["outcome_evidence"])
        self.assert_sustain_mastery_evidence(report, lesson_id)

    def assert_sustain_harness_source_is_safe(
        self,
        lesson_id: str,
        marker: str,
    ) -> None:
        source = self.python_harness_source(lesson_id, marker)
        tree = ast.parse(source)
        allowed_modules = {"hashlib", "json", "math", "statistics"}
        forbidden_calls = {
            "compile",
            "eval",
            "exec",
            "input",
            "open",
            "__import__",
        }
        imported_modules: set[str] = set()
        called_names: set[str] = set()
        for node in ast.walk(tree):
            self.assertNotIsInstance(
                node,
                ast.While,
                f"{lesson_id}: unbounded while loop",
            )
            if isinstance(node, ast.Import):
                imported_modules.update(
                    alias.name.partition(".")[0]
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add((node.module or "").partition(".")[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called_names.add(node.func.id)

        self.assertLessEqual(imported_modules, allowed_modules)
        self.assertTrue(called_names.isdisjoint(forbidden_calls))
        self.assertNotRegex(
            source,
            r"\b(?:os|pathlib|socket|subprocess|urllib|requests)\b",
        )

    def assert_harness_source_mutation_fails(
        self,
        lesson_id: str,
        marker: str,
        original: str,
        replacement: str,
    ) -> None:
        source = self.python_harness_source(lesson_id, marker)
        self.assertIn(original, source)
        mutated = source.replace(original, replacement, 1)
        self.assertNotEqual(mutated, source)

        result = self.execute_python_harness_source(mutated)

        self.assertNotEqual(result.returncode, 0)

    def assert_causal_harness_source_mutation_fails(
        self,
        lesson_id: str,
        marker: str,
        original: str,
        replacement: str,
        diagnostic: str,
    ) -> None:
        source = self.python_harness_source(lesson_id, marker)
        self.assertIn(original, source)
        mutated = source.replace(original, replacement, 1)
        self.assertNotEqual(mutated, source)

        result = self.execute_python_harness_source(mutated)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(diagnostic, result.stderr)

    def assert_body_contract(self, body: str, lesson_id: str) -> None:
        parser = _BodyContractParser()
        parser.feed(body)
        parser.close()

        self.assertEqual(
            tuple(parser.headings),
            BODY_HEADINGS,
            f"{lesson_id}: ordered section headings",
        )
        self.assertGreaterEqual(
            parser.figure_count,
            1,
            f"{lesson_id}: mechanism figure",
        )
        self.assertEqual(
            len(parser.figure_captions),
            parser.figure_count,
            f"{lesson_id}: every figure has a caption",
        )
        self.assertTrue(
            all(parser.figure_captions),
            f"{lesson_id}: non-empty figure caption",
        )
        self.assertEqual(
            len(parser.table_captions),
            parser.table_count,
            f"{lesson_id}: every table has a caption",
        )
        self.assertTrue(
            all(parser.table_captions),
            f"{lesson_id}: non-empty table caption",
        )
        self.assertEqual(
            parser.table_headers_without_scope,
            [],
            f"{lesson_id}: every table header has scope",
        )
        self.assertTrue(
            any("decision table" in text for text in parser.table_captions),
            f"{lesson_id}: captioned decision table",
        )
        self.assertTrue(
            {"前提", "入力", "操作", "観測", "結論"}.issubset(
                parser.definition_terms
            ),
            f"{lesson_id}: worked example stages",
        )
        self.assertGreaterEqual(
            len(parser.misdiagnosis_items),
            2,
            f"{lesson_id}: plausible misdiagnoses",
        )
        self.assertTrue(
            all("反証:" in item for item in parser.misdiagnosis_items),
            f"{lesson_id}: misdiagnosis and rebuttal share one list item",
        )
        worked_text = " ".join(parser.worked_example_text)
        self.assertTrue(
            bool(re.search(r"\d", worked_text))
            or any(parser.worked_example_code),
            f"{lesson_id}: numeric or executable worked example",
        )
        self.assertIn("断定への注意:", body, f"{lesson_id}: caution")
        self.assertNotIn("http://", body, f"{lesson_id}: external URL")
        self.assertNotIn("https://", body, f"{lesson_id}: external URL")
        self.assertEqual(
            parser.dangerous_elements,
            [],
            f"{lesson_id}: script or style element",
        )
        self.assertEqual(
            parser.unsafe_attributes,
            [],
            f"{lesson_id}: inline behavior or remote resource",
        )

    def assert_track(
        self,
        contract: dict[str, dict[str, object]],
        *,
        expected_track: str,
        source_contract: dict[
            str,
            tuple[tuple[str, str, str], ...],
        ] | None,
    ) -> None:
        for lesson_id, expected in contract.items():
            with self.subTest(lesson_id=lesson_id):
                path = (
                    REPOSITORY_ROOT
                    / "content"
                    / "lessons"
                    / lesson_id
                    / "lesson.json"
                )
                self.assertTrue(path.is_file(), f"missing {path}")
                lesson = load_lesson(path)

                self.assertEqual(lesson.track, expected_track)
                self.assertEqual(lesson.status, "complete")
                self.assertEqual(
                    lesson.prerequisite_ids,
                    tuple(expected["prerequisites"]),
                )
                self.assertIsNotNone(lesson.lab)
                assert lesson.lab is not None
                self.assertEqual(lesson.lab.artifact, expected["artifact"])
                self.assertEqual(lesson.transfer_task, expected["transfer"])
                self.assertEqual(
                    tuple(
                        item.level
                        for item in lesson.capability_progression
                    ),
                    ("recognize", "explain", "apply", "diagnose", "lead"),
                )
                self.assertEqual(lesson.review_intervals, (1, 7, 30, 90))
                self.assertEqual(lesson.updated_at, "2026-07-30")
                if source_contract is not None:
                    self.assertEqual(
                        tuple(
                            (source.title, source.url, source.kind)
                            for source in lesson.sources
                        ),
                        source_contract[lesson_id],
                    )

    def test_foundations(self) -> None:
        self.assert_track(
            FOUNDATIONS,
            expected_track="foundations",
            source_contract=FOUNDATION_SOURCES,
        )

    def test_build(self) -> None:
        self.assert_track(
            BUILD,
            expected_track="build",
            source_contract=BUILD_SOURCES,
        )

    def test_data_scale(self) -> None:
        self.assert_track(
            DATA_SCALE,
            expected_track="data-scale",
            source_contract=DATA_SCALE_SOURCES,
        )

    def test_human_product(self) -> None:
        self.assert_track(
            HUMAN_PRODUCT,
            expected_track="human-product",
            source_contract=HUMAN_PRODUCT_SOURCES,
        )

    def test_sustain(self) -> None:
        self.assert_track(
            SUSTAIN,
            expected_track="sustain",
            source_contract=SUSTAIN_SOURCES,
        )

    def test_sustain_uses_only_canonical_lesson_ids(self) -> None:
        lessons_root = REPOSITORY_ROOT / "content" / "lessons"
        for deprecated_id in DEPRECATED_SUSTAIN_IDS:
            with self.subTest(deprecated_id=deprecated_id):
                self.assertFalse(
                    (lessons_root / deprecated_id).exists(),
                    f"deprecated Sustain lesson id: {deprecated_id}",
                )

    def test_foundation_bodies_follow_semantic_contract(self) -> None:
        for lesson_id in FOUNDATIONS:
            with self.subTest(lesson_id=lesson_id):
                body = self.body_path(lesson_id).read_text(encoding="utf-8")
                self.assert_body_contract(body, lesson_id)

    def test_build_bodies_follow_semantic_contract(self) -> None:
        for lesson_id in BUILD:
            with self.subTest(lesson_id=lesson_id):
                body = self.body_path(lesson_id).read_text(encoding="utf-8")
                self.assert_body_contract(body, lesson_id)

    def test_data_scale_bodies_follow_semantic_contract(self) -> None:
        for lesson_id in DATA_SCALE:
            with self.subTest(lesson_id=lesson_id):
                body = self.body_path(lesson_id).read_text(encoding="utf-8")
                self.assert_body_contract(body, lesson_id)

    def test_human_product_bodies_follow_semantic_contract(self) -> None:
        for lesson_id in HUMAN_PRODUCT:
            with self.subTest(lesson_id=lesson_id):
                body = self.body_path(lesson_id).read_text(encoding="utf-8")
                self.assert_body_contract(body, lesson_id)

    def test_sustain_bodies_follow_semantic_contract(self) -> None:
        for lesson_id in SUSTAIN:
            with self.subTest(lesson_id=lesson_id):
                body = self.body_path(lesson_id).read_text(encoding="utf-8")
                self.assert_body_contract(body, lesson_id)

    def test_sustain_bodies_scope_standards_and_system_outcomes(
        self,
    ) -> None:
        required_markers = {
            "core-21-maintenance-legacy-comprehension": (
                "SWEBOK Guide Version 4.0a",
                "ISO/IEC/IEEE 14764:2022",
                "program comprehension",
                "characterization test",
                "unknown",
            ),
            "core-22-evolution-safe-migrations": (
                "expand",
                "dual write",
                "backfill",
                "dual read",
                "contract",
                "stop",
                "rollback",
            ),
            "core-23-incident-response-learning": (
                "NIST SP 800-61 Rev. 3",
                "evidence timeline",
                "contributing factor",
                "non-blaming",
                "verifiable action",
            ),
            "core-24-delivery-ci-release-safety": (
                "SLSA v1.2",
                "Approved",
                "NIST SSDF 1.1",
                "five metrics",
                "fail-closed",
                "provenance presence alone",
                "rollback outcome",
            ),
            "core-25-engineering-economics-capacity": (
                "FinOps Framework",
                "unit economics",
                "opportunity cost",
                "operations hours",
                "reliability",
                "capacity",
                "sensitivity",
                "price accuracy",
            ),
        }
        for lesson_id, markers in required_markers.items():
            with self.subTest(lesson_id=lesson_id):
                body = self.body_path(lesson_id).read_text(encoding="utf-8")
                for marker in markers:
                    self.assertIn(marker, body, f"{lesson_id}: {marker}")
                self.assertIn(
                    "command success",
                    body,
                    f"{lesson_id}: command/system distinction",
                )
                self.assertIn(
                    "system outcome",
                    body,
                    f"{lesson_id}: command/system distinction",
                )

    def test_sustain_bodies_are_static_and_harnesses_are_safe(
        self,
    ) -> None:
        for lesson_id, (marker, _) in SUSTAIN_HARNESSES.items():
            with self.subTest(lesson_id=lesson_id):
                body = self.body_path(lesson_id).read_text(encoding="utf-8")
                self.assertNotIn("http://", body)
                self.assertNotIn("https://", body)
                self.assertNotRegex(body, r"(?i)<\s*(?:script|style)\b")
                self.assertNotRegex(body, r"(?i)\sstyle\s*=")
                self.assertNotRegex(
                    body,
                    r"(?i)(?:javascript|data)\s*:",
                )
                self.assert_sustain_harness_source_is_safe(
                    lesson_id,
                    marker,
                )

    def test_sustain_body_ids_do_not_collide_with_lesson_template(
        self,
    ) -> None:
        template = (
            REPOSITORY_ROOT / "templates" / "lesson.html"
        ).read_text(encoding="utf-8")
        template_ids = set(re.findall(r'\bid="([^"]+)"', template))
        self.assertTrue(template_ids)

        for lesson_id in SUSTAIN:
            with self.subTest(lesson_id=lesson_id):
                body = self.body_path(lesson_id).read_text(encoding="utf-8")
                body_ids = set(re.findall(r'\bid="([^"]+)"', body))
                self.assertTrue(body_ids)
                self.assertTrue(
                    body_ids.isdisjoint(template_ids),
                    (
                        f"{lesson_id}: body/template duplicate ids "
                        f"{sorted(body_ids & template_ids)}"
                    ),
                )

    def test_human_product_bodies_scope_standards_and_practice(
        self,
    ) -> None:
        required_markers = {
            "core-16-hci-usability-accessibility": (
                "WCAG 2.2",
                "Level AA",
                "ISO 9241-210:2019",
                "WCAG 3.0",
                "Working Draft",
                "APCA",
                "非標準",
                "keyboard",
                "200%",
                "reading order",
                "usability",
            ),
            "core-17-graphics-visual-information": (
                "OpenGL 4.6",
                "SVG 2",
                "Cleveland",
                "Munzner",
                "semantic HTML",
                "CSS",
                "roadmap",
                "quantitative chart",
                "同等のテキスト構造",
                "colorだけ",
            ),
            "core-18-product-discovery-experiments": (
                "反証可能",
                "success metric",
                "guardrail",
                "stop condition",
                "simulated",
                "always-valid",
                "p-hacking",
            ),
            "core-19-technical-communication-design-docs": (
                "one-page executive summary",
                "technical appendix",
                "alternatives",
                "risk",
                "decision",
                "ADR",
                "validation",
                "plain language",
            ),
            "core-20-ethics-privacy-societal-impact": (
                "ACM Code of Ethics",
                "NIST Privacy Framework 1.0",
                "affected people",
                "data lifecycle",
                "uneven harm",
                "mitigation",
                "residual risk",
                "privacyとsecurityは同義ではない",
            ),
        }
        for lesson_id, markers in required_markers.items():
            with self.subTest(lesson_id=lesson_id):
                body = self.body_path(lesson_id).read_text(encoding="utf-8")
                for marker in markers:
                    self.assertIn(marker, body, f"{lesson_id}: {marker}")

    def test_body_contract_rejects_heading_mutation(self) -> None:
        lesson_id = "core-01-systems-tradeoffs"
        body = self.body_path(lesson_id).read_text(encoding="utf-8")
        mutated = body.replace(
            "<h2>なぜ重要か</h2>",
            "<h2>概要</h2>",
            1,
        )

        with self.assertRaisesRegex(
            AssertionError,
            "ordered section headings",
        ):
            self.assert_body_contract(mutated, lesson_id)

    def test_body_contract_rejects_semantic_structure_mutations(self) -> None:
        lesson_id = "core-01-systems-tradeoffs"
        body = self.body_path(lesson_id).read_text(encoding="utf-8")
        worked_start = body.index('<section id="worked-example">')
        worked_end = body.index("</section>", worked_start)
        worked = body[worked_start:worked_end]
        without_marker = "".join(
            part if part.startswith("<") else re.sub(r"\d", "", part)
            for part in re.split(r"(<[^>]+>)", worked)
        )
        without_marker = re.sub(
            r"<pre><code>.*?</code></pre>",
            "<pre><code></code></pre>",
            without_marker,
            flags=re.DOTALL,
        )
        diagnosis_start = body.index("<li><strong>誤診:</strong>")
        rebuttal_start = body.index(
            "<strong>反証:</strong>",
            diagnosis_start,
        )
        without_paired_rebuttal = (
            body[:rebuttal_start]
            + "<strong>検証:</strong>"
            + body[rebuttal_start + len("<strong>反証:</strong>"):]
        )
        mutations = {
            "non-empty figure caption": body.replace(
                "判断を更新可能にする因果ループ",
                "",
                1,
            ),
            "non-empty table caption": body.replace(
                "受付方式を選ぶdecision table",
                "",
                1,
            ),
            "every table header has scope": body.replace(
                ' scope="col"',
                "",
                1,
            ),
            "misdiagnosis and rebuttal": without_paired_rebuttal,
            "numeric or executable worked example": (
                body[:worked_start]
                + without_marker
                + body[worked_end:]
            ),
        }

        for expected_message, mutated in mutations.items():
            with self.subTest(expected_message=expected_message):
                with self.assertRaisesRegex(
                    AssertionError,
                    expected_message,
                ):
                    self.assert_body_contract(mutated, lesson_id)

    def test_systems_weighted_score_is_arithmetically_correct(self) -> None:
        systems = self.body_path(
            "core-01-systems-tradeoffs"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "3×0.4 + 5×0.3 + 4×0.2 + 3×0.1 = 3.8",
            systems,
        )
        self.assertIn("同期案は3.8、キュー案は3.7", systems)
        self.assertIn("差は0.1", systems)
        self.assertNotIn("同期案は3.9", systems)
        self.assertNotIn("0.2差", systems)

    def test_algorithm_complexity_distinguishes_upper_and_tight_bounds(
        self,
    ) -> None:
        algorithms = self.body_path(
            "core-02-algorithms-measurement"
        ).read_text(encoding="utf-8")
        memory = self.body_path(
            "core-03-architecture-memory-caches"
        ).read_text(encoding="utf-8")

        self.assertIn("Big-Oは漸近上界", algorithms)
        self.assertIn("Θ(n)", algorithms)
        self.assertIn("Θ(n²)", algorithms)
        self.assertNotIn(
            "Big-Oは入力が増えたときの成長率を表す記法",
            algorithms,
        )
        self.assertNotIn("両者のBig-OはO(n)", memory)

    def test_foundation_labs_are_reproducible_from_the_lesson(self) -> None:
        systems = self.body_path(
            "core-01-systems-tradeoffs"
        ).read_text(encoding="utf-8")
        algorithms = self.body_path(
            "core-02-algorithms-measurement"
        ).read_text(encoding="utf-8")
        memory = self.body_path(
            "core-03-architecture-memory-caches"
        ).read_text(encoding="utf-8")
        concurrency = self.body_path(
            "core-04-os-processes-concurrency"
        ).read_text(encoding="utf-8")
        networks = self.body_path(
            "core-05-networks-latency-failure"
        ).read_text(encoding="utf-8")

        self.assertIn("decision-observations.csv", systems)
        self.assertIn("python3.13", systems)
        self.assertIn("repeat=7", algorithms)
        self.assertIn("json.dumps", algorithms)
        self.assertIn("全7反復値", algorithms)
        for marker in (
            "tuple(range(access_count))",
            "range(7)",
            "condition_order",
            "expected_checksums",
            "lscpu --caches",
            "sysctl",
        ):
            self.assertIn(marker, memory)
        for marker in (
            "Java 21",
            "javac RaceLab.java",
            "java RaceLab racy",
            "java RaceLab synchronized",
            "TRIALS = 200",
            "volatile int stock",
            "violations=",
            "C/C++のvolatile",
        ):
            self.assertIn(marker, concurrency)
        self.assertIn("trace-fixture.csv", networks)
        self.assertIn("curl", networks)

    def test_memory_model_diagram_is_a_machine_specific_diagnostic(
        self,
    ) -> None:
        memory = self.body_path(
            "core-03-architecture-memory-caches"
        ).read_text(encoding="utf-8")

        for marker in (
            "診断用の論理段階",
            "VIPT",
            "並行",
            "private/shared",
            "機種依存",
        ):
            self.assertIn(marker, memory)
        self.assertNotIn(
            "L1 miss時により大きい共有階層を探索する",
            memory,
        )

    def test_java_memory_model_claims_are_language_scoped(self) -> None:
        concurrency = self.body_path(
            "core-04-os-processes-concurrency"
        ).read_text(encoding="utf-8")

        self.assertIn("Java SE 21", concurrency)
        self.assertIn("happens-before", concurrency)
        self.assertIn("visibilityとordering", concurrency)
        self.assertIn("複合incrementのatomicity", concurrency)
        self.assertIn("一回の非再現", concurrency)

    def test_systems_harness_covers_every_lab_step(self) -> None:
        report = self.run_python_harness(
            "core-01-systems-tradeoffs",
            "decision_lab_v2",
        )

        self.assertEqual(
            set(report["options"]),
            {"sync", "queued", "adaptive_queue"},
        )
        self.assertEqual(report["measurement_conditions"]["sample_count"], 5)
        for option in report["options"].values():
            self.assertEqual(len(option["raw"]["response_ms"]), 5)
            self.assertIn("p95_response_ms", option["metrics"])
            self.assertIn("duplicate_rate", option["metrics"])
            self.assertIn("recovery_minutes", option["metrics"])
            self.assertIn("monthly_operations_hours", option["metrics"])
            self.assertEqual(
                set(option["scores"]),
                {
                    "latency",
                    "consistency",
                    "operations",
                    "reversibility",
                    "weighted_total",
                },
            )
            self.assertGreaterEqual(
                len(option["falsification_conditions"]),
                2,
            )
        self.assertEqual(report["decision_record"]["selected"], "sync")
        self.assertTrue(report["decision_record"]["decision_maker"])
        self.assertTrue(report["decision_record"]["review_date"])
        self.assertTrue(report["decision_record"]["unresolved_risks"])

    def test_algorithms_harness_covers_every_lab_step(self) -> None:
        report = self.run_python_harness(
            "core-02-algorithms-measurement",
            "algorithm_lab_v2",
        )

        self.assertEqual(report["seed"], 20260731)
        self.assertEqual(report["sizes"], [1000, 10000, 100000])
        self.assertEqual(
            set(report["distributions"]),
            {"unique", "duplicate_90", "front_biased"},
        )
        self.assertEqual(len(report["conditions"]), 9)
        for condition in report["conditions"]:
            self.assertEqual(condition["repeat"], 7)
            self.assertEqual(
                set(condition["samples_ns"]),
                {
                    "generation",
                    "set_build",
                    "linear_lookup",
                    "set_lookup",
                },
            )
            for samples in condition["samples_ns"].values():
                self.assertEqual(len(samples), 7)
            self.assertIn("median_ns", condition)
            self.assertIn("range_ns", condition)
            self.assertGreater(condition["query_count"], 0)
            self.assertTrue(condition["query_digest"])
            self.assertGreaterEqual(condition["crossover_queries"], 0)
            facts = condition["distribution_facts"]
            if condition["distribution"] == "unique":
                self.assertEqual(facts["unique_fraction"], 1.0)
            elif condition["distribution"] == "duplicate_90":
                self.assertEqual(facts["dominant_value_fraction"], 0.9)
            else:
                self.assertGreaterEqual(
                    facts["front_query_fraction"],
                    0.9,
                )
        self.assertTrue(report["growth_rates"])
        self.assertEqual(len(report["hypotheses"]), 2)
        self.assertTrue(report["additional_measurement"]["falsified"])

    def test_memory_harness_covers_every_lab_step(self) -> None:
        report = self.run_python_harness(
            "core-03-architecture-memory-caches",
            "memory_lab_v2",
            environment={"CURRICULUM_LAB_QUICK": "1"},
        )

        self.assertEqual(
            set(report["portable_defaults"]),
            {"l1_probe", "llc_probe", "beyond_llc_probe"},
        )
        self.assertTrue(report["topology_observation_commands"])
        self.assertTrue(report["warmup_excluded"])
        self.assertEqual(
            set(report["access_patterns"]),
            {"sequential", "stride16", "random"},
        )
        self.assertEqual(len(report["results"]), 9)
        for result in report["results"]:
            self.assertEqual(result["repeat_count"], 7)
            self.assertEqual(result["access_count"], result["size"])
            self.assertTrue(result["checksum_matches"])
            self.assertTrue(result["same_index_type"])
            self.assertEqual(len(result["samples_ns"]), 7)
        self.assertIn("cache_probe", report["additional_experiments"])
        self.assertIn("tlb_probe", report["additional_experiments"])
        self.assertTrue(report["limitations"])

    def test_concurrency_harness_is_safe_and_deterministic(self) -> None:
        body = self.body_path(
            "core-04-os-processes-concurrency"
        ).read_text(encoding="utf-8")
        safety_pattern = re.compile(
            r"<aside>.*?競合再現専用の意図的にunsafeな教材コード。"
            r"本番へ流用しない.*?</aside>\s*"
            r"<p>次を<code>RaceLab.java</code>",
            re.DOTALL,
        )

        self.assertRegex(body, safety_pattern)
        self.assertIn("CyclicBarrier", body)
        self.assertIn("join(TIMEOUT_MILLIS)", body)
        self.assertIn("isAlive()", body)
        self.assertIn("System.nanoTime()", body)
        self.assertIn("expected=%d final=%d min=%d violations=%d", body)
        self.assertIn("minimumStock", body)
        self.assertIn("elapsedNsSamples", body)
        self.assertIn("elapsed_ns_median", body)
        self.assertIn("process-message", body)
        self.assertIn("ProcessBuilder", body)
        self.assertIn("destroyForcibly()", body)
        self.assertIn("dedupe_prevented", body)
        self.assertIn("failure_radius", body)
        self.assertIn(
            "A:read(1000),B:read(1000),A:write(500),B:write(500)",
            body,
        )
        self.assertIn("java RaceLab serial", body)
        self.assertIn("java RaceLab process-message", body)
        self.assertNotIn("Thread.yield()", body)

        mutated = safety_pattern.sub(
            '<p>次を<code>RaceLab.java</code>',
            body,
            count=1,
        )
        with self.assertRaisesRegex(
            AssertionError,
            "Regex didn't match",
        ):
            self.assertRegex(mutated, safety_pattern)

    def test_concurrency_java21_harness_executes_when_configured(self) -> None:
        java_home_text = os.environ.get("CURRICULUM_JAVA21_HOME")
        if java_home_text is None:
            # Static contracts above remain mandatory on machines without a
            # JDK; CI or a local evidence run can opt into execution.
            return

        java_home = Path(java_home_text)
        javac = java_home / "bin" / "javac"
        java = java_home / "bin" / "java"
        self.assertTrue(javac.is_file(), javac)
        self.assertTrue(java.is_file(), java)
        version = subprocess.run(
            [java, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertRegex(version.stdout, r"(?m)^openjdk 21(?:\.|\s)")

        blocks = self.pre_code_blocks(
            "core-04-os-processes-concurrency"
        )
        matching = [
            block
            for block in blocks
            if "public final class RaceLab" in block
        ]
        self.assertEqual(len(matching), 1)
        with TemporaryDirectory() as directory:
            source = Path(directory) / "RaceLab.java"
            source.write_text(matching[0], encoding="utf-8")
            compiled = subprocess.run(
                [javac, "--release", "21", source.name],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)

            reports: dict[str, dict[str, object]] = {}
            for mode in (
                "racy",
                "synchronized",
                "serial",
                "process-message",
            ):
                executed = subprocess.run(
                    [java, "RaceLab", mode],
                    cwd=directory,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(
                    executed.returncode,
                    0,
                    f"{mode}: {executed.stderr}\n{executed.stdout}",
                )
                try:
                    report = json.loads(executed.stdout.splitlines()[-1])
                except (IndexError, json.JSONDecodeError) as error:
                    self.fail(f"{mode}: invalid final JSON line: {error}")
                self.assertEqual(report["mode"], mode)
                reports[mode] = report

        for mode in ("racy", "synchronized", "serial"):
            report = reports[mode]
            self.assertEqual(report["trials"], 200)
            self.assertGreaterEqual(report["minimum_stock"], 0)
            elapsed = report["elapsed_ns"]
            self.assertEqual(len(elapsed["samples"]), 200)
            self.assertLessEqual(elapsed["min"], elapsed["median"])
            self.assertLessEqual(elapsed["median"], elapsed["max"])
        self.assertEqual(reports["racy"]["violations"], 200)
        self.assertEqual(reports["synchronized"]["violations"], 0)
        self.assertEqual(reports["serial"]["violations"], 0)

        process_report = reports["process-message"]
        self.assertEqual(
            process_report["trial_scope"],
            "single-owner-session-not-200-thread-trials",
        )
        self.assertEqual(process_report["final_stock"], 0)
        self.assertEqual(process_report["minimum_stock"], 0)
        self.assertEqual(process_report["dedupe_prevented"], 1)
        self.assertEqual(process_report["child_exit"], 0)
        self.assertTrue(process_report["forced_cleanup"])
        self.assertTrue(process_report["parent_continued"])
        self.assertEqual(
            process_report["failure_radius"],
            "owner-child-process",
        )

    def test_network_harness_covers_every_lab_step_without_network(
        self,
    ) -> None:
        body = self.body_path(
            "core-05-networks-latency-failure"
        ).read_text(encoding="utf-8")
        self.assertIn("def main():", body)
        self.assertIn('if __name__ == "__main__":', body)
        report = self.run_python_harness(
            "core-05-networks-latency-failure",
            "network_lab_v2",
        )

        self.assertEqual(report["bind_address"], "127.0.0.1")
        self.assertFalse(report["external_network_used"])
        self.assertTrue(report["tls_simulated"])
        self.assertTrue(report["dns_cache_simulated"])
        self.assertEqual(len(report["baseline"]["cold"]), 7)
        self.assertEqual(len(report["baseline"]["warm"]), 7)
        for sample in report["baseline"]["cold"] + report["baseline"]["warm"]:
            self.assertEqual(
                set(sample["monotonic_ns"]),
                {
                    "dns_start",
                    "dns_end",
                    "connect_start",
                    "connect_end",
                    "tls_start",
                    "tls_end",
                    "first_byte",
                    "body_finish",
                },
            )
        self.assertLessEqual(report["budget"]["worst_case_ms"], 2000)
        self.assertGreater(
            report["faults"]["dependency_delay_ms"],
            report["baseline_median_ms"],
        )
        self.assertEqual(report["non_idempotent"]["automatic_retry"], "stopped")
        self.assertEqual(report["non_idempotent"]["lookup_result"], "applied")

        security = report["protocol_security"]
        self.assertEqual(security["max_line_bytes"], 256)
        self.assertLessEqual(security["socket_deadline_ms"], 1000)
        self.assertEqual(
            security["rejections"],
            {
                "unterminated": "newline_required",
                "oversized": "line_too_long",
                "timeout": "receive_timeout",
                "invalid_id": "invalid_request_id",
                "excessive_delay": "invalid_delay_ms",
                "invalid_arity": "invalid_arity",
                "invalid_mode": "invalid_mode",
            },
        )
        self.assertEqual(
            report["faults"]["connection_failure"],
            "injected_before_socket_creation",
        )
        self.assertEqual(report["faults"]["real_connector_calls"], 0)
        self.assertEqual(
            report["cleanup"]["injected_exception"],
            "observed",
        )
        self.assertTrue(report["cleanup"]["server_stopped"])
        self.assertFalse(report["cleanup"]["thread_alive"])
        self.assertTrue(report["cleanup"]["listener_closed"])

    def test_domain_model_harness_traces_rules_and_exceptions(self) -> None:
        report = self.run_python_harness(
            "core-06-requirements-domain-modeling",
            "domain_model_lab_v1",
        )

        self.assertEqual(report["fixture"], "equipment-rental-v1")
        self.assertEqual(
            {entry["term"] for entry in report["glossary"]},
            {"Asset", "Reservation", "Hold", "Checkout", "Return"},
        )
        self.assertEqual(
            {context["name"] for context in report["bounded_contexts"]},
            {"Catalog", "Rental Operations", "Billing"},
        )
        scenarios = {
            scenario["id"]: scenario
            for scenario in report["example_scenarios"]
        }
        self.assertGreaterEqual(len(scenarios), 5)
        state_machine = report["asset_state_machine"]
        self.assertEqual(state_machine["asset_id"], "camera-17")
        state_trace = state_machine["state_trace"]
        self.assertEqual(
            [step["id"] for step in state_trace],
            [
                "normal-checkout",
                "competing-reservation",
                "normal-return",
                "expired-hold",
                "overdue-checkout",
                "overdue-return",
            ],
        )
        self.assertTrue(
            all(
                step["asset_id"] == state_machine["asset_id"]
                for step in state_trace
            )
        )
        self.assertEqual(
            [step["active_loan_count"] for step in state_trace],
            [1, 1, 0, 0, 1, 0],
        )
        self.assertEqual(state_machine["max_active_loan_count"], 1)
        self.assertEqual(state_machine["final_state"], "available")
        competing = scenarios["competing-reservation"]
        self.assertEqual(competing["state_before"], "checked-out")
        self.assertEqual(competing["state_after"], "checked-out")
        self.assertEqual(competing["observed"], "rejected-unavailable")
        normal_return = scenarios["normal-return"]
        self.assertEqual(normal_return["state_before"], "checked-out")
        self.assertEqual(normal_return["state_after"], "available")
        overdue = scenarios["overdue-return"]
        self.assertEqual(overdue["command"], "ReturnAsset")
        self.assertEqual(overdue["event"], "LoanReturned")
        self.assertEqual(overdue["observed"], "accepted-overdue")
        self.assertEqual(overdue["state_before"], "checked-out")
        self.assertEqual(overdue["state_after"], "available")
        self.assertGreater(overdue["returned_at"], overdue["due_at"])
        self.assertEqual(
            overdue["policy_event"],
            "OverdueChargeAssessmentRequested",
        )
        exceptions = {
            exception["code"]: exception
            for exception in report["exceptions"]
        }
        self.assertGreaterEqual(len(exceptions), 3)
        self.assertEqual(
            exceptions["overdue-return"]["event"],
            "LoanReturned",
        )
        self.assertTrue(exceptions["overdue-return"]["policy_event"])
        self.assertTrue(all(item["passed"] for item in report["invariants"]))
        invariant_names = {
            item["name"] for item in report["invariants"]
        }
        self.assertIn("return-restores-availability", invariant_names)
        one_active = next(
            item
            for item in report["invariants"]
            if item["name"] == "one-active-checkout-per-asset"
        )
        self.assertEqual(
            one_active["evidence"]["max_active_loan_count"],
            state_machine["max_active_loan_count"],
        )
        self.assertIn(
            "overdue-return-emits-policy-event",
            invariant_names,
        )
        self.assertTrue(
            all(
                item["commands"]
                and item["events"]
                and item["invariants"]
                for item in report["traceability"]
            )
        )
        return_trace = [
            item
            for item in report["traceability"]
            if "ReturnAsset" in item["commands"]
        ]
        self.assertEqual(len(return_trace), 1)
        self.assertIn("LoanReturned", return_trace[0]["events"])
        self.assertIn(
            "overdue-return-emits-policy-event",
            return_trace[0]["invariants"],
        )
        self.assertEqual(
            {item["status"] for item in report["ambiguities"]},
            {"detected", "resolved"},
        )
        self.assertFalse(report["external_network_used"])

    def test_domain_model_rejects_overdue_return_trace_mutation(
        self,
    ) -> None:
        source = self.python_harness_source(
            "core-06-requirements-domain-modeling",
            "domain_model_lab_v1",
        )
        marker = '"id": "overdue-return",'
        self.assertIn(marker, source)
        mutated = source.replace(
            marker,
            '"id": "overdue-return-removed",',
            1,
        )

        result = self.execute_python_harness_source(mutated)

        self.assertNotEqual(result.returncode, 0)

        active_state_marker = 'if asset["active_loan"] is not None:'
        self.assertIn(active_state_marker, source)
        active_state_mutation = source.replace(
            active_state_marker,
            "if False:",
            1,
        )

        active_state_result = self.execute_python_harness_source(
            active_state_mutation
        )

        self.assertNotEqual(active_state_result.returncode, 0)

    def test_api_contract_harness_models_replay_and_evolution(self) -> None:
        report = self.run_python_harness(
            "core-07-api-contract-design",
            "api_contract_lab_v1",
        )

        self.assertEqual(report["fixture"], "offline-field-client-v1")
        self.assertEqual(report["supported_versions"], ["v1", "v2"])
        evidence = report["idempotency_evidence"]
        self.assertEqual(evidence["initial"]["effect_count"], 1)
        self.assertEqual(evidence["replay"]["effect_count"], 1)
        self.assertEqual(
            evidence["initial"]["scope"],
            {
                "tenant": "tenant-a",
                "principal": "field-7",
                "route": "POST /work-items/{id}:complete",
                "idempotency_key": "key-42",
            },
        )
        self.assertEqual(
            evidence["initial"]["scope"],
            evidence["replay"]["scope"],
        )
        self.assertEqual(
            evidence["initial"]["request_fingerprint"],
            evidence["replay"]["request_fingerprint"],
        )
        self.assertRegex(
            evidence["initial"]["request_fingerprint"],
            r"\A[0-9a-f]{64}\Z",
        )
        self.assertRegex(
            evidence["initial"]["response_generated_at"],
            r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z",
        )
        self.assertNotEqual(
            evidence["initial"]["response_generated_at"],
            evidence["replay"]["response_generated_at"],
        )
        self.assertTrue(evidence["same_effect"])
        self.assertFalse(evidence["same_response"])
        self.assertFalse(evidence["exactly_once_claimed"])
        conflict = evidence["payload_conflict"]
        self.assertEqual(conflict["status"], 409)
        self.assertFalse(conflict["effect_applied"])
        self.assertEqual(conflict["effect_count"], 1)
        self.assertNotEqual(
            conflict["request_fingerprint"],
            evidence["initial"]["request_fingerprint"],
        )
        other_tenant = evidence["other_tenant"]
        self.assertEqual(other_tenant["scope"]["tenant"], "tenant-b")
        self.assertEqual(
            other_tenant["scope"]["idempotency_key"],
            "key-42",
        )
        self.assertNotEqual(
            other_tenant["effect"]["operation_id"],
            evidence["initial"]["effect"]["operation_id"],
        )
        self.assertEqual(other_tenant["effect_count"], 2)
        compatibility = report["compatibility_cases"]
        self.assertEqual(
            set(compatibility),
            {
                "add_optional_field",
                "remove_required_field",
                "expand_enum",
            },
        )
        trace_ids = {
            trace["id"] for trace in report["offline_client_trace"]
        }
        for change in compatibility.values():
            self.assertEqual(
                set(change),
                {"source", "wire", "semantic", "trace_id"},
            )
            self.assertIn(change["trace_id"], trace_ids)
            for axis in ("source", "wire", "semantic"):
                self.assertIs(type(change[axis]["compatible"]), bool)
                self.assertTrue(change[axis]["evidence"])
        self.assertEqual(
            set(report["problem_contract"]["rfc_standard_members"]),
            {"type", "title", "status", "detail", "instance"},
        )
        self.assertEqual(
            set(report["problem_contract"]["required_by_this_api"]),
            {"type", "title", "status"},
        )
        self.assertEqual(
            set(report["problem_contract"]["optional_by_this_api"]),
            {"detail", "instance"},
        )
        self.assertEqual(
            set(conflict["problem_details"]),
            {"type", "title", "status"},
        )
        self.assertTrue(report["authorization_boundary"]["schema_valid"])
        self.assertFalse(report["authorization_boundary"]["authorized"])
        self.assertGreaterEqual(len(report["state_transitions"]), 3)
        self.assertFalse(report["external_network_used"])

    def test_api_contract_rejects_fingerprint_check_mutation(
        self,
    ) -> None:
        source = self.python_harness_source(
            "core-07-api-contract-design",
            "api_contract_lab_v1",
        )
        marker = 'if stored["request_fingerprint"] != fingerprint:'
        self.assertIn(marker, source)
        mutated = source.replace(marker, "if False:", 1)

        result = self.execute_python_harness_source(mutated)

        self.assertNotEqual(result.returncode, 0)

    def test_api_contract_rejects_tenant_scope_mutation(self) -> None:
        source = self.python_harness_source(
            "core-07-api-contract-design",
            "api_contract_lab_v1",
        )
        marker = 'principal["tenant"],'
        self.assertIn(marker, source)
        mutated = source.replace(marker, '"shared-tenant",', 1)

        result = self.execute_python_harness_source(mutated)

        self.assertNotEqual(result.returncode, 0)

    def test_architecture_harness_exposes_dependencies_and_decision(
        self,
    ) -> None:
        report = self.run_python_harness(
            "core-08-modularity-evolutionary-architecture",
            "architecture_lab_v1",
        )

        self.assertEqual(report["fixture"], "pricing-change-hotspot-v1")
        self.assertTrue(report["before"]["cycles"])
        self.assertTrue(report["before"]["direction_violations"])
        self.assertEqual(report["after"]["cycles"], [])
        self.assertEqual(report["after"]["direction_violations"], [])
        self.assertEqual(
            report["fixture_metadata"]["kind"],
            "synthetic",
        )
        self.assertTrue(report["fixture_metadata"]["purpose"])
        self.assertEqual(
            report["fixture_metadata"]["provenance"],
            "lesson-defined synthetic scenario",
        )
        self.assertTrue(report["fixture_metadata"]["limitations"])
        architecture_body = self.body_path(
            "core-08-modularity-evolutionary-architecture"
        ).read_text(encoding="utf-8")
        self.assertIn("lesson-defined synthetic scenario", architecture_body)
        architecture_metadata = json.loads(
            self.body_path(
                "core-08-modularity-evolutionary-architecture"
            ).with_name("lesson.json").read_text(encoding="utf-8")
        )
        metadata_text = json.dumps(
            architecture_metadata,
            ensure_ascii=False,
        )
        self.assertNotIn("1・3・5", metadata_text)
        self.assertIn(
            "1〜5の全anchor",
            next(
                objective["statement"]
                for objective in architecture_metadata["objectives"]
                if objective["id"] == "obj-decision"
            ),
        )
        self.assertTrue(
            any(
                "1〜5の全anchor" in step
                for step in architecture_metadata["lab"]["steps"]
            )
        )
        self.assertEqual(
            set(report["after"]["modules"]),
            {
                "pricing-domain",
                "pricing-application",
                "pricing-adapters",
                "reporting",
            },
        )
        criteria = report["criteria"]
        self.assertEqual(
            set(criteria),
            {
                "change_locality",
                "migration_cost",
                "operability",
                "reversibility",
            },
        )
        self.assertAlmostEqual(
            sum(criterion["weight"] for criterion in criteria.values()),
            1.0,
        )
        for criterion in criteria.values():
            self.assertEqual(
                set(criterion["scale"]),
                {"1", "2", "3", "4", "5"},
            )
            self.assertTrue(all(criterion["scale"].values()))
        self.assertEqual(len(report["options"]), 3)
        for option in report["options"]:
            self.assertEqual(set(option["ratings"]), set(criteria))
            numerator = 0.0
            denominator = 0.0
            for criterion_id, rating in option["ratings"].items():
                self.assertIn(rating["rating"], range(1, 6))
                self.assertIn(
                    str(rating["rating"]),
                    criteria[criterion_id]["scale"],
                )
                self.assertEqual(
                    rating["evidence_kind"],
                    "synthetic-fixture-observation",
                )
                self.assertTrue(rating["evidence"])
                weight = criteria[criterion_id]["weight"]
                numerator += rating["rating"] * weight
                denominator += weight
            self.assertAlmostEqual(
                option["score"],
                numerator / denominator,
            )
            self.assertTrue(option["risks"])
        winner = max(report["options"], key=lambda item: item["score"])
        self.assertEqual(report["selected_option"], winner["id"])
        adr = report["adr"]
        self.assertEqual(adr["status"], "accepted")
        for field in (
            "context",
            "decision",
            "alternatives",
            "positive_consequences",
            "negative_consequences",
            "confirmation",
        ):
            self.assertTrue(adr[field])
        impact = report["change_impact"]
        self.assertEqual(impact["target"], "pricing-domain")
        self.assertEqual(
            set(impact["actual_impacted_modules"]),
            {
                "pricing-domain",
                "pricing-application",
                "pricing-adapters",
            },
        )
        self.assertEqual(
            impact["expected_impacted_modules"],
            impact["actual_impacted_modules"],
        )
        self.assertEqual(impact["unexpected_impacted_modules"], [])
        self.assertEqual(impact["missing_expected_modules"], [])
        self.assertEqual(impact["unexpected_count"], 0)
        self.assertEqual(impact["missing_count"], 0)
        self.assertNotIn("unrelated_modules_changed", impact)
        mutations = report["impact_mutations"]
        self.assertEqual(
            set(mutations),
            {"edge_removed", "target_changed"},
        )
        expected = set(impact["expected_impacted_modules"])
        for mutation in mutations.values():
            actual = set(mutation["actual_impacted_modules"])
            unexpected = actual - expected
            missing = expected - actual
            self.assertEqual(
                set(mutation["unexpected_impacted_modules"]),
                unexpected,
            )
            self.assertEqual(
                set(mutation["missing_expected_modules"]),
                missing,
            )
            self.assertEqual(mutation["unexpected_count"], len(unexpected))
            self.assertEqual(mutation["missing_count"], len(missing))
        self.assertEqual(
            mutations["edge_removed"]["unexpected_impacted_modules"],
            [],
        )
        self.assertEqual(
            set(mutations["edge_removed"]["missing_expected_modules"]),
            {"pricing-application", "pricing-adapters"},
        )
        self.assertEqual(
            set(mutations["target_changed"]["unexpected_impacted_modules"]),
            {"reporting"},
        )
        self.assertEqual(
            set(mutations["target_changed"]["missing_expected_modules"]),
            expected,
        )
        self.assertEqual(
            adr["decision"],
            report["selected_option"],
        )
        self.assertFalse(report["external_network_used"])

    def test_testing_harness_executes_red_green_refactor_and_mutation(
        self,
    ) -> None:
        body = self.body_path(
            "core-09-test-strategy-tdd"
        ).read_text(encoding="utf-8")
        self.assertIn("subprocess.run", body)
        report = self.run_python_harness(
            "core-09-test-strategy-tdd",
            "test_strategy_lab_v1",
        )

        self.assertEqual(report["fixture"], "order-discount-v1")
        phases = report["phases"]
        self.assertEqual(
            [phase["name"] for phase in phases],
            ["RED", "GREEN", "REFACTOR"],
        )
        self.assertNotEqual(phases[0]["returncode"], 0)
        self.assertEqual(
            phases[0]["test_id"],
            "test_strategy_fixture.PureUnitTests.test_discount",
        )
        self.assertIn(
            "NotImplementedError: total is not implemented",
            phases[0]["failure_reason"],
        )
        self.assertEqual(phases[1]["returncode"], 0)
        self.assertEqual(phases[2]["returncode"], 0)
        self.assertNotEqual(
            phases[0]["source_sha256"],
            phases[1]["source_sha256"],
        )
        self.assertNotEqual(
            phases[1]["source_sha256"],
            phases[2]["source_sha256"],
        )
        self.assertEqual(
            phases[1]["behavior_sha256"],
            phases[2]["behavior_sha256"],
        )
        self.assertTrue(
            all(
                phase["command"][-4:-1]
                == ["-m", "unittest", "-q"]
                and phase["command"][-1] == phase["test_id"]
                for phase in phases
            )
        )
        strategy = {
            item["kind"]: item
            for item in report["strategy_evidence"]
        }
        self.assertEqual(
            set(strategy),
            {"unit", "integration", "contract", "property", "metamorphic"},
        )
        self.assertEqual(
            len({item["test_id"] for item in strategy.values()}),
            5,
        )
        for item in strategy.values():
            self.assertTrue(item["passed"])
            self.assertEqual(item["returncode"], 0)
            self.assertEqual(item["command"][-1], item["test_id"])
            self.assertTrue(item["boundary"])
            self.assertTrue(item["evidence"])
        self.assertEqual(strategy["unit"]["boundary"], "pure-function")
        self.assertEqual(
            strategy["integration"]["boundary"],
            "stdlib-sqlite-repository-adapter",
        )
        self.assertEqual(
            strategy["contract"]["boundary"],
            "consumer-provider-schema-and-semantics",
        )
        self.assertEqual(
            strategy["property"]["generation"],
            "bounded-exhaustive",
        )
        self.assertGreaterEqual(strategy["property"]["case_count"], 100)
        self.assertEqual(
            strategy["metamorphic"]["relation"],
            "permutation-and-zero-item-preserve-total",
        )
        defect = report["nondeterministic_defect"]
        self.assertEqual(defect["seed_sequence"], [11, 12, 13, 14])
        self.assertEqual(set(defect["outcomes"]), {"pass", "fail"})
        self.assertEqual(defect["root_cause"], "order-and-clock-coupling")
        self.assertEqual(len(defect["schedules"]), 4)
        self.assertEqual(
            set(defect["isolation"]["fixed_order_variable_clock"]),
            {"pass", "fail"},
        )
        self.assertEqual(
            set(defect["isolation"]["fixed_clock_variable_order"]),
            {"pass", "fail"},
        )
        self.assertTrue(report["mutation"]["killed"])
        self.assertNotEqual(report["mutation"]["returncode"], 0)
        self.assertEqual(
            report["mutation"]["test_id"],
            strategy["integration"]["test_id"],
        )
        self.assertIn(
            "AssertionError",
            report["mutation"]["failure_reason"],
        )
        workspace = report["workspace"]
        self.assertTrue(workspace["temporary_directory_used"])
        self.assertTrue(workspace["all_subprocesses_used_workspace_cwd"])
        self.assertEqual(
            set(workspace["explicit_test_ids"]),
            {item["test_id"] for item in strategy.values()},
        )
        self.assertFalse(report["external_network_used"])

    def test_testing_harness_isolates_symlinks_and_ambient_tests(
        self,
    ) -> None:
        source = self.python_harness_source(
            "core-09-test-strategy-tdd",
            "test_strategy_lab_v1",
        )
        with TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            victim = directory / "victim.txt"
            victim.write_text("do-not-overwrite", encoding="utf-8")
            os.symlink(victim, directory / "order_discount.py")
            ambient_marker = directory / "ambient-ran.txt"
            ambient_test = directory / "test_ambient.py"
            ambient_test.write_text(
                "from pathlib import Path\n"
                f"Path({str(ambient_marker)!r}).write_text("
                "'ran', encoding='utf-8')\n"
                "raise RuntimeError('ambient test must not run')\n",
                encoding="utf-8",
            )
            script = directory / "harness.py"
            script.write_text(source, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, script],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(
                [phase["returncode"] for phase in report["phases"]],
                [1, 0, 0],
            )
            self.assertEqual(
                victim.read_text(encoding="utf-8"),
                "do-not-overwrite",
            )
            self.assertFalse(ambient_marker.exists())

    def test_threat_model_harness_links_assets_controls_and_verification(
        self,
    ) -> None:
        report = self.run_python_harness(
            "core-10-threat-modeling-secure-design",
            "threat_model_lab_v1",
        )

        self.assertEqual(report["fixture"], "operations-portal-v1")
        self.assertEqual(
            {asset["id"] for asset in report["assets"]},
            {"customer-data", "deployment-credential", "audit-log"},
        )
        actors = {
            actor["id"]: actor
            for actor in report["actors"]
        }
        self.assertIn("operations-contractor", actors)
        self.assertTrue(
            all(
                actor["id"]
                and actor["type"] in {"external", "insider"}
                and actor["scope"]
                for actor in actors.values()
            )
        )
        self.assertGreaterEqual(len(report["trust_boundaries"]), 2)
        boundary_ids = {
            boundary["id"]
            for boundary in report["trust_boundaries"]
        }
        known_zones = {
            zone
            for boundary in report["trust_boundaries"]
            for zone in (boundary["from"], boundary["to"])
        }
        self.assertTrue(
            all(
                flow["from"] in actors
                and flow["to"] in known_zones
                and set(flow["crosses"]) <= boundary_ids
                and flow["crosses"]
                for flow in report["cross_boundary_flows"]
            )
        )
        flows = {
            flow["id"]: flow
            for flow in report["cross_boundary_flows"]
        }
        self.assertEqual(
            {threat["actor_type"] for threat in report["threats"]},
            {"external", "insider"},
        )
        threat_ids = {threat["id"] for threat in report["threats"]}
        for threat in report["threats"]:
            actor_id = threat["actor_id"]
            self.assertIn(actor_id, actors)
            self.assertEqual(actors[actor_id]["type"], threat["actor_type"])
            self.assertEqual(flows[threat["flow_id"]]["from"], actor_id)
        credential_threat = next(
            threat
            for threat in report["threats"]
            if threat["id"] == "T-IN-CREDENTIAL"
        )
        self.assertEqual(
            credential_threat["actor_id"],
            "operations-contractor",
        )
        self.assertEqual(
            flows[credential_threat["flow_id"]]["from"],
            "operations-contractor",
        )
        controls = {
            control["id"]: control
            for control in report["controls"]
        }
        self.assertEqual(
            {control["type"] for control in controls.values()},
            {"prevent", "detect", "recover"},
        )
        self.assertEqual(
            {link["threat_id"] for link in report["control_links"]},
            threat_ids,
        )
        for link in report["control_links"]:
            linked_types = {
                controls[control_id]["type"]
                for control_id in link["control_ids"]
            }
            self.assertEqual(
                linked_types,
                {"prevent", "detect", "recover"},
            )
        self.assertEqual(
            {link["threat_id"] for link in report["verification_links"]},
            threat_ids,
        )
        self.assertTrue(
            all(
                link["result"] == "passed"
                and link["control_id"] in controls
                for link in report["verification_links"]
            )
        )
        verification_ids = [
            link["verification_id"]
            for link in report["verification_links"]
        ]
        self.assertTrue(all(verification_ids))
        self.assertEqual(
            len(verification_ids),
            len(set(verification_ids)),
        )
        residual_risk_ids = [
            risk["id"]
            for risk in report["residual_risks"]
        ]
        self.assertTrue(all(residual_risk_ids))
        self.assertEqual(
            len(residual_risk_ids),
            len(set(residual_risk_ids)),
        )
        self.assertTrue(
            all(
                risk["threat_id"] in threat_ids
                and risk["owner"]
                and risk["review_date"]
                and risk["decision"]
                and risk["uncertainty"]
                for risk in report["residual_risks"]
            )
        )
        for risk in report["residual_risks"]:
            parsed_review_date = date.fromisoformat(risk["review_date"])
            self.assertEqual(
                parsed_review_date.isoformat(),
                risk["review_date"],
            )
        self.assertEqual(
            report["model_validation"],
            {
                "valid": True,
                "errors": [],
                "actor_count": len(report["actors"]),
                "threat_count": len(report["threats"]),
                "control_count": len(report["controls"]),
                "verification_count": len(report["verification_links"]),
                "residual_risk_count": len(report["residual_risks"]),
            },
        )
        negative_mutations = report["negative_mutations"]
        self.assertEqual(
            set(negative_mutations),
            {
                "empty_controls",
                "unknown_reference",
                "failed_verification",
                "blank_owner",
                "missing_control_type",
                "empty_actors",
                "unknown_actor",
                "actor_flow_mismatch",
                "blank_verification_id",
                "duplicate_verification_id",
                "blank_risk_id",
                "duplicate_risk_id",
                "invalid_review_date",
            },
        )
        for mutation in negative_mutations.values():
            self.assertTrue(mutation["rejected"])
            self.assertTrue(mutation["errors"])
        self.assertFalse(report["attack_code_executed"])
        self.assertFalse(report["external_network_used"])

    def test_threat_model_rejects_disabled_validation_mutation(
        self,
    ) -> None:
        source = self.python_harness_source(
            "core-10-threat-modeling-secure-design",
            "threat_model_lab_v1",
        )
        marker = "return sorted(errors)"
        self.assertIn(marker, source)
        mutated = source.replace(marker, "return []", 1)

        result = self.execute_python_harness_source(mutated)

        self.assertNotEqual(result.returncode, 0)

    def test_storage_harness_compares_models_and_recomputes_adr(
        self,
    ) -> None:
        lesson_id = "core-11-data-modeling-storage"
        report = self.run_python_harness(
            lesson_id,
            "storage_decision_lab_v1",
        )

        self.assertEqual(report["fixture"], "order-history-workload-v1")
        self.assertEqual(
            report["fixture_metadata"]["kind"],
            "synthetic",
        )
        self.assertTrue(report["fixture_metadata"]["limitations"])
        query_shapes = report["workload"]["query_shapes"]
        self.assertGreaterEqual(len(query_shapes), 4)
        self.assertEqual(
            len({query["id"] for query in query_shapes}),
            len(query_shapes),
        )
        self.assertTrue(
            all(
                query["frequency_per_hour"] > 0
                and query["accessed_together"]
                for query in query_shapes
            )
        )
        self.assertTrue(report["workload"]["invariants"])
        self.assertTrue(report["workload"]["update_conflicts"])
        forecast = report["growth_forecast"]
        self.assertEqual(
            forecast["projected_records"],
            forecast["current_records"]
            + forecast["monthly_growth"] * forecast["months"],
        )
        self.assertEqual(forecast["evidence_kind"], "synthetic-projection")

        criteria = report["criteria"]
        self.assertEqual(
            set(criteria),
            {
                "access_fit",
                "constraint_coverage",
                "capacity",
                "operations",
                "recovery",
            },
        )
        self.assertAlmostEqual(
            sum(criterion["weight"] for criterion in criteria.values()),
            1.0,
        )
        options = {
            option["id"]: option
            for option in report["baseline"]["options"]
        }
        baseline_frequencies = {
            query["id"]: query["frequency_per_hour"]
            for query in report["workload"]["query_shapes"]
        }
        self.assertEqual(
            report["baseline"]["rating_inputs"],
            baseline_frequencies,
        )
        baseline_dominant = max(
            baseline_frequencies,
            key=baseline_frequencies.__getitem__,
        )
        self.assertEqual(
            report["baseline"]["dominant_query_id"],
            baseline_dominant,
        )
        self.assertEqual(
            report["baseline"]["workload_profile"],
            f"{baseline_dominant}-dominant",
        )
        self.assertEqual(set(options), {"relational", "document", "key-value"})
        self.assertEqual(
            report["baseline"]["derived_access_fit_ratings"],
            {
                option_id: option["ratings"]["access_fit"]
                for option_id, option in options.items()
            },
        )
        total_frequency = sum(baseline_frequencies.values())
        for option in options.values():
            self.assertEqual(set(option["ratings"]), set(criteria))
            self.assertEqual(
                set(option["query_fit_ratings"]),
                set(baseline_frequencies),
            )
            self.assertEqual(
                option["query_contributions"],
                {
                    query_id: (
                        frequency
                        * option["query_fit_ratings"][query_id]
                    )
                    for query_id, frequency in baseline_frequencies.items()
                },
            )
            self.assertAlmostEqual(
                option["ratings"]["access_fit"],
                sum(option["query_contributions"].values())
                / total_frequency,
            )
            expected_score = sum(
                rating * criteria[criterion_id]["weight"]
                for criterion_id, rating in option["ratings"].items()
            )
            self.assertAlmostEqual(option["score"], expected_score)
            self.assertTrue(option["constraint_evidence"])
            self.assertTrue(option["operations_evidence"])
            self.assertTrue(option["recovery_evidence"])
        baseline_winner = max(
            options.values(),
            key=lambda option: option["score"],
        )
        self.assertEqual(
            report["baseline"]["selected_option"],
            baseline_winner["id"],
        )
        self.assertEqual(
            report["adr"]["decision"],
            report["baseline"]["selected_option"],
        )
        self.assertTrue(report["adr"]["negative_consequences"])
        self.assertTrue(report["adr"]["confirmation"])

        mutation = report["access_pattern_mutation"]
        mutated_options = {
            option["id"]: option
            for option in mutation["options"]
        }
        mutated_frequencies = {
            query["id"]: query["frequency_per_hour"]
            for query in mutation["workload"]["query_shapes"]
        }
        self.assertEqual(
            mutation["rating_inputs"],
            mutated_frequencies,
        )
        self.assertEqual(
            mutation["dominant_query_id"],
            max(mutated_frequencies, key=mutated_frequencies.__getitem__),
        )
        self.assertEqual(
            mutation["derived_access_fit_ratings"],
            {
                option_id: option["ratings"]["access_fit"]
                for option_id, option in mutated_options.items()
            },
        )
        mutated_winner = max(
            mutated_options.values(),
            key=lambda option: option["score"],
        )
        self.assertEqual(mutation["selected_option"], mutated_winner["id"])
        self.assertNotEqual(
            mutation["selected_option"],
            report["baseline"]["selected_option"],
        )
        self.assertTrue(mutation["decision_recomputed"])
        order_detail_mutation = report["order_detail_mutation"]
        order_detail_frequencies = order_detail_mutation["rating_inputs"]
        self.assertEqual(
            set(order_detail_frequencies),
            set(baseline_frequencies),
        )
        self.assertEqual(
            order_detail_mutation["dominant_query_id"],
            "get_order_detail",
        )
        self.assertEqual(
            order_detail_frequencies["get_order_detail"],
            max(order_detail_frequencies.values()),
        )
        self.assertEqual(
            order_detail_mutation["selected_option"],
            "document",
        )
        self.assertNotEqual(
            order_detail_mutation["selected_option"],
            report["baseline"]["selected_option"],
        )
        self.assertTrue(order_detail_mutation["decision_recomputed"])
        self.assertEqual(
            report["vendor_scope"],
            {
                "PostgreSQL": "18",
                "MongoDB": "8.0",
                "Dynamo": "2007-paper-model",
            },
        )
        self.assert_data_scale_mastery_evidence(report, lesson_id)
        self.assertFalse(report["external_network_used"])

    def test_storage_harness_rejects_access_pattern_mutation(
        self,
    ) -> None:
        self.assert_harness_source_mutation_fails(
            "core-11-data-modeling-storage",
            "storage_decision_lab_v1",
            '"get_order_detail": 5,',
            '"get_order_detail": 1,',
        )

    def test_transaction_harness_reproduces_anomalies_and_retry(
        self,
    ) -> None:
        lesson_id = "core-12-transactions-isolation-consistency"
        report = self.run_python_harness(
            lesson_id,
            "transaction_scheduler_lab_v1",
        )

        self.assertEqual(
            report["simulator"],
            "pedagogical-deterministic-scheduler",
        )
        self.assertEqual(
            report["fixture_metadata"]["kind"],
            "simulated",
        )
        self.assertFalse(report["fixture_metadata"]["real_database"])
        scope = report["isolation_scope"]
        self.assertEqual(scope["vendor"], "PostgreSQL")
        self.assertEqual(scope["version"], "18")
        self.assertTrue(scope["vendor_differences"])
        scenarios = {
            scenario["id"]: scenario
            for scenario in report["scenarios"]
        }
        self.assertEqual(
            set(scenarios),
            {
                "read-committed-non-repeatable-read",
                "snapshot-write-skew",
                "serializable-retry",
            },
        )
        read_committed = scenarios[
            "read-committed-non-repeatable-read"
        ]
        self.assertEqual(read_committed["isolation"], "Read Committed")
        self.assertNotEqual(
            read_committed["first_read"],
            read_committed["second_read"],
        )
        self.assertEqual(
            read_committed["anomaly"],
            "non-repeatable-read",
        )
        self.assertGreaterEqual(len(read_committed["event_trace"]), 4)

        snapshot = scenarios["snapshot-write-skew"]
        self.assertIn(
            snapshot["isolation"],
            {"Snapshot Isolation", "PostgreSQL Repeatable Read"},
        )
        self.assertEqual(snapshot["committed_transactions"], 2)
        self.assertFalse(snapshot["invariant_after"])
        self.assertEqual(snapshot["anomaly"], "write-skew")

        serializable = scenarios["serializable-retry"]
        self.assertEqual(serializable["isolation"], "Serializable")
        self.assertEqual(serializable["aborted_transactions"], 1)
        self.assertEqual(serializable["retry_scope"], "whole-transaction")
        self.assertTrue(serializable["invariant_after_retry"])
        self.assertGreaterEqual(len(serializable["attempts"]), 3)
        self.assertTrue(report["schedule_mutation"]["detected"])
        self.assertNotEqual(
            report["schedule_mutation"]["baseline_outcome"],
            report["schedule_mutation"]["mutated_outcome"],
        )
        self.assertEqual(
            report["consistency_scope"],
            "business-invariant-is-explicit-not-inferred-by-ACID",
        )
        self.assert_data_scale_mastery_evidence(report, lesson_id)
        self.assertFalse(report["external_network_used"])

    def test_transaction_harness_rejects_serializable_check_mutation(
        self,
    ) -> None:
        self.assert_harness_source_mutation_fails(
            "core-12-transactions-isolation-consistency",
            "transaction_scheduler_lab_v1",
            'if isolation == "serializable" and active_conflict:',
            "if False:",
        )

    def test_coordination_harness_replays_partial_failure(
        self,
    ) -> None:
        lesson_id = "core-13-distributed-coordination-failure"
        report = self.run_python_harness(
            lesson_id,
            "coordination_simulator_lab_v1",
        )

        self.assertEqual(report["seed"], 20260731)
        self.assertEqual(
            report["fixture_metadata"]["kind"],
            "simulated",
        )
        self.assertTrue(report["replay"]["identical"])
        self.assertEqual(
            report["replay"]["first_trace"],
            report["replay"]["second_trace"],
        )
        event_kinds = {
            event["kind"]
            for event in report["replay"]["first_trace"]
        }
        self.assertTrue(
            {"deliver", "duplicate", "partition_start", "partition_end"}
            <= event_kinds
        )
        self.assertTrue(report["reorder_observed"])
        dedupe = report["persistent_dedupe"]
        self.assertTrue(dedupe["key"])
        self.assertEqual(dedupe["applied_state_transitions"], 1)
        self.assertGreaterEqual(dedupe["result_reuse_count"], 1)
        self.assertEqual(
            dedupe["first_result"],
            dedupe["reused_result"],
        )
        self.assertRegex(dedupe["input_fingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            dedupe["stored_entry"],
            {
                "input_fingerprint": dedupe["input_fingerprint"],
                "result": dedupe["first_result"],
            },
        )
        self.assertTrue(dedupe["state_fingerprint_result_atomic"])
        self.assertTrue(report["idempotent_state_transition"])
        partition_mutation = report["partition_mutation"]
        self.assertTrue(partition_mutation["detected"])
        self.assertNotEqual(
            partition_mutation["baseline_outcome"],
            partition_mutation["mutated_outcome"],
        )
        self.assertTrue(report["model_assumptions"])
        scope = report["scope"]
        self.assertTrue(scope["flp_is_asynchronous_consensus_scope"])
        self.assertFalse(scope["flp_means_practical_consensus_impossible"])
        self.assertFalse(scope["simulation_is_formal_proof"])
        self.assertEqual(
            scope["retry_semantics"],
            "at-least-once-with-idempotent-result-reuse",
        )
        self.assert_data_scale_mastery_evidence(report, lesson_id)
        self.assertFalse(report["external_network_used"])

    def test_coordination_harness_rejects_same_key_different_payload(
        self,
    ) -> None:
        report = self.run_python_harness(
            "core-13-distributed-coordination-failure",
            "coordination_simulator_lab_v1",
        )

        conflict = report["same_key_different_payload"]
        self.assertEqual(conflict["error_type"], "IdempotencyConflict")
        self.assertEqual(conflict["code"], "same-key-different-input")
        self.assertTrue(conflict["rejected"])
        self.assertNotEqual(
            conflict["attempted_input_fingerprint"],
            conflict["stored_input_fingerprint"],
        )
        self.assertEqual(conflict["applied_state_transitions"], 1)
        self.assertTrue(conflict["stored_entry_unchanged"])

    def test_coordination_harness_rejects_partition_mutation(
        self,
    ) -> None:
        source = self.python_harness_source(
            "core-13-distributed-coordination-failure",
            "coordination_simulator_lab_v1",
        )
        original = 'if event["kind"] == "partition_start":'
        self.assertIn(original, source)
        mutated = source.replace(original, "if False:", 1)

        result = self.execute_python_harness_source(mutated)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("partition-causal-invariant", result.stderr)
        self.assertNotIn("KeyError", result.stderr)

    def test_performance_harness_separates_simulation_and_measurement(
        self,
    ) -> None:
        lesson_id = "core-14-performance-capacity"
        report = self.run_python_harness(
            lesson_id,
            "performance_capacity_lab_v1",
        )

        self.assertEqual(
            report["simulation_metadata"]["kind"],
            "simulated",
        )
        curve = report["load_curve"]
        self.assertEqual(
            [point["stage"] for point in curve],
            ["low", "near-limit", "overload", "recovery"],
        )
        for point in curve:
            self.assertGreater(point["offered_rps"], 0)
            self.assertLessEqual(
                point["accepted_rps"],
                point["offered_rps"],
            )
            self.assertLessEqual(
                point["success_rps"],
                point["accepted_rps"],
            )
            self.assertLessEqual(point["p50_ms"], point["p95_ms"])
            self.assertLessEqual(point["p95_ms"], point["p99_ms"])
            self.assertGreaterEqual(point["cpu_percent"], 0)
            self.assertGreaterEqual(point["memory_mb"], 0)
            self.assertGreaterEqual(point["queue_depth"], 0)
            self.assertGreaterEqual(point["downstream_ms"], 0)
            self.assertGreater(point["observed_active_concurrency"], 0)
            samples = point["latency_samples_ms"]
            self.assertGreaterEqual(len(samples), 5)
            self.assertTrue(all(sample > 0 for sample in samples))
            self.assertAlmostEqual(
                point["mean_ms"],
                sum(samples) / len(samples),
            )
            self.assertEqual(
                point["mean_source"],
                "bounded-latency-samples-arithmetic-mean",
            )
            self.assertNotAlmostEqual(
                point["mean_ms"],
                (point["p50_ms"] + point["p95_ms"]) / 2,
            )
        analysis = report["curve_analysis"]
        self.assertTrue(analysis["throughput_plateau"])
        self.assertTrue(analysis["tail_growth"])
        self.assertTrue(analysis["error_growth"])
        self.assertTrue(analysis["recovery_hysteresis"])
        capacity = report["capacity"]
        self.assertLess(
            capacity["safe_capacity_rps"],
            capacity["observed_knee_rps"],
        )
        self.assertGreater(capacity["headroom_fraction"], 0)
        self.assertAlmostEqual(
            capacity["safe_capacity_rps"],
            capacity["observed_knee_rps"]
            * (1 - capacity["headroom_fraction"]),
        )
        little = report["little_law"]
        near_limit = next(
            point for point in curve if point["stage"] == "near-limit"
        )
        self.assertEqual(little["source_stage"], "near-limit")
        self.assertEqual(
            little["throughput_per_second"],
            near_limit["success_rps"],
        )
        self.assertEqual(
            little["mean_response_seconds"],
            near_limit["mean_ms"] / 1_000,
        )
        self.assertEqual(
            little["observed_concurrency"],
            near_limit["observed_active_concurrency"],
        )
        self.assertEqual(
            little["observed_concurrency_source"],
            "independent-simulated-fixture-input",
        )
        self.assertAlmostEqual(
            little["calculated_concurrency"],
            little["throughput_per_second"]
            * little["mean_response_seconds"],
        )
        self.assertNotEqual(
            little["observed_concurrency"],
            little["calculated_concurrency"],
        )
        self.assertAlmostEqual(
            little["relative_error"],
            abs(
                little["observed_concurrency"]
                - little["calculated_concurrency"]
            )
            / little["observed_concurrency"],
        )
        self.assertLessEqual(little["relative_error"], 0.05)
        self.assertEqual(
            little["mean_response_source"],
            "bounded-latency-samples-arithmetic-mean",
        )

        profile = report["local_profile"]
        self.assertEqual(
            profile["evidence_kind"],
            "actual-local-measurement",
        )
        self.assertEqual(profile["profiler"], "cProfile")
        self.assertEqual(profile["declared_target"], "profile_target")
        self.assertGreater(profile["total_calls"], 0)
        self.assertTrue(profile["measurement_derived"])
        self.assertIn(
            profile["measured_top_function"],
            profile["measured_functions"],
        )
        self.assertEqual(
            profile["tool_scope"],
            {
                "python": "3.13",
                "profiler": "cProfile/pstats standard library",
                "go_docs": "rolling; reviewed 2026-07-31",
            },
        )
        self.assertTrue(profile["environment_limitations"])
        mutation = report["request_mix_mutation"]
        self.assertTrue(mutation["recomputed"])
        self.assertNotEqual(
            mutation["baseline_bottleneck"],
            mutation["mutated_bottleneck"],
        )
        self.assertNotEqual(
            mutation["baseline_safe_capacity_rps"],
            mutation["mutated_safe_capacity_rps"],
        )
        self.assertEqual(
            mutation["baseline_safe_capacity_rps"],
            capacity["safe_capacity_rps"],
        )
        def inferred_knee(load_curve: list[dict[str, object]]) -> int:
            for previous, current in zip(load_curve, load_curve[1:]):
                plateau = (
                    current["success_rps"]
                    <= previous["success_rps"]
                )
                tail_growth = (
                    current["p99_ms"] > previous["p99_ms"]
                )
                error_growth = (
                    current["success_rps"]
                    < current["accepted_rps"]
                )
                if plateau and tail_growth and error_growth:
                    return previous["offered_rps"]
            self.fail("load curve has no measured knee")

        self.assertEqual(
            capacity["observed_knee_rps"],
            inferred_knee(curve),
        )
        self.assertIn(
            capacity["observed_knee_rps"],
            {point["offered_rps"] for point in curve},
        )
        transfer_curve = mutation["mutated_load_curve"]
        self.assertEqual(
            mutation["mutated_observed_knee_rps"],
            inferred_knee(transfer_curve),
        )
        self.assertIn(
            mutation["mutated_observed_knee_rps"],
            {point["offered_rps"] for point in transfer_curve},
        )
        self.assertEqual(
            mutation["knee_criteria"],
            ["throughput-plateau", "tail-growth", "error-growth"],
        )
        self.assertLessEqual(report["runtime_bound"]["iterations"], 50_000)
        self.assert_data_scale_mastery_evidence(report, lesson_id)
        self.assertFalse(report["external_network_used"])

    def test_performance_harness_rejects_capacity_mutation(
        self,
    ) -> None:
        self.assert_harness_source_mutation_fails(
            "core-14-performance-capacity",
            "performance_capacity_lab_v1",
            "if offered_rps > capacity:",
            "if False:",
        )

    def test_reliability_harness_derives_slo_alerts_and_runbook(
        self,
    ) -> None:
        lesson_id = "core-15-reliability-observability-slo"
        report = self.run_python_harness(
            lesson_id,
            "reliability_slo_lab_v1",
        )

        self.assertEqual(
            report["fixture_metadata"]["kind"],
            "synthetic",
        )
        sli = report["sli"]
        self.assertEqual(sli["good_events"] + sli["bad_events"], sli["valid_events"])
        self.assertLessEqual(sli["valid_events"], sli["total_events"])
        self.assertAlmostEqual(
            sli["ratio"],
            sli["good_events"] / sli["valid_events"],
        )
        self.assertEqual(sli["journey"], "purchase-completion")
        self.assertTrue(
            all(
                event["timestamp"].endswith("+00:00")
                for event in report["fixture_events"]
            )
        )
        slo = report["slo"]
        self.assertGreater(slo["window_days"], 0)
        self.assertGreater(slo["target"], 0)
        self.assertLess(slo["target"], 1)
        self.assertAlmostEqual(
            slo["error_budget_fraction"],
            1 - slo["target"],
        )
        burn_windows = report["burn_windows"]
        self.assertEqual(set(burn_windows), {"short", "long"})
        self.assertEqual(burn_windows["short"]["window_minutes"], 5)
        self.assertEqual(burn_windows["long"]["window_minutes"], 60)
        for window in burn_windows.values():
            self.assertGreater(window["valid_events"], 0)
            self.assertEqual(
                window["good_events"] + window["bad_events"],
                window["valid_events"],
            )
            self.assertAlmostEqual(
                window["observed_bad_fraction"],
                window["bad_events"] / window["valid_events"],
            )
            self.assertAlmostEqual(
                window["rate"],
                window["observed_bad_fraction"]
                / slo["error_budget_fraction"],
            )
            self.assertTrue(window["start_timestamp"].endswith("+00:00"))
            self.assertTrue(window["end_timestamp"].endswith("+00:00"))
        alerts = report["alerts"]
        self.assertTrue(alerts["multi_window"])
        self.assertEqual(alerts["combination"], "short-and-long")
        self.assertTrue(alerts["page"]["actionable"])
        self.assertTrue(alerts["ticket"]["actionable"])
        self.assertEqual(
            alerts["page"]["triggered"],
            (
                alerts["page"]["conditions"]["short"]
                and alerts["page"]["conditions"]["long"]
            ),
        )
        scenarios = alerts["scenarios"]
        self.assertEqual(set(scenarios), {"normal", "short-only", "both"})
        self.assertEqual(
            {
                name: (
                    scenario["conditions"]["short"],
                    scenario["conditions"]["long"],
                    scenario["page_triggered"],
                )
                for name, scenario in scenarios.items()
            },
            {
                "normal": (False, False, False),
                "short-only": (True, False, False),
                "both": (True, True, True),
            },
        )
        for scenario in scenarios.values():
            for window in scenario["windows"].values():
                self.assertAlmostEqual(
                    window["observed_bad_fraction"],
                    window["bad_events"] / window["valid_events"],
                )
                self.assertAlmostEqual(
                    window["rate"],
                    window["observed_bad_fraction"]
                    / slo["error_budget_fraction"],
                )
        runbook = report["runbook"]
        self.assertTrue(runbook["owner"])
        self.assertTrue(runbook["user_impact_check"])
        self.assertTrue(runbook["mitigation"])
        self.assertTrue(runbook["rollback"])
        self.assertTrue(runbook["escalation"])

        telemetry = report["telemetry_contract"]
        self.assertEqual(telemetry["otel_specification"], "1.59.0")
        self.assertEqual(telemetry["semantic_conventions"], "1.43.0")
        self.assertEqual(
            set(telemetry["required_resource_attributes"]),
            {
                "service.name",
                "deployment.environment.name",
                "service.version",
            },
        )
        self.assertNotIn(
            "deployment.environment",
            telemetry["required_resource_attributes"],
        )
        schema_validation = telemetry["schema_validation"]
        self.assertIs(
            schema_validation["deprecated_attribute_rejected"],
            True,
        )
        self.assertEqual(
            schema_validation["deprecated_probe_errors"],
            ["deprecated-resource-attribute:deployment.environment"],
        )
        correlation = telemetry["trace_correlation"]
        self.assertIs(type(correlation["passed"]), bool)
        self.assertIs(type(correlation["correlated_requests"]), int)
        self.assertIs(type(correlation["total_requests"]), int)
        self.assertEqual(
            correlation["passed"],
            (
                correlation["correlated_requests"]
                == correlation["total_requests"]
            ),
        )
        self.assertEqual(
            correlation["correlated_request_ids"],
            correlation["request_ids"],
        )
        self.assertTrue(telemetry["pii_check"]["passed"])
        cardinality = telemetry["cardinality_check"]
        self.assertIs(type(cardinality["bounded"]), bool)
        self.assertIs(type(cardinality["unique_series_count"]), int)
        self.assertIs(type(cardinality["series_bound"]), int)
        self.assertEqual(
            cardinality["bounded"],
            (
                cardinality["unique_series_count"]
                <= cardinality["series_bound"]
            ),
        )
        self.assertEqual(
            cardinality["unique_series_count"],
            len(
                {
                    tuple(sorted(sample.items()))
                    for sample in cardinality["metric_series_fixture"]
                }
            ),
        )
        self.assertTrue(telemetry["sampling_limitations"])
        self.assertTrue(telemetry["stability"])
        transfer = report["journey_boundary_transfer"]
        self.assertEqual(transfer["changed_fields"], ["journey"])
        self.assertEqual(
            transfer["baseline_sli"]["journey"],
            "search-success",
        )
        self.assertEqual(
            transfer["transferred_sli"]["journey"],
            "purchase-completion",
        )
        self.assertNotEqual(
            transfer["baseline_sli"]["ratio"],
            transfer["transferred_sli"]["ratio"],
        )
        self.assertEqual(
            transfer["baseline_event_ids"],
            transfer["transferred_event_ids"],
        )
        self.assertEqual(
            transfer["unchanged"],
            {
                "event_fixture": True,
                "target": True,
                "window": True,
                "telemetry_contract": True,
            },
        )
        self.assertEqual(
            transfer["telemetry_errors_before"],
            transfer["telemetry_errors_after"],
        )
        self.assert_data_scale_mastery_evidence(report, lesson_id)
        self.assertFalse(report["external_network_used"])

    def test_reliability_harness_rejects_good_event_mutation(
        self,
    ) -> None:
        self.assert_harness_source_mutation_fails(
            "core-15-reliability-observability-slo",
            "reliability_slo_lab_v1",
            (
                'good = event["status"] == "ok" '
                'and event["latency_ms"] <= 300'
            ),
            "good = True",
        )

    def test_hci_harness_derives_generated_site_audit(self) -> None:
        lesson_id = "core-16-hci-usability-accessibility"
        report = self.run_python_harness(
            lesson_id,
            "hci_accessibility_audit_lab_v1",
        )

        self.assertEqual(
            report["site_under_audit"],
            "generated-static-curriculum",
        )
        standards = report["standards"]
        self.assertEqual(
            standards["normative_target"],
            {
                "name": "WCAG",
                "version": "2.2",
                "level": "AA",
                "status": "W3C Recommendation",
                "date": "2024-12-12",
            },
        )
        self.assertEqual(standards["human_centred_design"], "ISO 9241-210:2019")
        self.assertEqual(
            standards["non_normative_candidates"],
            {
                "WCAG 3.0": "W3C Working Draft 2026-03-03",
                "APCA": "not-a-WCAG-2.2-conformance-standard",
            },
        )
        observations = report["audit"]["observations"]
        self.assertEqual(
            {item["dimension"] for item in observations},
            {"keyboard", "zoom-200", "reading-order", "usability"},
        )
        self.assertTrue(
            all(
                item["passed"]
                == (item["actual"] == item["expected"])
                for item in observations
            )
        )
        summary = report["audit"]["summary"]
        self.assertEqual(summary["total"], len(observations))
        self.assertEqual(
            summary["passed"],
            sum(item["passed"] for item in observations),
        )
        self.assertEqual(
            summary["failed"],
            summary["total"] - summary["passed"],
        )
        self.assertTrue(report["audit"]["manual_review_required"])
        self.assertFalse(report["audit"]["conformance_claim"])
        transfer = report["input_mode_transfer"]
        self.assertEqual(transfer["changed_assumption"], "input-mode")
        self.assertEqual(transfer["changed_fields"], ["input_mode"])
        self.assertEqual(
            transfer["unchanged"],
            {
                "page_fixture": True,
                "wcag_target": True,
                "expected_outcomes": True,
            },
        )
        self.assertNotEqual(
            transfer["baseline_check_ids"],
            transfer["transferred_check_ids"],
        )
        self.assert_human_product_harness_contract(
            report,
            lesson_id,
            "synthetic",
        )

    def test_hci_harness_rejects_uncausal_audit_mutation(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-16-hci-usability-accessibility",
            "hci_accessibility_audit_lab_v1",
            'passed = observation["actual"] == observation["expected"]',
            "passed = True",
            "hci-causal-invariant",
        )

    def test_hci_transfer_reaudits_mode_specific_outcomes(self) -> None:
        lesson_id = "core-16-hci-usability-accessibility"
        report = self.run_python_harness(
            lesson_id,
            "hci_accessibility_audit_lab_v1",
        )

        transfer = report["input_mode_transfer"]
        baseline = transfer["baseline_observations"]
        transferred = transfer["transferred_observations"]
        self.assertEqual(
            {item["dimension"] for item in baseline},
            {item["dimension"] for item in transferred},
        )
        self.assertTrue(
            all(item["input_mode"] == "pointer-primary" for item in baseline)
        )
        self.assertTrue(
            all(item["input_mode"] == "keyboard-only" for item in transferred)
        )
        self.assertTrue(
            all(item["operation"] for item in baseline + transferred)
        )
        self.assertTrue(
            all(
                baseline_item["operation"]
                != transferred_item["operation"]
                for baseline_item, transferred_item in zip(
                    baseline,
                    transferred,
                    strict=True,
                )
            )
        )
        baseline_actual = {
            item["dimension"]: item["actual"]
            for item in baseline
        }
        transferred_actual = {
            item["dimension"]: item["actual"]
            for item in transferred
        }
        changed_dimensions = {
            dimension
            for dimension in baseline_actual
            if baseline_actual[dimension] != transferred_actual[dimension]
        }
        self.assertEqual(
            set(transfer["changed_dimensions"]),
            changed_dimensions,
        )
        self.assertIn("keyboard", changed_dimensions)
        self.assertNotEqual(
            transfer["baseline_summary"],
            transfer["transferred_summary"],
        )
        body = self.body_path(lesson_id).read_text(encoding="utf-8")
        for marker in (
            "mode別operationとactual",
            "pointer-primaryは3/4",
            "keyboard-onlyは2/4",
        ):
            self.assertIn(marker, body)

    def test_hci_transfer_rejects_input_mode_bypass(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-16-hci-usability-accessibility",
            "hci_accessibility_audit_lab_v1",
            'actual = source["actual_by_input_mode"][input_mode]',
            'actual = source["actual_by_input_mode"]["pointer-primary"]',
            "hci-input-mode-invariant",
        )

    def test_graphics_harness_preserves_semantic_equivalence(self) -> None:
        lesson_id = "core-17-graphics-visual-information"
        report = self.run_python_harness(
            lesson_id,
            "graphics_semantic_equivalence_lab_v1",
        )

        roadmap = report["roadmap"]
        node_ids = [node["id"] for node in roadmap["data"]["nodes"]]
        edge_pairs = [
            [edge["from"], edge["to"]]
            for edge in roadmap["data"]["edges"]
        ]
        self.assertEqual(roadmap["semantic_html"]["node_ids"], node_ids)
        self.assertEqual(roadmap["text_equivalent"]["node_ids"], node_ids)
        self.assertEqual(
            roadmap["text_equivalent"]["edge_pairs"],
            edge_pairs,
        )
        chart = report["quantitative_chart"]
        expected_rows = [
            {"id": point["id"], "label": point["label"], "value": point["value"]}
            for point in chart["data"]
        ]
        self.assertEqual(chart["semantic_html"]["table_rows"], expected_rows)
        self.assertEqual(chart["text_equivalent"]["rows"], expected_rows)
        self.assertEqual(
            chart["summary"]["maximum_id"],
            max(chart["data"], key=lambda point: point["value"])["id"],
        )
        self.assertEqual(
            chart["summary"]["minimum_id"],
            min(chart["data"], key=lambda point: point["value"])["id"],
        )
        self.assertEqual(
            chart["encoding"]["quantitative"],
            "position-on-common-scale",
        )
        self.assertFalse(chart["encoding"]["color_only"])
        transfer = report["display_mode_transfer"]
        self.assertEqual(transfer["changed_assumption"], "display-mode")
        self.assertEqual(transfer["changed_fields"], ["display_mode"])
        self.assertEqual(transfer["baseline_mode"], "color")
        self.assertEqual(transfer["transferred_mode"], "monochrome")
        self.assertTrue(transfer["data_unchanged"])
        self.assertTrue(transfer["text_equivalence_preserved"])
        baseline_artifact = transfer["baseline_artifact"]
        transferred_artifact = transfer["transferred_artifact"]
        self.assertEqual(baseline_artifact["display_mode"], "color")
        self.assertEqual(
            transferred_artifact["display_mode"],
            "monochrome",
        )
        self.assertIn("display-color", baseline_artifact["html"])
        self.assertIn(
            "display-monochrome",
            transferred_artifact["html"],
        )
        self.assertIn(
            ".display-monochrome",
            transferred_artifact["css"],
        )
        self.assertEqual(
            baseline_artifact["data_fingerprint"],
            transferred_artifact["data_fingerprint"],
        )
        self.assert_human_product_harness_contract(
            report,
            lesson_id,
            "synthetic",
        )

    def test_graphics_harness_rejects_text_equivalence_mutation(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-17-graphics-visual-information",
            "graphics_semantic_equivalence_lab_v1",
            "text_rows = [dict(point) for point in chart_data]",
            "text_rows = []",
            "graphics-causal-invariant",
        )

    def test_graphics_harness_emits_validated_html_css_artifacts(
        self,
    ) -> None:
        report = self.run_python_harness(
            "core-17-graphics-visual-information",
            "graphics_semantic_equivalence_lab_v1",
        )

        roadmap = report["roadmap"]
        roadmap_artifact = roadmap["artifact"]
        roadmap_parser = _StaticArtifactParser()
        roadmap_parser.feed(roadmap_artifact["html"])
        roadmap_parser.close()
        self.assertEqual(roadmap_parser.unsafe, [])
        self.assertTrue(
            {"figure", "figcaption", "ol", "li"}.issubset(
                roadmap_parser.tags
            )
        )
        node_ids = [node["id"] for node in roadmap["data"]["nodes"]]
        self.assertEqual(
            [item for item in roadmap_parser.ids if item in node_ids],
            node_ids,
        )
        self.assertEqual(
            roadmap_parser.edge_pairs,
            roadmap["text_equivalent"]["edge_pairs"],
        )
        self.assertTrue(roadmap["artifact_validation"]["valid"])

        chart = report["quantitative_chart"]
        chart_artifact = chart["artifact"]
        chart_parser = _StaticArtifactParser()
        chart_parser.feed(chart_artifact["html"])
        chart_parser.close()
        self.assertEqual(chart_parser.unsafe, [])
        self.assertTrue(
            {
                "figure",
                "figcaption",
                "table",
                "caption",
                "thead",
                "tbody",
                "tr",
                "th",
                "td",
            }.issubset(chart_parser.tags)
        )
        self.assertTrue(
            all(
                scope in {"col", "row"}
                for scope in chart_parser.table_header_scopes
            )
        )
        self.assertTrue(chart["artifact_validation"]["valid"])
        self.assertEqual(
            chart["artifact_validation"]["table_rows"],
            chart["text_equivalent"]["rows"],
        )
        combined_css = (
            roadmap_artifact["css"] + chart_artifact["css"]
        )
        self.assertIn(".roadmap", combined_css)
        self.assertIn(".quantitative-chart", combined_css)
        self.assertNotIn("url(", combined_css.casefold())
        self.assertTrue(
            "border" in combined_css or "outline" in combined_css
        )

    def test_graphics_harness_rejects_incomplete_rendered_chart(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-17-graphics-visual-information",
            "graphics_semantic_equivalence_lab_v1",
            "chart_html = render_chart_html(chart_data)",
            "chart_html = render_chart_html(chart_data[:-1])",
            "graphics-artifact-invariant",
        )

    def test_graphics_harness_renders_quantitative_scale_and_modes(
        self,
    ) -> None:
        report = self.run_python_harness(
            "core-17-graphics-visual-information",
            "graphics_semantic_equivalence_lab_v1",
        )

        chart = report["quantitative_chart"]
        artifact = chart["artifact"]
        parser = _StaticArtifactParser()
        parser.feed(artifact["html"])
        parser.close()
        raw_max = max(point["value"] for point in chart["data"])
        expected_meters = [
            {
                "id": point["id"],
                "min": 0,
                "max": 100,
                "value": round(point["value"] / raw_max * 100),
                "raw_value": point["value"],
            }
            for point in chart["data"]
        ]
        self.assertEqual(parser.meter_values, expected_meters)
        self.assertEqual(
            chart["artifact_validation"]["meter_values"],
            expected_meters,
        )
        self.assertIn(".chart-bar", artifact["css"])
        for point in chart["data"]:
            self.assertIn(
                f'{point["label"]}: {point["value"]} hours',
                artifact["html"],
            )
        transfer = report["display_mode_transfer"]
        baseline = transfer["baseline_artifact"]
        transferred = transfer["transferred_artifact"]
        for artifact, expected_class in (
            (baseline, "display-color"),
            (transferred, "display-monochrome"),
        ):
            validation = artifact["validation"]
            self.assertTrue(validation["html_valid"])
            self.assertTrue(validation["css_valid"])
            self.assertEqual(
                validation["section_classes"],
                [expected_class],
            )
            self.assertEqual(validation["unsafe_html"], [])
        self.assertIn("accent-color: #245d63", baseline["css"])
        self.assertIn(
            "accent-color: CanvasText",
            transferred["css"],
        )
        self.assertIn("border-style: double", transferred["css"])
        self.assertNotEqual(baseline["css"], transferred["css"])
        self.assertEqual(
            chart["visual_encoding"],
            {
                "mark": "meter-bar",
                "scale": "normalized-common-zero-to-100",
                "scale_min": 0,
                "scale_max": 100,
                "raw_max": raw_max,
                "visible_value_labels": True,
                "non_color_cue": "length-pattern-border-and-text",
            },
        )
        visible_body = self.body_path(
            "core-17-graphics-visual-information"
        ).read_text(encoding="utf-8").partition("<pre><code>")[0]
        for class_name in (
            "quantitative-chart-artifact",
            "chart-scale",
            "chart-display--color",
            "chart-display--monochrome",
            "chart-bar--40",
            "chart-bar--60",
            "chart-bar--100",
        ):
            self.assertIn(class_name, visible_body)
        for label in (
            "学習: 12 hours (60%)",
            "実践: 20 hours (100%)",
            "復習: 8 hours (40%)",
        ):
            self.assertIn(label, visible_body)

    def test_graphics_harness_rejects_incomplete_visual_scale(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-17-graphics-visual-information",
            "graphics_semantic_equivalence_lab_v1",
            "meter_rows = render_meter_rows(chart_data, scale_max)",
            "meter_rows = render_meter_rows(chart_data[:-1], scale_max)",
            "graphics-scale-invariant",
        )

    def test_graphics_harness_rejects_unknown_display_mode(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-17-graphics-visual-information",
            "graphics_semantic_equivalence_lab_v1",
            (
                "baseline_artifact = render_display_artifact(\n"
                '        "color",'
            ),
            (
                "baseline_artifact = render_display_artifact(\n"
                '        "sepia",'
            ),
            "graphics-display-mode-invariant",
        )

    def test_graphics_harness_rejects_css_selector_injection(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-17-graphics-visual-information",
            "graphics_semantic_equivalence_lab_v1",
            (
                "baseline_artifact = render_display_artifact(\n"
                '        "color",'
            ),
            (
                "baseline_artifact = render_display_artifact(\n"
                '        "x}body{display:none}/*",'
            ),
            "graphics-display-mode-invariant",
        )

    def test_graphics_harness_rejects_html_attribute_injection(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-17-graphics-visual-information",
            "graphics_semantic_equivalence_lab_v1",
            (
                "baseline_artifact = render_display_artifact(\n"
                '        "color",'
            ),
            (
                "baseline_artifact = render_display_artifact(\n"
                """        'color" data-unsafe="true',"""
            ),
            "graphics-display-mode-invariant",
        )

    def test_graphics_harness_rejects_javascript_url_in_artifact(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-17-graphics-visual-information",
            "graphics_semantic_equivalence_lab_v1",
            (
                "roadmap = derive_roadmap("
                "ROADMAP_NODES, ROADMAP_EDGES)"
            ),
            (
                "roadmap = derive_roadmap("
                "ROADMAP_NODES, ROADMAP_EDGES)\n"
                """    roadmap["artifact"]["html"] += """
                """'<a href="javascript:alert(1)">unsafe</a>'"""
            ),
            "graphics-artifact-invariant",
        )

    def test_graphics_harness_rejects_data_url_in_artifact(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-17-graphics-visual-information",
            "graphics_semantic_equivalence_lab_v1",
            (
                "roadmap = derive_roadmap("
                "ROADMAP_NODES, ROADMAP_EDGES)"
            ),
            (
                "roadmap = derive_roadmap("
                "ROADMAP_NODES, ROADMAP_EDGES)\n"
                """    roadmap["artifact"]["html"] += """
                """'<a href="data:text/html,unsafe">unsafe</a>'"""
            ),
            "graphics-artifact-invariant",
        )

    def test_experiment_harness_derives_metrics_and_stop_decision(
        self,
    ) -> None:
        lesson_id = "core-18-product-discovery-experiments"
        report = self.run_python_harness(
            lesson_id,
            "product_experiment_lab_v1",
        )

        hypothesis = report["hypothesis"]
        self.assertTrue(hypothesis["falsifiable"])
        self.assertTrue(hypothesis["statement"])
        plan = report["analysis_plan"]
        self.assertTrue(plan["locked_before_exposure"])
        self.assertEqual(plan["primary_metric"], "completion-rate")
        self.assertEqual(
            set(plan["guardrail_metrics"]),
            {"complaint-rate", "p95-latency-ms"},
        )
        self.assertTrue(plan["stop_conditions"])
        self.assertEqual(plan["sequential_method"], "always-valid")
        self.assertTrue(plan["p_hacking_prohibited"])
        variants = report["experiment"]["variants"]
        metrics = report["experiment"]["derived_metrics"]
        for variant_id, variant in variants.items():
            derived = metrics[variant_id]
            self.assertAlmostEqual(
                derived["completion_rate"],
                variant["completions"] / variant["visitors"],
            )
            self.assertAlmostEqual(
                derived["complaint_rate"],
                variant["complaints"] / variant["visitors"],
            )
        treatment_effect = (
            metrics["treatment"]["completion_rate"]
            - metrics["control"]["completion_rate"]
        )
        complaint_delta = (
            metrics["treatment"]["complaint_rate"]
            - metrics["control"]["complaint_rate"]
        )
        self.assertAlmostEqual(
            report["experiment"]["primary_effect"],
            treatment_effect,
        )
        self.assertAlmostEqual(
            report["experiment"]["complaint_delta"],
            complaint_delta,
        )
        transfer = report["guardrail_threshold_transfer"]
        self.assertEqual(
            transfer["changed_assumption"],
            "guardrail-threshold",
        )
        self.assertEqual(transfer["changed_fields"], ["complaint_rate_limit"])
        self.assertEqual(
            transfer["baseline_inputs"],
            transfer["transferred_inputs"],
        )
        self.assertEqual(transfer["baseline_decision"], "continue")
        self.assertEqual(transfer["transferred_decision"], "stop")
        self.assert_human_product_harness_contract(
            report,
            lesson_id,
            "simulated",
        )

    def test_experiment_harness_rejects_guardrail_mutation(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-18-product-discovery-experiments",
            "product_experiment_lab_v1",
            "guardrail_passed = complaint_delta <= guardrail_limit",
            "guardrail_passed = True",
            "experiment-causal-invariant",
        )

    def test_communication_harness_aligns_summary_appendix_and_adr(
        self,
    ) -> None:
        lesson_id = "core-19-technical-communication-design-docs"
        report = self.run_python_harness(
            lesson_id,
            "technical_communication_lab_v1",
        )

        decision = report["decision"]
        expected_option = max(
            decision["options"],
            key=lambda option: option["weighted_score"],
        )
        self.assertEqual(decision["selected_option"], expected_option["id"])
        summary = report["one_page_executive_summary"]
        self.assertEqual(summary["page_budget"], 1)
        self.assertLessEqual(summary["word_count"], summary["word_limit"])
        self.assertEqual(summary["decision"], decision["selected_option"])
        self.assertTrue(summary["reader_outcome"])
        appendix = report["technical_appendix"]
        self.assertEqual(
            {item["id"] for item in appendix["alternatives"]},
            {item["id"] for item in decision["options"]},
        )
        self.assertEqual(appendix["decision"], decision["selected_option"])
        self.assertTrue(appendix["risks"])
        self.assertTrue(appendix["validation_evidence"])
        adr = report["adr_validation"]
        self.assertTrue(adr["valid"])
        self.assertEqual(adr["missing_fields"], [])
        self.assertEqual(
            set(adr["required_fields"]),
            {
                "context",
                "decision",
                "alternatives",
                "consequences",
                "risks",
                "validation",
            },
        )
        transfer = report["audience_transfer"]
        self.assertEqual(transfer["changed_assumption"], "audience")
        self.assertEqual(transfer["changed_fields"], ["audience"])
        self.assertEqual(transfer["baseline_audience"], "executive")
        self.assertEqual(transfer["transferred_audience"], "implementer")
        self.assertEqual(
            transfer["baseline_decision"],
            transfer["transferred_decision"],
        )
        self.assertTrue(transfer["decision_evidence_unchanged"])
        self.assert_human_product_harness_contract(
            report,
            lesson_id,
            "synthetic",
        )

    def test_communication_harness_rejects_document_drift(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-19-technical-communication-design-docs",
            "technical_communication_lab_v1",
            'appendix_decision = decision["selected_option"]',
            'appendix_decision = "undocumented-option"',
            "communication-causal-invariant",
        )

    def test_communication_harness_derives_audience_specific_views(
        self,
    ) -> None:
        report = self.run_python_harness(
            "core-19-technical-communication-design-docs",
            "technical_communication_lab_v1",
        )

        summary = report["one_page_executive_summary"]
        appendix = report["technical_appendix"]
        transfer = report["audience_transfer"]
        baseline_view = transfer["baseline_view"]
        transferred_view = transfer["transferred_view"]
        self.assertEqual(baseline_view["audience"], "executive")
        self.assertEqual(transferred_view["audience"], "implementer")
        self.assertEqual(summary["audience_view"], baseline_view)
        self.assertEqual(appendix["audience_view"], transferred_view)
        self.assertEqual(
            baseline_view["decision_evidence"],
            transferred_view["decision_evidence"],
        )
        self.assertEqual(
            baseline_view["decision"],
            transferred_view["decision"],
        )
        self.assertNotEqual(
            baseline_view["sections"],
            transferred_view["sections"],
        )
        self.assertTrue(transfer["decision_evidence_unchanged"])
        self.assertTrue(transfer["audience_specific_content_differs"])

    def test_communication_harness_rejects_audience_bypass(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-19-technical-communication-design-docs",
            "technical_communication_lab_v1",
            (
                'transferred_view = build_audience_view('
                '"implementer", decision)'
            ),
            (
                'transferred_view = build_audience_view('
                '"executive", decision)'
            ),
            "communication-audience-invariant",
        )

    def test_ethics_harness_derives_uneven_harm_and_residual_risk(
        self,
    ) -> None:
        lesson_id = "core-20-ethics-privacy-societal-impact"
        report = self.run_python_harness(
            lesson_id,
            "ethics_privacy_impact_lab_v1",
        )

        self.assertEqual(
            report["frameworks"],
            {
                "professional_ethics": "ACM Code of Ethics 2018",
                "privacy": "NIST Privacy Framework 1.0",
                "privacy_protocol": "RFC 6973",
                "human_rights": "RFC 9620",
                "ai_risk": "NIST AI RMF 1.0",
            },
        )
        self.assertEqual(
            report["data_lifecycle"],
            ["collect", "use", "share", "retain", "delete"],
        )
        impacts = report["impact_assessment"]["impacts"]
        self.assertGreaterEqual(len({item["affected_people"] for item in impacts}), 3)
        for impact in impacts:
            self.assertEqual(
                impact["inherent_risk"],
                impact["likelihood"]
                * impact["severity"]
                * impact["exposure"],
            )
            self.assertEqual(
                impact["residual_risk"],
                max(0, impact["inherent_risk"] - impact["mitigation_reduction"]),
            )
            self.assertTrue(impact["mitigations"])
        residuals = [item["residual_risk"] for item in impacts]
        uneven = report["impact_assessment"]["uneven_harm"]
        self.assertEqual(uneven["maximum"], max(residuals))
        self.assertEqual(uneven["minimum"], min(residuals))
        self.assertEqual(uneven["gap"], max(residuals) - min(residuals))
        relation = report["privacy_security_relation"]
        self.assertTrue(relation["related"])
        self.assertTrue(relation["distinct"])
        self.assertFalse(relation["privacy_equals_security"])
        self.assertTrue(report["impact_assessment"]["residual_risk_owner"])
        transfer = report["affected_population_transfer"]
        self.assertEqual(
            transfer["changed_assumption"],
            "affected-population",
        )
        self.assertEqual(transfer["changed_fields"], ["affected_population"])
        self.assertEqual(
            transfer["unchanged"],
            {
                "data_lifecycle": True,
                "mitigations": True,
                "risk_formula": True,
            },
        )
        self.assertGreater(
            transfer["transferred_maximum_residual_risk"],
            transfer["baseline_maximum_residual_risk"],
        )
        self.assert_human_product_harness_contract(
            report,
            lesson_id,
            "simulated",
        )

    def test_ethics_harness_rejects_residual_risk_mutation(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-20-ethics-privacy-societal-impact",
            "ethics_privacy_impact_lab_v1",
            "residual_risk = max(0, inherent_risk - mitigation_reduction)",
            "residual_risk = inherent_risk",
            "ethics-causal-invariant",
        )

    def test_ethics_harness_traces_every_data_lifecycle_phase(
        self,
    ) -> None:
        report = self.run_python_harness(
            "core-20-ethics-privacy-societal-impact",
            "ethics_privacy_impact_lab_v1",
        )

        assessment = report["data_lifecycle_assessment"]
        policy = report["lifecycle_policy"]
        self.assertEqual(
            [item["phase"] for item in assessment],
            report["data_lifecycle"],
        )
        impacts = report["impact_assessment"]["impacts"]
        known_harm_ids = {item["harm_id"] for item in impacts}
        known_control_ids = {
            control_id
            for item in impacts
            for control_id in item["control_ids"]
        }
        known_residual_risk_ids = {
            item["residual_risk_id"] for item in impacts
        }
        referenced_harm_ids: set[str] = set()
        referenced_control_ids: set[str] = set()
        referenced_residual_risk_ids: set[str] = set()
        for item in assessment:
            self.assertEqual(
                set(item),
                {
                    "phase",
                    "approved_purpose",
                    "data_classes",
                    "necessity",
                    "allowed_roles",
                    "retention_days",
                    "delete_sla_days",
                    "deletion_enabled",
                    "forbidden_data_classes",
                    "owner",
                    "harm_ids",
                    "control_ids",
                    "residual_risk_ids",
                    "verification",
                },
            )
            self.assertTrue(all(item.values()))
            phase = item["phase"]
            self.assertEqual(
                item["approved_purpose"],
                policy["approved_purposes"][phase],
            )
            self.assertIs(item["necessity"], True)
            self.assertLessEqual(
                set(item["data_classes"]),
                set(policy["allowed_data_classes"][phase]),
            )
            self.assertFalse(
                set(item["data_classes"])
                & set(item["forbidden_data_classes"]),
            )
            self.assertEqual(
                item["forbidden_data_classes"],
                policy["forbidden_data_classes"],
            )
            self.assertLessEqual(
                set(item["allowed_roles"]),
                set(policy["allowed_roles"][phase]),
            )
            self.assertNotIn("public", item["allowed_roles"])
            self.assertNotIn("all-roles", item["allowed_roles"])
            self.assertGreater(item["retention_days"], 0)
            self.assertLessEqual(
                item["retention_days"],
                policy["max_retention_days"][phase],
            )
            self.assertGreater(item["delete_sla_days"], 0)
            self.assertLessEqual(
                item["delete_sla_days"],
                policy["max_delete_sla_days"],
            )
            self.assertIs(item["deletion_enabled"], True)
            self.assertLessEqual(set(item["harm_ids"]), known_harm_ids)
            self.assertLessEqual(
                set(item["control_ids"]),
                known_control_ids,
            )
            self.assertLessEqual(
                set(item["residual_risk_ids"]),
                known_residual_risk_ids,
            )
            referenced_harm_ids.update(item["harm_ids"])
            referenced_control_ids.update(item["control_ids"])
            referenced_residual_risk_ids.update(
                item["residual_risk_ids"]
            )
        self.assertEqual(referenced_harm_ids, known_harm_ids)
        self.assertEqual(referenced_control_ids, known_control_ids)
        self.assertEqual(
            referenced_residual_risk_ids,
            known_residual_risk_ids,
        )
        transfer = report["affected_population_transfer"]
        self.assertEqual(
            transfer["baseline_lifecycle"],
            assessment,
        )
        self.assertEqual(
            transfer["transferred_lifecycle"],
            assessment,
        )

    def test_ethics_harness_rejects_missing_lifecycle_evidence(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-20-ethics-privacy-societal-impact",
            "ethics_privacy_impact_lab_v1",
            (
                "lifecycle_assessment = "
                "validate_lifecycle(LIFECYCLE_FIXTURE)"
            ),
            "lifecycle_assessment = []",
            "ethics-lifecycle-invariant",
        )

    def test_ethics_harness_rejects_forbidden_data_overcollection(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-20-ethics-privacy-societal-impact",
            "ethics_privacy_impact_lab_v1",
            '"data_classes": ["availability-window"],',
            (
                '"data_classes": ['
                '"availability-window", "health-diagnosis"'
                "],"
            ),
            "ethics-lifecycle-policy-invariant",
        )

    def test_ethics_harness_rejects_public_all_role_access(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-20-ethics-privacy-societal-impact",
            "ethics_privacy_impact_lab_v1",
            (
                '"allowed_roles": ['
                '"data-subject", "assignment-operator"'
                "],"
            ),
            '"allowed_roles": ["public", "all-roles"],',
            "ethics-lifecycle-policy-invariant",
        )

    def test_ethics_harness_rejects_unlimited_retention(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-20-ethics-privacy-societal-impact",
            "ethics_privacy_impact_lab_v1",
            '"retention_days": 30,',
            '"retention_days": -1,',
            "ethics-lifecycle-policy-invariant",
        )

    def test_ethics_harness_rejects_disabled_deletion(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-20-ethics-privacy-societal-impact",
            "ethics_privacy_impact_lab_v1",
            (
                '        "delete_sla_days": 7,\n'
                '        "deletion_enabled": True,\n'
                '        "owner": "deletion-control-owner",'
            ),
            (
                '        "delete_sla_days": 7,\n'
                '        "deletion_enabled": False,\n'
                '        "owner": "deletion-control-owner",'
            ),
            "ethics-lifecycle-policy-invariant",
        )

    def test_sustain_harnesses_are_bounded_offline_and_auditable(
        self,
    ) -> None:
        for lesson_id, (marker, expected_kind) in SUSTAIN_HARNESSES.items():
            with self.subTest(lesson_id=lesson_id):
                report = self.run_python_harness(lesson_id, marker)
                self.assertEqual(report["harness"], marker)
                self.assert_sustain_harness_contract(
                    report,
                    lesson_id,
                    expected_kind,
                )

    def test_legacy_harness_maps_change_before_editing(self) -> None:
        lesson_id = "core-21-maintenance-legacy-comprehension"
        report = self.run_python_harness(
            lesson_id,
            "legacy_comprehension_lab_v1",
        )

        system_map = report["system_map"]
        analysis = report["change_analysis"]
        self.assertEqual(
            system_map["execution_path"],
            analysis["affected_path"],
        )
        self.assertEqual(
            system_map["change_reason"],
            analysis["change_request"],
        )
        self.assertGreaterEqual(len(system_map["unknowns"]), 1)
        self.assertGreaterEqual(len(report["characterization_tests"]), 2)
        for test in report["characterization_tests"]:
            self.assertEqual(test["actual"], test["expected"])
            self.assertTrue(test["passed"])
            self.assertTrue(test["observed_path"])
        transfer = report["change_request_transfer"]
        self.assertEqual(transfer["changed_assumption"], "change-request")
        self.assertEqual(transfer["changed_fields"], ["change_request"])
        self.assertTrue(transfer["same_legacy_fixture"])
        self.assertEqual(
            transfer["baseline_fixture_snapshot"],
            transfer["transferred_fixture_snapshot"],
        )
        self.assertNotEqual(
            transfer["baseline_affected_path"],
            transfer["transferred_affected_path"],
        )
        self.assertNotEqual(
            transfer["baseline_characterization_tests"],
            transfer["transferred_characterization_tests"],
        )

    def test_legacy_harness_rejects_affected_path_bypass(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-21-maintenance-legacy-comprehension",
            "legacy_comprehension_lab_v1",
            "affected_path = trace_execution(fixture, change_request)",
            "affected_path = []",
            "maintenance-comprehension-invariant",
        )

    def test_legacy_harness_rejects_transfer_fixture_drift(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-21-maintenance-legacy-comprehension",
            "legacy_comprehension_lab_v1",
            "transferred_fixture = fixed_legacy_fixture()",
            (
                "transferred_fixture = fixed_legacy_fixture()\n"
                '    transferred_fixture["entry_point"] = "drifted-entry"'
            ),
            "maintenance-comprehension-invariant",
        )

    def test_legacy_harness_rejects_invalid_nested_fixture_schema(
        self,
    ) -> None:
        cases = (
            (
                '    "fixture_id": "legacy-invoice-v1",',
                (
                    '    "fixture_id": "legacy-invoice-v1",\n'
                    '    "unreviewed_owner": "nobody",'
                ),
            ),
            (
                '            "owner": "billing-intake",',
                (
                    '            "owner": "billing-intake",\n'
                    '            "unreviewed_side_effect": True,'
                ),
            ),
            (
                (
                    '            "tax_basis_points": 0,\n'
                    '            "tax_rounding_increment": 1,\n'
                    '            "observed_output_cents": 9000,'
                ),
                (
                    '            "tax_basis_points": 0,\n'
                    '            "observed_output_cents": 9000,'
                ),
            ),
            (
                (
                    '            "change_requests": ['
                    '"discount-rate-change", "tax-rounding-change"],'
                ),
                '            "change_requests": "discount-rate-change",',
            ),
            (
                '            "id": "lookup-discount",',
                '            "id": "receive-invoice",',
            ),
        )
        for original, replacement in cases:
            with self.subTest(replacement=replacement):
                self.assert_causal_harness_source_mutation_fails(
                    "core-21-maintenance-legacy-comprehension",
                    "legacy_comprehension_lab_v1",
                    original,
                    replacement,
                    "maintenance-comprehension-invariant",
                )

    def test_legacy_harness_rejects_invalid_change_schema(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-21-maintenance-legacy-comprehension",
            "legacy_comprehension_lab_v1",
            (
                "BASELINE_CHANGE = {\n"
                '    "change_request": "discount-rate-change",\n'
                "}"
            ),
            "BASELINE_CHANGE = {}",
            "maintenance-comprehension-invariant",
        )

    def test_legacy_harness_rejects_characterization_behavior_drift(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-21-maintenance-legacy-comprehension",
            "legacy_comprehension_lab_v1",
            "return discounted + rounded_tax",
            "return discounted + rounded_tax + 1",
            "maintenance-comprehension-invariant",
        )

    def test_legacy_harness_rejects_detached_fixture_path(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-21-maintenance-legacy-comprehension",
            "legacy_comprehension_lab_v1",
            (
                "baseline = analyze_change(\n"
                "        baseline_fixture,\n"
                '        BASELINE_CHANGE["change_request"],\n'
                "    )"
            ),
            (
                "baseline_fixture[\"stages\"] = [\n"
                '        {**stage, "change_requests": []}\n'
                '        for stage in baseline_fixture["stages"]\n'
                "    ]\n"
                "    baseline = analyze_change(\n"
                "        baseline_fixture,\n"
                '        BASELINE_CHANGE["change_request"],\n'
                "    )"
            ),
            "maintenance-comprehension-invariant",
        )

    def test_migration_harness_models_expand_contract_state_machine(
        self,
    ) -> None:
        lesson_id = "core-22-evolution-safe-migrations"
        report = self.run_python_harness(
            lesson_id,
            "migration_state_machine_lab_v1",
        )

        phases = report["migration_plan"]["phases"]
        self.assertEqual(
            [phase["name"] for phase in phases],
            ["expand", "dual-write", "backfill", "dual-read", "contract"],
        )
        for phase in phases:
            self.assertTrue(phase["compatibility"])
            self.assertTrue(phase["observation"])
            self.assertTrue(phase["stop_condition"])
            self.assertTrue(phase["rollback"])
        self.assertTrue(report["compatibility"]["old_reader_supported"])
        self.assertTrue(report["compatibility"]["new_reader_supported"])
        self.assertTrue(report["compatibility"]["dual_write_verified"])
        transfer = report["backfill_error_rate_transfer"]
        self.assertEqual(
            transfer["changed_assumption"],
            "backfill-error-rate",
        )
        self.assertEqual(
            transfer["changed_fields"],
            ["backfill_error_rate"],
        )
        self.assertTrue(transfer["same_migration_plan"])
        self.assertEqual(
            transfer["baseline_plan"],
            transfer["transferred_plan"],
        )
        self.assertEqual(transfer["baseline_decision"], "continue")
        self.assertEqual(transfer["transferred_decision"], "rollback")
        rollback = transfer["rollback_outcome"]
        self.assertTrue(rollback["executed"])
        self.assertTrue(rollback["observed"])
        self.assertTrue(rollback["system_outcome"])
        self.assertTrue(
            report["command_success_distinction"]["system_outcome_checked"],
        )

    def test_migration_harness_rejects_stop_decision_bypass(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-22-evolution-safe-migrations",
            "migration_state_machine_lab_v1",
            "decision = decide_migration(observation, thresholds)",
            'decision = "continue"',
            "migration-causal-invariant",
        )

    def test_migration_harness_rejects_unknown_transfer_field(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-22-evolution-safe-migrations",
            "migration_state_machine_lab_v1",
            '"backfill_errors": 20,',
            (
                '"backfill_errors": 20,\n'
                '    "unreviewed_reader_errors": 1,'
            ),
            "migration-transfer-invariant",
        )

    def test_migration_harness_rejects_missing_transfer_field(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-22-evolution-safe-migrations",
            "migration_state_machine_lab_v1",
            (
                '    "dual_write_attempts": 200,\n'
                '    "backfill_rows": 500,\n'
                '    "backfill_errors": 20,'
            ),
            (
                '    "dual_write_attempts": 200,\n'
                '    "backfill_errors": 20,'
            ),
            "migration-transfer-invariant",
        )

    def test_migration_harness_rejects_invalid_transfer_schema(
        self,
    ) -> None:
        cases = (
            (
                '"backfill_errors": 20,',
                '"backfill_errors": "20",',
            ),
            (
                (
                    "TRANSFER_OBSERVATION = {\n"
                    '    "old_reader_successes": 200,'
                ),
                (
                    "TRANSFER_OBSERVATION = {\n"
                    '    "old_reader_successes": 199,'
                ),
            ),
        )
        for original, replacement in cases:
            with self.subTest(replacement=replacement):
                self.assert_causal_harness_source_mutation_fails(
                    "core-22-evolution-safe-migrations",
                    "migration_state_machine_lab_v1",
                    original,
                    replacement,
                    "migration-transfer-invariant",
                )

    def test_migration_harness_rejects_noncanonical_phase_sequence(
        self,
    ) -> None:
        cases = (
            (
                "]\nTHRESHOLDS = {",
                "]\nPHASE_INPUTS.reverse()\nTHRESHOLDS = {",
            ),
            (
                '        "name": "dual-write",',
                '        "name": "expand",',
            ),
        )
        for original, replacement in cases:
            with self.subTest(replacement=replacement):
                self.assert_causal_harness_source_mutation_fails(
                    "core-22-evolution-safe-migrations",
                    "migration_state_machine_lab_v1",
                    original,
                    replacement,
                    "migration-plan-invariant",
                )

    def test_migration_harness_rejects_plan_snapshot_drift(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-22-evolution-safe-migrations",
            "migration_state_machine_lab_v1",
            "phases = build_phases(PHASE_INPUTS)",
            (
                "phases = build_phases(PHASE_INPUTS)\n"
                '    phases[0]["rollback"] = "drifted rollback"'
            ),
            "migration-plan-invariant",
        )

    def test_migration_harness_rejects_unobserved_rollback_outcome(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-22-evolution-safe-migrations",
            "migration_state_machine_lab_v1",
            '"observed": True,',
            '"observed": False,',
            "migration-rollback-outcome-invariant",
        )

    def test_incident_harness_builds_non_blaming_evidence_review(
        self,
    ) -> None:
        lesson_id = "core-23-incident-response-learning"
        report = self.run_python_harness(
            lesson_id,
            "incident_learning_review_lab_v1",
        )

        timeline = report["evidence_timeline"]
        self.assertEqual(
            [event["minute"] for event in timeline],
            sorted(event["minute"] for event in timeline),
        )
        evidence_ids = {event["evidence_id"] for event in timeline}
        self.assertGreater(report["impact"]["duration_minutes"], 0)
        self.assertGreater(report["impact"]["affected_requests"], 0)
        for decision in report["decisions"]:
            self.assertLessEqual(set(decision["evidence_ids"]), evidence_ids)
        self.assertGreaterEqual(len(report["contributing_factors"]), 2)
        self.assertTrue(
            all(
                factor["system_condition"]
                and not factor["individual_blame"]
                for factor in report["contributing_factors"]
            ),
        )
        for action in report["verifiable_actions"]:
            self.assertTrue(action["owner"])
            self.assertTrue(action["due"])
            self.assertTrue(action["verification"])
            self.assertLessEqual(set(action["evidence_ids"]), evidence_ids)
        transfer = report["detection_delay_transfer"]
        self.assertEqual(transfer["changed_assumption"], "detection-delay")
        self.assertEqual(transfer["changed_fields"], ["detection_minute"])
        self.assertTrue(transfer["same_incident_evidence"])
        self.assertEqual(
            transfer["baseline_incident_evidence"],
            transfer["transferred_incident_evidence"],
        )
        self.assertGreater(
            transfer["transferred_detection_minute"],
            transfer["baseline_detection_minute"],
        )
        self.assertGreater(
            transfer["transferred_impact_minutes"],
            transfer["baseline_impact_minutes"],
        )
        for action in report["verifiable_actions"]:
            verification = action["verification_result"]
            self.assertTrue(verification["observed"])
            self.assertTrue(verification["system_outcome"])

    def test_incident_harness_rejects_impact_derivation_bypass(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-23-incident-response-learning",
            "incident_learning_review_lab_v1",
            (
                "impact_minutes = "
                "detection_minute - incident_start_minute"
            ),
            "impact_minutes = recovery_minute",
            "incident-causal-invariant",
        )

    def test_incident_harness_rejects_transfer_evidence_drift(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-23-incident-response-learning",
            "incident_learning_review_lab_v1",
            "transferred_evidence = fixed_incident_evidence()",
            (
                "transferred_evidence = fixed_incident_evidence()\n"
                '    transferred_evidence["timeline"] = []'
            ),
            "incident-transfer-invariant",
        )

    def test_incident_harness_rejects_unobserved_action_outcome(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-23-incident-response-learning",
            "incident_learning_review_lab_v1",
            '"observed": True,',
            '"observed": False,',
            "incident-action-outcome-invariant",
        )

    def test_incident_harness_rejects_future_decision_evidence(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-23-incident-response-learning",
            "incident_learning_review_lab_v1",
            '"evidence_ids": ["ev-saturation"],',
            '"evidence_ids": ["ev-saturation", "ev-recovery"],',
            "incident-decision-evidence-invariant",
        )

    def test_incident_harness_rejects_unknown_transfer_assumption(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-23-incident-response-learning",
            "incident_learning_review_lab_v1",
            '"detection_minute": 18,',
            (
                '"detection_minute": 18,\n'
                '    "unreviewed_signal_delay": 2,'
            ),
            "incident-transfer-invariant",
        )

    def test_incident_harness_rejects_missing_transfer_assumption(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-23-incident-response-learning",
            "incident_learning_review_lab_v1",
            (
                "TRANSFER_ASSUMPTION = {\n"
                '    "detection_minute": 18,\n'
                "}"
            ),
            "TRANSFER_ASSUMPTION = {}",
            "incident-transfer-invariant",
        )

    def test_incident_harness_rejects_invalid_transfer_schema(
        self,
    ) -> None:
        cases = (
            (
                '"detection_minute": 18,',
                '"detection_minute": "18",',
            ),
            (
                '"detection_minute": 18,',
                (
                    '"detection_minute": 18,\n'
                    '    "unreviewed_clock_skew": 1,'
                ),
            ),
        )
        for original, replacement in cases:
            with self.subTest(replacement=replacement):
                self.assert_causal_harness_source_mutation_fails(
                    "core-23-incident-response-learning",
                    "incident_learning_review_lab_v1",
                    original,
                    replacement,
                    "incident-transfer-invariant",
                )

    def test_incident_harness_rejects_invalid_impact_schema(
        self,
    ) -> None:
        cases = (
            (
                '    "affected_requests_per_minute": 24,',
                (
                    '    "affected_requests_per_minute": 24,\n'
                    '    "unreviewed_impact_weight": 2,'
                ),
            ),
            (
                (
                    '    "recovery_minute": 48,\n'
                    '    "affected_requests_per_minute": 24,'
                ),
                '    "recovery_minute": 48,',
            ),
            (
                '    "affected_requests_per_minute": 24,',
                '    "affected_requests_per_minute": True,',
            ),
            (
                '    "affected_requests_per_minute": 24,',
                '    "affected_requests_per_minute": -1,',
            ),
        )
        for original, replacement in cases:
            with self.subTest(replacement=replacement):
                self.assert_causal_harness_source_mutation_fails(
                    "core-23-incident-response-learning",
                    "incident_learning_review_lab_v1",
                    original,
                    replacement,
                    "incident-causal-invariant",
                )

    def test_incident_harness_rejects_duplicate_evidence_ids(
        self,
    ) -> None:
        cases = (
            (
                '        "evidence_id": "ev-mitigation",',
                '        "evidence_id": "ev-recovery",',
                "incident-evidence-invariant",
            ),
            (
                '        "factor_id": "factor-change-guard",',
                '        "factor_id": "factor-alert-routing",',
                "incident-causal-invariant",
            ),
            (
                '        "action_id": "action-canary-pool",',
                '        "action_id": "action-route-alert",',
                "incident-action-outcome-invariant",
            ),
        )
        for original, replacement, diagnostic in cases:
            with self.subTest(replacement=replacement):
                self.assert_causal_harness_source_mutation_fails(
                    "core-23-incident-response-learning",
                    "incident_learning_review_lab_v1",
                    original,
                    replacement,
                    diagnostic,
                )

    def test_delivery_harness_fails_closed_and_verifies_provenance(
        self,
    ) -> None:
        lesson_id = "core-24-delivery-ci-release-safety"
        report = self.run_python_harness(
            lesson_id,
            "delivery_safety_lab_v1",
        )

        self.assertEqual(report["ci"]["failure_policy"], "fail-closed")
        self.assertTrue(report["ci"]["all_required_checks_observed"])
        self.assertEqual(
            set(report["dora_five_metrics"]),
            {
                "change_lead_time",
                "deployment_frequency",
                "failed_deployment_recovery_time",
                "change_fail_rate",
                "deployment_rework_rate",
            },
        )
        provenance = report["provenance_verification"]
        self.assertTrue(provenance["present"])
        self.assertTrue(provenance["subject_digest_matches"])
        self.assertTrue(provenance["builder_trusted"])
        self.assertTrue(provenance["verified"])
        self.assertFalse(provenance["presence_alone_is_trusted"])
        self.assertEqual(
            report["staged_delivery"]["decision"],
            "advance",
        )
        rollback = report["rollback_outcome"]
        self.assertTrue(rollback["executed"])
        self.assertTrue(rollback["system_outcome_verified"])
        self.assertTrue(rollback["service_restored"])
        transfer = report["canary_error_rate_transfer"]
        self.assertEqual(transfer["changed_assumption"], "canary-error-rate")
        self.assertEqual(transfer["changed_fields"], ["canary_error_rate"])
        self.assertTrue(transfer["same_artifact"])
        self.assertTrue(transfer["same_provenance"])
        self.assertEqual(
            transfer["baseline_artifact_digest"],
            transfer["transferred_artifact_digest"],
        )
        self.assertEqual(
            transfer["baseline_provenance"],
            transfer["transferred_provenance"],
        )
        self.assertEqual(transfer["baseline_decision"], "advance")
        self.assertEqual(transfer["transferred_decision"], "rollback")

    def test_delivery_harness_rejects_provenance_presence_bypass(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-24-delivery-ci-release-safety",
            "delivery_safety_lab_v1",
            (
                "provenance_verified = "
                "verify_provenance(PROVENANCE, artifact_digest)"
            ),
            "provenance_verified = bool(PROVENANCE)",
            "delivery-provenance-invariant",
        )

    def test_delivery_harness_rejects_transfer_artifact_drift(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-24-delivery-ci-release-safety",
            "delivery_safety_lab_v1",
            (
                "transferred_delivery_inputs = {\n"
                '        "artifact_bytes": ARTIFACT_BYTES,'
            ),
            (
                "transferred_delivery_inputs = {\n"
                '        "artifact_bytes": ARTIFACT_BYTES + "-drift",'
            ),
            "delivery-transfer-invariant",
        )

    def test_delivery_harness_rejects_unknown_canary_transfer_field(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-24-delivery-ci-release-safety",
            "delivery_safety_lab_v1",
            '"canary_error_rate": 0.05,',
            (
                '"canary_error_rate": 0.05,\n'
                '    "unreviewed_latency_seconds": 3,'
            ),
            "delivery-transfer-invariant",
        )

    def test_delivery_harness_rejects_unknown_top_level_transfer_field(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-24-delivery-ci-release-safety",
            "delivery_safety_lab_v1",
            (
                "transferred_delivery_inputs = {\n"
                '        "artifact_bytes": ARTIFACT_BYTES,\n'
                '        "provenance": dict(PROVENANCE),\n'
                '        "canary": dict(TRANSFER_CANARY),\n'
                "    }"
            ),
            (
                "transferred_delivery_inputs = {\n"
                '        "artifact_bytes": ARTIFACT_BYTES,\n'
                '        "provenance": dict(PROVENANCE),\n'
                '        "canary": dict(TRANSFER_CANARY),\n'
                '        "unreviewed_rollout_window": 30,\n'
                "    }"
            ),
            "delivery-transfer-invariant",
        )

    def test_delivery_harness_rejects_invalid_transfer_schema(
        self,
    ) -> None:
        cases = (
            (
                (
                    "transferred_delivery_inputs = {\n"
                    '        "artifact_bytes": ARTIFACT_BYTES,\n'
                    '        "provenance": dict(PROVENANCE),'
                ),
                (
                    "transferred_delivery_inputs = {\n"
                    '        "provenance": dict(PROVENANCE),'
                ),
            ),
            (
                '"canary_error_rate": 0.05,',
                '"canary_error_rate": "degraded",',
            ),
            (
                (
                    '        "provenance": dict(PROVENANCE),\n'
                    '        "canary": dict(TRANSFER_CANARY),'
                ),
                (
                    '        "provenance": {\n'
                    '            **PROVENANCE,\n'
                    '            "unreviewed_attestation": True,\n'
                    "        },\n"
                    '        "canary": dict(TRANSFER_CANARY),'
                ),
            ),
            (
                (
                    "TRANSFER_CANARY = {\n"
                    '    "canary_error_rate": 0.05,\n'
                    '    "maximum_error_rate": 0.02,\n'
                    "}"
                ),
                (
                    "TRANSFER_CANARY = {\n"
                    '    "canary_error_rate": 0.05,\n'
                    '    "maximum_error_rate": 0.10,\n'
                    "}"
                ),
            ),
        )
        for original, replacement in cases:
            with self.subTest(replacement=replacement):
                self.assert_causal_harness_source_mutation_fails(
                    "core-24-delivery-ci-release-safety",
                    "delivery_safety_lab_v1",
                    original,
                    replacement,
                    "delivery-transfer-invariant",
                )

    def test_delivery_harness_rejects_invalid_raw_input_collections(
        self,
    ) -> None:
        cases = (
            (
                'ARTIFACT_BYTES = "curriculum-release-24"',
                "ARTIFACT_BYTES = []",
            ),
            (
                (
                    "BASELINE_CANARY = {\n"
                    '    "canary_error_rate": 0.01,\n'
                    '    "maximum_error_rate": 0.02,\n'
                    "}\n"
                    "TRANSFER_CANARY = {"
                ),
                (
                    "BASELINE_CANARY = {\n"
                    '    "canary_error_rate": 0.01,\n'
                    '    "maximum_error_rate": 0.02,\n'
                    "}\n"
                    "BASELINE_CANARY = []\n"
                    "TRANSFER_CANARY = {"
                ),
            ),
            (
                (
                    'TRUSTED_BUILDERS = ["builder://curriculum/release"]'
                ),
                "TRUSTED_BUILDERS = []",
            ),
        )
        for original, replacement in cases:
            with self.subTest(replacement=replacement):
                self.assert_causal_harness_source_mutation_fails(
                    "core-24-delivery-ci-release-safety",
                    "delivery_safety_lab_v1",
                    original,
                    replacement,
                    "delivery-input-invariant",
                )

    def test_economics_harness_compares_input_derived_investments(
        self,
    ) -> None:
        lesson_id = "core-25-engineering-economics-capacity"
        report = self.run_python_harness(
            lesson_id,
            "engineering_economics_lab_v1",
        )

        comparisons = report["investment_comparison"]
        self.assertGreaterEqual(len(comparisons), 2)
        for option in comparisons:
            expected_total = (
                option["direct_cost"]
                + option["opportunity_cost"]
                + option["operations_cost"]
                + option["reliability_cost"]
            )
            self.assertEqual(option["total_cost"], expected_total)
            self.assertEqual(
                option["unit_cost"],
                option["total_cost"] / option["served_units"],
            )
            self.assertEqual(
                option["capacity_headroom"],
                option["capacity"] - option["required_capacity"],
            )
            self.assertGreaterEqual(option["operations_hours"], 0)
        selected = min(
            comparisons,
            key=lambda option: (
                option["constraint_breaches"],
                option["unit_cost"],
            ),
        )
        self.assertEqual(report["decision"]["selected_option"], selected["id"])
        self.assertFalse(report["price_claim"]["current_price_claimed"])
        self.assertTrue(report["price_claim"]["fixture_only"])
        self.assertTrue(report["price_claim"]["accuracy_limitation"])
        transfer = report["demand_growth_transfer"]
        self.assertEqual(transfer["changed_assumption"], "demand-growth")
        self.assertEqual(transfer["changed_fields"], ["demand_growth"])
        baseline_assumptions = transfer["baseline_assumptions"]
        transferred_assumptions = transfer["transferred_assumptions"]
        self.assertEqual(
            [
                field
                for field in sorted(baseline_assumptions)
                if baseline_assumptions[field]
                != transferred_assumptions[field]
            ],
            ["demand_growth"],
        )
        self.assertTrue(transfer["same_investment_candidates"])
        self.assertEqual(
            transfer["baseline_candidate_snapshot"],
            transfer["transferred_candidate_snapshot"],
        )
        self.assertNotEqual(
            transfer["baseline_selected_option"],
            transfer["transferred_selected_option"],
        )
        self.assertTrue(transfer["sensitivity_recomputed"])

    def test_economics_harness_rejects_total_cost_bypass(self) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-25-engineering-economics-capacity",
            "engineering_economics_lab_v1",
            (
                "total_cost = direct_cost + opportunity_cost + "
                "operations_cost + reliability_cost"
            ),
            "total_cost = direct_cost",
            "economics-causal-invariant",
        )

    def test_economics_harness_rejects_multi_assumption_transfer(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-25-engineering-economics-capacity",
            "engineering_economics_lab_v1",
            (
                '    "demand_growth": 0.5,\n'
                "}"
            ),
            (
                '    "demand_growth": 0.5,\n'
                '    "operations_hour_cost": 1,\n'
                "}"
            ),
            "economics-transfer-invariant",
        )

    def test_economics_harness_rejects_candidate_snapshot_drift(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-25-engineering-economics-capacity",
            "engineering_economics_lab_v1",
            (
                "baseline = compare_all(\n"
                "        baseline_candidates,\n"
                "        baseline_assumptions,\n"
                "    )"
            ),
            (
                "baseline = compare_all(\n"
                "        baseline_candidates,\n"
                "        baseline_assumptions,\n"
                "    )\n"
                '    transferred_candidates[0]["direct_cost"] += 1'
            ),
            "economics-candidate-invariant",
        )

    def test_economics_harness_rejects_missing_transfer_assumption(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-25-engineering-economics-capacity",
            "engineering_economics_lab_v1",
            (
                '    "demand_growth": 0.5,\n'
                "}"
            ),
            (
                '    "demand_growth": 0.5,\n'
                "}\n"
                'TRANSFER_ASSUMPTIONS.pop("operations_hour_cost")'
            ),
            "economics-transfer-invariant",
        )

    def test_economics_harness_rejects_invalid_transfer_schema(
        self,
    ) -> None:
        cases = (
            (
                '"demand_growth": 0.5,',
                '"demand_growth": "high",',
            ),
            (
                '"demand_growth": 0.5,',
                (
                    '"demand_growth": 0.5,\n'
                    '    "unreviewed_financing_rate": 0.1,'
                ),
            ),
        )
        for original, replacement in cases:
            with self.subTest(replacement=replacement):
                self.assert_causal_harness_source_mutation_fails(
                    "core-25-engineering-economics-capacity",
                    "engineering_economics_lab_v1",
                    original,
                    replacement,
                    "economics-transfer-invariant",
                )

    def test_economics_harness_rejects_invalid_candidate_schema(
        self,
    ) -> None:
        cases = (
            (
                '        "direct_cost": 12000,',
                (
                    '        "direct_cost": 12000,\n'
                    '        "unreviewed_vendor_score": 5,'
                ),
            ),
            (
                (
                    '        "id": "scale-up",\n'
                    '        "direct_cost": 12000,'
                ),
                '        "id": "scale-up",',
            ),
            (
                '        "direct_cost": 12000,',
                '        "direct_cost": "12000",',
            ),
        )
        for original, replacement in cases:
            with self.subTest(replacement=replacement):
                self.assert_causal_harness_source_mutation_fails(
                    "core-25-engineering-economics-capacity",
                    "engineering_economics_lab_v1",
                    original,
                    replacement,
                    "economics-candidate-invariant",
                )

    def test_economics_harness_rejects_invalid_raw_assumptions(
        self,
    ) -> None:
        self.assert_causal_harness_source_mutation_fails(
            "core-25-engineering-economics-capacity",
            "engineering_economics_lab_v1",
            (
                "BASELINE_ASSUMPTIONS = {\n"
                '    "demand_growth": 0.0,\n'
                '    "engineering_hour_value": 100,\n'
                '    "operations_hour_cost": 80,\n'
                '    "loss_per_incident_hour": 10000,\n'
                "}\n"
                "TRANSFER_ASSUMPTIONS = {"
            ),
            (
                "BASELINE_ASSUMPTIONS = {\n"
                '    "demand_growth": 0.0,\n'
                '    "engineering_hour_value": 100,\n'
                '    "operations_hour_cost": 80,\n'
                '    "loss_per_incident_hour": 10000,\n'
                "}\n"
                "BASELINE_ASSUMPTIONS = []\n"
                "TRANSFER_ASSUMPTIONS = {"
            ),
            "economics-transfer-invariant",
        )

    def test_sustain_harnesses_defer_raw_derivation_until_main(
        self,
    ) -> None:
        contracts = {
            "core-24-delivery-ci-release-safety": (
                "delivery_safety_lab_v1",
                (
                    "**BASELINE_CANARY",
                    'TRANSFER_CANARY["',
                    'BASELINE_CANARY["',
                    "ARTIFACT_BYTES.encode",
                    "TRUSTED_BUILDERS[0]",
                ),
            ),
            "core-25-engineering-economics-capacity": (
                "engineering_economics_lab_v1",
                ("**BASELINE_ASSUMPTIONS",),
            ),
        }
        for lesson_id, (marker, forbidden) in contracts.items():
            with self.subTest(lesson_id=lesson_id):
                source = self.python_harness_source(lesson_id, marker)
                before_main, separator, _ = source.partition("def main():")
                self.assertTrue(separator)
                for expression in forbidden:
                    self.assertNotIn(expression, before_main)
