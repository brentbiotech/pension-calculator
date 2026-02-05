import streamlit as st
import pdfplumber
import re
from datetime import date, timedelta, datetime
import math

# --- 設定：歷年郵局一年期定存固定利率 (百分比) ---
# 資料來源整理自勞保局與郵局歷史資料
INTEREST_RATES = {
    2009: 1.39, 2010: 0.83, 2011: 1.08, 
    2012: 1.37, 2013: 1.37, 2014: 1.37, 2015: 1.37,
    2016: 1.20, 2017: 1.04, 2018: 1.04, 2019: 1.04, 2020: 1.04,
    2021: 0.78, 2022: 0.78, 
    2023: 1.475, 2024: 1.600, 2025: 1.725, 2026: 1.725  # 2026 暫定沿用
}

def get_rate(year):
    """取得該年度的利率，若無資料則回傳最近一年的資料"""
    return INTEREST_RATES.get(year, INTEREST_RATES[max(INTEREST_RATES.keys())])

def parse_pdf(file):
    """
    嘗試從 PDF 中提取「應繳金額」與「繳費期限」。
    注意：不同版本的繳費單格式可能不同，這裡使用常見的關鍵字進行正則表達式搜尋。
    """
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    
    # 預設值
    amount = 0
    deadline = date.today()

    # 1. 嘗試抓取金額 (常見關鍵字：合計、應繳總金額)
    # 尋找 "合計" 或 "金額" 後面的數字，允許包含千分位逗號
    amt_match = re.search(r'(應繳總金額|合計|小計)\s*[:：]?\s*[\$NTD]*\s*([0-9,]+)', text)
    if amt_match:
        try:
            amount_str = amt_match.group(2).replace(',', '')
            amount = int(amount_str)
        except:
            pass

    # 2. 嘗試抓取日期 (常見格式：112/01/31 或 112.01.31 或 2023/01/31)
    # 這裡針對民國年格式 (如 1120131 或 112/01/31) 進行粗略搜尋
    date_match = re.search(r'繳費期限\s*[:：]?\s*(\d{2,3})[./]?(\d{2})[./]?(\d{2})', text)
    if date_match:
        try:
            y, m, d = date_match.groups()
            year = int(y) + 1911 # 轉西元
            deadline = date(year, int(m), int(d))
        except:
            pass

    return text, amount, deadline

def calculate_interest(principal, deadline_date, payment_date):
    """
    核心計算邏輯
    公式：本金 × 利率 × (天數/365)
    規則：分段計算、小數點第二位無條件捨去、最後四捨五入
    """
    start_date = deadline_date + timedelta(days=1)
    end_date = payment_date - timedelta(days=1)
    
    if start_date > end_date:
        return 0, []

    current = start_date
    breakdown = []
    total_interest_raw = 0.0

    # 逐日計算 (為了精確處理跨年度利率變動，雖然迴圈較多但邏輯最穩)
    # 優化版：按年份分段計算
    
    iter_date = start_date
    while iter_date <= end_date:
        year = iter_date.year
        # 找出這一年在區間內的結束點 (年底或繳費前一日)
        year_end = date(year, 12, 31)
        segment_end = min(year_end, end_date)
        
        days_in_segment = (segment_end - iter_date).days + 1
        rate = get_rate(year)
        
        # 該段利息 = 本金 * 利率% * 天數 / 365
        # 依規：小數點以下第2位無條件捨去 (即保留1位)
        interest_segment = (principal * rate * 0.01 * days_in_segment) / 365
        interest_truncated = math.floor(interest_segment * 10) / 10.0
        
        breakdown.append({
            "year": year,
            "days": days_in_segment,
            "rate": rate,
            "interest": interest_truncated
        })
        
        total_interest_raw += interest_truncated
        
        # 推進到下一段
        iter_date = segment_end + timedelta(days=1)

    # 最後總利息四捨五入
    final_interest = int(round(total_interest_raw + 0.00001)) # +epsilon 處理 .5 進位問題
    
    return final_interest, breakdown

# --- Streamlit 介面 ---

st.set_page_config(page_title="國民年金利息試算器", layout="centered")

st.title("🧮 國民年金遲繳利息試算")
st.markdown("上傳您的繳費單 PDF，系統將嘗試自動讀取金額與期限，並依據[勞保局規定](https://www.bli.gov.tw/0014977.html)計算滯納利息。")

uploaded_file = st.file_uploader("請上傳國民年金繳費單 (PDF)", type="pdf")

# 初始化變數
default_amount = 0
default_deadline = date.today() - timedelta(days=30)
pdf_text_debug = ""

if uploaded_file is not None:
    with st.spinner("正在分析 PDF..."):
        # 呼叫解析函式
        pdf_text_debug, extracted_amount, extracted_deadline = parse_pdf(uploaded_file)
        
        # --- 除錯區塊 START ---
        with st.expander("🛠️ 開發者除錯模式 (點擊展開)", expanded=True):
            st.info(f"偵測到的金額: {extracted_amount}")
            st.info(f"偵測到的日期: {extracted_deadline}")
            
            if not pdf_text_debug.strip():
                st.error("⚠️ 警告：無法從 PDF 中提取任何文字！")
                st.markdown("這張 PDF 可能是**「掃描圖片」**而非文字檔，`pdfplumber` 無法讀取圖片內的文字。請改用電子帳單 PDF，或是需要加入 OCR (文字辨識) 功能。")
            else:
                st.text_area("PDF 原始讀取內容 (請檢查關鍵字是否存在)", pdf_text_debug, height=300)
        # --- 除錯區塊 END ---

        if extracted_amount > 0:
            default_amount = extracted_amount
            st.success("✅ 已成功讀取金額！")
        if extracted_deadline != date.today():
            default_deadline = extracted_deadline
            st.success(f"✅ 已成功讀取繳費期限：{default_deadline}")

# 輸入區塊 (允許使用者手動修正)
with st.container():
    col1, col2 = st.columns(2)
    with col1:
        amount = st.number_input("繳費單本金 (元)", min_value=0, value=default_amount, step=100)
    with col2:
        deadline = st.date_input("繳費期限", value=default_deadline)
    
    pay_date = st.date_input("預計繳費日期", value=date.today())

# 計算按鈕
if st.button("計算利息", type="primary"):
    if pay_date <= deadline:
        st.info("🎉 在期限內繳費，無需支付利息！")
    else:
        interest, details = calculate_interest(amount, deadline, pay_date)
        
        # 顯示結果
        st.divider()
        if interest <= 30:
            st.subheader(f"試算利息：{interest} 元")
            st.success("✨ 依規定，利息總額在 30 元(含)以下免徵，您**不需要**繳納利息。")
        else:
            st.subheader(f"應繳利息：{interest} 元")
            st.warning("⚠️ 利息超過 30 元，需一併繳納。")
            
        # 顯示詳細計算過程
        with st.expander("查看詳細計算過程"):
            st.write(f"**計息區間**：{deadline + timedelta(days=1)} 至 {pay_date - timedelta(days=1)}")
            st.write("**計算公式**：本金 × 利率 × (天數/365)，分段計算後加總四捨五入。")
            
            for row in details:
                st.write(f"- **{row['year']}年度** (利率 {row['rate']}%)：延遲 {row['days']} 天 → 利息 {row['interest']} 元")
            
            st.write(f"**總計 (未捨入)**：{sum(d['interest'] for d in details):.1f} 元")

# 除錯區 (選用)
# with st.expander("查看 PDF 原始文字 (除錯用)"):
#     st.text(pdf_text_debug)
