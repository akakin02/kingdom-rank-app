import streamlit as st
import pandas as pd
import io
import google.generativeai as genai
import json
import difflib # 似ている文字を探すためのライブラリ（標準装備）

# ==========================================
# 1. 設定
# ==========================================

EVENT_STRUCTURE = {
    "討伐戦系": ["秦国討伐戦", "趙国討伐戦", "魏国討伐戦", "合従軍討伐戦"],
    "争覇戦系": ["争覇戦①", "争覇戦②", "争覇戦③"],
    "大同盟戦系": ["大同盟戦①", "大同盟戦②"]
}
MONTHS = [f"{i}月" for i in range(1, 13)]

st.set_page_config(page_title="キンラン同盟管理", layout="wide")
st.title("🏯 キングダム乱 同盟ランキング集計ツール (名簿連携版)")

# ==========================================
# 2. サイドバー（設定・入力）
# ==========================================
st.sidebar.header("⚙️ 設定")

# APIキー (Secretsから読み込む安全な方法)
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    st.error("設定エラー: APIキーが設定されていません。StreamlitのSecretsを設定してください。")
    st.stop()

# ★ここが追加：同盟員名簿のアップロード
st.sidebar.markdown("---")
st.sidebar.header("📂 同盟員名簿 (Excel)")
st.sidebar.info("A列に「名前」、B列に「コード」という見出しがあるExcelをアップロードしてください。")
master_file = st.sidebar.file_uploader("名簿Excelを選択", type=['xlsx'])

master_df = None
if master_file:
    try:
        master_df = pd.read_excel(master_file)
        # 必要な列があるかチェック
        if '名前' in master_df.columns and 'コード' in master_df.columns:
            st.sidebar.success(f"{len(master_df)} 名のデータを読み込みました")
            # データ型を文字列に変換しておく（エラー防止）
            master_df['名前'] = master_df['名前'].astype(str)
            master_df['コード'] = master_df['コード'].astype(str)
        else:
            st.sidebar.error("エラー: A列に「名前」、B列に「コード」が必要です")
            master_df = None
    except Exception as e:
        st.sidebar.error("Excelの読み込みに失敗しました")

st.sidebar.markdown("---")
st.sidebar.header("📅 イベント選択")
selected_month = st.sidebar.selectbox("開催月", MONTHS)
event_category = st.sidebar.selectbox("イベント種類", list(EVENT_STRUCTURE.keys()))
selected_event = st.sidebar.selectbox("詳細イベント名", EVENT_STRUCTURE[event_category])

# ==========================================
# 3. 便利な関数（AI解析 & 名寄せ）
# ==========================================

# 名前が似ている人を探す関数（AI読み取りミス対策）
def find_closest_name(target_name, name_list):
    if not isinstance(target_name, str):
        return None, 0.0
    
    # 完全に一致する人がいればそれを返す
    if target_name in name_list:
        return target_name, 1.0
    
    # 少し違う場合は、一番似ている人を探す (類似度0.6以上)
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=0.6)
    
    if matches:
        return matches[0], 0.8 # 似ている人がいた
    else:
        return None, 0.0 # 誰も似ていない

def analyze_images_with_gemini(api_key, uploaded_files):
    genai.configure(api_key=api_key)
    # 動作確認済みのモデルを指定
    model = genai.GenerativeModel('gemini-1.5-flash')

    all_data = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, file in enumerate(uploaded_files):
        status_text.text(f"AIが {i+1} / {len(uploaded_files)} 枚目を解析中...")
        
        try:
            image_bytes = file.getvalue()
            image_parts = [{"mime_type": file.type, "data": image_bytes}]

            prompt = """
            このゲームのランキング画像を解析し、以下の情報をJSON形式で抽出してください。
            順位(rank), プレイヤー名(name), ポイント/スコア(score)
            
            ルール:
            1. 数値のカンマは削除すること (例: 1,000 -> 1000)
            2. プレイヤー名が読み取れない場合は '不明' とする
            3. リスト形式で返すこと: [{"rank": 1, "name": "...", "score": 100}]
            4. JSON以外の文字列は一切出力しないこと
            """

            response = model.generate_content([prompt, image_parts[0]])
            text_result = response.text.replace("```json", "").replace("```", "").strip()
            json_data = json.loads(text_result)
            
            if isinstance(json_data, list):
                all_data.extend(json_data)
            
        except Exception as e:
            st.error(f"{file.name} の解析失敗: {e}")
        
        progress_bar.progress((i + 1) / len(uploaded_files))

    status_text.empty()
    progress_bar.empty()
    
    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df = df.rename(columns={'rank': '順位', 'name': '画像の名前', 'score': 'ポイント'})
    
    # 重複削除
    df = df.drop_duplicates(subset=['順位', '画像の名前'])
    
    # 数値変換とソート
    if '順位' in df.columns:
        df['順位'] = pd.to_numeric(df['順位'], errors='coerce')
        df = df.sort_values('順位')

    return df

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

# ==========================================
# 4. メイン画面
# ==========================================
st.header(f"【{selected_month}】 {selected_event}")

st.write("① ランキングのスクリーンショットをアップロード")
uploaded_files = st.file_uploader("画像をドラッグ＆ドロップ", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

if uploaded_files:
    if st.button("AI解析 & コード紐付け開始"):
        if not api_key:
            st.error("⚠️ 左のサイドバーにGoogle APIキーを入力してください！")
        else:
            # 1. 画像解析を実行
            with st.spinner('AIが画像を解析しています...'):
                df_result = analyze_images_with_gemini(api_key, uploaded_files)
            
            if not df_result.empty:
                # 2. 名簿データがある場合、紐付け処理を行う
                if master_df is not None:
                    with st.spinner('名簿と照合中...'):
                        # マスタの名前リストを作成
                        master_names = master_df['名前'].tolist()
                        
                        # 解析結果の各行について、一番似ている名前を探す
                        matched_names = []
                        matched_codes = []
                        
                        for img_name in df_result['画像の名前']:
                            best_match, score = find_closest_name(img_name, master_names)
                            if best_match:
                                matched_names.append(best_match)
                                # その名前のコードを取得
                                code = master_df[master_df['名前'] == best_match]['コード'].values[0]
                                matched_codes.append(code)
                            else:
                                matched_names.append("該当なし")
                                matched_codes.append("-")
                        
                        # 結果の表に追加
                        df_result.insert(1, '登録名', matched_names) # 2列目に挿入
                        df_result.insert(2, '盟員コード', matched_codes) # 3列目に挿入
                        
                        st.success("名簿との紐付けが完了しました！")
                else:
                    st.warning("※ 名簿ファイルがアップロードされていないため、コードの紐付けはスキップされました。")

                # 結果表示
                st.dataframe(df_result, use_container_width=True)
                
                # Excelダウンロード
                excel_data = to_excel(df_result)
                file_name = f"キンラン_{selected_month}_{selected_event}.xlsx"
                st.download_button(
                    label="📥 結果をExcelでダウンロード",
                    data=excel_data,
                    file_name=file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("データの抽出に失敗しました。")