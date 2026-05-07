# 5G WDM バックボーンネットワーク 障害検知・根本原因究明

## 概要
このスキルは、5G WDM バックボーン環境におけるネットワーク品質異常の検知から根本原因特定・復旧指示までの一連のフローをガイドする。
Splunkのエピソード相関分析を活用し、ThousandEyes・TWAMP・Telemetry・ios・syslog の各データソースを横断的に分析することで、障害箇所と影響範囲を特定、障害を発生させていると想定される装置を特定する。

## ネットワーク構成
```
R8 -- R6 -- R4 -- R2
|     |           |
R9 -- R7 -- R5 -- R3
```
- ルーター: R2〜R9（Cisco NCS シリーズ）
- プロトコル: SR-MPLS、IS-IS、BFD、BGP
- 管理IP: 172.20.0.{2-9} = R{2-9}
- サービス: VRF スライスごとに SR-TE Policy で経路制御（Slice 1001 〜 1004）

## 実行フロー
以下のステップで進める。**各ステップの冒頭では必ず以下の形式でステータスを表示すること**:

```
▶ Step X 実行中: [何をしているか簡潔に]
```
ステップ完了時は結果サマリーを出力し、次のステップへの導線を示す。 

### Step 1: ThousandEyes のモニター
**冒頭に必ず表示する:**
```
▶ Step 1 実行中: ThousandEyes による直近 60 分のサービスモニターの状態を確認しています...
```

```spl
# ThousandEyes サービスモニター
index=thousandeyes 
| bin _time span=1m 
| stats avg(response_time_sec) by _time 
| join type=left _time 
    [ search index=thousandeyes earliest=-7d 
    | bin _time span=1m 
    | stats avg(response_time_sec) by _time 
    | predict algorithm=LLP5 avg(response_time_sec) algorithm=LLP5 holdback=60 future_timespan=60 period=1440 lower95=lower_bound upper95=upper_bound
    | rename lower_bound(prediction(avg(response_time_sec))) as lower_bound upper_bound(prediction(avg(response_time_sec))) as upper_bound
    | fields _time lower_bound upper_bound ] 
| fields _time avg(response_time_sec) lower* upper*
```
上記のサーチを過去 60 分の範囲で実行。

#### サーチ結果の読み方
上記のサーチで、avg(response_time_sec) が upper_bound を超えた場合はサービス異常。
サービス異常を検知した時間を障害認知の時間とする。

#### 完了後の必須アウトプット
サービス異常検知後、**次の Step に進む前に**、必ず以下の形式で出力すること:
```
## 📋 Step 1 完了 — サービス異常を検知しました。

**サービス検知時刻**: YYYY-mm-dd H:M:S Timezone 
**期待される応答時間**: upper_bound 秒
**実際の応答時間**: avg(response_time_sec)
```

サービス異常を検知しなかった場合は以下のメッセージを出力:
```
## 📋 Step 1 完了 — サービス異常は検知できませんでしたが調査を進めます。
```

### Step 2: エピソード相関分析（アラート発生状況の確認）
**冒頭に必ず表示する:**
```
▶ Step 2 実行中: Splunk エピソード相関分析でアラートの発生状況を確認しています...
```

Splunk の保存済みサーチでエピソード一覧を取得し、アラートの発生状況を確認する。
ユーザーが時間範囲を指定している場合はそれに従う（デフォルトは過去60分）。

```spl
# エピソード一覧（相関分析結果）
| savedsearch list_episodes
```

#### list_episodes の読み方
エピソードは複数のアラートを相関分析して集約したもの。
- episode — エピソード名（障害スライスと障害リンクが示される）
- slice — 影響スライス 
- alerts — 集約されたアラート一覧
 - [Critical] Interface Counter Mismatch — インターフェースカウンタ不整合（障害リンク特定）
 - Packet Loss Threshold Exceeded — パケットロス閾値超過
 - [DEGRADED] sr_policy — SR-TE Policyの劣化検知
