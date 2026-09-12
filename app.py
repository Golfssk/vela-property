import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from supabase import create_client, Client

st.set_page_config(page_title="Vela Property OS", layout="wide")

SUPABASE_URL = "https://vfieyjxlrpziiksyccdt.supabase.co"
SUPABASE_KEY = "sb_publishable_udkJwGJ8zjXlEOlYszDRUg_yVD4g7ie"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("🏢 Vela Property Operating System")

# แบ่งหน้าจอเป็น 2 แท็บ
tab1, tab2 = st.tabs(["📍 Market Scout (แผนที่ตลาด)", "👥 CRM (ฐานข้อมูลลูกค้า)"])

# ---------------- TAB 1: MARKET SCOUT ----------------
with tab1:
    try:
        res_market = supabase.table("pakchong_market_scout").select("*").order("created_at", desc=True).execute()
        df_market = pd.DataFrame(res_market.data)

        if not df_market.empty:
            st.subheader("📊 ประกาศขายล่าสุด")
            display_df = df_market[["created_at", "property_type", "location_zone", "price", "size_sq_wah", "price_per_sq_wah", "latitude", "longitude"]]
            st.dataframe(display_df, use_container_width=True)

            m = folium.Map(location=[14.6000, 101.4000], zoom_start=11)
            for index, row in df_market.iterrows():
                lat = row.get("latitude")
                lng = row.get("longitude")
                if pd.notnull(lat) and pd.notnull(lng):
                    price_val = row.get('price')
                    price_text = f"{price_val:,.0f} บาท" if pd.notnull(price_val) else "ไม่ระบุ"
                    popup_text = f"<b>{row.get('property_type')}</b><br>โซน: {row.get('location_zone')}<br>ราคา: {price_text}"
                    folium.Marker(
                        location=[lat, lng],
                        popup=popup_text,
                        tooltip=price_text,
                        icon=folium.Icon(color="red", icon="home")
                    ).add_to(m)

            st_folium(m, width=1000, height=500)
        else:
            st.info("ยังไม่มีข้อมูลทรัพย์ในระบบ")
    except Exception as e:
        st.error(f"Error Market Scout: {str(e)}")

# ---------------- TAB 2: CRM ----------------
with tab2:
    try:
        res_crm = supabase.table("pakchong_crm").select("*").order("created_at", desc=True).execute()
        df_crm = pd.DataFrame(res_crm.data)

        if not df_crm.empty:
            # สร้างตัวกรองข้อมูล
            contact_filter = st.selectbox("📌 เลือกประเภทผู้ติดต่อ", ["ทั้งหมด", "ผู้ซื้อ", "ผู้ขาย", "นายหน้า"])
            
            if contact_filter != "ทั้งหมด":
                df_crm = df_crm[df_crm["contact_type"] == contact_filter]

            # จัดเรียงคอลัมน์ให้ดูง่าย
            df_display = df_crm[["created_at", "contact_type", "name", "property_type", "location_zone", "budget_max", "contact_info", "note"]]
            
            st.subheader(f"🗂️ รายการ: {contact_filter} ({len(df_crm)} รายการ)")
            st.dataframe(df_display, use_container_width=True)
            
        else:
            st.info("ยังไม่มีข้อมูลลูกค้า ลองส่งคำสั่ง 'เพิ่มลูกค้า' ผ่าน LINE OA ครับ")
    except Exception as e:
        st.error(f"Error CRM: {str(e)}")