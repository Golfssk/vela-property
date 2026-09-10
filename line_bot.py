import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from supabase import create_client, Client
import google.generativeai as genai
import json

app = Flask(__name__)

# ดึงค่าจาก Environment Variables เพื่อความปลอดภัย
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
    ช่วยสกัดข้อมูลอสังหาริมทรัพย์จากข้อความนี้ให้อยู่ในรูปแบบ JSON เท่านั้น โดยไม่มี markdown หรือข้อความอื่น:
    ข้อความ: "{user_text}"
    
    รูปแบบ JSON ที่ต้องการ:
    {{
        "price": ตัวเลขราคาขายรวม (บาท) เป็น integer เช่น 5000000 (ถ้าไม่พบให้ใส่ null),
        "size_sq_wah": ขนาดพื้นที่เป็นตารางวา เช่น 800 (ถ้าหน่วยเป็นไร่-งาน-วา ให้แปลงเป็นตารางวา เช่น 2 ไร่ = 800 ตร.ว.),
        "contact_name": "ชื่อผู้ติดต่อหรือนายหน้า (ถ้าไม่ระบุให้ใส่ null)",
        "contact_number": "เบอร์โทรศัพท์ติดต่อ",
        "property_url": "ลิงก์รูปหรือลิงก์ประกาศ (ถ้ามี)"
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        text_response = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text_response)
        
        price = data.get('price')
        size = data.get('size_sq_wah')
        
        if price and size:
            price_per_sq_wah = price / size
            status = "Good Deal" if price_per_sq_wah < 12000 else "Overpriced" if price_per_sq_wah > 18000 else "Market Price"
            
            insert_data = {
                "price": price,
                "size_sq_wah": size,
                "contact_name": data.get('contact_name', '-'),
                "contact_number": data.get('contact_number', '-'),
                "property_url": data.get('property_url', '-'),
                "status": status
            }
            
            supabase.table("vela_khaoyai_properties").insert(insert_data).execute()
            
            reply_msg = f"✅ บันทึกข้อมูลเข้าระบบเรียบร้อยแล้วครับ!\n\n" \
                        f"💰 ราคา: {price:,.0f} บาท\n" \
                        f"📐 ขนาด: {size} ตร.ว. ({price_per_sq_wah:,.0f} บาท/ตร.ว.)\n" \
                        f"👤 ผู้ติดต่อ: {data.get('contact_name', '-')}\n" \
                        f"📞 เบอร์โทร: {data.get('contact_number', '-')}\n" \
                        f"📊 ผลประเมิน AI: {status}"
        else:
            reply_msg = "⚠️ ไม่สามารถอ่านข้อมูลราคาหรือขนาดพื้นที่ได้ชัดเจน กรุณาระบุรายละเอียดเพิ่มเติมครับ"
            
    except Exception as e:
        reply_msg = f"❌ เกิดข้อผิดพลาดในการประมวลผล: {str(e)}"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)