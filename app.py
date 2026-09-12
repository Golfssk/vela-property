import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from supabase import create_client, Client

st.set_page_config(page_title="Pak Chong Property OS", layout="wide")

SUPABASE_URL = "https://vfieyjxlrpziiksyccdt.supabase.co"
SUPABASE_KEY = "sb_publishable_udkJwGJ8zjXlEOlYszDRUg_yVD4g7ie"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("📍 Pak Chong Market Scout")

try:
    response = supabase.table("pakchong_market_scout").select("*").order("created_at", desc=True).execute()
    df = pd.DataFrame(response.data)

    if not df.empty:
        st.subheader("📊 ฐานข้อมูลประกาศขายล่าสุด")
        display_df = df[["created_at", "property_type", "location_zone", "price", "size_sq_wah", "price_per_sq_wah", "latitude", "longitude", "status"]]
        st.dataframe(display_df, use_container_width=True)

        st.subheader("🗺️ แผนที่พิกัดทรัพย์ (ระดับแปลง)")
        # ตั้งค่าศูนย์กลางแผนที่ไปที่อำเภอปากช่อง
        m = folium.Map(location=[14.6000, 101.4000], zoom_start=11)

        for index, row in df.iterrows():
            lat = row.get("latitude")
            lng = row.get("longitude")
            
            # ปักหมุดเฉพาะรายการที่มีพิกัดเท่านั้น
            if pd.notnull(lat) and pd.notnull(lng):
                price_val = row.get('price')
                price_text = f"{price_val:,.0f} บาท" if pd.notnull(price_val) else "ไม่ระบุ"
                
                popup_text = f"<b>{row.get('property_type', 'ทรัพย์')}</b><br>โซน: {row.get('location_zone')}<br>ราคา: {price_text}"
                
                folium.Marker(
                    location=[lat, lng],
                    popup=popup_text,
                    tooltip=price_text,
                    icon=folium.Icon(color="red", icon="home"),
                ).add_to(m)

        st_folium(m, width=1000, height=600)
    else:
        st.info("ยังไม่มีข้อมูลในระบบ ลองส่งคำสั่ง 'บันทึกตลาด' ผ่าน LINE OA ครับ")

except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {str(e)}")