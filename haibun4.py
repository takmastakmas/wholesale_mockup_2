import pandas as pd
import streamlit as st
from datetime import datetime

def allocate_stock_recursive(customers, logic_stock):
    """
    【ロジック用在庫】に対して、
    再帰的に「配分比率 × 在庫数」を割り当てる関数。

    Parameters
    ----------
    customers: list of dict
        [
            {
                "name": 得意先名,
                "ratio": 配分比率 (0.0 ~ 1.0),
                "demand": 希望数量(受注数量),
            },
            ...
        ]
    logic_stock: int
        今回のロジックで配分する在庫数(裁量で除外した分を引いた後の在庫)

    Returns
    -------
    customers: list of dict
        "allocated" (float)キーで配分結果を保持。
        最終的には round() で整数化済みの割当数が入る。
    """

    # 1) 初期割当: ratio * logic_stock を、その得意先の希望数量(demand)上限で割り当て
    for c in customers:
        init_alloc = c["ratio"] * logic_stock
        c["allocated"] = min(init_alloc, c["demand"])

    used = sum(c["allocated"] for c in customers)
    leftover = logic_stock - used

    # 2) leftover を再帰的に配分する関数
    def redistribute_recursive(customer_list, lf):
        if lf <= 0:
            return lf

        # 需要が残っている得意先の ratio 合計を求める
        ratio_sum = 0.0
        for cust in customer_list:
            remain = cust["demand"] - cust["allocated"]
            if remain > 0:
                ratio_sum += cust["ratio"]

        if ratio_sum == 0:
            return lf

        allocated_this_round = 0.0
        for cust in customer_list:
            remain = cust["demand"] - cust["allocated"]
            if remain > 0:
                # 再正規化した比率で leftover を配分
                portion = lf * (cust["ratio"] / ratio_sum)
                actual = min(portion, remain)
                cust["allocated"] += actual
                allocated_this_round += actual

        lf -= allocated_this_round

        # まだ leftover が残る場合は再帰
        if lf > 0 and allocated_this_round > 0:
            lf = redistribute_recursive(customer_list, lf)

        return lf

    # 3) 再帰的に leftover を配分
    leftover = redistribute_recursive(customers, leftover)

    # 4) 整数に丸める (ルールに応じて変更可能)
    for c in customers:
        c["allocated"] = round(c["allocated"])

    return customers


