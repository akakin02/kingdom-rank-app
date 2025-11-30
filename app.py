import streamlit as st
import pandas as pd
import io
import google.generativeai as genai
import json
import difflib

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

# APIキー読み込み
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
except:
    st.error("設定エラー: StreamlitのSecretsに GOOGLE_API_KEY を設定してください。")
    st.stop()

# ★ここが新機能：使えるAIモデルを自動で探してリストにする
try:
    # サーバーで使えるモデル一覧を取得
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            name = m.name.replace("models/", "")
            available_models.append(name)
    
    # 使いやすそうな順に並べ替え（FlashやProを優先）
    available_models.sort(key=lambda x: "flash" not in x) 
    
    # セレクトボックスを表示
    selected_model_name = st.sidebar.selectbox("使用するAIモデル", available_models)

except Exception as e:
    # エラーが出た場合の保険
    st.sidebar.error(f"モデル一覧の取得に失敗: {e}")
    selected_model_name = "gemini-1.5-flash" # 強制デフォルト

st.sidebar.markdown("---")
st.sidebar.header("📂 同盟員名簿 (Excel)")
master_file = st.sidebar.file_uploader("名簿Excelを選択", type=['xlsx'])

master_df = None
if master_file:
    try:
        master_df = pd.read_excel(master_file)
        if '名前' in master_df.columns and 'コード' in master_df.columns:
            st.sidebar.success(f"{len(master_df)} 名のデータを読み込みました")
            master_df['名前'] = master_df['名前'].astype(str)
            master_df['コード'] = master_df['コード'].astype(str)
        else:
            st.sidebar.error("A列に「名前」、B列に「コード」が必要です")
    except:
        st.sidebar.error("Excel読み込み失敗")

st.sidebar.markdown("---")
st.sidebar.header("📅 イベント選択")
selected_month = st.sidebar.selectbox("開催月", MONTHS)
event_category = st.sidebar.selectbox("イベント種類", list(EVENT_STRUCTURE.keys()))
selected_event = st.sidebar.selectbox("詳細イベント名", EVENT_STRUCTURE[event_category])

# ==========================================
# 3. 処理ロジック
# ==========================================

def find_closest_name(target_name, name_list):
    if not isinstance(target_name, str): return None
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=0.6)
    return matches[0] if matches else None

def analyze_images_with_gemini(model_name, uploaded_files):
    # ★ユーザーが選んだモデル名を使う
    model = genai.GenerativeModel(model_name)

    all_data = []
    progress_bar = st.progress(0)
    
    for i, file in enumerate(uploaded_files):
        try:
            image_bytes = file.getvalue()
            image_parts = [{"mime_type": file.type, "data": image_bytes}]

            prompt = """
            このランキング画像を解析しJSONリスト形式で出力:
            [{"rank": 数値, "name": "名前", "score": 数値}]
            ※カンマ削除, 読み取れない場合は'不明'
            """

            response = model.generate_content([prompt, image_parts[0]])
            text_result = response.text.replace("```json", "").replace("```", "").strip()
            json_data = json.loads(text_result)
            
            if isinstance(json_data, list):
                all_data.extend(json_data)
        except Exception:
            pass # エラーはスキップ
        
        progress_bar.progress((i + 1) / len(uploaded_files))

    progress_bar.empty()
    if not all_data: return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df = df.rename(columns={'rank': '順位', 'name': '画像の名前', 'score': 'ポイント'})
    df = df.drop_duplicates(subset=['順位', '画像の名前'])
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
st.write("ランキング画像をアップロードしてください")
uploaded_files = st.file_uploader("画像をドラッグ＆ドロップ", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

if uploaded_files:
    if st.button("AI解析開始"):
        with st.spinner(f'AIモデル「{selected_model_name}」で解析中...'):
            df_result = analyze_images_with_gemini(selected_model_name, uploaded_files)
        
        if not df_result.empty:
            if master_df is not None:
                master_names = master_df['名前'].tolist()
                matched_names, matched_codes = [], []
                for img_name in df_result['画像の名前']:
                    best = find_closest_name(img_name, master_names)
                    if best:
                        matched_names.append(best)
                        code = master_df[master_df['名前'] == best]['コード'].values[0]
                        matched_codes.append(code)
                    else:
                        matched_names.append("該当なし")
                        matched_codes.append("-")
                df_result.insert(1, '登録名', matched_names)
                df_result.insert(2, '盟員コード', matched_codes)

            st.dataframe(df_result, use_container_width=True)
            
            st.download_button(
                label="📥 Excelダウンロード",
                data=to_excel(df_result),
                file_name=f"キンラン_{selected_month}_{selected_event}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("データの読み取りに失敗しました。別のAIモデルを選んで試してください。")