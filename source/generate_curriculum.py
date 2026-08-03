from __future__ import annotations

import html
import json
import os
import re
import shutil
import textwrap
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from knowledge import MODULE_PRIMERS, CONCEPT_NOTES, DOMAIN_RESOURCES

OUT = Path('/mnt/data/engineering-expert-curriculum')
ZIP_PATH = Path('/mnt/data/engineering-expert-curriculum.zip')

@dataclass
class Module:
    title: str
    concepts: list[str]
    outcome: str

@dataclass
class Domain:
    id: int
    slug: str
    title: str
    family: str
    description: str
    prerequisites: list[int]
    modules: list[Module]


def M(title: str, concepts: str, outcome: str) -> Module:
    return Module(title, [x.strip() for x in concepts.split('|')], outcome)


domains: list[Domain] = [
    Domain(1, 'math-statistics', '数学・統計', 'theory',
           'エンジニアリングで必要になる離散数学、確率、統計、線形代数、最適化、情報理論を、式の暗記ではなくモデル化と意思決定の道具として学ぶ。', [], [
        M('離散数学と論理', '集合・写像・関係|命題と述語|量化記号|数学的帰納法', '仕様、データ構造、アルゴリズムを形式的に表現できる'),
        M('組合せ論と数え上げ', '順列と組合せ|包除原理|鳩の巣原理|生成関数', '状態数や探索空間を見積もり、計算量の直感を持てる'),
        M('確率の基礎', '標本空間と事象|条件付き確率|ベイズの定理|独立性', '不確実性を定量化し、観測から仮説を更新できる'),
        M('確率分布', 'ベルヌーイ・二項分布|ポアソン分布|正規分布|期待値と分散', '現象に合う分布を選び、指標の意味を説明できる'),
        M('統計的推定', '標本と母集団|点推定と区間推定|最尤推定|バイアスと分散', 'データから母集団を推測する際の不確実性を扱える'),
        M('仮説検定と実験', '帰無仮説|p値と有意水準|検出力|多重検定', 'A/Bテストを誤解なく設計・解釈できる'),
        M('線形代数', 'ベクトルと行列|線形写像|固有値と固有ベクトル|特異値分解', 'ML、グラフィクス、最適化の基礎計算を理解できる'),
        M('微積分と最適化', '微分と勾配|連鎖律|多変数最適化|制約付き最適化', '損失関数や性能関数の最適化を説明できる'),
        M('情報理論', 'エントロピー|相互情報量|KLダイバージェンス|符号化と圧縮', '情報量、圧縮、学習目標の関係を説明できる'),
        M('時系列と意思決定', '自己相関|移動平均|ベイズ意思決定|モンテカルロ法', '時間変化するデータを扱い、リスク下で意思決定できる'),
    ]),
    Domain(2, 'data-structures-algorithms', 'データ構造・アルゴリズム', 'theory',
           '性能と正しさを両立するために、データ構造、探索、ソート、グラフ、動的計画法、近似を実装と証明の両面から学ぶ。', [1], [
        M('計算量と漸近解析', 'Big O・Theta・Omega|最悪・平均・償却計算量|再帰式|実測と理論値', '処理量の増加に対する性能変化を説明できる'),
        M('配列・連結リスト・スタック・キュー', '連続メモリ|ポインタ構造|LIFO・FIFO|リングバッファ', '用途に応じて基本構造を選択し実装できる'),
        M('ハッシュテーブル', 'ハッシュ関数|衝突解決|負荷率|一貫性ハッシュ', '平均O(1)の条件と破綻条件を理解できる'),
        M('木構造', '二分探索木|平衡木|B木・B+木|Trie', '検索・索引・階層表現に適切な木を選べる'),
        M('ヒープと優先度付きキュー', '二分ヒープ|ヒープ化|Top-K|スケジューリング', '優先順位処理やストリーム集計を効率化できる'),
        M('ソートと選択', '比較ソート|安定性|クイックソート|線形時間選択', 'データ特性に応じたソート戦略を選べる'),
        M('グラフアルゴリズム', 'BFS・DFS|最短経路|最小全域木|トポロジカルソート', '依存関係、経路、ネットワーク問題をモデル化できる'),
        M('動的計画法と貪欲法', '最適部分構造|重複部分問題|状態設計|貪欲選択性', '最適化問題を状態遷移へ落とし込める'),
        M('文字列アルゴリズム', 'KMP|Rabin-Karp|Suffix Array|編集距離', '検索、差分、自然言語処理の基礎を実装できる'),
        M('高度なアルゴリズム設計', '分割統治|ランダム化|近似アルゴリズム|オンラインアルゴリズム', '厳密解が難しい問題に現実的な解法を設計できる'),
    ]),
    Domain(3, 'computation-complexity', '計算理論・計算量理論', 'theory',
           '何が計算でき、どの程度の資源が必要で、どこからが現実的に難しいのかを理解する。', [1, 2], [
        M('形式言語とオートマトン', 'アルファベットと文字列|正規言語|有限オートマトン|正規表現', 'パターン認識と言語処理の限界を説明できる'),
        M('文脈自由文法', '生成規則|プッシュダウンオートマトン|構文木|曖昧文法', 'プログラミング言語の構文を形式化できる'),
        M('チューリング機械', 'テープと遷移|万能機械|停止問題|計算可能性', 'アルゴリズムという概念の理論的境界を理解できる'),
        M('決定可能性と帰着', '判定問題|写像帰着|Riceの定理|半決定可能性', '問題間の難しさを比較し、不可能性を証明できる'),
        M('計算量クラス', 'P|NP|co-NP|PSPACE', '計算資源による問題分類を説明できる'),
        M('NP完全性', 'SAT|Cook-Levin|多項式時間帰着|代表的NP完全問題', '新しい問題の難しさを既知問題との帰着で示せる'),
        M('近似可能性', '近似比|PTAS・FPTAS|APX|近似困難性', '厳密解と近似解の境界を判断できる'),
        M('パラメータ化計算量', '固定パラメータ tractable|kernelization|木幅|探索木', '入力全体ではなく難しさのパラメータに注目できる'),
        M('確率的計算', '乱択アルゴリズム|Monte Carlo|Las Vegas|BPP', '確率を使う計算の保証を理解できる'),
        M('量子計算の理論基礎', '量子ビット|重ね合わせ|量子回路|BQP', '量子計算が高速化し得る範囲を誇張なく説明できる'),
    ]),
    Domain(4, 'formal-methods-logic', '形式手法・論理学', 'theory',
           '仕様の曖昧さを減らし、システムの安全性・活性・不変条件をモデルと証明で扱う。', [1, 3], [
        M('命題論理と述語論理', '構文と意味論|健全性と完全性|自然演繹|充足可能性', '仕様や証明を論理式として扱える'),
        M('集合・関係・代数的仕様', '関係代数|同値関係|順序|代数的データ型', '状態と操作を数学的に定義できる'),
        M('状態機械', '状態・遷移・イベント|決定性|不変条件|状態爆発', '業務フローやプロトコルを状態機械で表現できる'),
        M('時相論理', 'LTL|CTL|安全性|活性', '時間に関する要件を形式化できる'),
        M('モデル検査', '状態空間探索|反例|抽象化|部分順序削減', '小さなモデルから設計バグを機械的に見つけられる'),
        M('定理証明', '公理と補題|帰納証明|Coq・Leanの考え方|証明オブジェクト', 'コードや仕様の性質を厳密に示せる'),
        M('契約による設計', '事前条件|事後条件|不変条件|責務分担', 'API境界の期待を実行可能な契約にできる'),
        M('型による検証', '精緻化型|依存型|ファントム型|型状態', '不正状態を型で表現不能にする設計ができる'),
        M('分散システムの形式化', 'TLA+|PlusCal|公平性|線形化可能性', '並行・分散アルゴリズムをモデル検査できる'),
        M('形式手法の実務導入', '対象選定|抽象化境界|レビュー運用|コスト対効果', '重要箇所へ過不足なく形式手法を適用できる'),
    ]),
    Domain(5, 'computer-architecture', 'コンピュータアーキテクチャ', 'systems',
           'CPU、メモリ、キャッシュ、命令、入出力、アクセラレータを理解し、ソフトウェア性能の物理的背景を掴む。', [1, 2], [
        M('デジタル論理と数表現', '論理ゲート|二進数と補数|固定小数点・浮動小数点|誤差とオーバーフロー', '計算が回路上でどのように表現されるか説明できる'),
        M('命令セットアーキテクチャ', '命令形式|レジスタ|RISC・CISC|特権レベル', 'コンパイラとCPUの契約を理解できる'),
        M('CPUパイプライン', 'fetch・decode・execute|ハザード|分岐予測|投機実行', '命令レベル並列性と性能劣化要因を説明できる'),
        M('キャッシュとメモリ階層', '局所性|キャッシュライン|連想度|プリフェッチ', 'データ配置を性能へ結びつけられる'),
        M('仮想記憶ハードウェア', 'ページテーブル|TLB|ページフォルト|巨大ページ', 'OSの仮想メモリとCPU支援の関係を理解できる'),
        M('マルチコアとメモリ一貫性', 'キャッシュコヒーレンス|MESI|メモリ順序|false sharing', '並行コードのハードウェア上の挙動を説明できる'),
        M('I/Oとバス', '割り込み|DMA|PCIe|メモリマップドI/O', 'デバイスとCPU・メモリのデータ経路を理解できる'),
        M('NUMAと大規模サーバ', 'ソケット|ローカル・リモートメモリ|CPU affinity|帯域とレイテンシ', 'サーバ配置とスレッド配置を最適化できる'),
        M('SIMDとベクトル化', 'ベクトル命令|データ並列|自動ベクトル化|アラインメント', '数値処理をCPUの並列機能へ写像できる'),
        M('アクセラレータと異種計算', 'GPU・TPU・NPU|メモリ転送|カーネル|ワークロード適合性', 'CPU以外の計算資源を選定できる'),
    ]),
    Domain(6, 'os-linux-systems', 'OS・Linux・システムプログラミング', 'systems',
           'OSが提供する抽象化とLinuxの実装を理解し、プロセス・メモリ・ファイル・I/O・カーネル境界を操作する。', [5], [
        M('OSの役割とシステムコール', 'ユーザー空間とカーネル空間|割り込みと例外|syscall ABI|保護と抽象化', 'アプリとカーネルの境界を説明できる'),
        M('プロセスとスレッド', 'fork・exec|スケジューラ|コンテキストスイッチ|プロセス状態', '実行単位と資源分離を理解できる'),
        M('仮想メモリ', 'アドレス空間|ページング|copy-on-write|mmap', 'メモリ使用量やページフォルトを診断できる'),
        M('ファイルシステム', 'inode|ディレクトリエントリ|journaling|VFS', 'ファイル操作の永続化と整合性を説明できる'),
        M('Linux I/O', 'blocking・non-blocking|select・poll・epoll|AIO・io_uring|ゼロコピー', '高性能I/O方式を選定できる'),
        M('シグナル・IPC・同期', 'signal|pipe|shared memory|futex', 'プロセス間通信と同期を安全に設計できる'),
        M('Linux管理と観測', 'procfs・sysfs|systemd|namespaces|cgroups', '稼働中システムの状態を確認し制御できる'),
        M('シェルとCLIシステム運用', 'POSIX shell|パイプライン|終了コード|安全なスクリプト', '再現可能な運用コマンドを構築できる'),
        M('カーネルネットワークとストレージ', 'socket buffer|block layer|page cache|writeback', 'アプリ性能をカーネル内部の経路へ関連付けられる'),
        M('システムプログラミング実践', 'C・Rust FFI|ptrace|eBPF|capability', '低レイヤのツールやデーモンを安全に実装できる'),
    ]),
    Domain(7, 'concurrency-parallelism', '並行処理・並列処理', 'systems',
           '複数の仕事を正しく、高速に、観測可能に実行するためのモデル、同期、メモリモデル、分散実行を学ぶ。', [2, 5, 6], [
        M('並行性の基本モデル', '並行と並列|タスクとスレッド|インターリーブ|競合状態', '同時実行バグを正確な語彙で説明できる'),
        M('ロックと同期プリミティブ', 'mutex|semaphore|condition variable|read-write lock', '共有状態を安全に保護できる'),
        M('アトミック操作とメモリモデル', 'compare-and-swap|memory order|happens-before|可視性', 'ロックより低レイヤの正しさを理解できる'),
        M('デッドロック・ライブロック・飢餓', '必要条件|ロック順序|backoff|公平性', '停止しない並行障害を予防・診断できる'),
        M('Lock-free・Wait-free', '進行保証|ABA問題|hazard pointer|epoch reclamation', '高度な非ブロッキング構造の条件を説明できる'),
        M('Actor・CSP・メッセージパッシング', 'mailbox|channel|select|supervision', '共有メモリ以外の並行モデルを設計できる'),
        M('タスクスケジューリング', 'work stealing|thread pool|backpressure|priority inversion', '実行基盤のスループットと公平性を調整できる'),
        M('並列アルゴリズム', 'map-reduce|prefix sum|fork-join|データ分割', '処理を安全に分割して並列化できる'),
        M('非同期I/O', 'callback|future・promise|async・await|structured concurrency', 'I/O待ちを効率化しキャンセルを管理できる'),
        M('並行プログラムの検証とデバッグ', 'race detector|deterministic test|linearizability|trace analysis', '再現しにくいバグを体系的に追跡できる'),
    ]),
    Domain(8, 'pl-type-systems', 'プログラミング言語理論・型システム', 'language',
           '言語機能を表面的な文法ではなく、意味論・型・評価戦略・抽象化の設計として理解する。', [1, 3, 4], [
        M('構文・意味論・評価', '抽象構文|操作的意味論|表示的意味論|評価戦略', 'プログラムがどう意味を持つか形式的に説明できる'),
        M('ラムダ計算', '変数束縛|置換|β簡約|Church encoding', '関数型言語の計算モデルを理解できる'),
        M('静的型付けと動的型付け', '型検査|型安全性|progress・preservation|gradual typing', '型システムの保証と限界を比較できる'),
        M('多相性とGenerics', 'parametric polymorphism|ad-hoc polymorphism|subtyping|variance', '再利用性と型安全性のトレードオフを設計できる'),
        M('型推論', 'unification|Hindley-Milner|制約生成|一般化', '型注釈なしで型が決まる仕組みを説明できる'),
        M('代数的データ型とパターンマッチ', 'sum・product type|再帰型|exhaustiveness|GADT', '状態を型で明確にモデル化できる'),
        M('効果と副作用', '参照透明性|monad|effect system|handler', '副作用を制御する抽象化を比較できる'),
        M('所有権・ライフタイム・線形型', 'move semantics|borrow|affine type|resource safety', 'メモリと資源の安全性を型で表現できる'),
        M('オブジェクト指向の型理論', 'nominal・structural typing|dynamic dispatch|LSP|row polymorphism', 'OOPの設計を型の観点から評価できる'),
        M('言語設計とDSL', 'syntax design|macro|internal・external DSL|interoperability', '目的に合う小さな言語を設計できる'),
    ]),
    Domain(9, 'compiler-interpreter-runtime', 'Compiler・Interpreter・Runtime', 'language',
           'ソースコードが字句解析、構文解析、最適化、コード生成、実行時管理を経て動く全過程を実装目線で学ぶ。', [3, 5, 8], [
        M('コンパイラ全体像', 'front-end・middle-end・back-end|source-to-source|AOT・JIT|toolchain', '翻訳系の構成要素と責務を説明できる'),
        M('字句解析', 'token|正規表現|DFA|lexer generator', '文字列をトークン列へ安全に変換できる'),
        M('構文解析', 'LL・LR|recursive descent|precedence|error recovery', '文法からASTを構築できる'),
        M('AST・意味解析・型検査', 'symbol table|scope|name resolution|type checking', '構文上正しいコードの意味を検証できる'),
        M('中間表現', 'three-address code|SSA|CFG|data-flow', '最適化しやすい表現へ変換できる'),
        M('最適化', 'constant folding|dead code elimination|inlining|loop optimization', '意味を保った性能改善を設計できる'),
        M('コード生成', 'instruction selection|register allocation|calling convention|assembly emission', 'IRを機械語へ落とし込む過程を理解できる'),
        M('InterpreterとVM', 'tree-walk|bytecode|stack VM|dispatch', '小さな言語実行系を実装できる'),
        M('JITとプロファイル誘導最適化', 'hot path|inline cache|deoptimization|tiered compilation', '実行時最適化の速度と複雑性を説明できる'),
        M('Runtime・GC・Linker・Loader', 'heap management|mark-sweep|dynamic linking|ABI', '言語ランタイムとOSの協調を理解できる'),
    ]),
    Domain(10, 'network-protocols', 'ネットワーク・インターネットプロトコル', 'network',
           '物理層からアプリケーション層まで、パケットが届く仕組み、障害、性能、セキュリティを端から端まで理解する。', [5, 6], [
        M('OSI・TCP/IPモデル', '層と責務|encapsulation|PDU|end-to-end principle', '通信問題を適切な層へ切り分けられる'),
        M('Ethernet・ARP・VLAN', 'MAC address|frame|ARP・ND|switching・VLAN', '同一リンク内の配送と分離を説明できる'),
        M('IP・ルーティング', 'IPv4・IPv6|subnet|routing table|ICMP', 'ネットワーク間配送と経路選択を理解できる'),
        M('TCP・UDP', 'three-way handshake|flow・congestion control|retransmission|datagram semantics', '信頼性と遅延のトレードオフを選べる'),
        M('DNS', 'recursive・authoritative|record types|cache・TTL|DNSSEC', '名前解決の経路と障害を診断できる'),
        M('HTTP/1.1', 'request・response|method・status|header・cache|connection reuse', 'Web APIの通信をプロトコルレベルで説明できる'),
        M('HTTP/2・HTTP/3・QUIC', 'multiplexing|HPACK・QPACK|stream|0-RTT', '新しいHTTPの性能特性と注意点を理解できる'),
        M('TLS・PKI', 'handshake|certificate|key exchange|forward secrecy', '暗号化通信の信頼モデルを説明できる'),
        M('Proxy・Load Balancer・CDN', 'forward・reverse proxy|L4・L7|health check|edge cache', 'トラフィック経路を設計・診断できる'),
        M('ネットワーク観測とトラブルシュート', 'tcpdump|Wireshark|traceroute|latency・loss・MTU', 'パケット証拠から障害原因を絞り込める'),
    ]),
    Domain(11, 'typescript-javascript-nodejs', 'TypeScript・JavaScript・Node.js', 'node',
           'ECMAScript、TypeScriptの型システム、V8、libuv、Node.js APIを統合して、正しく高速なサーバとツールを作る。', [6, 7, 8, 9, 10], [
        M('JavaScript言語モデル', 'lexical environment|prototype|this|closure', 'JavaScriptの実行規則を説明できる'),
        M('非同期JavaScript', 'promise|microtask・macrotask|async・await|cancellation', '非同期制御を順序と失敗の両面で設計できる'),
        M('TypeScript型システム', 'structural typing|union・intersection|narrowing|soundness boundary', '業務モデルを型で安全に表現できる'),
        M('高度なTypeScript', 'conditional type|mapped type|infer|template literal type', '再利用可能な型レベルAPIを構築できる'),
        M('Decorator・Metadata・DI', 'decorator semantics|Reflect metadata|inversion of control|container lifetime', 'NestJS等のメタプログラミングを理解できる'),
        M('Node.js Runtime', 'V8|libuv|event loop|thread pool', 'Nodeの性能とブロッキング原因を説明できる'),
        M('Buffer・Stream・Backpressure', 'binary data|Readable・Writable|pipeline|highWaterMark', '大容量データを低メモリで処理できる'),
        M('Module・Package・Toolchain', 'ESM・CommonJS|package exports|npm・pnpm|transpile・bundle', '配布可能なNodeパッケージを設計できる'),
        M('Worker・Process・Native連携', 'worker_threads|child_process|cluster|N-API・WASM', 'CPU負荷やネイティブ処理を分離できる'),
        M('Node.js本番品質', 'diagnostics|AsyncLocalStorage|graceful shutdown|security・performance', '本番サービスを観測・保守・最適化できる'),
    ]),
    Domain(12, 'go', 'Go', 'go',
           'Goの型、メモリ、goroutine、channel、runtime、標準ライブラリを理解し、運用しやすいネットワークサービスを構築する。', [6, 7, 10], [
        M('Go言語基礎と設計哲学', 'package|zero value|explicit error|composition', 'Goらしい単純で読みやすいコードを書ける'),
        M('型・Interface・Generics', 'method set|implicit interface|type parameter|constraint', '抽象化しすぎない再利用設計ができる'),
        M('メモリ・Pointer・Escape Analysis', 'stack・heap|pointer|escape|allocation', '割り当てとGC負荷を意識できる'),
        M('Goroutine・Channel', 'goroutine|unbuffered・buffered channel|select|ownership', '通信による並行設計ができる'),
        M('Context・Cancellation・Timeout', 'context tree|deadline|cancellation propagation|request scope', '処理の中断と期限を一貫して伝播できる'),
        M('Go Runtime・Scheduler・GC', 'GMP model|work stealing|preemption|concurrent GC', '実行時挙動を性能問題へ結びつけられる'),
        M('標準ライブラリで作るHTTP', 'net/http|handler・middleware|client transport|server tuning', '依存を抑えたHTTPサービスを構築できる'),
        M('Error・Testing・Tooling', 'error wrapping|table-driven test|race detector|go vet・pprof', '失敗を診断しやすいGoコードを保守できる'),
        M('I/O・Serialization・Database', 'io.Reader・Writer|encoding|database/sql|connection pool', '効率的なデータ入出力を実装できる'),
        M('Goサービスの本番運用', 'graceful shutdown|profiling|build・cross compile|security', '小さく配布しやすい本番バイナリを運用できる'),
    ]),
    Domain(13, 'rust', 'Rust', 'rust',
           '所有権・借用・型・trait・非同期・unsafeを通じて、メモリ安全と高性能を両立するシステムを構築する。', [5, 6, 7, 8], [
        M('Ownership・Move・Copy', 'owner|move semantics|Copy trait|drop', '資源の寿命をコンパイル時に管理できる'),
        M('Borrow・Lifetime', 'shared・mutable borrow|lifetime annotation|elision|reborrow', '参照の有効性を安全に設計できる'),
        M('Struct・Enum・Pattern Matching', 'data modeling|Option・Result|match|destructuring', '不正状態を型で排除できる'),
        M('Trait・Generics・Dynamic Dispatch', 'trait bound|associated type|impl Trait|trait object', 'ゼロコスト抽象化と動的多相を使い分けられる'),
        M('Error HandlingとAPI設計', 'Result|? operator|custom error|panic boundary', '回復可能性に応じた失敗設計ができる'),
        M('Iterator・Closure・Zero-cost Abstraction', 'iterator adapter|lazy evaluation|monomorphization|inlining', '高水準かつ高速な処理を書ける'),
        M('ConcurrencyとSend・Sync', 'thread|Arc・Mutex|Send・Sync|channel', '型保証のある並行コードを構築できる'),
        M('Async Rust・Tokio', 'Future|Pin|executor|structured task', '高並行I/Oサービスを安全に実装できる'),
        M('Unsafe・FFI・メモリ表現', 'raw pointer|aliasing|layout|C ABI', '安全な境界を保ちながら低レイヤ連携できる'),
        M('Cargo・Library・Production Rust', 'workspace|feature|testing・benchmark|profiling・release', '再利用可能で運用可能なRustプロジェクトを作れる'),
    ]),
    Domain(14, 'web-backend-api', 'Web・Backend・API Engineering', 'backend',
           'HTTP、フレームワーク、API契約、認証、永続化、非同期処理を統合して、保守可能なバックエンドを設計する。', [10, 11, 16], [
        M('Webバックエンドの責務分解', 'transport|application|domain|infrastructure', 'フレームワークと業務ロジックを分離できる'),
        M('REST API設計', 'resource modeling|method semantics|status code|idempotency', '一貫したHTTP API契約を設計できる'),
        M('GraphQL・RPC・gRPC', 'schema|resolver|protobuf|streaming', '用途に応じたAPIスタイルを選定できる'),
        M('Express・Fastify・NestJS', 'routing|middleware・hook|DI・module|adapter', 'フレームワークの内部モデルと差を説明できる'),
        M('Validation・Serialization・Error', 'schema validation|DTO|content negotiation|problem details', '境界で入力と出力を安全に統制できる'),
        M('Authentication・Authorization', 'session・token|OAuth・OIDC|RBAC・ABAC|policy enforcement', '認証認可を業務要件へ落とし込める'),
        M('Transactionと整合性', 'unit of work|isolation|optimistic・pessimistic lock|outbox', 'DB更新と外部副作用を安全に設計できる'),
        M('非同期処理とジョブ', 'queue|retry|deduplication|dead-letter queue', '遅延・再試行・重複を制御できる'),
        M('API性能とスケーリング', 'cache|pagination|N+1|rate limiting', 'レイテンシと負荷を測定し改善できる'),
        M('本番API運用', 'versioning|backward compatibility|observability|graceful degradation', '変更と障害に強いAPIを運用できる'),
    ]),
    Domain(15, 'software-design-architecture', 'ソフトウェア設計・アーキテクチャ', 'architecture',
           '変更容易性、理解容易性、整合性を高めるために、モジュール、境界、依存、ドメインモデル、アーキテクチャ判断を学ぶ。', [8, 14], [
        M('設計原則と品質属性', 'cohesion・coupling|SOLID|information hiding|quality attribute', '設計判断を品質目標と結びつけられる'),
        M('モジュールと依存関係', 'dependency direction|stable abstraction|cycle|package design', '変更の波及を抑える境界を作れる'),
        M('DDD戦略設計', 'bounded context|ubiquitous language|context map|subdomain', '複雑な事業を意味の境界で分割できる'),
        M('DDD戦術設計', 'entity・value object|aggregate|domain service|repository', '業務不変条件をモデル内に保持できる'),
        M('Clean・Hexagonal・Onion', 'use case|port・adapter|dependency rule|framework boundary', '中心のロジックを外部技術から独立させられる'),
        M('Design Pattern', 'strategy|factory|adapter|observer|mediator', '繰り返す設計課題に適切な構造を適用できる'),
        M('CQRS・Event-driven Design', 'command・query|event|projection|eventual consistency', '読み書きの性質が異なるシステムを分離できる'),
        M('モノリス・モジュラーモノリス・Microservices', 'deployment boundary|data ownership|distributed cost|team topology', '分割の利益と分散コストを比較できる'),
        M('Architecture DecisionとEvolution', 'ADR|fitness function|strangler|technical debt', '設計理由を残し段階的に進化させられる'),
        M('設計レビューと可視化', 'C4 model|sequence diagram|threat model|trade-off analysis', '他者が検証できる形で設計を表現できる'),
    ]),
    Domain(16, 'database-storage-search', 'データベース・ストレージ・検索', 'data',
           'RDB、NoSQL、ストレージエンジン、トランザクション、索引、検索を内部構造から理解し、要件に合う永続化を選ぶ。', [2, 5, 6], [
        M('リレーショナルモデルとSQL', 'relation・tuple|key・constraint|relational algebra|SQL semantics', 'データ整合性をスキーマと問い合わせで表現できる'),
        M('スキーマ設計と正規化', 'functional dependency|1NF-BCNF|denormalization|migration', '更新異常を抑えつつ性能要件へ適応できる'),
        M('Indexと実行計画', 'B+tree|hash index|selectivity|cost-based optimizer', '遅いクエリを計画と統計から改善できる'),
        M('TransactionとIsolation', 'ACID|MVCC|lock|serializability', '競合下の整合性とスループットを設計できる'),
        M('Storage Engine', 'page|WAL|buffer pool|compaction', 'DB内部の読み書き経路を説明できる'),
        M('Replication・Partition・Backup', 'primary-replica|consistency|sharding|PITR', '可用性と拡張性をデータ損失目標と結びつけられる'),
        M('Key-Value・Document・Wide-column', 'data model|access pattern|partition key|secondary index', 'NoSQLを流行ではなくアクセスパターンで選べる'),
        M('CacheとIn-memory Store', 'cache-aside|write-through|eviction|stampede', '鮮度と負荷のバランスを設計できる'),
        M('全文検索・Vector検索', 'inverted index|tokenization|ranking|ANN', '検索要件に合わせた索引と評価を構築できる'),
        M('Database Reliability・Security', 'connection pool|schema change|encryption|audit', '本番DBを安全に変更・復旧・監査できる'),
    ]),
    Domain(17, 'distributed-systems-messaging', '分散システム・メッセージング', 'distributed',
           '部分障害、遅延、複製、整合性、合意、メッセージングを前提に、壊れ方まで含めてシステムを設計する。', [7, 10, 16], [
        M('分散システムの前提', 'partial failure|unreliable network|clock|failure detector', '単一プロセスと異なる失敗モデルを理解できる'),
        M('CAP・PACELC・整合性モデル', 'consistency|availability|partition|latency trade-off', '整合性要求を具体的な読み書き保証へ落とせる'),
        M('Replication', 'leader-follower|multi-leader|leaderless|quorum', '複製方式を競合と障害の観点で選べる'),
        M('Consensus', 'Raft・Paxos|term・log|leader election|safety・liveness', '合意アルゴリズムの保証とコストを説明できる'),
        M('Clock・Ordering・ID', 'Lamport clock|vector clock|HLC|UUID・Snowflake', 'イベント順序と識別子を分散環境で設計できる'),
        M('Messaging基礎', 'queue・log|at-most・at-least once|ordering|consumer group', '配信保証を業務副作用へ結びつけられる'),
        M('Kafka・Stream Processing', 'partition|offset|retention|stateful stream', '大規模イベントストリームを設計できる'),
        M('Idempotency・Saga・Outbox', 'deduplication|compensation|transactional outbox|inbox', '分散トランザクションを現実的に処理できる'),
        M('Distributed Cache・Coordination', 'consistent hashing|lease|distributed lock|membership', '共有状態と調停の危険性を理解できる'),
        M('分散システムのテストと運用', 'fault injection|Jepsen thinking|reconciliation|disaster recovery', '部分障害から回復する仕組みを検証できる'),
    ]),
    Domain(18, 'cloud-aws-infrastructure', 'Cloud・AWS・Infrastructure', 'cloud',
           'AWSをサービス名の暗記ではなく、責任共有、ネットワーク、計算、データ、権限、コスト、復旧の設計として学ぶ。', [6, 10, 16, 17], [
        M('Cloud設計原則と責任共有', 'IaaS・PaaS・SaaS|shared responsibility|region・AZ|well-architected thinking', 'クラウド採用の責任境界を説明できる'),
        M('AWS Network', 'VPC|subnet・route table|security group・NACL|Transit Gateway・PrivateLink', '安全な通信経路と分離を設計できる'),
        M('Compute', 'EC2|Auto Scaling|Lambda|ECS・Fargate', '負荷・運用・起動特性に応じて計算基盤を選べる'),
        M('Storage・CDN', 'S3|EBS・EFS|CloudFront|lifecycle・replication', '耐久性、性能、配信、コストを最適化できる'),
        M('Managed Database', 'RDS・Aurora|DynamoDB|ElastiCache|OpenSearch', 'アクセスパターンに合う管理型データサービスを選べる'),
        M('IAM・Organizations・Governance', 'principal・policy|role・STS|SCP|multi-account', '最小権限と組織統制を設計できる'),
        M('Load Balancing・API・Event', 'ALB・NLB|API Gateway|EventBridge|SQS・SNS', '同期・非同期トラフィック経路を構築できる'),
        M('Observability・Security', 'CloudWatch|CloudTrail|Config|GuardDuty・KMS', '監査・検知・暗号化を標準化できる'),
        M('Infrastructure as Code', 'CloudFormation|CDK|Terraform concepts|drift・state', '再現可能でレビュー可能なインフラ変更を行える'),
        M('Cost・Reliability・Disaster Recovery', 'FinOps|capacity|RTO・RPO|multi-AZ・multi-region', 'コストと可用性を事業要件に合わせて設計できる'),
    ]),
    Domain(19, 'containers-kubernetes-platform', 'Container・Kubernetes・Platform Engineering', 'cloud',
           'コンテナの隔離からKubernetesの制御ループ、Platform Engineeringの製品設計までを学ぶ。', [6, 10, 17, 18], [
        M('Container基礎', 'namespace|cgroup|image layer|OCI runtime', 'コンテナがVMと異なる理由を説明できる'),
        M('Docker Build・Runtime', 'Dockerfile|multi-stage build|volume・network|rootless', '小さく安全なイメージを構築できる'),
        M('Kubernetes Architecture', 'API server|etcd|scheduler|controller manager', '宣言と制御ループの仕組みを説明できる'),
        M('Workload Resource', 'Pod|Deployment|StatefulSet|Job・CronJob', 'ワークロード特性に合うリソースを選べる'),
        M('Service・Ingress・Networking', 'Service|Ingress・Gateway API|CNI|NetworkPolicy', 'クラスタ内外の通信と分離を設計できる'),
        M('Config・Secret・Storage', 'ConfigMap・Secret|CSI|PV・PVC|stateful workload', '設定と永続データを安全に扱える'),
        M('Scheduling・Scaling・Resource', 'request・limit|HPA・VPA|affinity・taint|eviction', '資源競合とスケーリングを調整できる'),
        M('Security・Policy・Supply Chain', 'RBAC|Pod Security|admission|image signing・SBOM', 'クラスタと配布物の信頼境界を守れる'),
        M('Service Mesh・Multi-cluster', 'sidecar・ambient|mTLS|traffic policy|federation', '複雑な通信制御の利益とコストを評価できる'),
        M('Platform Engineering', 'internal developer platform|golden path|self-service|platform product', '開発者体験を製品として設計できる'),
    ]),
    Domain(20, 'devops-build-cicd-release', 'DevOps・Build・CI/CD・Release', 'delivery',
           '変更を安全かつ高速に本番へ届けるためのGit、ビルド、テスト、アーティファクト、デプロイ、供給網を学ぶ。', [6, 14, 18, 19], [
        M('DevOps原則とValue Stream', 'flow|feedback|continuous learning|lead time', '開発から価値提供までの滞留を可視化できる'),
        M('Git内部とWorkflow', 'object model|branch・merge・rebase|trunk-based|release branch', '履歴と協業の目的に合う運用を選べる'),
        M('Build System', 'dependency graph|incremental build|cache|hermetic build', '再現可能で高速なビルドを設計できる'),
        M('CI Pipeline', 'stage・job|change detection|parallelism|flaky test control', '変更に応じた効率的な検証を構築できる'),
        M('Artifact・Package・Registry', 'immutable artifact|semantic version|registry|provenance', '同一物を環境間で昇格できる'),
        M('Deployment Strategy', 'rolling|blue-green|canary|feature flag', 'リスクに応じて段階的にリリースできる'),
        M('Database・Schema Release', 'expand-contract|backfill|dual write|rollback limit', 'アプリとDBの互換性を維持して変更できる'),
        M('GitOps・Environment Management', 'desired state|reconciliation|promotion|configuration drift', '環境差分をコードと自動収束で管理できる'),
        M('Software Supply Chain Security', 'SBOM|SLSA concepts|dependency pinning|signing・attestation', '依存物から配布までの改ざんリスクを下げられる'),
        M('Release Engineering Metrics', 'deployment frequency|change failure rate|MTTR|rollback・post-release verification', 'デリバリー能力を指標で改善できる'),
    ]),
    Domain(21, 'sre-reliability', 'SRE・信頼性工学', 'reliability',
           '信頼性を感覚ではなく、SLI/SLO、エラーバジェット、容量、障害対応、復旧設計で管理する。', [17, 18, 20, 22], [
        M('ReliabilityとSRE原則', 'user journey|risk|toil|engineering approach', '信頼性を事業価値とコストの均衡で説明できる'),
        M('SLI・SLO・SLA', 'availability|latency|correctness|error budget', 'ユーザー視点の信頼性目標を定義できる'),
        M('監視とAlerting', 'symptom・cause|burn rate|paging|noise reduction', '行動につながるアラートを設計できる'),
        M('Incident Response', 'severity|role|timeline|communication', '重大障害を役割分担して収束できる'),
        M('Postmortem・学習文化', 'blameless|contributing factor|action item|recurrence prevention', '個人非難なしにシステム改善へつなげられる'),
        M('Capacity Planning', 'traffic forecast|saturation|headroom|load shedding', '需要増加と資源限界を事前に扱える'),
        M('Resilience Pattern', 'timeout|retry|circuit breaker|bulkhead', '連鎖障害を防ぐ回復戦略を実装できる'),
        M('Disaster Recovery', 'backup|restore test|RTO・RPO|failover', '復旧目標に合う災害対策を構築できる'),
        M('Chaos Engineering', 'steady state|hypothesis|fault injection|blast radius', '安全な実験で未知の弱点を発見できる'),
        M('SRE組織と運用自動化', 'on-call|toil budget|runbook・automation|production readiness', '持続可能な運用体制を設計できる'),
    ]),
    Domain(22, 'observability', 'Observability・運用監視', 'reliability',
           'ログ、メトリクス、トレース、プロファイル、イベントを相互に関連付け、未知の障害を説明可能にする。', [6, 10, 14], [
        M('Observabilityの考え方', 'known unknown・unknown unknown|telemetry|context|debuggability', '監視と可観測性の違いを説明できる'),
        M('Logging', 'structured log|level|correlation ID|PII control', '検索・監査・診断に使えるログを設計できる'),
        M('Metrics', 'counter・gauge・histogram|label cardinality|aggregation|RED・USE', '傾向と飽和を低コストで観測できる'),
        M('Distributed Tracing', 'trace・span|context propagation|sampling|critical path', '分散リクエストの遅延原因を追跡できる'),
        M('OpenTelemetry', 'API・SDK|collector|semantic convention|exporter', 'ベンダー中立の計装パイプラインを構築できる'),
        M('Profiling', 'CPU profile|heap profile|allocation|continuous profiling', 'コード単位の資源消費を特定できる'),
        M('Dashboard Design', 'signal hierarchy|overview・drilldown|comparison|annotation', '判断を速める運用画面を設計できる'),
        M('Alert Engineering', 'threshold|anomaly|multi-window|routing・deduplication', '誤検知と見逃しを抑えた通知を構築できる'),
        M('Telemetry Pipeline', 'agent・collector|buffer|retention|cost control', '大量テレメトリを欠損とコストから守れる'),
        M('Observability-driven Debugging', 'hypothesis|evidence chain|cross-signal correlation|incident reconstruction', '複数信号から再現不能な障害を説明できる'),
    ]),
    Domain(23, 'performance-engineering', 'Performance Engineering', 'performance',
           'レイテンシ、スループット、CPU、メモリ、I/Oを測定し、モデル・証拠・実験で性能を改善する。', [1, 5, 6, 7, 22], [
        M('性能目標と測定', 'latency percentile|throughput|utilization|measurement error', '性能要求を測定可能な指標へ変換できる'),
        M('Benchmark設計', 'micro・macro benchmark|warm-up|noise|statistical comparison', '再現性のある性能実験を作れる'),
        M('CPU Profiling', 'sampling・instrumentation|flame graph|hotspot|branch・cache miss', 'CPU時間の主要因を証拠で特定できる'),
        M('Memory Profiling', 'heap|allocation rate|retained object|fragmentation', 'リークと過剰割り当てを区別できる'),
        M('GC Performance', 'pause|throughput|generation|heap sizing', 'GC方式とアプリ特性の相性を調整できる'),
        M('I/O・Network Performance', 'syscall|buffering|batching|connection pool', '待ち時間とコピー回数を削減できる'),
        M('Database Performance', 'query plan|index|lock contention|pool saturation', 'DBを含むエンドツーエンド遅延を改善できる'),
        M('Queueing Theory', 'Littleの法則|arrival・service rate|queue length|tail latency', '負荷と待ち行列の非線形な悪化を予測できる'),
        M('Load Test・Capacity', 'workload model|ramp・soak・spike|bottleneck|headroom', '本番に近い負荷で限界と安全域を測れる'),
        M('Performance Optimization Process', 'baseline|hypothesis|experiment|regression guard', '推測ではなく反復可能な改善を行える'),
    ]),
    Domain(24, 'cybersecurity-privacy-crypto', 'Cybersecurity・Privacy・Cryptography', 'security',
           '脅威モデル、認証認可、アプリ・ネットワーク・クラウド・供給網、暗号、プライバシーを防御者視点で統合する。', [6, 10, 14, 18], [
        M('Security MindsetとThreat Modeling', 'asset|actor|trust boundary|STRIDE・abuse case', '何を誰から守るかを明文化できる'),
        M('Identity・Authentication', 'password|MFA|session|OAuth・OIDC', '本人確認とセッションを安全に設計できる'),
        M('Authorization', 'RBAC|ABAC|ReBAC|policy decision・enforcement', '権限要件を一貫したポリシーへ変換できる'),
        M('Web Application Security', 'XSS|CSRF|SQL injection|SSRF', '代表的な入力・出力・境界攻撃を防げる'),
        M('API・Service Security', 'token validation|rate limit|schema abuse|service identity', 'API固有の攻撃面を守れる'),
        M('Network・Cloud Security', 'segmentation|zero trust|IAM|security monitoring', '通信と権限の最小化を設計できる'),
        M('Cryptography基礎', 'symmetric・asymmetric|hash・MAC|signature|key management', '暗号プリミティブを正しい目的で使える'),
        M('Secure SDLC・Supply Chain', 'SAST・DAST|dependency risk|secret scanning|SBOM・signing', '開発工程へセキュリティを組み込める'),
        M('Privacy Engineering', 'data minimization|purpose limitation|anonymization|retention', '個人データのライフサイクルを設計できる'),
        M('Incident・Forensics・Security Operations', 'detection|containment|evidence|recovery', '侵害時に証拠を保ち被害を抑えられる'),
    ]),
    Domain(25, 'qa-testing-verification', 'QA・Testing・Verification', 'quality',
           '品質をテスト件数ではなく、リスク、仕様、探索、静的解析、負荷、継続的フィードバックとして設計する。', [2, 4, 14, 20], [
        M('Quality ModelとTest Strategy', 'quality attribute|risk-based test|test pyramid|shift-left・right', '製品リスクに合う検証戦略を立てられる'),
        M('Unit Testing', 'test double|boundary|determinism|behavior・state verification', '小さな単位を速く安定して検証できる'),
        M('Integration・E2E Testing', 'real dependency|test container|fixture|environment parity', '結合境界とユーザー経路を現実的に検証できる'),
        M('Contract Testing', 'consumer-driven contract|schema compatibility|mock drift|versioning', 'サービス間変更を独立して安全に進められる'),
        M('Property-based・Metamorphic Testing', 'generator|invariant|shrinking|oracle problem', '例示だけでは見つからない欠陥を発見できる'),
        M('Fuzzing・Security Testing', 'coverage-guided fuzz|input corpus|sanitizer|abuse test', '予期しない入力への耐性を検証できる'),
        M('Mutation・Static Analysis', 'mutation score|lint|type checker|symbolic execution', 'テストの検出力とコード上のリスクを測れる'),
        M('Performance・Reliability Testing', 'load・stress・soak|fault injection|recovery test|SLO verification', '非機能要件を継続的に検証できる'),
        M('Test Data・Environment・Flakiness', 'data factory|isolation|time・randomness|retry anti-pattern', '不安定テストの原因を構造的に除去できる'),
        M('QA ProcessとRelease Decision', 'defect taxonomy|coverage model|quality gate|exploratory testing', '不確実性を可視化してリリース判断できる'),
    ]),
    Domain(26, 'data-engineering', 'Data Engineering', 'data',
           'データ収集、変換、保存、品質、メタデータ、バッチ・ストリーム、分析基盤を信頼性とコストの観点で設計する。', [16, 17, 18], [
        M('Data Architecture', 'source・sink|OLTP・OLAP|warehouse・lake・lakehouse|data product', '分析目的に合う全体アーキテクチャを描ける'),
        M('Ingestion', 'CDC|API・file|batch・stream|schema evolution', 'データ発生源から安全に取り込める'),
        M('ETL・ELT・Transformation', 'pipeline DAG|idempotency|incremental processing|SQL・code transform', '再実行可能な変換処理を構築できる'),
        M('Data Modeling for Analytics', 'star schema|fact・dimension|slowly changing dimension|semantic layer', '分析しやすく意味が一貫したモデルを作れる'),
        M('Batch Processing', 'partition|shuffle|Spark concepts|resource planning', '大規模データを効率的に一括処理できる'),
        M('Stream Processing', 'event time|window|watermark|state・exactly-once semantics', '遅延イベントを含む連続処理を設計できる'),
        M('Orchestration', 'scheduler|dependency|retry・backfill|data-aware scheduling', '複数パイプラインの実行と復旧を管理できる'),
        M('Data Quality・Observability', 'freshness|completeness|distribution|lineage', '壊れたデータを早期検知し影響範囲を追跡できる'),
        M('Metadata・Governance・Security', 'catalog|ownership|access control|PII・retention', 'データの意味・責任・権限を管理できる'),
        M('Cost・Performance・DataOps', 'file format|partition pruning|compute scaling|CI for data', '分析基盤を速く安く安全に運用できる'),
    ]),
    Domain(27, 'machine-learning-deep-learning', 'Machine Learning・Deep Learning', 'ai',
           '統計的学習、特徴量、評価、ニューラルネット、Transformerを理論・実装・失敗分析まで学ぶ。', [1, 2, 26], [
        M('ML問題設定', 'supervised・unsupervised|target・feature|train・validation・test|data leakage', '業務課題を学習問題へ正しく変換できる'),
        M('回帰・分類', 'linear・logistic regression|loss|regularization|decision boundary', '基本モデルを実装し解釈できる'),
        M('Tree・Ensemble', 'decision tree|random forest|gradient boosting|feature importance', '表形式データの強力な基準モデルを作れる'),
        M('Unsupervised Learning', 'clustering|dimensionality reduction|anomaly detection|representation', 'ラベルなしデータの構造を探索できる'),
        M('評価と実験', 'precision・recall・AUC|calibration|cross validation|error analysis', '指標を目的と失敗コストに合わせて選べる'),
        M('Neural Network基礎', 'perceptron|backpropagation|activation|optimization', '深層学習の訓練過程を数式とコードで説明できる'),
        M('CNN・Sequence Model', 'convolution|pooling|RNN・LSTM|attention', '画像・系列データの代表構造を理解できる'),
        M('Transformer', 'self-attention|positional encoding|encoder・decoder|scaling', '現代的なモデルの中核計算を説明できる'),
        M('Generalization・Robustness', 'bias・variance|overfitting|distribution shift|adversarial robustness', '本番環境で崩れる原因を分析できる'),
        M('Responsible ML', 'fairness|explainability|privacy|human oversight', '性能以外の社会的・運用的リスクを評価できる'),
    ]),
    Domain(28, 'llm-generative-ai', 'LLM・Generative AI', 'ai',
           'Tokenizer、Transformer、事前学習、推論、RAG、Agent、評価、安全性を、LLMアプリとモデル双方の視点で学ぶ。', [11, 16, 17, 27], [
        M('LLM全体像', 'foundation model|pretraining・post-training|inference|capability・limitation', 'LLMの能力源と限界を説明できる'),
        M('Tokenization・Embedding', 'BPE・SentencePiece|token budget|embedding space|similarity', 'テキスト表現がコストと検索へ与える影響を理解できる'),
        M('Transformer内部', 'attention|KV cache|normalization|feed-forward network', 'LLMの計算とメモリ特性を説明できる'),
        M('Pretraining・Scaling・Data', 'next-token objective|data mixture|scaling law|contamination', '学習データと計算量が能力へ与える影響を理解できる'),
        M('Post-training・Alignment', 'SFT|preference optimization|RLHF concepts|reasoning tuning', '用途に合わせた振る舞い調整を比較できる'),
        M('Prompt・Context Engineering', 'instruction|few-shot|structured output|context compression', '再現性のある入力設計を構築できる'),
        M('RAG・Memory', 'chunking|retrieval・rerank|citation|short・long-term memory', '根拠に基づく応答システムを評価・改善できる'),
        M('Agent・Tool Use', 'planning|tool schema|state machine|multi-agent trade-off', '失敗を制御できるエージェントワークフローを設計できる'),
        M('LLM Evaluation', 'gold set|LLM-as-judge|task・safety metric|online experiment', '品質を感覚ではなく継続測定できる'),
        M('LLM Security・Safety・Economics', 'prompt injection|data exfiltration|guardrail|latency・cost', '安全性、コスト、速度を統合して本番化できる'),
    ]),
    Domain(29, 'mlops-ai-systems', 'MLOps・AI Systems Engineering', 'aiops',
           'データ・学習・モデル登録・配信・GPU・監視・評価を一つの信頼できるライフサイクルとして設計する。', [18, 19, 20, 22, 27, 28], [
        M('ML LifecycleとReproducibility', 'experiment tracking|data・code・model version|seed|environment', '結果を再現し比較できる学習工程を作れる'),
        M('Feature・Data Pipeline', 'feature store|offline・online parity|label pipeline|data validation', '学習と推論のデータずれを防げる'),
        M('Training Infrastructure', 'distributed training|checkpoint|mixed precision|fault tolerance', '大規模学習を効率的に実行できる'),
        M('Model Registry・Promotion', 'artifact|metadata|approval|rollback', 'モデルを検証段階から本番へ安全に昇格できる'),
        M('Model Serving', 'online・batch|server|autoscaling|dynamic batching', 'SLOに合う推論経路を設計できる'),
        M('GPU・Accelerator Operation', 'memory|utilization|scheduling|multi-tenancy', '高価な計算資源を効率的に共有できる'),
        M('Inference Optimization', 'quantization|distillation|pruning|compilation・kernel', '品質を保ちながら速度とコストを改善できる'),
        M('Model Monitoring', 'drift|performance decay|data quality|feedback loop', '本番モデルの劣化を検知できる'),
        M('AI Evaluation Platform', 'dataset|runner|judge|regression gate', 'モデル・prompt・RAG変更を継続評価できる'),
        M('AI Governance・Security・Cost', 'access|lineage|risk review|FinOps for AI', 'AI資産を安全かつ持続可能に運用できる'),
    ]),
    Domain(30, 'developer-tooling-productivity', 'Developer Tooling・開発者生産性', 'tooling',
           'IDE、LSP、デバッガ、静的解析、コード生成、CLI、パッケージ、開発環境を理解し、開発者の認知負荷を下げる。', [6, 9, 20], [
        M('Developer Experienceの測定', 'cognitive load|feedback latency|setup time|flow state', '生産性問題を個人の努力ではなくシステムとして捉えられる'),
        M('Editor・IDE・LSP', 'language server|completion|diagnostics|semantic token', '言語支援ツールの通信と機能を実装できる'),
        M('Debugger', 'breakpoint|stack・frame|watch|source map', '実行状態を停止・観察・再現できる'),
        M('Static Analysis', 'AST|control・data flow|rule engine|false positive', '独自の品質・安全ルールを自動化できる'),
        M('Formatter・Linter・Code Action', 'syntax-preserving transform|style|autofix|editor integration', '一貫性を低摩擦で維持できる'),
        M('Code Generation・Scaffolding', 'template|schema-driven|AST transform|migration', '反復作業を安全に生成へ置き換えられる'),
        M('CLI・TUI Design', 'argument parser|stdin・stdout|exit code|interactive UX', '自動化と人間操作の双方に強いツールを作れる'),
        M('Package Manager・Dependency', 'resolution|lockfile|workspace|cache', '依存関係の再現性と速度を改善できる'),
        M('Local Development Environment', 'dev container|mock・emulator|seed|one-command setup', '新規参加者が短時間で開発を始められる'),
        M('Internal Developer Platform・AI Coding', 'portal|catalog|golden path|agentic workflow', 'ツール群を一貫した開発体験へ統合できる'),
    ]),
    Domain(31, 'product-engineering-requirements', 'Product Engineering・要求分析', 'product',
           'ユーザー課題、事業目標、要求、仮説、計測、技術制約を一つの意思決定系として扱う。', [14, 15, 25], [
        M('Problem Discovery', 'user interview|observation|job-to-be-done|pain・gain', '解決策の前に実在する課題を特定できる'),
        M('Requirement Engineering', 'stakeholder|functional・non-functional|constraint|acceptance criteria', '曖昧な要求を検証可能な形へ変換できる'),
        M('Domain Modeling Workshop', 'event storming|example mapping|story map|ubiquitous language', '関係者の知識を共通モデルへ統合できる'),
        M('Product Metric', 'north star|input metric|funnel|retention', '行動と成果を結ぶ指標体系を設計できる'),
        M('Experiment・A/B Test', 'hypothesis|randomization|sample size|guardrail metric', '製品変更の因果効果を検証できる'),
        M('Prioritization・Roadmap', 'impact・effort|risk|dependency|option value', '不確実性下で実装順序を説明できる'),
        M('Technical Product Decision', 'build・buy|architecture runway|platform leverage|operating cost', '技術選定を製品戦略へ結びつけられる'),
        M('Delivery・Scope Control', 'MVP|vertical slice|feature flag|definition of done', '価値を小さく安全に届けられる'),
        M('Feedback・Analytics・Iteration', 'qualitative・quantitative|instrumentation|cohort|learning loop', '利用後の証拠から製品を改善できる'),
        M('Ethics・Accessibility・Sustainability', 'inclusive design|dark pattern|social impact|lifecycle cost', '長期的なユーザー価値と責任を考慮できる'),
    ]),
    Domain(32, 'technical-leadership-management', 'Technical Leadership・Engineering Management', 'leadership',
           '技術的意思決定、レビュー、育成、組織設計、採用、計画、インシデント対応を通じて、チームの出力と学習を高める。', [15, 20, 21, 31], [
        M('Technical Leadershipの役割', 'direction|context|decision quality|multiplication', '自分が書く量ではなくチーム能力で成果を出せる'),
        M('Architecture・Design Review', 'question framing|trade-off|risk|decision record', '設計の質を上げつつ所有権を奪わないレビューができる'),
        M('Code Review', 'correctness|maintainability|security|feedback style', '欠陥検出と育成を両立できる'),
        M('Planning・Estimation・Risk', 'uncertainty|milestone|dependency|contingency', '予測を約束にせず意思決定へ使える'),
        M('Team Topology・Ownership', 'cognitive load|stream-aligned|platform|service ownership', '組織境界とシステム境界を整合させられる'),
        M('Hiring・Onboarding・Growth', 'competency|structured interview|onboarding|career ladder', '公平に採用し早期に戦力化できる'),
        M('Communication・Conflict・Decision', 'written context|disagreement|RACI・DRI|escalation', '対立を品質向上へ変換できる'),
        M('Operational Leadership', 'on-call|incident commander|readiness|risk acceptance', '本番責任をチームの仕組みにできる'),
        M('Strategy・Portfolio・Technical Debt', 'business alignment|option|debt register|investment', '複数の技術投資を戦略的に配分できる'),
        M('Culture・Learning・Change', 'psychological safety|retrospective|community of practice|change management', '継続学習する組織を育てられる'),
    ]),
    Domain(33, 'browser-frontend-platform', 'Browser・Frontend Platform', 'frontend',
           'ブラウザのネットワーク、DOM、CSS、レンダリング、JavaScript、セキュリティ、アクセシビリティを基盤から理解する。', [10, 11, 23, 24], [
        M('Browser Architecture', 'process model|renderer|sandbox|site isolation', 'ブラウザの責務分離と安全性を説明できる'),
        M('Navigation・Resource Loading', 'URL・fetch|preload・prefetch|cache|CORS', 'ページ表示までの通信経路を最適化できる'),
        M('DOM・Event', 'node tree|event loop|capture・bubble|custom element', 'UI状態とイベント伝播を正しく扱える'),
        M('CSS・Layout', 'cascade|box model|flex・grid|containment', '予測可能で保守しやすいレイアウトを作れる'),
        M('Rendering Pipeline', 'style|layout|paint|composite', 'jankや再描画コストを診断できる'),
        M('Frontend Architecture', 'state management|component boundary|routing|data fetching', '複雑な画面を変更可能な構造に分割できる'),
        M('Web Performance', 'Core Web Vitals concepts|bundle|image・font|runtime cost', '表示・操作・安定性を測定し改善できる'),
        M('Accessibility', 'semantic HTML|keyboard|screen reader|WCAG concepts', '多様な利用者が操作できるUIを作れる'),
        M('Web Security', 'same-origin|CSP|XSS・CSRF|trusted types', 'ブラウザ境界を利用した攻撃を防げる'),
        M('PWA・Offline・Edge', 'service worker|cache strategy|background sync|edge rendering', '不安定なネットワークでも動くWeb体験を設計できる'),
    ]),
    Domain(34, 'mobile-desktop-engineering', 'Mobile・Desktop Engineering', 'client',
           'iOS、Android、macOS、WindowsとクロスプラットフォームのUI、ライフサイクル、保存、同期、配布、OS連携を学ぶ。', [11, 15, 24, 33], [
        M('Client Platform Architecture', 'process・sandbox|app lifecycle|permission|background execution', '各OSの制約下でアプリ状態を設計できる'),
        M('Native UIとDeclarative UI', 'SwiftUI・UIKit|Compose・Views|state・binding|layout', '宣言的UIの状態管理を理解できる'),
        M('Navigation・State・Data Flow', 'screen graph|unidirectional data flow|dependency|restoration', '複雑な画面遷移と状態を保守できる'),
        M('Local Storage・Offline First', 'SQLite|file・keychain|cache|sync queue', 'オフラインと競合を前提にデータを扱える'),
        M('Network・Background Task', 'HTTP client|retry|push notification|background transfer', '制限された実行時間で通信を継続できる'),
        M('Device・OS Integration', 'sensor|camera・audio|share・intent|notification', '端末能力を権限とプライバシーに配慮して使える'),
        M('Cross-platform Architecture', 'shared core|FFI|React Native・Flutter concepts|native escape hatch', '共通化とネイティブ品質を両立できる'),
        M('Performance・Battery・Memory', 'frame budget|startup|energy|memory pressure', '体感性能と消費電力を測定・改善できる'),
        M('Security・Privacy', 'secure storage|biometric|certificate pinning risk|data protection', '端末内データと通信を保護できる'),
        M('Testing・Distribution・Release', 'simulator・device|UI test|signing|store rollout', '配布制約を含めて安全にリリースできる'),
    ]),
    Domain(35, 'embedded-iot-edge', 'Embedded・IoT・Edge Computing', 'embedded',
           '制約の強いデバイスで、電子回路、MCU、RTOS、通信、センサー、省電力、OTA、Edge AIを扱う。', [5, 6, 10, 13], [
        M('Electronics・Digital Interface', 'voltage・current|GPIO|pull-up|I2C・SPI・UART', 'センサーとMCUを安全に接続できる'),
        M('MCU Architecture', 'register|interrupt|timer|memory map', 'マイコン上の実行と周辺回路を理解できる'),
        M('Embedded C・Rust', 'volatile|bit operation|no_std|ownership for device', '資源制約下で安全なファームウェアを書ける'),
        M('RTOS', 'task|scheduler|queue・semaphore|real-time constraint', '期限と優先度を持つ処理を設計できる'),
        M('Sensor・Actuator', 'sampling|calibration|noise|control output', '物理世界の測定と駆動を扱える'),
        M('IoT Networking', 'BLE|Wi-Fi|MQTT|low-power protocol', '帯域・電力・距離に合う通信を選べる'),
        M('Power Management', 'sleep mode|duty cycle|battery|energy profiling', '長時間稼働するデバイスを設計できる'),
        M('Device Security', 'secure boot|device identity|key storage|firmware signing', '物理アクセスを含む脅威から守れる'),
        M('OTA・Fleet Management', 'update|rollback|telemetry|device twin', '多数端末を安全に更新・監視できる'),
        M('Edge AI・Edge Architecture', 'on-device inference|quantization|gateway|cloud-edge split', '遅延・プライバシー・電力を考慮してAI処理を配置できる'),
    ]),
    Domain(36, 'robotics-control-physical-ai', 'Robotics・Control・Physical AI', 'robotics',
           '運動学、制御、状態推定、計画、SLAM、センサーフュージョン、学習制御を統合して物理世界で動くAIを理解する。', [1, 5, 7, 27, 35], [
        M('Robotics System Overview', 'sense-plan-act|coordinate frame|real-time loop|safety', 'ロボットの情報と制御の流れを説明できる'),
        M('Kinematics', 'position・orientation|transformation|forward・inverse kinematics|Jacobian', '関節とエンドエフェクタの関係を計算できる'),
        M('Dynamics', 'force・torque|equation of motion|inertia|friction', '運動を生む力学をモデル化できる'),
        M('Classical Control', 'feedback|PID|stability|frequency response', '目標値へ安定追従する制御器を調整できる'),
        M('State Estimation', 'Bayes filter|Kalman filter|particle filter|observability', 'ノイズ下で見えない状態を推定できる'),
        M('Sensor Fusion', 'IMU|camera|LiDAR|time synchronization', '複数センサーを一貫した状態へ統合できる'),
        M('Path・Motion Planning', 'graph search|configuration space|sampling-based planning|trajectory', '障害物を避けて実行可能な動きを計画できる'),
        M('SLAM・Localization', 'mapping|loop closure|pose graph|visual・lidar SLAM', '未知環境で位置と地図を同時推定できる'),
        M('Robot Learning・Physical AI', 'imitation|reinforcement learning|world model|sim-to-real', '学習を制御へ安全に組み込める'),
        M('Safety・Deployment・Human Interaction', 'fail-safe|functional safety|teleoperation|HRI', '人と共存するロボットを検証・運用できる'),
    ]),
    Domain(37, 'gpu-hpc-accelerators', 'GPU・HPC・Accelerator', 'hpc',
           '並列ハードウェア、GPUメモリ、カーネル、数値計算、分散HPC、性能モデルを理解し、大規模計算を最適化する。', [1, 5, 7, 23, 27], [
        M('Parallel Computer Architecture', 'SIMD・SIMT|core・warp|memory hierarchy|throughput computing', 'GPUとCPUの実行モデルの違いを説明できる'),
        M('GPU Programming Model', 'kernel|thread・block・grid|synchronization|occupancy', '並列処理をGPU実行単位へ分解できる'),
        M('GPU Memory Optimization', 'global・shared・register|coalescing|bank conflict|transfer', 'メモリ帯域のボトルネックを改善できる'),
        M('Numerical Computing', 'floating point|BLAS|matrix operation|stability', '数値誤差と計算効率を両立できる'),
        M('Kernel Optimization', 'tiling|fusion|vectorization|autotuning', '高性能カーネルを測定し最適化できる'),
        M('Accelerator Compiler', 'graph compiler|operator lowering|kernel selection|runtime', '高水準モデルがデバイスコードになる過程を理解できる'),
        M('Distributed HPC', 'MPI|collective|domain decomposition|communication overlap', '複数ノードへ計算を分割できる'),
        M('Distributed Deep Learning', 'data・tensor・pipeline parallel|all-reduce|checkpoint|scaling efficiency', '大規模学習の並列方式を選べる'),
        M('Performance Model', 'roofline|arithmetic intensity|Amdahl・Gustafson|profiling', '理論上限と実測差を説明できる'),
        M('HPC Reliability・Scheduling・Cost', 'job scheduler|preemption|fault tolerance|energy・cost', '高価な計算基盤を効率的に運用できる'),
    ]),
    Domain(38, 'signal-processing-wireless', 'Signal Processing・Wireless Systems', 'signal',
           'サンプリング、フーリエ変換、フィルタ、音声、無線、Wi-Fi CSI、レーダーを数式と実装で扱う。', [1, 5, 10, 35], [
        M('Signal・Sampling', 'continuous・discrete|sampling theorem|aliasing|quantization', '物理信号をデジタル化する条件を説明できる'),
        M('Fourier・Frequency Domain', 'DFT・FFT|spectrum|convolution|window function', '時間領域と周波数領域を使い分けられる'),
        M('Digital Filter', 'FIR・IIR|frequency response|filter design|stability', 'ノイズ除去や特徴抽出のフィルタを設計できる'),
        M('Statistical Signal Processing', 'noise model|correlation|estimation|detection', '雑音下の信号有無やパラメータを推定できる'),
        M('Audio・Speech Signal', 'STFT|mel scale|beamforming|echo cancellation', '音声処理の前処理と空間処理を理解できる'),
        M('Wireless Communication', 'modulation|channel|SNR|error correction', '無線通信の容量と信頼性を説明できる'),
        M('OFDM・MIMO', 'subcarrier|cyclic prefix|spatial stream|channel estimation', '現代無線の多重化と伝搬推定を理解できる'),
        M('Wi-Fi・CSI Sensing', 'CSI amplitude・phase|multipath|Doppler|activity・breathing sensing', 'Wi-Fi信号から動きや呼吸を推定する基礎を説明できる'),
        M('Radar・Localization', 'time of flight|FMCW|range・velocity|angle estimation', '距離・速度・方向のセンシングを理解できる'),
        M('Signal ML・Edge Deployment', 'feature extraction|spectrogram model|sensor fusion|real-time pipeline', '信号処理とMLを端末上の推論へ統合できる'),
    ]),
]