- severity — Warning / Critical
エピソードが Critical に昇格するのは、Interface Counter Mismatch が検出された時。これはデータプレーンレベルでの確定的な障害証拠。
Step 1 でサービス異常を検知できなかった場合でも、ここで Critical なエピソードを検知した場合、その時刻を障害発生時刻とする。

#### 完了後の必須アウトプット
エピソード取得後、**次のStep（TWAMP/ios/syslog深掘り）に進む前に**、必ず以下の形式で出力すること:
```
## 📋 Step 2 完了 — エピソード相関分析サマリー

**Critical エピソード発生時刻: YYYY-mm-dd H:M:S Timezone 
**Critical エピソード概要: エピソードの概要
**検出エピソード数**: X件
**影響スライス**: SliceXXXX, SliceYYYY（エピソードがない場合は「なし」）
**注目アラート**: [検出されたアラート種別をリスト]
**最大Severity**: Critical / Warning（エピソードがない場合は「正常」）

### 次に必要な深掘り調査

アラートの内容から、以下の点を確認する必要があります：
- 確認事項: [エピソード名・アラート内容から読み取れる確認すべき事象を中立的に記述する]
**注意**: この時点では障害の種別（WDM 起因/ルーター起因など）を邪推しない。
障害原因に関する言及は、syslog との相関分析で裏付けが取れてから行うこと。

これを確認するために、以下の3つの観点で深掘り調査を行います。：

1. **TWAMP 品質分析 (Step 3)** — 各スライスのパケットロス・遅延を実測で確認
   → スライス別に品質劣化を確認し、障害スライスを絞り込み

2. **経路マッピング (Step 4)** — 正常スライスとの経路比較で障害ノードを特定
   → パケットロスが出ているスライスのみに存在するルーターを特定

3. **Telemetry によるインタフェース確認 (Step 5)** — 被疑ルーターのインタフェースレベルでのパケットロス状況確認
   → 絞り込まれたルーターに対してインタフェースレベルでのパケットロス状況を突き合わせ

4. **ルーター ios イベント分析 (Step 6)** — ルーター側の事象を時系列で確認
   → 障害発生時刻に対して BFD 断・IS-IS 隣接断・SR-TE Policy DOWN のタイムスタンプを突き合わせる

5. **WDM syslog イベント分析 (Step 7)** — WDM 側の事象を時系列で確認
   → WDM のアラート、およびパフォーマンスメトリックを問題を検知したルーターと突き合わせ根本原因を特定

6. 上記のアクションで取得した情報から取るべきアクションを提案

では Step 3（TWAMP品質分析）から深掘りを開始します。
```

上記を出力した後、ユーザーの確認なしに Step 3 以降を続けて実行してよい。 

### Step 3: TWAMP 品質分析

**冒頭に必ず表示する:**
```
▶ Step 3 実行中: TWAMP データで影響スライスのパケットロス・遅延を実測しています...
```

#### TWAMPフィールド解説
PCA TWAMPデータから品質指標を分析する。主要フィールドは以下の通り。
 | フィールド | 意味 | 単位 |
 |-----------|------|------|
 | `Session Name` | TWAMPセッション名（例: R2-R9_TWAMP_Slice1002_ipv4_SF） | — |
 | `Interface` | 関連インターフェース（例: L3-R2-VCE1002） | — |
 | `ul_lostperc` | 上り方向パケットロス率 | pct（百分率） |
 | `dl_lostperc` | 下り方向パケットロス率 | pct |
 | `ul_lostpkts` | 上り方向ロストパケット数 | packets |
 | `dl_lostpkts` | 下り方向ロストパケット数 | packets |
 | `rt_dmean` | ラウンドトリップ遅延（平均） | ms |
 | `rt_jmean` | ラウンドトリップジッター（平均） | ms |
 | `ul_dmean` | 上り方向遅延（平均） | ms |
 | `dl_dmean` | 下り方向遅延（平均） | ms | 
 
#### 分析クエリ（SPLリファレンスの references/spl_queries.md も参照）

