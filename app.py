import streamlit as st
from supabase import create_client, Client
import pandas as pd
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="Vela Property Dashboard", layout="wide")
st.title("🏡 Vela Property - ระบบวิเคราะห์อสังหาฯ เขาใหญ่")

SUPABASE_URL = "https://vfieyjxlrpziiksyccdt.supabase.co"
SUPABASE_KEY = "sb_publishable_udkJwGJ8zjXlEOlYszDRUg_yVD4g7ie"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

response = supabase.table("vela_khaoyai_properties").select("*").execute()
data = response.data

if data:
    df = pd.DataFrame(data)
    df['price_per_sq_wah'] = df['price'] / df['size_sq_wah']
    
    # เติมค่าว่างสำหรับข้อมูลเก่าที่ยังไม่มีชื่อผู้ติดต่อ
    if 'contact_name' not in df.columns:
        df['contact_name'] = ""
    df['contact_name'] = df['contact_name'].fillna("-")

    col1, col2, col3 = st.columns(3)
    col1.metric("จำนวนทรัพย์ในระบบ", f"{len(df)} รายการ")
    col2.metric("ราคาเฉลี่ยทำเล", f"{df['price_per_sq_wah'].mean():,.0f} บาท/ตร.ว.")
    col3.metric("รายการที่น่าสนใจ (Good Deal)", f"{len(df[df['status'] == 'Good Deal'])} รายการ")

    st.markdown("---")
    st.subheader("📍 แผนที่ปักหมุดทำเลเป้าหมาย (Interactive Farming Map)")
    
    m = folium.Map(location=[14.5385, 101.3781], zoom_start=12)
    sample_coords = [[14.5385, 101.3781], [14.5500, 101.3900], [14.5200, 101.3600], [14.5100, 101.3500]]

    for idx, row in df.iterrows():
        color = 'green' if row['status'] == 'Good Deal' else 'red' if row['status'] == 'Overpriced' else 'blue'
        coord = sample_coords[idx % len(sample_coords)]

        popup_text = f"""
        <b>ผู้ติดต่อ:</b> {row['contact_name']}<br>
        <b>โทร:</b> {row['contact_number']}<br>
        <b>ราคา:</b> {row['price']:,} บาท<br>
        <b>ขนาด:</b> {row['size_sq_wah']} ตร.ว.<br>
        <b>ราคา/ตร.ว.:</b> {row['price_per_sq_wah']:,.0f} บาท<br>
        <b>สถานะ:</b> {row['status']}
        """

        folium.Marker(
            location=coord,
            popup=folium.Popup(popup_text, max_width=300),
            tooltip=f"{row['status']} - {row['price']:,} บาท",
            icon=folium.Icon(color=color, icon='home', prefix='fa')
        ).add_to(m)

    st_folium(m, width=1200, height=500)
    st.markdown("---")

    st.subheader("📋 ตารางเปรียบเทียบราคาและประเมินความคุ้มค่า")
    st.dataframe(
        df[['property_url', 'contact_name', 'price', 'size_sq_wah', 'price_per_sq_wah', 'status', 'contact_number']],
        column_config={
            "property_url": st.column_config.LinkColumn("ลิงก์ประกาศ"),
            "contact_name": "ชื่อผู้ติดต่อ",
            "price": st.column_config.NumberColumn("ราคาขาย (บาท)", format="%d"),
            "size_sq_wah": st.column_config.NumberColumn("ขนาด (ตร.ว.)"),
            "price_per_sq_wah": st.column_config.NumberColumn("ราคา/ตร.ว.", format="%d"),
            "status": "ผลประเมิน AI",
            "contact_number": "เบอร์ติดต่อ"
        },
        use_container_width=True
    )
else:
    st.info("ยังไม่มีข้อมูลในระบบ กรุณารันสคริปต์เพิ่มข้อมูลก่อนครับ")