LEVELS = [
    ('L1', '基礎', 'Foundation', '概念、語彙、前提、最小モデルを構築する'),
    ('L2', '応用', 'Applied', '内部機構、設計判断、実装方法を具体化する'),
    ('L3', '専門', 'Expert', '障害、性能、検証、トレードオフを扱い専門家の判断へ進む'),
]

FAMILY_CODE = {
    'theory': ('python', 'Python / 擬似コード'),
    'systems': ('c', 'C / Linux'),
    'language': ('text', '言語処理系の擬似コード'),
    'network': ('http', 'HTTP / shell'),
    'node': ('typescript', 'TypeScript'),
    'go': ('go', 'Go'),
    'rust': ('rust', 'Rust'),
    'backend': ('typescript', 'TypeScript / SQL'),
    'architecture': ('text', '設計擬似コード'),
    'data': ('sql', 'SQL / Python'),
    'distributed': ('text', '分散処理擬似コード'),
    'cloud': ('yaml', 'YAML / IaC'),
    'delivery': ('yaml', 'CI/CD YAML'),
    'reliability': ('text', '運用設計'),
    'performance': ('bash', 'shell / benchmark'),
    'security': ('http', 'HTTP / policy'),
    'quality': ('typescript', 'TypeScript tests'),
    'ai': ('python', 'Python'),
    'aiops': ('yaml', 'Python / YAML'),
    'tooling': ('typescript', 'TypeScript'),
    'product': ('text', '要求・分析テンプレート'),
    'leadership': ('text', '意思決定テンプレート'),
    'frontend': ('javascript', 'JavaScript / HTML'),
    'client': ('swift', 'Swift / Kotlin'),
    'embedded': ('rust', 'Embedded Rust / C'),
    'robotics': ('python', 'Python / 制御式'),
    'hpc': ('cpp', 'CUDA風擬似コード'),
    'signal': ('python', 'Python / 数式'),
}


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-') or 'lesson'


