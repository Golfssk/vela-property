import streamlit as st
import pandas as pd
import altair as alt
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from supabase import create_client, Client
from datetime import datetime, timedelta

from thai_num import baht_text, fmt_money

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(
    page_title="VELA — Property Agent OS ปากช่อง",
    page_icon="🏔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

SUPABASE_URL = "https://vfieyjxlrpziiksyccdt.supabase.co"
SUPABASE_KEY = "sb_publishable_udkJwGJ8zjXlEOlYszDRUg_yVD4g7ie"

# ---- อ้างอิงตรงกับ line_bot.py: 12 ตำบลจริงของ อ.ปากช่อง ----
TAMBON_CENTROIDS = {
    "ปากช่อง": (14.7050, 101.4160),
    "หมูสี": (14.5060, 101.3720),
    "กลางดง": (14.6300, 101.2570),
    "จันทึก": (14.6820, 101.5540),
    "วังกะทะ": (14.4340, 101.5000),
    "หนองน้ำแดง": (14.6110, 101.4020),
    "หนองสาหร่าย": (14.7360, 101.3680),
    "ขนงพระ": (14.6250, 101.4600),
    "โป่งตาลอง": (14.5480, 101.4530),
    "คลองม่วง": (14.7860, 101.5820),
    "วังไทร": (14.7620, 101.4820),
    "พญาเย็น": (14.6190, 101.1820),
}
VALID_TAMBONS = list(TAMBON_CENTROIDS.keys())
MAP_CENTER = TAMBON_CENTROIDS["ปากช่อง"]

SELLER_TYPES = ["เจ้าของ", "นายหน้า", "โครงการ"]
LISTING_STATUSES = ["ใหม่", "กำลังต่อรอง", "ปิดการขาย", "ถอนออก"]
CRM_STATUSES = ["ใหม่", "ติดต่อแล้ว", "นัดชม", "ปิดการขาย", "ไม่สนใจแล้ว"]

CONFIDENCE_ICON = {"exact": "✅", "estimated": "🟡", "unknown": "❌"}
CONFIDENCE_LABEL = {
    "exact": "พิกัดแม่นยำ",
    "estimated": "ประมาณจากตำบล",
    "unknown": "ยังไม่มีพิกัด",
}

CONTRACT_LABELS = {
    "นายหน้าเปิด": "สัญญานายหน้าแบบเปิด",
    "นายหน้าปิด": "สัญญานายหน้าแบบปิด",
    "ใบจอง": "สัญญาจองซื้อ",
    "สัญญาจะซื้อจะขาย": "สัญญาจะซื้อจะขาย",
}

# =========================================================
# STYLE — Apple-inspired (SF Pro/Inter, single Action Blue accent)
# =========================================================
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --primary:#0066cc;
  --primary-focus:#0071e3;
  --primary-on-dark:#2997ff;
  --ink:#1d1d1f;
  --ink-muted-80:#333333;
  --ink-muted-48:#7a7a7a;
  --divider-soft:#f0f0f0;
  --hairline:#e0e0e0;
  --canvas:#ffffff;
  --canvas-parchment:#f5f5f7;
  --surface-pearl:#fafafc;
  --surface-black:#000000;
  --on-primary:#ffffff;
  --on-dark:#ffffff;
}
#MainMenu, footer {visibility:hidden;}
.stApp{
  background:var(--canvas);
}
.stApp, .stApp p, .stApp span, .stApp div, .stApp label, .stApp li{
  font-family:'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  color:var(--ink);
  font-size:17px;
  line-height:1.47;
  letter-spacing:-0.374px;
}
.stApp h1, .stApp h2, .stApp h3{
  font-family:'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  font-weight:600;
  letter-spacing:-0.374px;
  color:var(--ink);
}
section[data-testid="stSidebar"]{
  background:var(--surface-black);
}
section[data-testid="stSidebar"] *{
  color:var(--on-dark) !important;
}
section[data-testid="stSidebar"] .stRadio label{
  font-size:0.92rem;
}
section[data-testid="stSidebar"] input[type="radio"]{
  accent-color:var(--primary);
}
.stButton>button, .stFormSubmitButton>button{
  background:var(--primary);
  color:var(--on-primary);
  border:none;
  border-radius:9999px;
  font-weight:400;
  font-size:16px;
  padding:10px 20px;
  transition:transform 0.1s ease, background 0.15s ease;
}
.stButton>button:hover, .stFormSubmitButton>button:hover{
  background:var(--primary-focus);
  color:var(--on-primary);
}
.stButton>button:active, .stFormSubmitButton>button:active{
  transform:scale(0.95);
}
div[data-testid="stMetric"]{
  background:var(--canvas);
  border:1px solid var(--hairline);
  padding:24px;
  border-radius:18px;
}
div[data-testid="stMetric"] label{
  color:var(--ink-muted-48) !important;
  font-size:14px !important;
  font-weight:600 !important;
  letter-spacing:-0.224px !important;
}
div[data-testid="stMetricValue"]{
  color:var(--ink) !important;
  font-weight:600 !important;
  letter-spacing:-0.374px !important;
}
.hero-banner{
  position:relative;
  min-height:320px;
  border-radius:0px;
  overflow:hidden;
  display:flex;
  align-items:flex-end;
  padding:56px 48px;
  margin-bottom:0px;
  background:
    linear-gradient(180deg, rgba(0,0,0,0.15) 0%, rgba(0,0,0,0.35) 55%, rgba(0,0,0,0.78) 100%),
    url('https://images.unsplash.com/photo-1470770903676-69b98201ea1c?q=80&w=1800&auto=format&fit=crop') center/cover no-repeat;
}
.hero-eyebrow{color:var(--primary-on-dark); font-weight:600; font-size:14px; letter-spacing:-0.224px; margin-bottom:12px;}
.hero-title{color:var(--on-dark); font-weight:600; font-size:2.3rem; line-height:1.1; letter-spacing:-0.028em; margin:0;}
.hero-sub{color:#cccccc; max-width:600px; margin-top:14px; font-size:1.05rem; font-weight:400; line-height:1.4;}
.section-title{
  font-weight:600; font-size:1.6rem; color:var(--ink); letter-spacing:-0.374px;
  margin:36px 0 18px 0; padding-bottom:0;
}
.zone-card{
  background:var(--canvas); border:1px solid var(--hairline); padding:22px; border-radius:18px; height:100%;
}
.zone-card .tag{color:var(--ink-muted-48); font-weight:600; font-size:0.8rem; margin-bottom:8px; letter-spacing:-0.224px;}
.zone-card h4{font-weight:600; margin:0 0 6px 0; color:var(--ink); font-size:1.1rem; letter-spacing:-0.374px;}
.zone-card p{font-size:0.88rem; color:var(--ink-muted-80); margin:0; line-height:1.5;}
.listing-card{
  background:var(--canvas); border:1px solid var(--hairline); border-radius:18px;
  padding:22px; margin-bottom:14px;
}
.listing-card .badge-row{margin-bottom:12px;}
.listing-card .zone-badge{
  display:inline-block; font-size:0.72rem; padding:4px 12px; border-radius:9999px;
  background:var(--surface-pearl); color:var(--ink-muted-80); font-weight:600;
  margin-right:6px; margin-bottom:6px; border:1px solid var(--hairline);
}
.listing-card h4{color:var(--ink); font-weight:600; margin:0 0 2px 0; font-size:1.05rem; letter-spacing:-0.374px;}
.listing-card .project{color:var(--ink-muted-48); font-size:0.85rem; margin:0 0 8px 0;}
.listing-card .price{color:var(--ink); font-weight:600; font-size:1.25rem; margin:6px 0; letter-spacing:-0.374px;}
.listing-card .meta{color:var(--ink-muted-48); font-size:0.83rem; line-height:1.6;}
.listing-card .highlight{color:var(--ink-muted-80); font-size:0.85rem; margin-top:8px; font-style:normal;}
.listing-card a{color:var(--primary); font-size:0.85rem;}
.lead-card{
  background:var(--canvas); border:1px solid var(--hairline); padding:18px 22px; margin-bottom:12px; border-radius:18px;
}
.lead-card h5{margin:0 0 6px 0; font-weight:600; color:var(--ink); font-size:1rem; letter-spacing:-0.374px;}
.lead-card .lead-meta{font-size:0.85rem; color:var(--ink-muted-48); line-height:1.6;}
.contract-card{
  background:var(--canvas); border:1px solid var(--hairline); padding:16px 20px; margin-bottom:10px; border-radius:18px;
  display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;
}
.contract-card .ctype{font-weight:600; color:var(--ink); font-size:0.98rem;}
.contract-card .cmeta{color:var(--ink-muted-48); font-size:0.82rem;}
.info-box{
  background:var(--canvas-parchment); border:1px solid var(--hairline); padding:20px 24px; border-radius:18px;
  color:var(--ink-muted-80); font-size:0.92rem; line-height:1.6;
}
.empty-box{
  border:1px dashed var(--hairline); padding:32px; text-align:center; color:var(--ink-muted-48); border-radius:18px;
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# SUPABASE + DATA
# =========================================================
@st.cache_resource
def get_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_client()


@st.cache_data(ttl=60)
def load_market_scout():
    res = supabase.table("pakchong_market_scout").select("*").order("created_at", desc=True).execute()
    return pd.DataFrame(res.data)


@st.cache_data(ttl=60)
def load_crm():
    res = supabase.table("pakchong_crm").select("*").order("created_at", desc=True).execute()
    return pd.DataFrame(res.data)


@st.cache_data(ttl=60)
def load_contracts():
    res = supabase.table("contract_logs").select("*").order("created_at", desc=True).execute()
    return pd.DataFrame(res.data)


def refresh_data():
    load_market_scout.clear()
    load_crm.clear()
    load_contracts.clear()


def fmt_baht(v):
    if v is None or pd.isna(v):
        return "ไม่ระบุราคา"
    return f"{fmt_money(v)} บาท"


def confidence_tag(row):
    conf = row.get("location_confidence") or "unknown"
    icon = CONFIDENCE_ICON.get(conf, "❌")
    label = CONFIDENCE_LABEL.get(conf, "ยังไม่มีพิกัด")
    return f"{icon} {label}"


# =========================================================
# SIDEBAR NAV
# =========================================================
with st.sidebar:
    st.markdown("### 🏔️ VELA")
    st.caption("Property Agent OS · อ.ปากช่อง")
    page = st.radio(
        "เมนู",
        ["🏠 ภาพรวม", "📍 Market Scout", "📊 วิเคราะห์ตลาด", "👥 CRM", "📑 สัญญาที่ออกแล้ว", "🛠️ เครื่องมือ / เพิ่มข้อมูล"],
        label_visibility="collapsed",
    )
    st.divider()
    if st.button("🔄 รีเฟรชข้อมูล"):
        refresh_data()
        st.rerun()

try:
    df_market = load_market_scout()
except Exception as e:
    df_market = pd.DataFrame()
    st.sidebar.error(f"โหลด Market Scout ไม่สำเร็จ: {e}")

try:
    df_crm = load_crm()
except Exception as e:
    df_crm = pd.DataFrame()
    st.sidebar.error(f"โหลด CRM ไม่สำเร็จ: {e}")

try:
    df_contracts = load_contracts()
except Exception as e:
    df_contracts = pd.DataFrame()
    st.sidebar.error(f"โหลดสัญญาไม่สำเร็จ (ตาราง contract_logs): {e}")


# =========================================================
# PAGE: ภาพรวม
# =========================================================
if page == "🏠 ภาพรวม":
    st.markdown("""
    <div class="hero-banner">
      <div>
        <div class="hero-eyebrow">Market Scout • CRM • Content Studio • Legal • Tax • Valuation</div>
        <p class="hero-title">Vela Property Agent OS</p>
        <p class="hero-sub">ระบบหลังบ้านของทีมขายอสังหาฯ อ.ปากช่อง เชื่อมกับ LINE OA แบบเรียลไทม์ — พนักงานพิมพ์ในไลน์ ข้อมูลมาโผล่ที่นี่</p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    total_listings = len(df_market)
    avg_price_sqw = df_market["price_per_sq_wah"].dropna().mean() if not df_market.empty and "price_per_sq_wah" in df_market else None
    total_leads = len(df_crm)
    total_contracts = len(df_contracts)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ประกาศในระบบ", total_listings)
    c2.metric("ราคาเฉลี่ย/ตร.วา", f"{fmt_money(avg_price_sqw)} บาท" if avg_price_sqw else "—")
    c3.metric("ลูกค้าในระบบ", total_leads)
    c4.metric("สัญญาที่ออกแล้ว", total_contracts)

    if not df_market.empty and "created_at" in df_market.columns:
        since = (datetime.now() - timedelta(days=7)).isoformat()
        recent_mask = df_market["created_at"].astype(str) >= since
        recent_count = int(recent_mask.sum())
        st.caption(f"📈 7 วันล่าสุด: บันทึกทรัพย์ใหม่ {recent_count} รายการ")

    st.markdown('<div class="section-title">ตำบลที่มีทรัพย์เข้าเยอะที่สุด</div>', unsafe_allow_html=True)
    if df_market.empty or "location_zone" not in df_market.columns:
        st.markdown('<div class="empty-box">ยังไม่มีข้อมูลทรัพย์ในระบบ — บันทึกทรัพย์แรกผ่านเมนู "บันทึกตลาด" บน LINE OA หรือหน้า "เครื่องมือ / เพิ่มข้อมูล"</div>', unsafe_allow_html=True)
    else:
        zone_counts = df_market["location_zone"].value_counts().head(4)
        cols = st.columns(len(zone_counts)) if len(zone_counts) > 0 else []
        for col, (zone, count) in zip(cols, zone_counts.items()):
            zone_avg = df_market[df_market["location_zone"] == zone]["price_per_sq_wah"].dropna().mean()
            avg_text = f"{fmt_money(zone_avg)} บาท/ตร.วา (เฉลี่ย)" if pd.notnull(zone_avg) else "ยังไม่มีข้อมูลราคา/ตร.วา"
            with col:
                st.markdown(f"""
                <div class="zone-card">
                  <div class="tag">{count} รายการในระบบ</div>
                  <h4>ต.{zone}</h4>
                  <p>{avg_text}</p>
                </div>
                """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">ประกาศล่าสุด</div>', unsafe_allow_html=True)
    if df_market.empty:
        st.markdown('<div class="empty-box">ยังไม่มีประกาศในระบบ</div>', unsafe_allow_html=True)
    else:
        latest = df_market.head(3)
        cols = st.columns(3)
        for col, (_, row) in zip(cols, latest.iterrows()):
            with col:
                title = row.get('property_type', 'ไม่ระบุประเภท')
                project_line = f'<p class="project">โครงการ: {row.get("project_name")}</p>' if row.get("project_name") else ""
                st.markdown(f"""
                <div class="listing-card">
                  <div class="badge-row">
                    <span class="zone-badge">ต.{row.get('location_zone','ไม่ระบุ')}</span>
                    <span class="zone-badge">{row.get('seller_type','ไม่ระบุ')}</span>
                  </div>
                  <h4>{title}</h4>
                  {project_line}
                  <div class="price">{fmt_baht(row.get('price'))}</div>
                  <div class="meta">{fmt_money(row.get('size_sq_wah')) if pd.notnull(row.get('size_sq_wah')) else '-'} ตร.วา · {confidence_tag(row)}</div>
                </div>
                """, unsafe_allow_html=True)

# =========================================================
# PAGE: MARKET SCOUT
# =========================================================
elif page == "📍 Market Scout":
    st.markdown("## 📍 Market Scout")
    st.caption("ข้อมูลนี้มาจากพนักงานที่พิมพ์หรือส่งรูปโพสต์ขายเข้า LINE OA แล้วให้ AI แกะข้อมูลอัตโนมัติ")

    if df_market.empty:
        st.markdown('<div class="empty-box">ยังไม่มีประกาศในระบบ ลองเพิ่มที่หน้า "เครื่องมือ / เพิ่มข้อมูล" หรือพิมพ์ "บันทึกตลาด" ใน LINE OA</div>', unsafe_allow_html=True)
    else:
        f1, f2, f3, f4 = st.columns([1, 1, 1, 1.3])
        zones_available = sorted(df_market["location_zone"].dropna().unique().tolist())
        types_available = sorted(df_market["property_type"].dropna().unique().tolist())
        sellers_available = sorted(df_market["seller_type"].dropna().unique().tolist()) if "seller_type" in df_market else []

        sel_zones = f1.multiselect("ตำบล", zones_available, default=zones_available)
        sel_types = f2.multiselect("ประเภททรัพย์", types_available, default=types_available)
        sel_sellers = f3.multiselect("ผู้ขาย", sellers_available, default=sellers_available) if sellers_available else []
        only_exact = f4.checkbox("แสดงเฉพาะที่มีพิกัดแม่นยำ ✅")

        price_series = df_market["price"].dropna()
        if not price_series.empty:
            p_min, p_max = float(price_series.min()), float(price_series.max())
            if p_min == p_max:
                p_max += 1
            sel_price = st.slider("ช่วงราคา (บาท)", p_min, p_max, (p_min, p_max))
        else:
            sel_price = None

        filtered = df_market.copy()
        if sel_zones:
            filtered = filtered[filtered["location_zone"].isin(sel_zones)]
        if sel_types:
            filtered = filtered[filtered["property_type"].isin(sel_types)]
        if sel_sellers:
            filtered = filtered[filtered["seller_type"].isin(sel_sellers)]
        if sel_price:
            filtered = filtered[filtered["price"].between(sel_price[0], sel_price[1]) | filtered["price"].isna()]
        if only_exact and "location_confidence" in filtered.columns:
            filtered = filtered[filtered["location_confidence"] == "exact"]

        st.caption(f"พบ {len(filtered)} ประกาศจากทั้งหมด {len(df_market)} รายการ · ✅ พิกัดแม่นยำ · 🟡 ประมาณจากตำบล · ❌ ยังไม่มีพิกัด")

        map_col, list_col = st.columns([1.2, 1])

        with map_col:
            m = folium.Map(location=list(MAP_CENTER), zoom_start=11, tiles="CartoDB positron")
            cluster = MarkerCluster().add_to(m)
            for _, row in filtered.iterrows():
                lat, lng = row.get("latitude"), row.get("longitude")
                if pd.notnull(lat) and pd.notnull(lng):
                    popup = (
                        f"<b>{row.get('property_type','')}</b><br>"
                        f"ต.{row.get('location_zone','-')}<br>"
                        f"{fmt_baht(row.get('price'))}<br>"
                        f"{confidence_tag(row)}"
                    )
                    marker_color = "blue" if row.get("location_confidence") == "exact" else "lightgray"
                    folium.Marker(
                        location=[lat, lng],
                        popup=popup,
                        tooltip=fmt_baht(row.get("price")),
                        icon=folium.Icon(color=marker_color, icon="home"),
                    ).add_to(cluster)
            st_folium(m, width=None, height=540)

        with list_col:
            st.markdown("**รายการประกาศ**")
            for _, row in filtered.iterrows():
                project_line = f'<p class="project">โครงการ: {row.get("project_name")}</p>' if row.get("project_name") else ""
                extra_meta = []
                if pd.notnull(row.get("bedrooms")):
                    extra_meta.append(f"{int(row.get('bedrooms'))} ห้องนอน")
                if pd.notnull(row.get("usable_area_sqm")):
                    extra_meta.append(f"{fmt_money(row.get('usable_area_sqm'))} ตร.ม. ใช้สอย")
                if row.get("landmark"):
                    extra_meta.append(f"ใกล้ {row.get('landmark')}")
                extra_line = " · ".join(extra_meta)
                highlight_line = f'<div class="highlight">{row.get("highlights")}</div>' if row.get("highlights") else ""
                link_line = f'<div><a href="{row.get("source_url")}" target="_blank">ดูโพสต์ต้นฉบับ →</a></div>' if row.get("source_url") else ""

                st.markdown(f"""
                <div class="listing-card">
                  <div class="badge-row">
                    <span class="zone-badge">ต.{row.get('location_zone','ไม่ระบุ')}</span>
                    <span class="zone-badge">{row.get('seller_type','ไม่ระบุ')}</span>
                    <span class="zone-badge">{row.get('status','ใหม่')}</span>
                  </div>
                  <h4>{row.get('property_type','ไม่ระบุประเภท')}</h4>
                  {project_line}
                  <div class="price">{fmt_baht(row.get('price'))}</div>
                  <div class="meta">
                    {fmt_money(row.get('size_sq_wah')) if pd.notnull(row.get('size_sq_wah')) else '-'} ตร.วา
                    {' · ' + fmt_money(row.get('price_per_sq_wah')) + ' บาท/ตรว.' if pd.notnull(row.get('price_per_sq_wah')) else ''}
                    <br>{extra_line}
                    <br>{confidence_tag(row)}
                  </div>
                  {highlight_line}
                  {link_line}
                </div>
                """, unsafe_allow_html=True)

                if row.get("id") is not None:
                    with st.expander("อัปเดตสถานะ"):
                        new_status = st.selectbox(
                            "สถานะ", LISTING_STATUSES,
                            index=LISTING_STATUSES.index(row.get("status")) if row.get("status") in LISTING_STATUSES else 0,
                            key=f"status_{row.get('id')}",
                        )
                        if st.button("บันทึกสถานะ", key=f"save_status_{row.get('id')}"):
                            try:
                                supabase.table("pakchong_market_scout").update({"status": new_status}).eq("id", row.get("id")).execute()
                                st.success("อัปเดตแล้ว")
                                refresh_data()
                                st.rerun()
                            except Exception as e:
                                st.error(f"อัปเดตไม่สำเร็จ: {e}")

        st.download_button(
            "⬇️ ดาวน์โหลดผลลัพธ์เป็น CSV",
            filtered.to_csv(index=False).encode("utf-8-sig"),
            file_name="pakchong_listings.csv",
            mime="text/csv",
        )

# =========================================================
# PAGE: วิเคราะห์ตลาด
# =========================================================
elif page == "📊 วิเคราะห์ตลาด":
    st.markdown("## 📊 วิเคราะห์ตลาด")
    st.caption("ข้อมูลชุดเดียวกับที่โมดูล 'ประเมินราคา' บน LINE OA ใช้อ้างอิงเปรียบเทียบ")

    if df_market.empty:
        st.markdown('<div class="empty-box">ยังไม่มีข้อมูลเพียงพอสำหรับการวิเคราะห์</div>', unsafe_allow_html=True)
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**ราคาเฉลี่ยต่อตารางวา แยกตามตำบล**")
            zone_avg = df_market.dropna(subset=["price_per_sq_wah", "location_zone"]).groupby("location_zone", as_index=False)["price_per_sq_wah"].mean()
            if not zone_avg.empty:
                chart = alt.Chart(zone_avg).mark_bar(color="#0066cc").encode(
                    x=alt.X("location_zone:N", title="ตำบล"),
                    y=alt.Y("price_per_sq_wah:Q", title="บาท/ตร.วา"),
                    tooltip=["location_zone", "price_per_sq_wah"],
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.caption("ยังไม่มีข้อมูลราคาต่อตารางวาเพียงพอ")

        with col2:
            st.markdown("**จำนวนประกาศ แยกตามประเภททรัพย์**")
            type_count = df_market["property_type"].value_counts().reset_index()
            type_count.columns = ["property_type", "count"]
            if not type_count.empty:
                chart2 = alt.Chart(type_count).mark_bar(color="#1d1d1f").encode(
                    x=alt.X("property_type:N", title="ประเภททรัพย์"),
                    y=alt.Y("count:Q", title="จำนวน"),
                    tooltip=["property_type", "count"],
                )
                st.altair_chart(chart2, use_container_width=True)

        if "seller_type" in df_market.columns:
            st.markdown("**สัดส่วนตามประเภทผู้ขาย**")
            seller_count = df_market["seller_type"].value_counts().reset_index()
            seller_count.columns = ["seller_type", "count"]
            if not seller_count.empty:
                chart3 = alt.Chart(seller_count).mark_bar(color="#0066cc").encode(
                    x=alt.X("seller_type:N", title="ประเภทผู้ขาย"),
                    y=alt.Y("count:Q", title="จำนวน"),
                    tooltip=["seller_type", "count"],
                )
                st.altair_chart(chart3, use_container_width=True)

        st.markdown("**การกระจายตัวของราคา**")
        price_data = df_market.dropna(subset=["price"])
        if not price_data.empty:
            hist = alt.Chart(price_data).mark_bar(color="#7a7a7a").encode(
                x=alt.X("price:Q", bin=alt.Bin(maxbins=25), title="ราคา (บาท)"),
                y=alt.Y("count()", title="จำนวนประกาศ"),
            )
            st.altair_chart(hist, use_container_width=True)

        st.markdown("**ประกาศใหม่ตามช่วงเวลา**")
        if "created_at" in df_market.columns:
            ts = df_market.dropna(subset=["created_at"]).copy()
            ts["date"] = pd.to_datetime(ts["created_at"]).dt.date
            trend = ts.groupby("date").size().reset_index(name="count")
            if not trend.empty:
                line = alt.Chart(trend).mark_line(color="#0066cc", point=True).encode(
                    x="date:T", y="count:Q", tooltip=["date", "count"]
                )
                st.altair_chart(line, use_container_width=True)

# =========================================================
# PAGE: CRM
# =========================================================
elif page == "👥 CRM":
    st.markdown("## 👥 CRM — ฐานข้อมูลลูกค้า")
    st.caption("ลูกค้าที่พนักงานพิมพ์เพิ่มผ่านเมนู 'เพิ่มลูกค้า' / 'เพิ่มผู้ขาย' บน LINE OA")

    if df_crm.empty:
        st.markdown('<div class="empty-box">ยังไม่มีข้อมูลลูกค้า ลองเพิ่มที่หน้า "เครื่องมือ / เพิ่มข้อมูล" หรือผ่าน LINE OA</div>', unsafe_allow_html=True)
    else:
        k1, k2, k3 = st.columns(3)
        k1.metric("ผู้ซื้อ", int((df_crm["contact_type"] == "ผู้ซื้อ").sum()))
        k2.metric("ผู้ขาย", int((df_crm["contact_type"] == "ผู้ขาย").sum()))
        k3.metric("นายหน้า", int((df_crm["contact_type"] == "นายหน้า").sum()))

        f1, f2, f3 = st.columns([1, 1, 2])
        contact_filter = f1.selectbox("ประเภทผู้ติดต่อ", ["ทั้งหมด", "ผู้ซื้อ", "ผู้ขาย", "นายหน้า"])
        status_options = ["ทั้งหมด"] + CRM_STATUSES
        status_filter = f2.selectbox("สถานะ", status_options)
        search_term = f3.text_input("ค้นหาชื่อลูกค้า")

        filtered_crm = df_crm.copy()
        if contact_filter != "ทั้งหมด":
            filtered_crm = filtered_crm[filtered_crm["contact_type"] == contact_filter]
        if status_filter != "ทั้งหมด" and "status" in filtered_crm.columns:
            filtered_crm = filtered_crm[filtered_crm["status"] == status_filter]
        if search_term:
            filtered_crm = filtered_crm[filtered_crm["name"].str.contains(search_term, case=False, na=False)]

        st.caption(f"พบ {len(filtered_crm)} รายการ")

        for _, row in filtered_crm.iterrows():
            budget_min = row.get("budget_min")
            budget_max = row.get("budget_max")
            if pd.notnull(budget_min) and pd.notnull(budget_max):
                budget_text = f"{fmt_money(budget_min)} - {fmt_money(budget_max)} บาท"
            elif pd.notnull(budget_max):
                budget_text = f"ไม่เกิน {fmt_money(budget_max)} บาท"
            else:
                budget_text = "ไม่ระบุ"

            st.markdown(f"""
            <div class="lead-card">
              <h5>{row.get('name','ไม่ระบุชื่อ')} — {row.get('contact_type','-')} · {row.get('status','ใหม่')}</h5>
              <div class="lead-meta">
                สนใจ: {row.get('property_type') or '-'} · ตำบล: {row.get('location_zone') or '-'} ·
                งบ: {budget_text}<br>
                วัตถุประสงค์: {row.get('purpose') or '-'} · ติดต่อ: {row.get('contact_info','-')}
              </div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("รายละเอียด / อัปเดตสถานะ"):
                if row.get("note"):
                    st.write(row.get("note"))
                if row.get("id") is not None:
                    new_status = st.selectbox(
                        "สถานะ", CRM_STATUSES,
                        index=CRM_STATUSES.index(row.get("status")) if row.get("status") in CRM_STATUSES else 0,
                        key=f"crmstatus_{row.get('id')}",
                    )
                    if st.button("บันทึกสถานะ", key=f"save_crmstatus_{row.get('id')}"):
                        try:
                            supabase.table("pakchong_crm").update({"status": new_status}).eq("id", row.get("id")).execute()
                            st.success("อัปเดตแล้ว")
                            refresh_data()
                            st.rerun()
                        except Exception as e:
                            st.error(f"อัปเดตไม่สำเร็จ: {e}")

        st.download_button(
            "⬇️ ดาวน์โหลดรายชื่อลูกค้าเป็น CSV",
            filtered_crm.to_csv(index=False).encode("utf-8-sig"),
            file_name="pakchong_crm.csv",
            mime="text/csv",
        )

# =========================================================
# PAGE: สัญญาที่ออกแล้ว
# =========================================================
elif page == "📑 สัญญาที่ออกแล้ว":
    st.markdown("## 📑 สัญญาที่ออกแล้ว")
    st.caption("บันทึกทุกครั้งที่พนักงานสร้างเอกสาร PDF ผ่านเมนู 'สัญญา' บน LINE OA (ตาราง contract_logs)")

    if df_contracts.empty:
        st.markdown('<div class="empty-box">ยังไม่มีสัญญาที่ออกในระบบ</div>', unsafe_allow_html=True)
    else:
        k1, k2 = st.columns(2)
        k1.metric("สัญญาทั้งหมด", len(df_contracts))
        if "created_at" in df_contracts.columns:
            since = (datetime.now() - timedelta(days=7)).isoformat()
            recent = int((df_contracts["created_at"].astype(str) >= since).sum())
            k2.metric("ออกใหม่ใน 7 วัน", recent)

        if "contract_type" in df_contracts.columns:
            st.markdown("**จำนวนสัญญาแยกตามประเภท**")
            type_count = df_contracts["contract_type"].value_counts().reset_index()
            type_count.columns = ["contract_type", "count"]
            type_count["label"] = type_count["contract_type"].map(lambda c: CONTRACT_LABELS.get(c, c))
            chart = alt.Chart(type_count).mark_bar(color="#0066cc").encode(
                x=alt.X("label:N", title="ประเภทสัญญา"),
                y=alt.Y("count:Q", title="จำนวน"),
                tooltip=["label", "count"],
            )
            st.altair_chart(chart, use_container_width=True)

        st.markdown('<div class="section-title">รายการล่าสุด</div>', unsafe_allow_html=True)
        st.caption("หมายเหตุ: ลิงก์ดาวน์โหลด PDF มีอายุ 6 ชั่วโมง จึงมักหมดอายุไปแล้ว — สร้างไฟล์ใหม่ได้จากเมนูสัญญาบน LINE OA")

        for _, row in df_contracts.head(50).iterrows():
            ctype = row.get("contract_type", "-")
            label = CONTRACT_LABELS.get(ctype, ctype)
            user_id = str(row.get("line_user_id") or "")
            masked_user = ("···" + user_id[-6:]) if len(user_id) > 6 else user_id
            st.markdown(f"""
            <div class="contract-card">
              <div>
                <div class="ctype">{label}</div>
                <div class="cmeta">ผู้สร้าง: {masked_user} · ไฟล์: {row.get('pdf_path','-')}</div>
              </div>
              <div class="cmeta">{row.get('created_at','-')}</div>
            </div>
            """, unsafe_allow_html=True)
            if row.get("contract_data"):
                with st.expander("ดูข้อมูลที่ใช้กรอกสัญญา"):
                    st.json(row.get("contract_data"))

# =========================================================
# PAGE: เครื่องมือ / เพิ่มข้อมูล
# =========================================================
elif page == "🛠️ เครื่องมือ / เพิ่มข้อมูล":
    st.markdown("## 🛠️ เครื่องมือ / เพิ่มข้อมูล")

    st.markdown("""
    <div class="info-box">
      โมดูลที่ใช้ AI ต่อเนื่องกันหลายขั้นตอน — สร้างโพสต์ขาย (Content Studio), ตรวจ/แก้ไขสัญญา,
      คำนวณค่าโอน และประเมินราคา — ยังทำงานอยู่ฝั่ง LINE OA เท่านั้น เพราะต้องใช้ Gemini API และสถานะการสนทนาต่อเนื่อง
      หน้านี้จึงเน้นเป็นเครื่องมือจัดการข้อมูลตรงสำหรับพนักงานหน้างานแทน
    </div>
    """, unsafe_allow_html=True)

    tab_listing, tab_lead, tab_money = st.tabs(["🏠 ลงประกาศทรัพย์", "👤 เพิ่มลูกค้า/ผู้ขาย", "🧮 แปลงจำนวนเงินเป็นตัวอักษร"])

    with tab_listing:
        with st.form("listing_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            property_type = c1.text_input("ประเภททรัพย์*", placeholder="เช่น บ้านเดี่ยว, ที่ดิน, พูลวิลล่า")
            location_zone = c2.selectbox("ตำบล*", VALID_TAMBONS)

            c3, c4 = st.columns(2)
            price = c3.number_input("ราคา (บาท)*", min_value=0.0, step=10000.0)
            size_sq_wah = c4.number_input("ขนาด (ตร.วา)*", min_value=0.0, step=1.0)

            c5, c6 = st.columns(2)
            seller_type = c5.selectbox("ประเภทผู้ขาย", SELLER_TYPES)
            status = c6.selectbox("สถานะ", LISTING_STATUSES)

            c7, c8 = st.columns(2)
            default_lat, default_lng = TAMBON_CENTROIDS[location_zone]
            latitude = c7.number_input("ละติจูด*", value=default_lat, format="%.6f")
            longitude = c8.number_input("ลองจิจูด*", value=default_lng, format="%.6f")
            st.caption("เคล็ดลับ: หาพิกัดจริงได้จาก Google Maps → คลิกขวาที่ตำแหน่ง → คัดลอกพิกัด")

            with st.expander("ข้อมูลเพิ่มเติม (ไม่บังคับ)"):
                project_name = st.text_input("ชื่อโครงการ")
                landmark = st.text_input("จุดสังเกต", placeholder="เช่น ใกล้ตลาดปากช่อง, ติดถนนมิตรภาพ")
                d1, d2 = st.columns(2)
                bedrooms = d1.number_input("จำนวนห้องนอน", min_value=0, step=1)
                usable_area_sqm = d2.number_input("พื้นที่ใช้สอย (ตร.ม.)", min_value=0.0, step=1.0)
                contact_info = st.text_input("เบอร์โทร / LINE ผู้ขาย")
                highlights = st.text_area("จุดเด่น (สรุปสั้น)")

            submitted = st.form_submit_button("บันทึกประกาศ")
            if submitted:
                if not property_type or not location_zone or price <= 0 or size_sq_wah <= 0:
                    st.error("กรุณากรอกข้อมูลที่จำเป็น (มีเครื่องหมาย *) ให้ครบถ้วน")
                else:
                    price_per_sq_wah = price / size_sq_wah if size_sq_wah else None
                    payload = {
                        "property_type": property_type,
                        "project_name": project_name or None,
                        "location_zone": location_zone,
                        "landmark": landmark or None,
                        "price": price,
                        "size_sq_wah": size_sq_wah,
                        "usable_area_sqm": usable_area_sqm or None,
                        "bedrooms": bedrooms or None,
                        "price_per_sq_wah": price_per_sq_wah,
                        "contact_info": contact_info or None,
                        "seller_type": seller_type,
                        "highlights": highlights or None,
                        "latitude": latitude,
                        "longitude": longitude,
                        "location_confidence": "exact",
                        "location_source": "dashboard_manual",
                        "status": status,
                    }
                    try:
                        supabase.table("pakchong_market_scout").insert(payload).execute()
                        st.success("บันทึกประกาศเรียบร้อยแล้ว")
                        refresh_data()
                        st.rerun()
                    except Exception as e:
                        st.error(f"บันทึกไม่สำเร็จ: {e}")

    with tab_lead:
        with st.form("lead_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            contact_type = c1.selectbox("ท่านคือ*", ["ผู้ซื้อ", "ผู้ขาย", "นายหน้า"])
            name = c2.text_input("ชื่อ-นามสกุล*")

            c3, c4 = st.columns(2)
            property_type_l = c3.text_input("ประเภททรัพย์ที่สนใจ")
            location_zone_l = c4.selectbox("ตำบลที่สนใจ", ["ไม่ระบุ"] + VALID_TAMBONS)

            c5, c6 = st.columns(2)
            budget_min = c5.number_input("งบประมาณต่ำสุด (บาท)", min_value=0.0, step=10000.0)
            budget_max = c6.number_input("งบประมาณสูงสุด (บาท)", min_value=0.0, step=10000.0)

            c7, c8 = st.columns(2)
            purpose = c7.selectbox("วัตถุประสงค์", ["ไม่ระบุ", "อยู่เอง", "ลงทุน", "ปล่อยเช่า"])
            contact_info = c8.text_input("เบอร์โทร / LINE ID*")

            note = st.text_area("รายละเอียดเพิ่มเติม")

            submitted_lead = st.form_submit_button("บันทึกข้อมูล")
            if submitted_lead:
                if not name or not contact_info:
                    st.error("กรุณากรอกชื่อและช่องทางติดต่อให้ครบถ้วน")
                else:
                    payload = {
                        "contact_type": contact_type,
                        "name": name,
                        "budget_min": budget_min or None,
                        "budget_max": budget_max or None,
                        "property_type": property_type_l or None,
                        "location_zone": None if location_zone_l == "ไม่ระบุ" else location_zone_l,
                        "contact_info": contact_info,
                        "purpose": None if purpose == "ไม่ระบุ" else purpose,
                        "note": note or None,
                        "status": "ใหม่",
                    }
                    try:
                        supabase.table("pakchong_crm").insert(payload).execute()
                        st.success("บันทึกข้อมูลเรียบร้อยแล้ว")
                        refresh_data()
                        st.rerun()
                    except Exception as e:
                        st.error(f"บันทึกไม่สำเร็จ: {e}")

    with tab_money:
        st.caption("ใช้ตรรกะเดียวกับที่บอทใช้กรอกจำนวนเงินเป็นตัวอักษรในเอกสารสัญญา (thai_num.py)")
        amount = st.number_input("จำนวนเงิน (บาท)", min_value=0.0, step=1000.0, format="%.2f")
        if amount > 0:
            st.markdown(f"**คำอ่าน:** {baht_text(amount)}")
            st.caption(f"ตัวเลขพร้อม comma: {fmt_money(amount)} บาท")