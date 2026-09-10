import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from supabase import create_client, Client
import google.generativeai as genai
import json

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

SUPABASE_URL = "https://vfieyjxlrpziiksyccdt.supabase.co"
SUPABASE_KEY = "sb_publishable_udkJwGJ8zjXlEOlYszDRUg_yVD4g7ie"

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# พิกัดกลางของโซนต่างๆ ในเขาใหญ่
ZONE_COORDS = {
    "หมูสี": (14.5381, 101.4017),
    "หนองน้ำแดง": (14.6500, 101.4167),
    "พญาเย็น": (14.6333, 101.2167),
    "ปากช่อง": (14.7081, 101.4161),
    "ขนงพระ": (14.6100, 101.4500),
    "default": (14.5500, 101.4000) # พิกัดกลางเขาใหญ่
}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    
    prompt = f"""
    ช่วยสกัดข้อมูลอสังหาริมทรัพย์จากข้อความนี้ให้อยู่ในรูปแบบ JSON เท่านั้น โดยไม่มี markdown:
    ข้อความ: "{user_text}"
    
    รูปแบบ JSON ที่ต้องการ:
    {{
        "price": ตัวเลขราคาขายรวม (บาท) เป็น integer เช่น 6000000 (ถ้าไม่พบใส่ null),
        "size_sq_wah": ขนาดพื้นที่เป็นตารางวา เช่น 800 (ถ้าเป็นไร่ให้แปลงเป็นตารางวา เช่น 2 ไร่ = 800 ตร.ว.),
        "location_zone": "ชื่อตำบลหรือโซน เช่น หมูสี, หนองน้ำแดง, พญาเย็น (ถ้าไม่ระบุใส่ null)",
        "contact_name": "ชื่อผู้ติดต่อหรือนายหน้า",
        "contact_number": "เบอร์โทรศัพท์"
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        text_response = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text_response)
        
        price = data.get('price')
        size = data.get('size_sq_wah')
        zone = data.get('location_zone', 'default')
        
        # ดึงพิกัดตามโซน
        lat, lng = ZONE_COORDS.get(zone, ZONE_COORDS['default']) if zone in ZONE_COORDS else ZONE_COORDS['default']
        
        if price and size:
            price_per_sq_wah = price / size
            status = "Good Deal" if price_per_sq_wah < 12000 else "Overpriced" if price_per_sq_wah > 18000 else "Market Price"
            
            insert_data = {
                "price": price,
                "size_sq_wah": size,
                "contact_name": data.get('contact_name', '-'),
                "contact_number": data.get('contact_number', '-'),
                "latitude": lat,
                "longitude": lng,
                "status": status
            }
            
            supabase.table("vela_khaoyai_properties").insert(insert_data).execute()
            
            reply_msg = f"✅ บันทึกข้อมูลและปักหมุดเรียบร้อย!\n\n" \
                        f"📍 โซน: {zone if zone else 'เขาใหญ่'}\n" \
                        f"💰 ราคา: {price:,.0f} บาท\n" \
                        f"📐 ขนาด: {size} ตร.ว. ({price_per_sq_wah:,.0f} บ./ตร.ว.)\n" \
                        f"📊 ผลประเมิน AI: {status}"
        else:
            reply_msg = "⚠️ อ่านราคาหรือขนาดพื้นที่ไม่ชัดเจน กรุณาระบุ เช่น 'ขายที่หมูสี 2 ไร่ 6 ล้าน'"
            
    except Exception as e:
        reply_msg = f"❌ เกิดข้อผิดพลาด: {str(e)}"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)