def code_example(domain: Domain, module: Module, level_idx: int) -> tuple[str, str]:
    concepts = module.concepts
    c1 = concepts[0]
    c2 = concepts[1] if len(concepts) > 1 else concepts[0]
    lang, label = FAMILY_CODE.get(domain.family, ('text', '擬似コード'))

    if domain.family == 'node':
        if level_idx == 0:
            code = f"""type {re.sub(r'\W+', '', module.title) or 'Model'}State = {{\n  topic: string;\n  status: 'new' | 'validated';\n}};\n\nfunction validate(input: unknown): {re.sub(r'\W+', '', module.title) or 'Model'}State {{\n  if (typeof input !== 'object' || input === null) {{\n    throw new TypeError('invalid input');\n  }}\n  return {{ topic: '{c1}', status: 'validated' }};\n}}"""
        elif level_idx == 1:
            code = f"""import {{ performance }} from 'node:perf_hooks';\n\nasync function measure<T>(name: string, fn: () => Promise<T>): Promise<T> {{\n  const started = performance.now();\n  try {{\n    return await fn();\n  }} finally {{\n    console.log({{ name, ms: performance.now() - started }});\n  }}\n}}\n\nawait measure('{module.title}', async () => {{\n  // {c1} と {c2} の挙動を観測する\n}});"""
        else:
            code = f"""import {{ AsyncLocalStorage }} from 'node:async_hooks';\n\ntype Context = {{ requestId: string }};\nconst context = new AsyncLocalStorage<Context>();\n\nexport function runWithContext<T>(requestId: string, fn: () => T): T {{\n  return context.run({{ requestId }}, fn);\n}}\n\nexport function currentRequestId(): string {{\n  return context.getStore()?.requestId ?? 'unknown';\n}}\n// {module.title}: 計測、境界、失敗時の復旧まで設計する"""
    elif domain.family == 'go':
        code = f"""package main\n\nimport (\n    \"context\"\n    \"fmt\"\n    \"time\"\n)\n\nfunc run(ctx context.Context) error {{\n    select {{\n    case <-time.After(10 * time.Millisecond):\n        fmt.Println(\"{c1}\")\n        return nil\n    case <-ctx.Done():\n        return ctx.Err()\n    }}\n}}"""
    elif domain.family == 'rust':
        code = f"""#[derive(Debug)]\nenum State {{\n    New,\n    Ready(String),\n}}\n\nfn transition(state: State) -> Result<State, &'static str> {{\n    match state {{\n        State::New => Ok(State::Ready(\"{c1}\".into())),\n        State::Ready(_) => Err(\"already ready\"),\n    }}\n}}\n\n// {c2}: 所有権と失敗経路を型に含める"""
    elif domain.family in ('data',):
        code = f"""BEGIN;\n\nSELECT id, version\nFROM learning_state\nWHERE topic = '{esc(c1)}'\nFOR UPDATE;\n\nUPDATE learning_state\nSET version = version + 1, updated_at = CURRENT_TIMESTAMP\nWHERE topic = '{esc(c1)}';\n\nCOMMIT;\n-- {c2}: 実行計画と競合も必ず確認する"""
    elif domain.family in ('cloud', 'delivery', 'aiops'):
        code = f"""apiVersion: curriculum.example/v1\nkind: LearningExercise\nmetadata:\n  name: {slugify(module.title)}\nspec:\n  objective: \"{c1}\"\n  constraints:\n    - \"{c2}\"\n  verification:\n    - measurable\n    - repeatable\n    - reversible"""
    elif domain.family == 'backend':
        code = f"""type Command = {{ idempotencyKey: string; payload: unknown }};\n\nasync function execute(command: Command): Promise<void> {{\n  await db.transaction(async (tx) => {{\n    const seen = await tx.idempotency.find(command.idempotencyKey);\n    if (seen) return;\n\n    // {c1}: 境界で検証し、{c2}: トランザクション内で不変条件を守る\n    await tx.idempotency.insert(command.idempotencyKey);\n  }});\n}}"""
        lang = 'typescript'
        label = 'TypeScript / SQL'
    elif domain.family == 'security':
        code = f"""# Policy sketch: {module.title}\nallow(request) =\n  authenticated(request.subject)\n  and authorized(request.subject, request.resource, request.action)\n  and validated(request.input)\n  and audited(request.decision)\n\n# Verify: {c1}\n# Threat to test: {c2}"""
        lang = 'text'
    elif domain.family == 'quality':
        code = f"""describe('{module.title}', () => {{\n  it('preserves the invariant', async () => {{\n    const input = generateCase('{c1}');\n    const result = await systemUnderTest(input);\n    expect(invariant(result, '{c2}')).toBe(true);\n  }});\n}});"""
    elif domain.family in ('ai', 'robotics', 'signal', 'theory'):
        code = f"""from dataclasses import dataclass\n\n@dataclass\nclass Experiment:\n    topic: str\n    hypothesis: str\n    metric: str\n\nexperiment = Experiment(\n    topic={c1!r},\n    hypothesis={('If we control ' + c2 + ', the result becomes explainable.')!r},\n    metric='measurable evidence',\n)\nprint(experiment)"""
    elif domain.family == 'frontend':
        code = f"""const state = {{ topic: '{c1}', status: 'idle' }};\n\nfunction render(next) {{\n  const output = document.querySelector('[data-output]');\n  output.textContent = `${{next.topic}}: ${{next.status}}`;\n}}\n\ndocument.addEventListener('click', (event) => {{\n  if (event.target.matches('[data-run]')) {{\n    render({{ ...state, status: '{c2}' }});\n  }}\n}});"""
    elif domain.family == 'embedded':
        code = f"""#![no_std]\n\nfn sample_and_filter(raw: u16) -> u16 {{\n    // {c1}: 入力範囲を明示する\n    let bounded = raw.min(4095);\n    // {c2}: 実機では校正値と時間制約を確認する\n    bounded / 4\n}}"""
    elif domain.family == 'hpc':
        code = f"""// CUDA-style pseudocode\n__global__ void transform(const float* input, float* output, int n) {{\n    int i = blockIdx.x * blockDim.x + threadIdx.x;\n    if (i < n) {{\n        output[i] = input[i] * 2.0f; // {c1}\n    }}\n}}\n// Check memory access, occupancy, and {c2}."""
    elif domain.family == 'client':
        code = f"""struct LearningState {{\n    var topic: String = \"{c1}\"\n    var status: Status = .idle\n\n    enum Status {{ case idle, running, failed(String) }}\n}}\n\n// {c2}: UI状態と副作用を分離する"""
        lang = 'swift'
    elif domain.family == 'network':
        code = f"""curl -v --http2 https://example.test/resource \\\n  -H 'Accept: application/json' \\\n  -H 'X-Lesson-Topic: {c1}'\n\n# Observe DNS, connection, TLS, request, response, and {c2}."""
        lang = 'bash'
    elif domain.family == 'performance':
        code = f"""#!/usr/bin/env bash\nset -euo pipefail\n\nfor run in $(seq 1 10); do\n  /usr/bin/time -f '%e %M' ./target-workload \\\n    --topic '{c1}' --constraint '{c2}'\ndone\n\n# Record environment, warm-up, percentile, and variance."""
        lang = 'bash'
    else:
        code = f"""CONTEXT: {domain.title}\nTOPIC: {module.title}\nINPUT: {c1}\nCONSTRAINT: {c2}\nPROCESS:\n  1. Define the invariant.\n  2. Observe the mechanism.\n  3. Introduce one controlled failure.\n  4. Record evidence.\nOUTPUT: A decision that another engineer can verify."""
        lang = 'text'
        label = '擬似コード / テンプレート'
    return lang, code


