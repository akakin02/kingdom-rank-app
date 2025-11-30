import streamlit as st
import pandas as pd
import io
import google.generativeai as genai
import json
import difflib

# ==========================================
# 1. 究極のデザイン設定 (CSS)
# ==========================================
st.set_page_config(page_title="同盟戦功 本陣", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    /* ▼ 全体の世界観: 深い闇と戦場の空気 */
    .stApp {
        background: linear-gradient(to bottom, #0f0c29, #1a1a2e, #16213e);
        color: #e0e0e0;
        font-family: 'Yu Mincho', 'Hiragino Mincho ProN', serif;
    }

    /* ▼ ヘッダー: 黄金に輝くタイトル */
    h1 {
        font-family: 'Yu Mincho', serif;
        background: linear-gradient(to right, #bf953f, #fcf6ba, #b38728, #fbf5b7, #aa771c);
        -webkit-background-clip: text;
        color: transparent;
        text-shadow: 0px 0px 10px rgba(255, 215, 0, 0.3);
        font-weight: 800;
        text-align: center;
        padding-bottom: 20px;
        letter-spacing: 0.1em;
    }
    
    h3 {
        color: #d4af37 !important;
        border-left: 5px solid #8b0000;
        padding-left: 15px;
        margin-top: 30px;
    }

    /* ▼ コンテナ: ガラスのような質感（Glassmorphism） */
    .css-1r6slb0, .stFileUploader {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 215, 0, 0.2);
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
    }

    /* ▼ ボタン: 血塗られた深紅と黄金の縁取り */
    .stButton>button {
        background: linear-gradient(135deg, #8b0000 0%, #500000 100%);
        color: #ffd700;
        border: 1px solid #d4af37;
        border-radius: 5px;
        font-family: 'Yu Mincho', serif;
        font-weight: bold;
        letter-spacing: 0.1em;
        padding: 0.8em 2em;
        transition: all 0.3s ease;
        box-shadow: 0 5px 15px rgba(0,0,0,0.5);
    }
    
    .stButton>button:hover {
        background: linear-gradient(135deg, #a50000 0%, #800000 100%);
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(212, 175, 55, 0.4);
        border-color: #fff;
    }

    /* ▼ サイドバー: 闇の作戦室 */
    [data-testid="stSidebar"] {
        background-color: #0a0a0a;
        border-right: 1px solid #333;
    }

    /* ▼ テーブル(DataFrame): 洗練された黒 */
    [data-testid="stDataFrame"] {
        border: 1px solid #333;
    }
    
    /* スマホ調整 */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 3rem;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 設定データ
# ==========================================
EVENT_STRUCTURE = {
    "討伐戦": ["秦国討伐戦", "趙国討伐戦", "魏国討伐戦", "合従軍討伐戦"],
    "争覇戦": ["争覇戦①", "争覇戦②", "争覇戦③"],
    "大同盟戦": ["大同盟戦①", "大同盟戦②"]
}
MONTHS = [f"{i}月" for i in range(1, 13)]

# ==========================================
# 3. 内部ロジック
# ==========================================
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
except:
    st.error("⚠️ 本陣より通達: APIキーが設定されておりません。")
    st.stop()

def get_best_model():
    # 裏側で最適なモデルを静かに選定
    try:
        available_models = [m.name.replace("models/", "") for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m in available_models:
            if "flash" in m and "latest" in m: return m
        for m in available_models:
            if "flash" in m: return m
        return "gemini-1.5-flash"
    except:
        return "gemini-1.5-flash"

def find_closest_name(target_name, name_list):
    if not isinstance(target_name, str): return None
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=0.6)
    return matches[0] if matches else None

def analyze_images_with_gemini(uploaded_files):
    model_name = get_best_model()
    model = genai.GenerativeModel(model_name)
    all_data = []
    
    # カスタムプログレスバー表示
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, file in enumerate(uploaded_files):
        status_text.markdown(f"**⚔️ 戦況分析中... {i+1} / {len(uploaded_files)} 枚目**")
        try:
            image_bytes = file.getvalue()
            image_parts = [{"mime_type": file.type, "data": image_bytes}]
            prompt = """
            ランキング画像を解析しJSONリスト形式で出力せよ:
            [{"rank": 数値, "name": "名前", "score": 数値}]
            ※カンマ削除, 読み取れない場合は'不明'
            """
            response = model.generate_content([prompt, image_parts[0]])
            text_result = response.text.replace("```json", "").replace("```", "").strip()
            json_data = json.loads(text_result)
            if isinstance(json_data, list): all_data.extend(json_data)
        except:
            pass # エラーは静かに無視
        
        progress_bar.progress((i + 1) / len(uploaded_files))

    status_text.empty()
    progress_bar.empty()
    
    if not all_data: return pd.DataFrame()

    df = pd.DataFrame(all_data)
    df = df.rename(columns={'rank': '順位', 'name': '将軍名', 'score': '武功'})
    df = df.drop_duplicates(subset=['順位', '将軍名'])
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
# 4. 画面構築 (UI)
# ==========================================

st.markdown("# 🏯 大将軍 参謀本部")
st.markdown("<p style='text-align: center; color: #888; margin-bottom: 30px;'>同盟戦功 管理システム</p>", unsafe_allow_html=True)

# ▼ 設定エリア（アコーディオンで隠してスッキリさせる）
with st.expander("📜 兵員名簿の登録・更新（ここをタップ）"):
    st.info("ここに名簿Excel (A列:名前, B列:コード) を登録してください")
    master_file = st.file_uploader("名簿ファイル", type=['xlsx'], label_visibility="collapsed")
    master_df = None
    if master_file:
        try:
            master_df = pd.read_excel(master_file)
            master_df['名前'] = master_df['名前'].astype(str)
            master_df['コード'] = master_df['コード'].astype(str)
            st.success(f"✅ {len(master_df)} 名の将軍データを展開完了")
        except:
            st.error("名簿の読み込みに失敗しました")

# ▼ メイン操作エリア
st.markdown("### 🗓 戦場の選択")
col1, col2, col3 = st.columns([1, 1.5, 1.5])
with col1: selected_month = st.selectbox("時期", MONTHS)
with col2: event_category = st.selectbox("戦区", list(EVENT_STRUCTURE.keys()))
with col3: selected_event = st.selectbox("戦場名", EVENT_STRUCTURE[event_category])

st.markdown("### 📤 戦果報告書の提出")
st.caption("ランキングのスクリーンショットをまとめて提出してください")
uploaded_files = st.file_uploader("戦果報告書", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True, label_visibility="collapsed")

if uploaded_files:
    st.markdown(f"<div style='text-align:center; padding: 10px; color: #d4af37;'>計 {len(uploaded_files)} 枚の報告書を受領</div>", unsafe_allow_html=True)
    
    # 巨大なアクションボタン
    if st.button("全 軍 、 集 計 開 始 ！ ！"):
        with st.spinner('早馬を走らせております...'):
            df_result = analyze_images_with_gemini(uploaded_files)
        
        if not df_result.empty:
            # 名寄せ
            if master_df is not None:
                master_names = master_df['名前'].tolist()
                matched_names, matched_codes = [], []
                for img_name in df_result['将軍名']:
                    best = find_closest_name(img_name, master_names)
                    if best:
                        matched_names.append(best)
                        code = master_df[master_df['名前'] == best]['コード'].values[0]
                        matched_codes.append(code)
                    else:
                        matched_names.append("不明")
                        matched_codes.append("-")
                df_result.insert(1, '登録名', matched_names)
                df_result.insert(2, '盟員コード', matched_codes)

            st.markdown("---")
            st.markdown("### 🏆 戦功 恩賞確認")
            
            # データフレームを少しリッチに表示
            st.dataframe(
                df_result, 
                use_container_width=True,
                column_config={
                    "順位": st.column_config.NumberColumn(format="%d 位"),
                    "武功": st.column_config.NumberColumn(format="%d P"),
                }
            )
            
            # ダウンロード
            st.download_button(
                label="📥 戦功表(Excel)を保管する",
                data=to_excel(df_result),
                file_name=f"{selected_month}_{selected_event}_戦功表.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("⚠️ 報告書から文字を判読できませんでした。画像の鮮明さを確認してください。")