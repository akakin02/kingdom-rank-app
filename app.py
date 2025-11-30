import streamlit as st
import pandas as pd
import io
import google.generativeai as genai
import json
import difflib

# ==========================================
# 1. デザイン設定（キングダム風CSS）
# ==========================================
st.set_page_config(page_title="同盟戦功表", layout="wide", initial_sidebar_state="collapsed")

# カスタムCSS: 秦国カラー（赤・金・黒）とモバイル最適化
st.markdown("""
<style>
    /* 全体の背景と文字色 */
    .stApp {
        background-color: #0e1117;
        color: #f0f2f6;
    }
    
    /* ヘッダー（金色の明朝体） */
    h1, h2, h3 {
        font-family: 'Yu Mincho', 'MS PMincho', serif;
        color: #d4af37 !important;
        text-shadow: 2px 2px 4px #000000;
        border-bottom: 2px solid #8b0000;
        padding-bottom: 10px;
    }
    
    /* ボタン（秦国の赤） - モバイルでタップしやすい大きさ */
    .stButton>button {
        background-color: #8b0000;
        color: white;
        font-weight: bold;
        border: 2px solid #d4af37;
        border-radius: 8px;
        width: 100%;
        padding: 15px 0;
        font-size: 18px;
        transition: 0.3s;
    }
    .stButton>button:hover {
        background-color: #a50000;
        border-color: #ffd700;
        color: #fff;
    }

    /* サイドバーのデザイン */
    [data-testid="stSidebar"] {
        background-color: #1c1c1c;
        border-right: 1px solid #d4af37;
    }
    
    /* アップロードエリアのデザイン */
    [data-testid="stFileUploader"] {
        background-color: #1e1e1e;
        border: 1px dashed #d4af37;
        padding: 20px;
        border-radius: 10px;
    }
    
    /* スマホでの余白調整 */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 5rem;
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
# 3. 内部ロジック（モデル選択は隠蔽）
# ==========================================

# APIキー読み込み（Secretsから）
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
except:
    st.error("⚠️ エラー: APIキー設定なし")
    st.stop()

def find_closest_name(target_name, name_list):
    if not isinstance(target_name, str): return None
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=0.6)
    return matches[0] if matches else None

def analyze_images_with_gemini(uploaded_files):
    # ★モデルはここで固定（画面には出さない）
    # ユーザー環境で成功した実績のあるFlashモデルを指定
    model = genai.GenerativeModel('gemini-1.5-flash')

    all_data = []
    
    # スマホ向けに進捗バーを表示
    progress_text = "戦況分析中..."
    my_bar = st.progress(0, text=progress_text)
    
    for i, file in enumerate(uploaded_files):
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
            
            if isinstance(json_data, list):
                all_data.extend(json_data)
        except:
            pass 
        
        my_bar.progress((i + 1) / len(uploaded_files), text=f"戦況分析中... ({i+1}/{len(uploaded_files)}枚)")

    my_bar.empty()
    
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
# 4. 画面構築（モバイルファースト）
# ==========================================

st.title("🏯 同盟戦功 集計本陣")

# 名簿アップロード（サイドバーに隠す）
with st.sidebar:
    st.header("📜 兵員名簿")
    master_file = st.file_uploader("名簿(Excel)を登録", type=['xlsx'])
    
    master_df = None
    if master_file:
        try:
            master_df = pd.read_excel(master_file)
            master_df['名前'] = master_df['名前'].astype(str)
            master_df['コード'] = master_df['コード'].astype(str)
            st.success(f"{len(master_df)}名の将軍を確認")
        except:
            st.error("名簿読込失敗")

# イベント選択（メイン画面上部に配置してスマホで選びやすく）
col1, col2, col3 = st.columns([1, 1.5, 1.5])
with col1:
    selected_month = st.selectbox("時期", MONTHS)
with col2:
    event_category = st.selectbox("戦場区分", list(EVENT_STRUCTURE.keys()))
with col3:
    selected_event = st.selectbox("戦場名", EVENT_STRUCTURE[event_category])

st.markdown("---")

# 画像アップロードエリア
st.markdown("### 📷 戦果報告書（スクショ）")
uploaded_files = st.file_uploader("ここに画像をアップロード", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True, label_visibility="collapsed")

if uploaded_files:
    st.write(f"計 {len(uploaded_files)} 枚の報告書を受領")
    
    # 大きな赤いボタン
    if st.button("全軍、集計開始！！"):
        with st.spinner('早馬を走らせております...'):
            df_result = analyze_images_with_gemini(uploaded_files)
        
        if not df_result.empty:
            # 名寄せ処理
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

            # 結果表示（スマホ用にコンテナ幅いっぱいに）
            st.markdown("### 📊 集計結果")
            st.dataframe(df_result, use_container_width=True)
            
            # ダウンロードボタン
            st.download_button(
                label="📥 書簡(Excel)として保管",
                data=to_excel(df_result),
                file_name=f"{selected_month}_{selected_event}_戦功表.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("報告書から文字を判読できませんでした。")