def concept_explanation(concept: str, module: Module, domain: Domain, level_idx: int) -> str:
    note = CONCEPT_NOTES.get(concept)
    if note:
        if level_idx == 0:
            return note + ' 最小例を手で追い、入力・状態・出力を確認してください。'
        if level_idx == 1:
            return note + ' 実装では境界値、資源使用量、失敗時の挙動、代替方式との比較まで確認します。'
        return note + ' 専門段階では保証の前提、最悪ケース、観測証拠、復旧可能性を反例と障害注入で検証します。'
    if level_idx == 0:
        return (f'「{concept}」は、{module.title}を理解するための基本語彙です。定義だけを覚えるのではなく、'
                f'何を区別し、どの条件で成立し、どの現象を説明するための概念かを確認します。'
                f'{domain.title}では、入力・状態・変換・出力のどこに位置するかを図にすると理解が安定します。')
    if level_idx == 1:
        return (f'「{concept}」を実装や設計へ落とす際は、正常系だけでなく境界値、競合、失敗、観測方法を同時に扱います。'
                f'別の選択肢と比較し、性能・安全性・変更容易性・運用コストのどれを優先したかを記録してください。')
    return (f'専門家レベルでは「{concept}」が破綻する条件と、破綻を検知する証拠を先に設計します。'
            f'平均値ではなく分布、単体ではなく相互作用、理論上の保証と実装上の仮定を分け、反例を作って検証します。')