```spl
# サンプルデータ確認（フィールド構造の把握）
index=twamp sourcetype=pca_twamp_csv | head 3 | fields *

# スライス別パケットロス・遅延のタイムライン（5分粒度）
index=twamp sourcetype=pca_twamp_csv
| rex field="Session Name" "(?<slice>Slice\d+)"
| eval ul_loss_pct=round(ul_lostperc/10000, 2)
| eval dl_loss_pct=round(dl_lostperc/10000, 2)
| eval rt_delay=rt_dmean
| timechart span=5m
  avg(ul_loss_pct) as "Avg UL Loss %"
  avg(dl_loss_pct) as "Avg DL Loss %"
  avg(rt_delay) as "Avg RT Delay ms"
  max(ul_loss_pct) as "Max UL Loss %" by slice limit=0
  
# パケットロスが発生しているイベントだけ抽出
index=twamp sourcetype=pca_twamp_csv
| where ul_lostperc > 0 OR dl_lostperc > 0
| table _time "Session Name" Interface ul_lostpkts dl_lostpkts ul_lostperc dl_lostperc rt_dmean rt_jmean
| sort _time
```

#### 完了後の必須アウトプット
過去 60 分のネットワークスライスごとのパケットロス、遅延、ジッターの状況をスライスごとにチャート表示する。


### Step 4: 経路マッピング
**冒頭に必ず表示する:**
```
▶ Step 4 実行中: 異常が発生しているスライスと正常なスライスを比較し、問題のあるノードを特定します...
```

```spl
index=twamp sourcetype=pca_twamp_csv 
| head 5
| rename "Source Ip" as src_ip, "Destination Ip" as dest_ip, "Session Name" as session_name 
| rex field=session_name "^(?<src_host>[^-]+)-(?<dest_host>[^_]+)_TWAMP_Slice(?<slice>[^_]+)" 
| bin span=1h _time 
| stats p95(rt_dp95) as delay p95(rt_jp95) as jitter avg(dl_lostperc) as dl_lostperc avg(ul_lostperc) as ul_lostperc by _time session_name src_host src_ip Interface dest_host dest_ip slice
| eval dl_lostperc = ifnull(dl_lostperc,1000000) 
| eval ul_lostperc = ifnull(ul_lostperc,1000000) 
| stats avg(delay) as delay avg(jitter) as jitter p95(dl_lostperc) as dl_lostperc p95(ul_lostperc) as ul_lostperc by session_name src_host src_ip Interface dest_host dest_ip slice
| eval delay = round(delay, 2), jitter = round(jitter, 2), dl_lostperc = round(dl_lostperc, 2), ul_lostperc = round(ul_lostperc, 2) 
| fields session_name slice delay jitter dl_lostperc ul_lostperc src_ip dest_ip 
| join type=left slice 
    [ search index=telemetry sourcetype=cnc_srte_path_json
    | fields _time host sr_policy_results{}.hops{} 
    | rename sr_policy_results{}.hops{} as hops 
    | eval src = mvindex(hops, 0), hop1 = mvindex(hops, 1), hop2 = mvindex(hops, 2), hop3 = mvindex(hops, 3), dest = mvindex(hops, 4) 
    | stats count by _time host src hop1 hop2 hop3 dest 
    | eval slice = substr(host, 9, 4) ] 
| fields session_name slice dl_lostperc ul_lostperc delay jitter src hop* dest 
| eval slice = "Vlan".slice
| sort slice 
| rename session_name as Session slice as Slice, ul_lostperc as "R2->R9 Packet Loss%", dl_lostperc as "R9->R2 Packet Loss%", delay as "Delay (ms)", jitter as "Jitter (us)", src as Reflector, hop* as Hop*, dest as Sender 
| table Session Slice Reflector Hop* Sender "R9->R2 Packet Loss%" "R2->R9 Packet Loss%" "Delay (ms)" "Jitter (us)"
```
Packet Loss%、および Delay、Jitter が大きいスライスを特定し、異常スライス内にしかないネットワークノードを被疑箇所として絞り込む。
障害箇所の特定に最も重要な情報源。 
- PR2->R9 Packet Loss% / R9->R2 Packet Loss% — 方向別パケットロス 
- Delay (ms) — 遅延 
- Jitter (us) — ジッター 
- Reflector / Hop1 / Hop2 / Hop3 / Sender — TWAMP の Sender と Reflector、およびその経路ルーター。特定のスライスだけにパケットロスが出ている場合、そのスライスの経路に含まれるノードが障害箇所。 