def main():
    st.title("配分作成アプリ")

    # CSVファイルのアップロード
    uploaded_file = st.file_uploader("CSVファイルをアップロードしてください", type="csv")
    if uploaded_file:
        # データ読み込み
        df = pd.read_csv(uploaded_file)

        # 集計処理
        grouped = df.groupby(['得意先コード', '得意先名']).agg({
            '年月': pd.Series.nunique,      # 年月のユニーク数
            '売上日付ユニーク数': 'sum',   # 売上日付ユニーク数の合計
            '数量合計': 'sum',             # 数量合計
            '売上金額合計': 'sum',         # 売上金額合計
        }).reset_index()
        grouped.rename(columns={
            '年月': '注文月数',
            '売上日付ユニーク数': '注文回数',
            '数量合計': '数量計',
            '売上金額合計': '売上計'
        }, inplace=True)

        # 売上金額合計でソート
        grouped = grouped.sort_values(by='売上計', ascending=False)
        st.write("集計結果:")
        st.dataframe(grouped)

        # 得意先名順にソート
        grouped = grouped.sort_values(by='得意先名')

        # ドロップダウンボックスで得意先を選択
        selected_clients = st.multiselect(
            "得意先を選択してください（得意先名順）:",
            options=grouped['得意先名'].unique()
        )
        
        if selected_clients:
            filtered_data = grouped[grouped['得意先名'].isin(selected_clients)]
            st.write("選択された得意先のデータ:")
            st.dataframe(filtered_data)

            # セッションステートで発注数量を管理
            if "order_quantities" not in st.session_state:
                st.session_state.order_quantities = {}

            # 得意先からの受注数量を入力
            st.write("得意先からの受注数量を入力してください:")
            for client in selected_clients:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(client)
                with col2:
                    current_quantity = st.session_state.order_quantities.get(client, 0)
                    st.session_state.order_quantities[client] = st.number_input(
                        label="受注数量",
                        min_value=0,
                        step=1,
                        value=current_quantity,
                        key=f"order_quantity_{client}"
                    )
                    
            # ループ後に合計を集計して表示
            total_demand_input = sum(st.session_state.order_quantities[client] for client in selected_clients)
            st.write(f"受注数量合計: **{total_demand_input}** 個")

            # 商品の総数（入荷）
            total_products = st.number_input("商品の入荷数を入力してください", min_value=0, step=1)

            # 裁量比率を入力
            discretion_ratio = st.number_input(
                "裁量比率を入力してください (0 ~ 1の範囲)",
                min_value=0.0, max_value=1.0,
                step=0.1, value=0.3
            )

            # セッションステートで各集計データの重みを管理
            if "weights" not in st.session_state:
                st.session_state.weights = {
                    "weight_1": 0.5,
                    "weight_2": 0.5,
                    "weight_3": 0.5,
                    "weight_4": 0.5,
                }

            def reset_weights():
                """リセットボタンが押されたときの処理"""
                st.session_state.weights = {
                    "weight_1": 0.5,
                    "weight_2": 0.5,
                    "weight_3": 0.5,
                    "weight_4": 0.5,
                }
            
            # スライダーと数値入力を同期するヘルパー関数
            def sync_slider_and_input(label, key):
                col1, col2 = st.columns([3, 1])
                with col1:
                    slider_value = st.slider(
                        f"{label} (スライダー)",
                        0.0, 1.0,
                        st.session_state.weights[key],
                        key=f"slider_{key}"
                    )
                with col2:
                    number_value = st.number_input(
                        f"{label} (数値入力)",
                        0.0, 1.0,
                        st.session_state.weights[key],
                        key=f"input_{key}"
                    )
                if slider_value != st.session_state.weights[key]:
                    st.session_state.weights[key] = slider_value
                elif number_value != st.session_state.weights[key]:
                    st.session_state.weights[key] = number_value

            st.write("各集計データの重みを設定してください:")
            sync_slider_and_input("取引年月の重み", "weight_1")
            sync_slider_and_input("注文回数の重み", "weight_2")
            sync_slider_and_input("数量合計の重み", "weight_3")
            sync_slider_and_input("売上金額合計の重み", "weight_4")

            # 配分計算ボタン
            if st.button("配分計算"):
                # 0除算回避用
                def safe_div(x, y):
                    return x / y if y != 0 else 0

                # スコア計算
                filtered_data['年月スコア'] = filtered_data.apply(
                    lambda r: safe_div(r['注文月数'], filtered_data['注文月数'].sum()) * st.session_state.weights["weight_1"],
                    axis=1
                )
                filtered_data['注文回数スコア'] = filtered_data.apply(
                    lambda r: safe_div(r['注文回数'], filtered_data['注文回数'].sum()) * st.session_state.weights["weight_2"],
                    axis=1
                )
                filtered_data['数量スコア'] = filtered_data.apply(
                    lambda r: safe_div(r['数量計'], filtered_data['数量計'].sum()) * st.session_state.weights["weight_3"],
                    axis=1
                )
                filtered_data['売上金額スコア'] = filtered_data.apply(
                    lambda r: safe_div(r['売上計'], filtered_data['売上計'].sum()) * st.session_state.weights["weight_4"],
                    axis=1
                )

                # 総合スコア
                filtered_data['スコア'] = (
                    filtered_data['年月スコア'] +
                    filtered_data['注文回数スコア'] +
                    filtered_data['数量スコア'] +
                    filtered_data['売上金額スコア']
                )

                total_score = filtered_data['スコア'].sum()
                if total_score > 0:
                    filtered_data['配分比率'] = filtered_data['スコア'] / total_score
                else:
                    filtered_data['配分比率'] = 0

                # 受注数量を取得
                order_quantities = st.session_state.order_quantities
                filtered_data['受注数量'] = filtered_data['得意先名'].map(order_quantities)

                # 裁量分・ロジック分の在庫計算
                # 例: total_products=100, discretion_ratio=0.3 => 裁量30、ロジック70
                discretion_stock = round(total_products * discretion_ratio)
                logic_stock = total_products - discretion_stock

                # 再帰配分用のリストに格納
                customers = []
                for i, row in filtered_data.iterrows():
                    customers.append({
                        "name": row['得意先名'],
                        "ratio": row['配分比率'],
                        "demand": row['受注数量'] if row['受注数量'] is not None else 0,
                        "allocated": 0.0
                    })

                # ロジック在庫を再帰的に配分
                result_customers = allocate_stock_recursive(customers, logic_stock)

                # 結果をDataFrame化
                allocation_df = pd.DataFrame(result_customers)
                allocation_df.rename(columns={
                    "name": "得意先名",
                    "ratio": "配分比率",
                    "demand": "受注数量",
                    "allocated": "配分結果"
                }, inplace=True)

                allocation_df = allocation_df.sort_values(by='配分比率', ascending=False)
                # st.write("配分結果:")
                # st.dataframe(allocation_df)

                # ---- 各種指標の保存 ----
                # 入庫数
                st.session_state.total_stock_input = total_products
                # 希望数量合計
                st.session_state.total_demand = allocation_df["受注数量"].sum()
                # 実際の配分合計 (ロジック分)
                st.session_state.total_allocated = allocation_df['配分結果'].sum()
                # ロジック在庫の残り
                leftover_logic = logic_stock - st.session_state.total_allocated
                # 裁量在庫
                # → (discretion_stock) はユーザーが配分しないで確保した分
                # さらに leftover_logic があれば、ロジックで配りきれていない残がある。
                # ここでは「裁量分」と「ロジック未配分」合わせて「未配分合計」と考えてもよい。
                # 例: 裁量30 + ロジック残5 = 35
                # ただし仕様によっては表示を分けるなど運用要件に応じて調整可能。
                # 裁量在庫 + ロジック未配分分
                st.session_state.not_allocated_total = discretion_stock + leftover_logic

                csv_data = allocation_df.to_csv(index=False).encode("utf-8")

                # 配分結果をセッション状態に保存
                st.session_state.allocation_df = allocation_df.copy()
                st.session_state.csv_data = csv_data

            # 配分結果が計算済みの場合のみ表示
            if "allocation_df" in st.session_state:
                st.write("配分結果:")
                st.dataframe(st.session_state.allocation_df)
                st.write(f"希望数量合計: {int(st.session_state.total_demand)} 個")
                st.write(f"入荷数: {int(st.session_state.total_stock_input)} 個")
                st.write(f"ロジック配分合計: {int(st.session_state.total_allocated)} 個")
                st.write(f"裁量分計: {int(st.session_state.not_allocated_total)} 個")
                # ユーザーにファイル名を入力させる
                now_str = datetime.now().strftime("%Y%m%d_%H%M")
                default_filename = f"配分結果_{now_str}.csv"
                user_filename = st.text_input("保存するファイル名を入力してEnterを押してください（拡張子 .csv を含む）", value=default_filename)

                # ファイル名確認ボタン
                if st.button("ファイル名確認"):
                    if user_filename:
                        st.success(f"入力されたファイル名: {user_filename}")
                    else:
                        st.error("ファイル名を入力してください。")

                # ダウンロードボタン
                if st.download_button(
                    label="配分結果をCSVでダウンロード",
                    data=st.session_state.csv_data,
                    file_name=user_filename,
                    mime="text/csv"
                ):
                    st.success(f"ファイル {user_filename} を保存しました！")

            if st.button("重みのリセット（2回押す）"):
                reset_weights()
            
if __name__ == "__main__":
    main()