def level_specific_sections(domain: Domain, module: Module, level_idx: int) -> dict[str, list[str] | str]:
    cs = module.concepts
    if level_idx == 0:
        return {
            'mental': [
                f'{module.title}を「入力 → 状態 → 規則 → 出力」の流れで整理する。',
                f'各概念（{"、".join(cs)}）の違いを一文で説明する。',
                '小さな具体例を手作業で追跡し、用語と挙動を結びつける。',
                '成立条件と、成立しない反例を一つずつ用意する。',
            ],
            'steps': [
                '用語を自分の言葉で定義し、似た用語との差分を書く。',
                '最小の入力例を作り、状態がどう変化するかを追う。',
                '結果を予測してからコード・計算・観測で確かめる。',
                '予測との差分を「前提の不足」「観測の不足」「理解の誤り」に分類する。',
            ],
            'tradeoffs': '基礎段階では網羅性より、概念間の境界を正確にすることを優先します。便利な比喩は入口として使えますが、比喩が成立しない条件も必ず確認してください。',
            'challenge': f'{module.title}について、初学者が混同しやすい2概念を選び、図と100字以内の説明で区別してください。',
        }
    if level_idx == 1:
        return {
            'mental': [
                f'{module.title}を構成する責務を分け、境界ごとの契約を定義する。',
                '代表的な実装を一つ作り、計算量・資源・失敗経路を測る。',
                '代替方式を最低二つ比較し、採用条件と不採用条件を明示する。',
                'ログ、メトリクス、テストなど、正しく動いた証拠を実装に含める。',
            ],
            'steps': [
                '要件を機能要件・非機能要件・制約へ分解する。',
                '最小実装を作り、正常系と境界値を自動検証する。',
                '一つの障害を注入し、期待する失敗モードと復旧を確認する。',
                '計測結果を基に設計を一度変更し、差分を記録する。',
            ],
            'tradeoffs': '応用段階では、正解を一つに固定せず、どの条件でどの方式が有利かを判断します。性能・整合性・安全性・開発速度・運用負荷は同時に最大化できないため、優先順位を明示します。',
            'challenge': f'{module.title}を使う小規模システムを設計し、要件、図、コード、テスト、運用指標を一つのREADMEにまとめてください。',
        }
    return {
        'mental': [
            f'{module.title}の保証を、理論上の保証・実装の仮定・運用上の期待に分離する。',
            '最悪ケース、競合、部分障害、資源枯渇、悪意ある入力をモデルへ追加する。',
            '観測できない内部状態を推定するため、複数の証拠を相関させる。',
            '設計判断をADRとして残し、将来変更すべきトリガーを定義する。',
        ],
        'steps': [
            '既存実装または論文・仕様の主張を一つ選び、前提条件を列挙する。',
            '反例、障害注入、負荷試験、形式化のいずれかで主張を検証する。',
            '失敗時のblast radius、検知時間、復旧時間を測る。',
            '代替設計を提示し、事業・チーム・運用を含む総コストで比較する。',
        ],
        'tradeoffs': '専門段階では局所最適ではなく、システム全体の二次的影響を扱います。高性能な方式がデバッグ不能になる、強い整合性が可用性を下げる、抽象化が境界コストを隠す、といった反作用を定量化してください。',
        'challenge': f'{module.title}について障害事例を仮定し、タイムライン、検知証拠、根本要因、恒久対策、残存リスクを含む技術レポートを作成してください。',
    }