#### 完了後の必須アウトプット
各スライスを構成するノード情報をテーブル表示する。


### Step 5: Telemetry によるインタフェース確認
**冒頭に必ず表示する:**
```
▶ Step 5 実行中: Telemetry データを使って障害が疑われるルーターのインタフェース詳細を確認します...
```

```spl
| savedsearch telemetry_if_counter
| where r1_to_r2_drop_rate > 30
```
上記サーチ実行によりパケットロスが 30% 以上あるルータインタフェースが確認できる。
router_1 の interface_1 が送信側、router_2 の interface_2 が受信側

#### 完了後の必須アウトプット
パケットロスが 30% 以上あるルータインタフェースをテーブル表示する。


### Step 6: ルーター ios 分析
**冒頭に必ず表示する:**
```
▶ Step 6 実行中: ルーター ios ログから発生した事象を確認します...
```
ios からネットワーク障害関連イベントを抽出する。 
どのルーターでどのようなイベントが発生しているかを時系列で確認する。

```spl
# 全イベントを時系列で確認
index=ios
| table _time host _raw
| sort _time

# SR-TE Policy状態変化を抽出
index=ios (%OS-XTC-5-SR_POLICY_UPDOWN OR %PKT_INFRA-LINK-5-CHANGED OR %PLATFORM-DPA-2-RX_FAULT OR %ROUTING-ISIS-5-ADJCHANGE OR %L2-BFD-6-ADJACENCY_DELETE OR %L2-BFD-6-SESSION_REMOVED OR %L2-BFD-6-SESSION_STATE_DOWN)
| table _time host _raw
| sort _time
```
取得した ios イベントを時系列で整理し、どのルーター・どのリンク・どのプロトコルで 異常が発生しているかを確認する。
TWAMP データとタイムスタンプを突き合わせて 品質劣化と ios イベントの相関を分析する。
障害により SRTE ポリシーがどう変更されたかを確認する。

#### 完了後の必須アウトプット
現在の SRTE ポリシーの状況を報告する。


### Step 7: WDM syslog 分析 
**冒頭に必ず表示する:**
```
▶ Step 7 実行中: WDM syslog からルータごとにトランスポンダーで発生した事象を確認します...
```
Splunk の保存済みサーチを使いルータに接続されたトランスポンダーで発生した事象を確認し、原因を特定する。
利用可能な保存済みサーチ
- wdm_LSBIASCUR_over_time_by_router (Laser Bias Current, Tx side)
この値が高い場合、トランスポンダーの劣化が疑われる。
- wdm_FEC_BEF_COR_ER_over_time_by_router (Forward Error Correction Before Corrected Error, Rx side)
この値が高い場合、Tx 側のトランスポンダー、および光ファイバーの劣化が疑われる。
- wdm_LOSTOPCUR_over_time_by_router (Lost Optical Power Current between Tx and Rx)
lost_opcur の値が大きい場合、Tx 側のトランスポンダー、および光ファイバーの劣化が疑われる
- wdm_BDTEMPCUR_over_time_by_router (Board Temperature Current)
この値が高い場合、トランスポンダー装置のボード故障が疑われる
- wdm_EDTMPCUR_over_time_by_router
この値が高い場合、トランスポンダー装置の EDFA 故障が疑われる

### 根本原因とアクションの提示、現在のネットワークサービスレベルの確認
上記の保存済みサーチを利用し、Step 6 までで疑われたルーターに接続されている WDM トランスポンダーの状態を確認し、根本原因を推論する。
推論結果に基づき取るべきアクションを提案する。
また、最後に Step 1 の ThousandEyes によるサービスモニターの状態を確認し、SRTE ポリシーの切り替えにより現在ネットワークサービスは正常に復旧していることを確認する。

