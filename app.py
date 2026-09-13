import streamlit as st
import pandas as pd
import altair as alt
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from supabase import create_client, Client
from datetime import datetime

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(
    page_title="VELA — ปากช่อง เขาใหญ่ อสังหาริมทรัพย์เบอร์ 1",
    page_icon="🏔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

SUPABASE_URL = "https://vfieyjxlrpziiksyccdt.supabase.co"
SUPABASE_KEY = "sb_publishable_udkJwGJ8zjXlEOlYszDRUg_yVD4g7ie"

ZONES = [
    {"name": "เขาใหญ่", "tag": "โซนธรรมชาติ",
     "desc": "ติดอุทยานแห่งชาติ อากาศเย็นตลอดปี กลุ่มบ้านพักตากอากาศและรีสอร์ตระดับพรีเมียม"},
    {"name": "วังน้ำเขียว", "tag": "โซนไร่องุ่น",
     "desc": "ภูมิประเทศเป็นหุบเขา เหมาะกับที่ดินเกษตร ไร่องุ่น และโครงการเชิงท่องเที่ยว"},
    {"name": "กลางดง", "tag": "โซนคมนาคม",
     "desc": "ใกล้ทางหลวงและมอเตอร์เวย์ เหมาะกับที่ดินเพื่อการค้าและโครงการจัดสรร"},
    {"name": "มวกเหล็ก", "tag": "โซนอากาศเย็น",
     "desc": "ฟาร์มโคนมและทุ่งหญ้าเดิม กำลังเปลี่ยนเป็นที่ดินเพื่อบ้านพักและคาเฟ่"},
]

# =========================================================
# STYLE
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
  font-size:0.95rem;
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
  font-size:17px;
  padding:11px 22px;
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
  min-height:420px;
  border-radius:0px;
  overflow:hidden;
  display:flex;
  align-items:flex-end;
  padding:64px 48px;
  margin-bottom:0px;
  background:
    linear-gradient(180deg, rgba(0,0,0,0.15) 0%, rgba(0,0,0,0.35) 55%, rgba(0,0,0,0.78) 100%),
    url('https://images.unsplash.com/photo-1470770903676-69b98201ea1c?q=80&w=1800&auto=format&fit=crop') center/cover no-repeat;
}
.hero-eyebrow{color:var(--primary-on-dark); font-weight:600; font-size:14px; letter-spacing:-0.224px; margin-bottom:12px;}
.hero-title{color:var(--on-dark); font-weight:600; font-size:2.6rem; line-height:1.1; letter-spacing:-0.028em; margin:0;}
.hero-sub{color:#cccccc; max-width:560px; margin-top:16px; font-size:1.15rem; font-weight:400; line-height:1.4;}
.section-title{
  font-weight:600; font-size:1.7rem; color:var(--ink); letter-spacing:-0.374px;
  margin:40px 0 20px 0; padding-bottom:0;
}
.zone-card{
  background:var(--canvas); border:1px solid var(--hairline); padding:24px; border-radius:18px; height:100%;
}
.zone-card .tag{color:var(--ink-muted-48); font-weight:600; font-size:0.82rem; margin-bottom:10px; letter-spacing:-0.224px;}
.zone-card h4{font-weight:600; margin:0 0 8px 0; color:var(--ink); font-size:1.15rem; letter-spacing:-0.374px;}
.zone-card p{font-size:0.92rem; color:var(--ink-muted-80); margin:0; line-height:1.5;}
.listing-card{
  background:var(--canvas); border:1px solid var(--hairline); border-radius:18px;
  padding:22px; margin-bottom:14px;
}
.listing-card .zone-badge{
  display:inline-block; font-size:0.75rem; padding:4px 12px; border-radius:9999px;
  background:var(--surface-pearl); color:var(--ink-muted-80); font-weight:600;
  margin-bottom:12px; border:1px solid var(--hairline);
}
.listing-card h4{color:var(--ink); font-weight:600; margin:0 0 6px 0; font-size:1.05rem; letter-spacing:-0.374px;}
.listing-card .price{color:var(--ink); font-weight:600; font-size:1.3rem; margin:6px 0; letter-spacing:-0.374px;}
.listing-card .meta{color:var(--ink-muted-48); font-size:0.85rem;}
.lead-card{
  background:var(--canvas); border:1px solid var(--hairline); padding:18px 22px; margin-bottom:12px; border-radius:18px;
}
.lead-card h5{margin:0 0 6px 0; font-weight:600; color:var(--ink); font-size:1rem; letter-spacing:-0.374px;}
.lead-card .lead-meta{font-size:0.85rem; color:var(--ink-muted-48);}
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


def refresh_data():
    load_market_scout.clear()
    load_crm.clear()


def fmt_baht(v):
    if v is None or pd.isna(v):
        return "ไม่ระบุราคา"
    return f"{v:,.0f} บาท"


# =========================================================
# SIDEBAR NAV
# =========================================================
with st.sidebar:
    st.markdown("### 🏔️ VELA")
    st.caption("ปากช่อง–เขาใหญ่ อสังหาริมทรัพย์เบอร์ 1")
    page = st.radio(
        "เมนู",
        ["🏠 ภาพรวม", "📍 Market Scout", "📊 วิเคราะห์ตลาด", "👥 CRM", "➕ ลงประกาศ / เพิ่มลูกค้า"],
        label_visibility="collapsed",
    )
    st.divider()
    if st.button("🔄 รีเฟรชข้อมูล"):
        refresh_data()
        st.rerun()

# Load data once per run (cached)
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


# =========================================================
# PAGE: ภาพรวม
# =========================================================
if page == "🏠 ภาพรวม":
    st.markdown("""
    <div class="hero-banner">
      <div>
        <div class="hero-eyebrow">ที่ดิน • บ้านพักตากอากาศ • รีสอร์ต • ฟาร์มองุ่น</div>
        <p class="hero-title">ศูนย์กลางอสังหาริมทรัพย์<br>ปากช่อง–เขาใหญ่</p>
        <p class="hero-sub">รวมทุกประกาศ ทุกโซน ทุกช่วงราคาไว้ในที่เดียว ข้อมูลอัปเดตจากพื้นที่จริงทุกวัน</p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    total_listings = len(df_market)
    avg_price_sqw = df_market["price_per_sq_wah"].dropna().mean() if not df_market.empty and "price_per_sq_wah" in df_market else None
    total_leads = len(df_crm)
    zones_covered = df_market["location_zone"].nunique() if not df_market.empty and "location_zone" in df_market else 0

    c1.metric("ประกาศในระบบ", total_listings)
    c2.metric("ราคาเฉลี่ย/ตร.วา", f"{avg_price_sqw:,.0f} บาท" if avg_price_sqw else "—")
    c3.metric("ลูกค้าในระบบ", total_leads)
    c4.metric("โซนที่ครอบคลุม", zones_covered)

    st.markdown('<div class="section-title">พื้นที่ที่เรารู้จักดีที่สุด</div>', unsafe_allow_html=True)
    zc = st.columns(4)
    for col, z in zip(zc, ZONES):
        with col:
            st.markdown(f"""
            <div class="zone-card">
              <div class="tag">{z['tag']}</div>
              <h4>{z['name']}</h4>
              <p>{z['desc']}</p>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">ประกาศล่าสุด</div>', unsafe_allow_html=True)
    if df_market.empty:
        st.markdown('<div class="empty-box">ยังไม่มีประกาศในระบบ — เมื่อมีข้อมูลใหม่จะแสดงที่นี่โดยอัตโนมัติ</div>', unsafe_allow_html=True)
    else:
        latest = df_market.head(3)
        cols = st.columns(3)
        for col, (_, row) in zip(cols, latest.iterrows()):
            with col:
                st.markdown(f"""
                <div class="listing-card">
                  <span class="zone-badge">{row.get('location_zone','ไม่ระบุ')}</span>
                  <h4>{row.get('property_type','ไม่ระบุประเภท')}</h4>
                  <div class="price">{fmt_baht(row.get('price'))}</div>
                  <div class="meta">{row.get('size_sq_wah','-')} ตร.วา · {fmt_baht(row.get('price_per_sq_wah')) if row.get('price_per_sq_wah') else 'ไม่ระบุราคา/ตรว.'}</div>
                </div>
                """, unsafe_allow_html=True)

# =========================================================
# PAGE: MARKET SCOUT
# =========================================================
elif page == "📍 Market Scout":
    st.markdown("## 📍 Market Scout — แผนที่ตลาดแบบเรียลไทม์")
    st.caption("ประกาศทั้งหมดถูกปักหมุดตามพิกัดจริง อัปเดตจากฐานข้อมูลโดยตรง")

    if df_market.empty:
        st.markdown('<div class="empty-box">ยังไม่มีประกาศในระบบ ลองเพิ่มประกาศแรกที่เมนู "➕ ลงประกาศ / เพิ่มลูกค้า"</div>', unsafe_allow_html=True)
    else:
        # ---- Filters ----
        f1, f2, f3 = st.columns([1, 1, 1.4])
        zones_available = sorted(df_market["location_zone"].dropna().unique().tolist())
        types_available = sorted(df_market["property_type"].dropna().unique().tolist())

        sel_zones = f1.multiselect("โซน", zones_available, default=zones_available)
        sel_types = f2.multiselect("ประเภททรัพย์", types_available, default=types_available)

        price_series = df_market["price"].dropna()
        if not price_series.empty:
            p_min, p_max = float(price_series.min()), float(price_series.max())
            if p_min == p_max:
                p_max += 1
            sel_price = f3.slider("ช่วงราคา (บาท)", p_min, p_max, (p_min, p_max))
        else:
            sel_price = None

        filtered = df_market.copy()
        if sel_zones:
            filtered = filtered[filtered["location_zone"].isin(sel_zones)]
        if sel_types:
            filtered = filtered[filtered["property_type"].isin(sel_types)]
        if sel_price:
            filtered = filtered[filtered["price"].between(sel_price[0], sel_price[1]) | filtered["price"].isna()]

        st.caption(f"พบ {len(filtered)} ประกาศจากทั้งหมด {len(df_market)} รายการ")

        map_col, list_col = st.columns([1.2, 1])

        with map_col:
            m = folium.Map(location=[14.6000, 101.4000], zoom_start=11, tiles="CartoDB positron")
            cluster = MarkerCluster().add_to(m)
            for _, row in filtered.iterrows():
                lat, lng = row.get("latitude"), row.get("longitude")
                if pd.notnull(lat) and pd.notnull(lng):
                    popup = f"<b>{row.get('property_type','')}</b><br>โซน: {row.get('location_zone','-')}<br>{fmt_baht(row.get('price'))}"
                    folium.Marker(
                        location=[lat, lng],
                        popup=popup,
                        tooltip=fmt_baht(row.get("price")),
                        icon=folium.Icon(color="blue", icon="home"),
                    ).add_to(cluster)
            st_folium(m, width=None, height=520)

        with list_col:
            st.markdown("**รายการประกาศ**")
            for _, row in filtered.iterrows():
                st.markdown(f"""
                <div class="listing-card">
                  <span class="zone-badge">{row.get('location_zone','ไม่ระบุ')}</span>
                  <h4>{row.get('property_type','ไม่ระบุประเภท')}</h4>
                  <div class="price">{fmt_baht(row.get('price'))}</div>
                  <div class="meta">{row.get('size_sq_wah','-')} ตร.วา
                    {' · ' + fmt_baht(row.get('price_per_sq_wah')) + '/ตรว.' if pd.notnull(row.get('price_per_sq_wah')) else ''}
                  </div>
                </div>
                """, unsafe_allow_html=True)

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

    if df_market.empty:
        st.markdown('<div class="empty-box">ยังไม่มีข้อมูลเพียงพอสำหรับการวิเคราะห์</div>', unsafe_allow_html=True)
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**ราคาเฉลี่ยต่อตารางวา แยกตามโซน**")
            zone_avg = df_market.dropna(subset=["price_per_sq_wah", "location_zone"]).groupby("location_zone", as_index=False)["price_per_sq_wah"].mean()
            if not zone_avg.empty:
                chart = alt.Chart(zone_avg).mark_bar(color="#0066cc").encode(
                    x=alt.X("location_zone:N", title="โซน"),
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

    if df_crm.empty:
        st.markdown('<div class="empty-box">ยังไม่มีข้อมูลลูกค้า ลองเพิ่มลูกค้าใหม่ที่เมนู "➕ ลงประกาศ / เพิ่มลูกค้า"</div>', unsafe_allow_html=True)
    else:
        k1, k2, k3 = st.columns(3)
        k1.metric("ผู้ซื้อ", int((df_crm["contact_type"] == "ผู้ซื้อ").sum()))
        k2.metric("ผู้ขาย", int((df_crm["contact_type"] == "ผู้ขาย").sum()))
        k3.metric("นายหน้า", int((df_crm["contact_type"] == "นายหน้า").sum()))

        f1, f2 = st.columns([1, 2])
        contact_filter = f1.selectbox("ประเภทผู้ติดต่อ", ["ทั้งหมด", "ผู้ซื้อ", "ผู้ขาย", "นายหน้า"])
        search_term = f2.text_input("ค้นหาชื่อลูกค้า")

        filtered_crm = df_crm.copy()
        if contact_filter != "ทั้งหมด":
            filtered_crm = filtered_crm[filtered_crm["contact_type"] == contact_filter]
        if search_term:
            filtered_crm = filtered_crm[filtered_crm["name"].str.contains(search_term, case=False, na=False)]

        st.caption(f"พบ {len(filtered_crm)} รายการ")

        for _, row in filtered_crm.iterrows():
            with st.container():
                st.markdown(f"""
                <div class="lead-card">
                  <h5>{row.get('name','ไม่ระบุชื่อ')} — {row.get('contact_type','-')}</h5>
                  <div class="lead-meta">
                    สนใจ: {row.get('property_type') or '-'} · โซน: {row.get('location_zone') or '-'} ·
                    งบสูงสุด: {fmt_baht(row.get('budget_max')) if pd.notnull(row.get('budget_max')) else 'ไม่ระบุ'} ·
                    ติดต่อ: {row.get('contact_info','-')}
                  </div>
                </div>
                """, unsafe_allow_html=True)
                if row.get("note"):
                    with st.expander("รายละเอียดเพิ่มเติม"):
                        st.write(row.get("note"))

        st.download_button(
            "⬇️ ดาวน์โหลดรายชื่อลูกค้าเป็น CSV",
            filtered_crm.to_csv(index=False).encode("utf-8-sig"),
            file_name="pakchong_crm.csv",
            mime="text/csv",
        )

# =========================================================
# PAGE: ลงประกาศ / เพิ่มลูกค้า
# =========================================================
elif page == "➕ ลงประกาศ / เพิ่มลูกค้า":
    st.markdown("## ➕ ลงประกาศทรัพย์ใหม่ หรือ เพิ่มลูกค้าใหม่")

    tab_listing, tab_lead = st.tabs(["🏠 ลงประกาศทรัพย์", "👤 เพิ่มลูกค้าใหม่"])

    with tab_listing:
        with st.form("listing_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            property_type = c1.text_input("ประเภททรัพย์*", placeholder="เช่น บ้านเดี่ยว, ที่ดิน, รีสอร์ต")
            location_zone = c2.selectbox("โซน*", [z["name"] for z in ZONES])

            c3, c4 = st.columns(2)
            price = c3.number_input("ราคา (บาท)*", min_value=0.0, step=10000.0)
            size_sq_wah = c4.number_input("ขนาด (ตร.วา)*", min_value=0.0, step=1.0)

            c5, c6 = st.columns(2)
            latitude = c5.number_input("ละติจูด*", value=14.6000, format="%.6f")
            longitude = c6.number_input("ลองจิจูด*", value=101.4000, format="%.6f")

            st.caption("เคล็ดลับ: หาพิกัดได้จาก Google Maps → คลิกขวาที่ตำแหน่ง → คัดลอกพิกัด")

            submitted = st.form_submit_button("บันทึกประกาศ")
            if submitted:
                if not property_type or not location_zone or price <= 0 or size_sq_wah <= 0:
                    st.error("กรุณากรอกข้อมูลที่จำเป็น (มีเครื่องหมาย *) ให้ครบถ้วน")
                else:
                    price_per_sq_wah = price / size_sq_wah if size_sq_wah else None
                    payload = {
                        "property_type": property_type,
                        "location_zone": location_zone,
                        "price": price,
                        "size_sq_wah": size_sq_wah,
                        "price_per_sq_wah": price_per_sq_wah,
                        "latitude": latitude,
                        "longitude": longitude,
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
            location_zone_l = c4.text_input("โซนที่สนใจ")

            c5, c6 = st.columns(2)
            budget_max = c5.number_input("งบประมาณสูงสุด (บาท)", min_value=0.0, step=10000.0)
            contact_info = c6.text_input("เบอร์โทร / LINE ID*")

            note = st.text_area("รายละเอียดเพิ่มเติม")

            submitted_lead = st.form_submit_button("บันทึกข้อมูลลูกค้า")
            if submitted_lead:
                if not name or not contact_info:
                    st.error("กรุณากรอกชื่อและช่องทางติดต่อให้ครบถ้วน")
                else:
                    payload = {
                        "contact_type": contact_type,
                        "name": name,
                        "property_type": property_type_l or None,
                        "location_zone": location_zone_l or None,
                        "budget_max": budget_max if budget_max > 0 else None,
                        "contact_info": contact_info,
                        "note": note or None,
                    }
                    try:
                        supabase.table("pakchong_crm").insert(payload).execute()
                        st.success("บันทึกข้อมูลลูกค้าเรียบร้อยแล้ว")
                        refresh_data()
                        st.rerun()
                    except Exception as e:
                        st.error(f"บันทึกไม่สำเร็จ: {e}")