def failure_modes(domain: Domain, module: Module, level_idx: int) -> list[str]:
    base = [
        f'{module.concepts[0]}と{module.concepts[1]}を同じものとして扱い、境界条件を失う。',
        '小さな成功例だけで一般化し、入力規模・並行性・障害時に破綻する。',
        '結果だけを確認し、途中状態や観測証拠を残さない。',
        '採用した方式の前提条件と、撤退条件を記録しない。',
    ]
    if level_idx == 1:
        base.append('テスト環境と本番環境の差を無視し、性能・権限・時刻・ネットワーク条件が再現されない。')
    if level_idx == 2:
        base.extend([
            '平均値で判断し、tail、分散、希少障害、攻撃者の適応を見落とす。',
            '抽象化の下にあるOS・ネットワーク・ハードウェアの制約を無視する。',
        ])
    return base


def exercises(domain: Domain, module: Module, level_idx: int) -> list[str]:
    c = module.concepts
    if level_idx == 0:
        return [
            f'{c[0]}、{c[1]}、{c[2]}をそれぞれ120字以内で定義し、違いを表にする。',
            f'{module.title}の最小例を紙またはコードで作り、入力から出力までを追跡する。',
            f'意図的に誤った説明を一つ書き、どこが誤りかを根拠付きで訂正する。',
        ]
    if level_idx == 1:
        return [
            f'{module.title}を扱う小さな実装を作り、正常系・境界値・失敗系のテストを追加する。',
            f'{c[0]}を採用する案と{c[1]}を採用する案を、性能・安全性・変更容易性・運用負荷で比較する。',
            '実装へ計測点を追加し、少なくとも3回測定して結果とばらつきを記録する。',
        ]
    return [
        f'{module.title}に対して、競合・資源枯渇・部分障害・悪意ある入力のうち二つを注入する。',
        f'{c[0]}の保証が崩れる最小反例を作り、検知するテストまたは監視を追加する。',
        '設計のADRを作成し、前提、代替案、採用理由、負の影響、再評価条件を記録する。',
    ]


def self_checks(domain: Domain, module: Module, level_idx: int) -> list[tuple[str, str]]:
    c = module.concepts
    if level_idx == 0:
        return [
            (f'{module.title}は何を解決するための概念群ですか？', f'{domain.description}の中で、特に「{module.outcome}」ために使います。'),
            (f'{c[0]}と{c[1]}の違いは何ですか？', '定義、入力、出力、成立条件、失敗条件の5点で比較してください。用語の言い換えだけではなく、同じ例へ適用したときの挙動差を示せれば十分です。'),
            ('理解したと判断する最小の証拠は何ですか？', '説明、具体例、反例、再現可能な確認の4つが揃っていることです。'),
        ]
    if level_idx == 1:
        return [
            (f'{module.title}の実装を選ぶ際の主要なトレードオフは何ですか？', '性能、整合性、安全性、開発速度、運用負荷、変更容易性から、今回重要な軸を選び、条件付きで比較します。'),
            ('正常に動くことと、正しく設計されていることの違いは何ですか？', '正常例の成功は一つの観測にすぎません。境界、失敗、競合、資源制約、将来変更でも不変条件が保たれる必要があります。'),
            ('実装を本番へ出す前に何を観測可能にしますか？', '入力規模、処理時間、失敗種別、資源使用量、重要な状態遷移、相関IDを候補にします。'),
        ]
    return [
        (f'{module.title}の保証はどの仮定に依存しますか？', 'ネットワーク、時刻、入力分布、権限、ハードウェア、ライブラリ、運用手順など、外部条件を列挙し、崩れたときの挙動を確認します。'),
        ('平均的な成功が重大障害を隠すのはなぜですか？', 'tail、希少競合、段階的リーク、相関障害、攻撃者の適応は平均値へ現れにくいためです。分布と時系列、個別トレースが必要です。'),
        ('専門家としての完了条件は何ですか？', '仕組みを説明でき、実装でき、壊せて、観測でき、復旧でき、別案との判断を他者へ説明できることです。'),
    ]


def make_styles() -> str:
    return r'''
:root {
  color-scheme: light dark;
  --bg: #0b1020;
  --surface: #11182b;
  --surface-2: #17213a;
  --text: #eef3ff;
  --muted: #a8b3cf;
  --line: #2a385b;
  --accent: #7dd3fc;
  --accent-2: #a7f3d0;
  --warning: #fde68a;
  --danger: #fca5a5;
  --shadow: 0 18px 50px rgba(0,0,0,.24);
  --radius: 18px;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: radial-gradient(circle at top right, #18264a 0, var(--bg) 42%); color: var(--text); line-height: 1.75; }
a { color: var(--accent); text-underline-offset: .18em; }
a:hover { color: var(--accent-2); }
header.site-header { position: sticky; top: 0; z-index: 20; backdrop-filter: blur(18px); background: rgba(11,16,32,.82); border-bottom: 1px solid var(--line); }
.nav { max-width: 1280px; margin: auto; padding: 12px 22px; display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
.brand { font-weight: 800; color: var(--text); text-decoration: none; margin-right: auto; }
.nav a:not(.brand) { text-decoration: none; color: var(--muted); font-size: .94rem; }
main { max-width: 1180px; margin: 0 auto; padding: 38px 22px 80px; }
.hero { padding: 34px; border: 1px solid var(--line); border-radius: 28px; background: linear-gradient(135deg, rgba(125,211,252,.12), rgba(167,243,208,.06)); box-shadow: var(--shadow); }
h1, h2, h3 { line-height: 1.28; letter-spacing: -.02em; }
h1 { font-size: clamp(2rem, 5vw, 4.2rem); margin: 0 0 14px; }
h2 { font-size: clamp(1.35rem, 2.2vw, 2rem); margin-top: 52px; }
h3 { margin-top: 28px; }
.lede { color: var(--muted); font-size: 1.08rem; max-width: 900px; }
.badges { display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0; }
.badge { border: 1px solid var(--line); border-radius: 999px; padding: 4px 10px; font-size: .82rem; color: var(--muted); background: rgba(255,255,255,.03); }
.badge.level { color: var(--accent-2); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 18px; }
.card { display: block; border: 1px solid var(--line); border-radius: var(--radius); padding: 20px; background: rgba(17,24,43,.86); color: var(--text); text-decoration: none; box-shadow: 0 8px 28px rgba(0,0,0,.16); }
.card:hover { transform: translateY(-2px); border-color: #4d659e; }
.card p { color: var(--muted); }
.card .meta { color: var(--accent-2); font-size: .86rem; }
.toolbar { display: flex; gap: 12px; flex-wrap: wrap; align-items: end; margin: 24px 0; }
label { display: grid; gap: 6px; color: var(--muted); font-size: .9rem; }
input, select, button, textarea { font: inherit; }
input, select, textarea { border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; background: var(--surface); color: var(--text); }
button, .button { display: inline-flex; align-items: center; justify-content: center; gap: 8px; border: 1px solid #4770a8; border-radius: 12px; padding: 10px 15px; background: #19365e; color: white; text-decoration: none; cursor: pointer; }
button:hover, .button:hover { background: #234b80; }
button.secondary, .button.secondary { background: transparent; border-color: var(--line); color: var(--muted); }
button.danger { border-color: #7f1d1d; background: #3b1218; }
.progress-shell { height: 10px; background: #081020; border: 1px solid var(--line); border-radius: 999px; overflow: hidden; }
.progress-bar { height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent-2)); width: 0; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 22px 0; }
.stat { border: 1px solid var(--line); border-radius: 16px; padding: 16px; background: rgba(17,24,43,.72); }
.stat strong { font-size: 1.8rem; display: block; }
.section { border: 1px solid var(--line); border-radius: var(--radius); padding: 24px; margin: 18px 0; background: rgba(17,24,43,.74); }
.section h2, .section h3 { margin-top: 0; }
.callout { border-left: 4px solid var(--accent); padding: 14px 18px; background: rgba(125,211,252,.08); border-radius: 0 12px 12px 0; }
.callout.warning { border-color: var(--warning); background: rgba(253,230,138,.07); }
.callout.expert { border-color: var(--accent-2); background: rgba(167,243,208,.07); }
.concept-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }
.concept { border: 1px solid var(--line); border-radius: 14px; padding: 16px; background: rgba(23,33,58,.78); }
.concept h3 { margin: 0 0 8px; font-size: 1rem; color: var(--accent-2); }
ul.checklist { list-style: none; padding: 0; }
ul.checklist li { padding-left: 28px; position: relative; margin: 10px 0; }
ul.checklist li::before { content: '□'; position: absolute; left: 0; color: var(--accent); }
ol.steps li { margin-bottom: 12px; }
pre { overflow: auto; padding: 18px; border: 1px solid var(--line); border-radius: 14px; background: #070b15; line-height: 1.55; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
code.inline { background: rgba(255,255,255,.08); border-radius: 6px; padding: .12em .38em; }
details { border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; margin: 10px 0; background: rgba(23,33,58,.5); }
summary { cursor: pointer; font-weight: 700; }
.breadcrumbs { color: var(--muted); font-size: .9rem; margin-bottom: 20px; }
.breadcrumbs a { color: var(--muted); }
.lesson-nav { display: grid; grid-template-columns: 1fr auto 1fr; gap: 14px; align-items: center; margin-top: 44px; }
.lesson-nav .next { text-align: right; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { border-bottom: 1px solid var(--line); text-align: left; padding: 10px 12px; vertical-align: top; }
th { color: var(--accent-2); }
.small { font-size: .9rem; color: var(--muted); }
.search-results { display: grid; gap: 10px; margin-top: 14px; }
.search-result { border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; background: rgba(17,24,43,.7); }
.search-result a { font-weight: 700; text-decoration: none; }
.daily-list { display: grid; gap: 16px; }
.daily-item { border: 1px solid var(--line); border-radius: 16px; padding: 18px; background: rgba(17,24,43,.8); }
footer { max-width: 1180px; margin: auto; padding: 20px 22px 60px; color: var(--muted); }
.kbd { border: 1px solid var(--line); border-bottom-width: 3px; border-radius: 6px; padding: 1px 6px; font-family: ui-monospace, monospace; }
@media (max-width: 700px) {
  main { padding: 24px 14px 60px; }
  .hero { padding: 22px; }
  .lesson-nav { grid-template-columns: 1fr; }
  .lesson-nav .next { text-align: left; }
}
@media print {
  header.site-header, .toolbar, .lesson-actions, footer { display: none !important; }
  body { background: white; color: black; }
  .section, .hero, .card { box-shadow: none; background: white; border-color: #bbb; }
  a { color: black; }
}
'''.strip()


def make_app_js() -> str:
    return r'''
(() => {
  const KEY = 'engineering-curriculum-progress-v1';
  const SERVED_KEY = 'engineering-curriculum-served-v1';

  function loadProgress() {
    try { return JSON.parse(localStorage.getItem(KEY) || '{}'); }
    catch { return {}; }
  }
  function saveProgress(data) {
    localStorage.setItem(KEY, JSON.stringify(data));
    window.dispatchEvent(new CustomEvent('curriculum-progress-changed'));
  }
  function loadServed() {
    try { return JSON.parse(localStorage.getItem(SERVED_KEY) || '{}'); }
    catch { return {}; }
  }
  function saveServed(data) { localStorage.setItem(SERVED_KEY, JSON.stringify(data)); }
  function markComplete(id, complete = true) {
    const p = loadProgress();
    p[id] = p[id] || {};
    p[id].completed = complete;
    p[id].completedAt = complete ? new Date().toISOString() : null;
    p[id].reviewCount = p[id].reviewCount || 0;
    p[id].nextReviewAt = complete ? new Date(Date.now() + 7*86400000).toISOString() : null;
    saveProgress(p);
  }
  function isComplete(id) { return !!loadProgress()[id]?.completed; }
  function updateLessonButton() {
    const btn = document.querySelector('[data-complete-lesson]');
    if (!btn) return;
    const id = btn.dataset.completeLesson;
    const done = isComplete(id);
    btn.textContent = done ? '完了を取り消す' : 'このLessonを完了';
    btn.classList.toggle('secondary', done);
    btn.onclick = () => { markComplete(id, !isComplete(id)); updateLessonButton(); };
  }
  function updateStats() {
    if (!window.CURRICULUM) return;
    const p = loadProgress();
    const completed = window.CURRICULUM.lessons.filter(x => p[x.id]?.completed).length;
    const total = window.CURRICULUM.lessons.length;
    document.querySelectorAll('[data-stat-total]').forEach(el => el.textContent = total.toLocaleString());
    document.querySelectorAll('[data-stat-completed]').forEach(el => el.textContent = completed.toLocaleString());
    document.querySelectorAll('[data-stat-percent]').forEach(el => el.textContent = total ? Math.round(completed/total*100) + '%' : '0%');
    document.querySelectorAll('[data-progress-bar]').forEach(el => el.style.width = (total ? completed/total*100 : 0) + '%');
  }
  function setupSearch() {
    const input = document.querySelector('[data-curriculum-search]');
    const target = document.querySelector('[data-search-results]');
    if (!input || !target || !window.CURRICULUM) return;
    const run = () => {
      const q = input.value.trim().toLowerCase();
      if (!q) { target.innerHTML = ''; return; }
      const tokens = q.split(/\s+/).filter(Boolean);
      const items = window.CURRICULUM.lessons.filter(item => {
        const hay = `${item.id} ${item.domainTitle} ${item.moduleTitle} ${item.title} ${item.concepts.join(' ')}`.toLowerCase();
        return tokens.every(t => hay.includes(t));
      }).slice(0, 40);
      target.innerHTML = items.length ? items.map(item => `
        <div class="search-result">
          <a href="${window.CURRICULUM.basePrefix || ''}${item.path}">${item.id} — ${item.title}</a>
          <div class="small">${item.domainTitle} / ${item.moduleTitle} / ${item.levelLabel}</div>
        </div>`).join('') : '<p class="small">該当するLessonがありません。</p>';
    };
    input.addEventListener('input', run);
  }
  function unlocked(lesson, progress) {
    if (lesson.level === 1) return true;
    const prev = window.CURRICULUM.lessons.find(x => x.domainId === lesson.domainId && x.moduleIndex === lesson.moduleIndex && x.level === lesson.level - 1);
    return !prev || !!progress[prev.id]?.completed;
  }
  function hashString(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function seededSort(items, seed) {
    return [...items].sort((a,b) => hashString(seed+a.id) - hashString(seed+b.id));
  }
  function setupDaily() {
    const form = document.querySelector('[data-daily-form]');
    const out = document.querySelector('[data-daily-output]');
    if (!form || !out || !window.CURRICULUM) return;
    const dateKey = new Date().toISOString().slice(0,10);
    const render = (force = false) => {
      const count = Math.min(5, Math.max(1, Number(form.elements.count.value || 3)));
      const track = form.elements.track.value;
      const progress = loadProgress();
      const served = loadServed();
      const todayKey = `${dateKey}:${track}:${count}`;
      let ids = !force ? served[todayKey] : null;
      let picks = ids ? ids.map(id => window.CURRICULUM.lessons.find(x => x.id === id)).filter(Boolean) : [];
      if (!picks.length) {
        let candidates = window.CURRICULUM.lessons.filter(x => !progress[x.id]?.completed && unlocked(x, progress));
        if (track !== 'balanced') {
          const trackDomains = window.CURRICULUM.tracks[track] || [];
          const filtered = candidates.filter(x => trackDomains.includes(x.domainId));
          if (filtered.length >= count) candidates = filtered;
        }
        const historicallyServed = new Set(Object.values(served).flat());
        const fresh = candidates.filter(x => !historicallyServed.has(x.id));
        if (fresh.length >= count) candidates = fresh;
        picks = seededSort(candidates, force ? dateKey + Date.now() : dateKey + track).slice(0, count);
        served[todayKey] = picks.map(x => x.id);
        saveServed(served);
      }
      out.innerHTML = picks.length ? picks.map((item, i) => `
        <article class="daily-item">
          <div class="small">${i+1}/${picks.length} · ${item.id} · ${item.levelLabel}</div>
          <h3><a href="${item.path}">${item.title}</a></h3>
          <p>${item.domainTitle} / ${item.moduleTitle}</p>
          <div class="badges">${item.concepts.map(c => `<span class="badge">${c}</span>`).join('')}</div>
        </article>`).join('') : '<p>選択可能な未完了Lessonがありません。進捗を取り消すか、履歴をリセットしてください。</p>';
    };
    form.addEventListener('submit', e => { e.preventDefault(); render(false); });
    document.querySelector('[data-daily-regenerate]')?.addEventListener('click', () => render(true));
    render(false);
  }
  function setupProgressTools() {
    const exportBtn = document.querySelector('[data-export-progress]');
    if (exportBtn) exportBtn.onclick = () => {
      const payload = { version: 1, exportedAt: new Date().toISOString(), progress: loadProgress(), served: loadServed() };
      const blob = new Blob([JSON.stringify(payload, null, 2)], {type:'application/json'});
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'engineering-curriculum-progress.json'; a.click(); URL.revokeObjectURL(a.href);
    };
    const importInput = document.querySelector('[data-import-progress]');
    if (importInput) importInput.onchange = async () => {
      const file = importInput.files?.[0]; if (!file) return;
      try {
        const payload = JSON.parse(await file.text());
        if (payload.progress) saveProgress(payload.progress);
        if (payload.served) saveServed(payload.served);
        alert('進捗を読み込みました。'); location.reload();
      } catch { alert('進捗ファイルを読み込めませんでした。'); }
    };
    document.querySelector('[data-reset-progress]')?.addEventListener('click', () => {
      if (confirm('すべての完了状態と配信履歴を削除しますか？')) {
        localStorage.removeItem(KEY); localStorage.removeItem(SERVED_KEY); location.reload();
      }
    });
  }
  window.CurriculumProgress = { loadProgress, saveProgress, markComplete, isComplete };
  document.addEventListener('DOMContentLoaded', () => {
    updateLessonButton(); updateStats(); setupSearch(); setupDaily(); setupProgressTools();
  });
  window.addEventListener('curriculum-progress-changed', updateStats);
})();
'''.strip()


def nav(prefix: str) -> str:
    return f'''<header class="site-header"><nav class="nav">
<a class="brand" href="{prefix}index.html">Engineering Expert Curriculum</a>
<a href="{prefix}roadmap.html">ロードマップ</a>
<a href="{prefix}daily.html">今日のLesson</a>
<a href="{prefix}progress.html">進捗</a>
<a href="{prefix}guide.html">使い方</a>
</nav></header>'''


def head(title: str, prefix: str, description: str = '') -> str:
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{esc(description)}">
<title>{esc(title)}</title>
<link rel="stylesheet" href="{prefix}assets/styles.css">
<script>window.CURRICULUM_BASE_PREFIX={json.dumps(prefix, ensure_ascii=False)};</script>
<script src="{prefix}assets/curriculum.js"></script>
<script>if(window.CURRICULUM) window.CURRICULUM.basePrefix=window.CURRICULUM_BASE_PREFIX;</script>
<script defer src="{prefix}assets/app.js"></script>
</head><body>'''


def foot() -> str:
    return '<footer>Engineering Expert Curriculum — 学習内容は、実装・検証・運用・説明までを一つの完了条件として設計しています。</footer></body></html>'


def lesson_id(domain_id: int, module_idx: int, level_idx: int) -> str:
    return f'D{domain_id:02d}-M{module_idx:02d}-L{level_idx+1}'


def build_metadata() -> tuple[list[dict], dict[int, Domain]]:
    lessons = []
    domain_map = {d.id: d for d in domains}
    for d in domains:
        ddir = f'domains/{d.id:02d}-{d.slug}'
        for mi, mod in enumerate(d.modules, 1):
            for li, (_, level_jp, level_en, _) in enumerate(LEVELS):
                lid = lesson_id(d.id, mi, li)
                title = f'{mod.title} — {level_jp}'
                lessons.append({
                    'id': lid,
                    'domainId': d.id,
                    'domainTitle': d.title,
                    'domainSlug': d.slug,
                    'moduleIndex': mi,
                    'moduleTitle': mod.title,
                    'level': li + 1,
                    'levelLabel': level_jp,
                    'title': title,
                    'concepts': mod.concepts,
                    'outcome': mod.outcome,
                    'path': f'{ddir}/lessons/{lid.lower()}.html',
                })
    return lessons, domain_map


lessons_meta, domain_map = build_metadata()
lesson_lookup = {x['id']: x for x in lessons_meta}


def generate_lesson_page(d: Domain, mi: int, mod: Module, li: int, meta: dict, prev_meta: dict | None, next_meta: dict | None) -> str:
    prefix = '../../../'
    _, level_jp, level_en, level_goal = LEVELS[li]
    specific = level_specific_sections(d, mod, li)
    lang, code = code_example(d, mod, li)
    concepts_html = ''.join(
        f'<article class="concept"><h3>{esc(c)}</h3><p>{esc(concept_explanation(c, mod, d, li))}</p></article>'
        for c in mod.concepts
    )
    outcomes = [
        mod.outcome,
        f'{"、".join(mod.concepts)}の関係を説明できる',
        '具体例と反例を用いて、成立条件と失敗条件を示せる',
        '学んだ内容を、コード・設計・検証・運用のいずれかへ適用できる',
    ]
    if li == 1:
        outcomes[-1] = '複数の実装方式を比較し、採用条件を設計判断として説明できる'
    elif li == 2:
        outcomes[-1] = '障害注入・負荷・攻撃・反例を使って保証の限界を検証できる'

    prev_link = f'<a class="button secondary" href="{Path(prev_meta["path"]).name}">← {esc(prev_meta["id"])} {esc(prev_meta["title"])}</a>' if prev_meta else '<span></span>'
    next_link = f'<a class="button secondary" href="{Path(next_meta["path"]).name}">{esc(next_meta["id"])} {esc(next_meta["title"])} →</a>' if next_meta else '<span></span>'
    checks_html = ''.join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in self_checks(d, mod, li))
    primer = MODULE_PRIMERS.get(
        (d.id, mod.title),
        f'{mod.title}では、まず {mod.concepts[0]} と {mod.concepts[1]} の境界を理解し、'
        f'{mod.concepts[2]} を通じて内部機構または実装へ落とし込み、{mod.concepts[3]} で限界・応用・検証へ進みます。'
        f'学習の中心は「{mod.outcome}」ことであり、定義、最小例、反例、計測可能な証拠を一組として扱います。'
    )
    tutor_prompt = f'''あなたは {d.title} の専門講師です。Lesson {meta['id']}「{mod.title} — {level_jp}」を、受講者が実装・検証・説明できるまで教えてください。

必須内容:
1. {', '.join(mod.concepts)} をそれぞれ正確に定義する。
2. 概念間の関係を図またはASCII図で示す。
3. 最小の具体例を段階的に追う。
4. 実務的なコード、設定、数式、protocol traceのうち適切なものを提示する。
5. 典型的な誤解、境界条件、性能問題、security risk、障害時の挙動を説明する。
6. normal case、boundary case、failure caseの演習を出す。
7. 私の回答を採点し、不足を追加問題で補う。
8. 最後に、このLessonを完了したと判断する実技課題を一つ出す。

難易度: {level_jp}。単なる用語集ではなく、仕組み、trade-off、観測・debug方法まで扱ってください。'''

    module_num = f'{mi:02d}'
    body = f'''{head(meta['title'] + ' | ' + d.title, prefix, d.description)}{nav(prefix)}
<main>
<div class="breadcrumbs"><a href="{prefix}index.html">Home</a> / <a href="../index.html">{esc(d.title)}</a> / Module {module_num} / {esc(level_jp)}</div>
<section class="hero">
  <div class="badges"><span class="badge">{esc(meta['id'])}</span><span class="badge">Domain {d.id:02d}</span><span class="badge">Module {module_num}</span><span class="badge level">{esc(level_en)} / {esc(level_jp)}</span></div>
  <h1>{esc(mod.title)}<br><span class="small">{esc(level_jp)}Lesson</span></h1>
  <p class="lede">{esc(d.description)} このLessonでは「{esc(level_goal)}」ことに集中します。</p>
  <div class="lesson-actions"><button data-complete-lesson="{esc(meta['id'])}">このLessonを完了</button> <a class="button secondary" href="../index.html">ドメイン一覧へ</a></div>
</section>

<section class="section">
<h2>このLessonの到達目標</h2>
<ul class="checklist">{''.join(f'<li>{esc(x)}</li>' for x in outcomes)}</ul>
<div class="callout"><strong>完了条件:</strong> 読んだだけでは完了ではありません。説明、具体例、反例、再現可能な検証の4点を残してください。</div>
</section>

<section class="section">
<h2>1. なぜ重要か</h2>
<p>{esc(mod.title)}は、{esc(d.title)}において「{esc(mod.outcome)}」ための中核テーマです。実務では単独で現れるより、周辺の概念や制約と組み合わさって現れます。そのため、用語の定義だけでなく、どの条件で使い、何を保証し、どこで破綻するかを一つのモデルとして理解します。</p>
<p>このLessonでは、{esc('、'.join(mod.concepts))}を同じ地図上に配置します。専門家は「知っている技術の数」ではなく、問題を正しい抽象度へ置き、必要な証拠を集め、複数案から条件付きで判断できる人です。</p>
<div class="callout expert"><strong>講義本文:</strong> {esc(primer)}</div>
</section>

<section class="section">
<h2>2. 中核概念</h2>
<div class="concept-grid">{concepts_html}</div>
</section>

<section class="section">
<h2>3. メンタルモデル</h2>
<ol class="steps">{''.join(f'<li>{esc(x)}</li>' for x in specific['mental'])}</ol>
<div class="callout warning"><strong>注意:</strong> 図や比喩は理解を助けますが、保証ではありません。境界条件と反例を一緒に持つことで、比喩の誤用を防げます。</div>
</section>

<section class="section">
<h2>4. 学習・実装手順</h2>
<ol class="steps">{''.join(f'<li>{esc(x)}</li>' for x in specific['steps'])}</ol>
<h3>最小実験</h3>
<pre><code class="language-{esc(lang)}">{esc(code)}</code></pre>
<p class="small">コードは完成品ではなく、観測可能な最小実験の出発点です。自分の環境で動かし、前提と結果を記録してください。</p>
</section>

<section class="section">
<h2>5. 設計判断とトレードオフ</h2>
<p>{esc(str(specific['tradeoffs']))}</p>
<div class="table-wrap"><table><thead><tr><th>観点</th><th>確認する問い</th></tr></thead><tbody>
<tr><td>正しさ</td><td>どの不変条件を守り、どの入力・並行性・障害まで保証するか。</td></tr>
<tr><td>性能</td><td>時間、空間、I/O、ネットワーク、待ち行列のどこが上限になるか。</td></tr>
<tr><td>安全性</td><td>悪意ある入力、権限境界、情報漏えい、誤操作にどう耐えるか。</td></tr>
<tr><td>変更容易性</td><td>要件変更時にどの境界まで影響し、互換性をどう維持するか。</td></tr>
<tr><td>運用性</td><td>失敗をどう検知し、誰が何を見て、どの手順で復旧するか。</td></tr>
</tbody></table></div>
</section>

<section class="section">
<h2>6. 典型的な失敗</h2>
<ul>{''.join(f'<li>{esc(x)}</li>' for x in failure_modes(d, mod, li))}</ul>
</section>

<section class="section">
<h2>7. 演習</h2>
<ol class="steps">{''.join(f'<li>{esc(x)}</li>' for x in exercises(d, mod, li))}</ol>
<div class="callout expert"><strong>Expert Challenge:</strong> {esc(str(specific['challenge']))}</div>
</section>

<section class="section">
<h2>8. 理解度チェック</h2>
{checks_html}
</section>

<section class="section">
<h2>9. 学習ノート用テンプレート</h2>
<pre><code>Lesson ID: {esc(meta['id'])}
理解したこと:
- 

自分で確認した証拠:
- 実行結果 / 計算 / 図 / テスト:

反例・失敗条件:
- 

設計判断:
- 採用案:
- 代替案:
- 採用理由:
- 再評価条件:

次に確認すること:
- </code></pre>
</section>

<section class="section">
<h2>10. GPT講師モード</h2>
<p>下記をGPTへ渡すと、このLessonを対話型の講義・演習・採点まで展開できます。Scheduled配信では選ばれたLessonのHTMLと一緒に使ってください。</p>
<pre><code>{esc(tutor_prompt)}</code></pre>
</section>

<nav class="lesson-nav">{prev_link}<a href="../index.html">Module一覧</a><div class="next">{next_link}</div></nav>
</main>{foot()}'''
    return body


def generate_domain_index(d: Domain, domain_lessons: list[dict]) -> str:
    prefix = '../../'
    prereq = ', '.join(f'<a href="../{pid:02d}-{domain_map[pid].slug}/index.html">{pid:02d} {esc(domain_map[pid].title)}</a>' for pid in d.prerequisites) or 'なし'
    cards = []
    for mi, mod in enumerate(d.modules, 1):
        lesson_links = []
        for li, (_, level_jp, level_en, _) in enumerate(LEVELS):
            meta = next(x for x in domain_lessons if x['moduleIndex'] == mi and x['level'] == li + 1)
            lesson_links.append(f'<a class="button secondary" href="lessons/{Path(meta["path"]).name}">{esc(level_jp)} {esc(meta["id"])}</a>')
        cards.append(f'''<article class="card">
<div class="meta">Module {mi:02d}</div><h3>{esc(mod.title)}</h3><p>{esc(mod.outcome)}</p>
<div class="badges">{''.join(f'<span class="badge">{esc(c)}</span>' for c in mod.concepts)}</div>
<div class="toolbar">{''.join(lesson_links)}</div></article>''')
    resources = DOMAIN_RESOURCES.get(d.id, [])
    resources_html = ''.join(
        f'<li><a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(title)}</a></li>'
        for title, url in resources
    )
    return f'''{head(d.title + ' | Engineering Expert Curriculum', prefix, d.description)}{nav(prefix)}<main>
<div class="breadcrumbs"><a href="{prefix}index.html">Home</a> / Domain {d.id:02d}</div>
<section class="hero"><div class="badges"><span class="badge">Domain {d.id:02d}</span><span class="badge">30 Lessons</span></div>
<h1>{esc(d.title)}</h1><p class="lede">{esc(d.description)}</p><p class="small">推奨前提: {prereq}</p></section>
<section><h2>Modules</h2><div class="grid">{''.join(cards)}</div></section>
<section class="section"><h2>公式・標準リファレンス</h2><p>Lesson本文と演習に加え、仕様・API・標準の一次資料で確認してください。version依存部分は必ず現在の公式資料を優先します。</p><ul>{resources_html}</ul></section>
</main>{foot()}'''


def generate_home() -> str:
    cards = []
    for d in domains:
        cards.append(f'''<a class="card" href="domains/{d.id:02d}-{d.slug}/index.html">
<div class="meta">Domain {d.id:02d} · 10 Modules · 30 Lessons</div><h3>{esc(d.title)}</h3><p>{esc(d.description)}</p></a>''')
    return f'''{head('Engineering Expert Curriculum', '', '38ドメイン、1,140Lessonのエンジニアリング専門カリキュラム')}{nav('')}<main>
<section class="hero"><div class="badges"><span class="badge">38 Domains</span><span class="badge">380 Modules</span><span class="badge">1,140 Lessons</span><span class="badge level">Offline HTML</span></div>
<h1>Engineering Expert Curriculum</h1>
<p class="lede">基礎理論、言語、OS、ネットワーク、バックエンド、クラウド、SRE、セキュリティ、AI、組み込みまでを、<strong>基礎 → 応用 → 専門</strong>の3段階で学ぶ自己完結型教材です。各Lessonには説明、実験、設計判断、失敗例、演習、理解度チェックがあります。</p>
<div class="toolbar"><a class="button" href="daily.html">今日のLessonを選ぶ</a><a class="button secondary" href="roadmap.html">学習順を見る</a><a class="button secondary" href="guide.html">使い方</a></div>
</section>
<section><h2>進捗</h2><div class="stats"><div class="stat"><span class="small">全Lesson</span><strong data-stat-total>1,140</strong></div><div class="stat"><span class="small">完了</span><strong data-stat-completed>0</strong></div><div class="stat"><span class="small">進捗率</span><strong data-stat-percent>0%</strong></div></div><div class="progress-shell"><div class="progress-bar" data-progress-bar></div></div></section>
<section><h2>Lesson検索</h2><label>キーワード、ID、概念<input data-curriculum-search type="search" placeholder="例: event loop / D17-M04 / 認証"></label><div class="search-results" data-search-results></div></section>
<section><h2>38 Domains</h2><div class="grid">{''.join(cards)}</div></section>
</main>{foot()}'''


def generate_roadmap() -> str:
    stages = [
        ('Stage 1 — 計算の土台', [1,2,3,4,5,6,7,8,9,10], '数学、アルゴリズム、ハードウェア、OS、言語処理、ネットワークの因果関係を作る。'),
        ('Stage 2 — 実装と設計', [11,12,13,14,15,16,17], '複数言語、Web、DB、設計、分散システムを統合してサービスを作る。'),
        ('Stage 3 — 本番運用', [18,19,20,21,22,23,24,25], 'クラウド、配布、信頼性、可観測性、性能、セキュリティ、品質を一体化する。'),
        ('Stage 4 — Data・AI', [26,27,28,29], 'データ基盤から学習、LLM、MLOpsまでを本番システムとして扱う。'),
        ('Stage 5 — 生産性・Product・Leadership', [30,31,32], '開発者体験、要求、意思決定、チーム能力を高める。'),
        ('Stage 6 — 専門選択', [33,34,35,36,37,38], 'ブラウザ、クライアント、IoT、ロボティクス、GPU、信号処理へ展開する。'),
    ]
    blocks=[]
    for name, ids, desc in stages:
        links=''.join(f'<a class="card" href="domains/{i:02d}-{domain_map[i].slug}/index.html"><div class="meta">Domain {i:02d}</div><h3>{esc(domain_map[i].title)}</h3></a>' for i in ids)
        blocks.append(f'<section><h2>{esc(name)}</h2><p>{esc(desc)}</p><div class="grid">{links}</div></section>')
    return f'''{head('ロードマップ | Engineering Expert Curriculum', '', '38ドメインの推奨学習順')}{nav('')}<main>
<section class="hero"><h1>推奨ロードマップ</h1><p class="lede">順番は絶対ではありません。ただし専門分野だけを先に暗記するより、下位レイヤと検証方法を並行して学ぶ方が応用力が残ります。</p></section>
{''.join(blocks)}
<section class="section"><h2>1日の推奨構成</h2><ol class="steps"><li>新規の基礎Lessonを1件。</li><li>現在の業務に直結する応用Lessonを1件。</li><li>完了済みLessonの復習または専門Lessonを1件。</li></ol><p>毎日1〜5件から選べます。継続を優先し、演習を省略してページ数だけ進めないでください。</p></section>
</main>{foot()}'''


def generate_daily() -> str:
    return f'''{head('今日のLesson | Engineering Expert Curriculum', '', '未完了Lessonから毎日1〜5件を重複なく選ぶ')}{nav('')}<main>
<section class="hero"><h1>今日のLesson</h1><p class="lede">完了状態と過去の選出履歴をブラウザ内に保存し、未完了かつ未選出のLessonを優先します。同じ日・同じ条件では同じ組み合わせを表示します。</p></section>
<section class="section"><form class="toolbar" data-daily-form>
<label>件数<select name="count"><option>1</option><option>2</option><option selected>3</option><option>4</option><option>5</option></select></label>
<label>トラック<select name="track"><option value="balanced">バランス</option><option value="backend">Backend専門</option><option value="systems">Systems専門</option><option value="cloud">Cloud/SRE専門</option><option value="ai">Data/AI専門</option><option value="product">Product/Leadership</option><option value="physical">Physical AI</option></select></label>
<button type="submit">今日のLessonを表示</button><button class="secondary" type="button" data-daily-regenerate>別の候補に入れ替える</button>
</form><div class="daily-list" data-daily-output></div></section>
<section class="section"><h2>重複しない仕組み</h2><p>選出履歴は <code class="inline">localStorage</code> に保存されます。基礎Lessonは常に候補になり、応用・専門Lessonは同じModuleの前段Lessonを完了すると優先的に解放されます。全端末で共有する場合は進捗ページからJSONをエクスポートしてください。</p></section>
</main>{foot()}'''


def generate_progress() -> str:
    return f'''{head('進捗 | Engineering Expert Curriculum', '', 'Lessonの完了状態を管理・エクスポートする')}{nav('')}<main>
<section class="hero"><h1>学習進捗</h1><p class="lede">進捗はこのブラウザに保存されます。バックアップや別端末への移行にはJSONのエクスポート・インポートを使います。</p></section>
<section><div class="stats"><div class="stat"><span class="small">全Lesson</span><strong data-stat-total>1,140</strong></div><div class="stat"><span class="small">完了</span><strong data-stat-completed>0</strong></div><div class="stat"><span class="small">進捗率</span><strong data-stat-percent>0%</strong></div></div><div class="progress-shell"><div class="progress-bar" data-progress-bar></div></div></section>
<section class="section"><h2>バックアップ</h2><div class="toolbar"><button data-export-progress>進捗JSONを書き出す</button><label class="button secondary">進捗JSONを読み込む<input data-import-progress type="file" accept="application/json" hidden></label><button class="danger" data-reset-progress>進捗を全削除</button></div></section>
<section class="section"><h2>完了の基準</h2><ul><li>Lessonを説明できる。</li><li>最小例を自分で再現できる。</li><li>反例または障害条件を示せる。</li><li>設計判断と検証証拠をノートへ残した。</li></ul></section>
</main>{foot()}'''


def generate_guide() -> str:
    return f'''{head('使い方 | Engineering Expert Curriculum', '', '教材の使い方とScheduled運用')}{nav('')}<main>
<section class="hero"><h1>使い方</h1><p class="lede">この教材は百科事典ではなく、専門家として考え、実装し、壊し、検証し、説明するための反復カリキュラムです。</p></section>
<section class="section"><h2>基本サイクル</h2><ol class="steps"><li><strong>読む:</strong> 中核概念とメンタルモデルを確認する。</li><li><strong>予測する:</strong> コードや実験を動かす前に結果を書く。</li><li><strong>実行する:</strong> 最小実験と演習を自分の環境で行う。</li><li><strong>壊す:</strong> 境界、競合、障害、悪意ある入力を追加する。</li><li><strong>証拠を残す:</strong> 出力、図、テスト、プロファイル、ログを保存する。</li><li><strong>説明する:</strong> 採用理由と再評価条件をADRまたはREADMEにする。</li></ol></section>
<section class="section"><h2>GPT Scheduledで毎日配信する場合</h2><p><code class="inline">scheduled/daily-prompt.txt</code> に、そのまま使える指示文を用意しています。<code class="inline">data/curriculum.json</code> と、進捗ページから書き出したJSONを同じProjectまたは会話へ渡し、毎日1〜5Lessonを選ばせます。</p><div class="callout warning">Scheduled側からローカルHTMLを自動で開くことはできません。Lesson IDと相対パスを通知させ、このZIPを展開したフォルダから開く運用を想定しています。</div></section>
<section class="section"><h2>教材の限界</h2><p>1,140Lessonで主要領域を広く深く覆っていますが、規格全文、すべての実装、全クラウドサービス、最新研究を永久に固定できるものではありません。バージョン依存のAPIやサービス仕様は公式ドキュメントと実環境で必ず検証してください。</p></section>
<section class="section"><h2>拡張</h2><p><code class="inline">source/generate_curriculum.py</code> を同梱しています。ModuleやLessonを追加し、同じID体系とHTML構造で再生成できます。</p></section>
</main>{foot()}'''


def scheduled_prompt() -> str:
    return '''あなたは「Engineering Expert Curriculum」の毎日学習コーチです。

入力:
- data/curriculum.json: 全Lessonメタデータ
- engineering-curriculum-progress.json: 完了状態と過去の配信履歴
- 今日選ぶLesson数: 1〜5

目的:
1. completed=true のLessonを新規Lessonとして選ばない。
2. 過去のservedに含まれるLessonは、未配信Lessonが残っている限り選ばない。
3. L2は同じModuleのL1完了後、L3は同じModuleのL2完了後を優先する。
4. 1日内で、基礎理論・現在の実務・運用/検証のバランスを取る。
5. Lesson ID、タイトル、相対HTMLパス、選定理由、今日の完了条件を日本語で出力する。
6. 最後にprogress JSONへ追加すべきservedレコードをJSONで出力する。

推奨トラック:
- Backend: 10,11,12,13,14,15,16,17,20,23,24,25
- Systems: 2,5,6,7,8,9,10,13,23
- Cloud/SRE: 10,17,18,19,20,21,22,23,24
- Data/AI: 1,16,17,26,27,28,29,37,38
- Product/Leadership: 15,21,25,30,31,32
- Physical AI: 1,5,7,27,29,34,35,36,37,38

出力は簡潔にするが、Lessonの重複防止ルールは厳守すること。'''


def build():
    if OUT.exists(): shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT/'assets').mkdir()
    (OUT/'data').mkdir()
    (OUT/'scheduled').mkdir()
    (OUT/'source').mkdir()

    # metadata
    curriculum = {
        'version': 1,
        'title': 'Engineering Expert Curriculum',
        'generated': '2026-07-30',
        'domainCount': len(domains),
        'moduleCount': sum(len(d.modules) for d in domains),
        'lessonCount': len(lessons_meta),
        'tracks': {
            'backend': [10,11,12,13,14,15,16,17,20,23,24,25],
            'systems': [2,5,6,7,8,9,10,13,23],
            'cloud': [10,17,18,19,20,21,22,23,24],
            'ai': [1,16,17,26,27,28,29,37,38],
            'product': [15,21,25,30,31,32],
            'physical': [1,5,7,27,29,34,35,36,37,38],
        },
        'domains': [
            {'id': d.id, 'slug': d.slug, 'title': d.title, 'description': d.description, 'prerequisites': d.prerequisites,
             'modules': [{'index': i, 'title': m.title, 'concepts': m.concepts, 'outcome': m.outcome} for i,m in enumerate(d.modules,1)]}
            for d in domains
        ],
        'lessons': lessons_meta,
    }
    (OUT/'data/curriculum.json').write_text(json.dumps(curriculum, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT/'data/progress-template.json').write_text(json.dumps({'version':1,'exportedAt':None,'progress':{},'served':{}}, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT/'assets/curriculum.js').write_text('window.CURRICULUM = ' + json.dumps(curriculum, ensure_ascii=False, separators=(',', ':')) + ';', encoding='utf-8')
    (OUT/'assets/styles.css').write_text(make_styles(), encoding='utf-8')
    (OUT/'assets/app.js').write_text(make_app_js(), encoding='utf-8')
    (OUT/'scheduled/daily-prompt.txt').write_text(scheduled_prompt(), encoding='utf-8')

    # top pages
    (OUT/'index.html').write_text(generate_home(), encoding='utf-8')
    (OUT/'roadmap.html').write_text(generate_roadmap(), encoding='utf-8')
    (OUT/'daily.html').write_text(generate_daily(), encoding='utf-8')
    (OUT/'progress.html').write_text(generate_progress(), encoding='utf-8')
    (OUT/'guide.html').write_text(generate_guide(), encoding='utf-8')

    # domain and lessons
    for d in domains:
        dpath = OUT/f'domains/{d.id:02d}-{d.slug}'
        (dpath/'lessons').mkdir(parents=True)
        dlessons = [x for x in lessons_meta if x['domainId'] == d.id]
        (dpath/'index.html').write_text(generate_domain_index(d, dlessons), encoding='utf-8')
        for idx, meta in enumerate(dlessons):
            mi = meta['moduleIndex']
            li = meta['level'] - 1
            mod = d.modules[mi-1]
            prev_meta = dlessons[idx-1] if idx > 0 else None
            next_meta = dlessons[idx+1] if idx < len(dlessons)-1 else None
            page = generate_lesson_page(d, mi, mod, li, meta, prev_meta, next_meta)
            (dpath/'lessons'/Path(meta['path']).name).write_text(page, encoding='utf-8')

    # README HTML and text
    readme = f'''Engineering Expert Curriculum\n\n- Domains: {len(domains)}\n- Modules: {sum(len(d.modules) for d in domains)}\n- Lessons: {len(lessons_meta)}\n- Entry point: index.html\n- Daily selection: daily.html\n- Progress export/import: progress.html\n- Scheduled prompt: scheduled/daily-prompt.txt\n\nOpen index.html in a modern browser. All pages work offline.\n'''
    (OUT/'README.txt').write_text(readme, encoding='utf-8')

    # include generator source
    src = Path(__file__).read_text(encoding='utf-8')
    (OUT/'source/generate_curriculum.py').write_text(src, encoding='utf-8')
    knowledge_src = (Path(__file__).parent/'knowledge.py').read_text(encoding='utf-8')
    (OUT/'source/knowledge.py').write_text(knowledge_src, encoding='utf-8')

    if ZIP_PATH.exists(): ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in sorted(OUT.rglob('*')):
            if p.is_file():
                zf.write(p, p.relative_to(OUT.parent))

if __name__ == '__main__':
    build()
    print(json.dumps({
        'out': str(OUT),
        'zip': str(ZIP_PATH),
        'domains': len(domains),
        'modules': sum(len(d.modules) for d in domains),
        'lessons': len(lessons_meta),
    }, ensure_ascii=False, indent=2))
