import os
import json
import requests
import uuid
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    QuickReply, QuickReplyButton, MessageAction
)
from supabase import create_client, Client
import google.generativeai as genai

# --- ไลบรารีสำหรับสร้างและจัดหน้า PDF ---
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4

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

USER_STATES = {}

# ---------------- ฟังก์ชันสร้าง PDF สัญญา ----------------
def create_contract_pdf(contract_data):
    # 1. โหลดฟอนต์ภาษาไทย (ดาวน์โหลดมาเก็บไว้ชั่วคราว)
    font_path = "/tmp/THSarabunNew.ttf"
    if not os.path.exists(font_path):
        font_url = "https://github.com/winitk/thaifonts/raw/master/THSarabunNew.ttf"
        r = requests.get(font_url, allow_redirects=True)
        open(font_path, 'wb').write(r.content)
    
    pdfmetrics.registerFont(TTFont('THSarabun', font_path))
    
    # 2. ตั้งชื่อไฟล์และที่เก็บชั่วคราว
    file_name = f"contract_{uuid.uuid4().hex[:8]}.pdf"
    file_path = f"/tmp/{file_name}"
    
    # 3. วาดข้อความลง PDF
    c = canvas.Canvas(file_path)
    c.setFont("THSarabun", 24)
    c.drawString(200, 800, f"บันทึกข้อตกลง / สัญญา")
    
    c.setFont("THSarabun", 16)
    y_position = 750
    for key, value in contract_data.items():
        c.drawString(50, y_position, f"{key}: {value}")
        y_position -= 30
        
    c.save()
    
    # 4. อัปโหลดขึ้น Supabase Storage (ถังชื่อ 'contracts')
    with open(file_path, "rb") as f:
        supabase.storage.from_("contracts").upload(file_name, f, {"content-type": "application/pdf"})
    
    # 5. ดึง Public URL ส่งกลับไป
    public_url = supabase.storage.from_("contracts").get_public_url(file_name)
    return public_url


@app.route("/")
def home():
    return "Vela Property LINE Bot is running actively!"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

def parse_gemini_json(response_text):
    raw_text = response_text.strip()
    if "```json" in raw_text:
        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_text:
        raw_text = raw_text.split("```")[1].strip()
    return json.loads(raw_text)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()
    user_id = event.source.user_id
    model = genai.GenerativeModel('gemini-3.6-flash')
    
    current_state = USER_STATES.get(user_id)

    # ---------------- ดักจับคำสั่งจากปุ่ม Rich Menu ----------------
    if user_text == "[MENU] บันทึกตลาด":
        USER_STATES[user_id] = "MARKET_SCOUT"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📍 **โหมดบันทึกตลาด**\n\nวางข้อความหรือลิงก์โพสต์ขายได้เลยครับ (ไม่ต้องพิมพ์ 'บันทึกตลาด' แล้ว)"))
        return

    elif user_text == "[MENU] เพิ่มลูกค้า":
        USER_STATES[user_id] = "CRM"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="👥 **โหมดเพิ่มลูกค้า / CRM**\n\nวางรายละเอียดความต้องการและงบประมาณได้เลยครับ"))
        return

    elif user_text == "[MENU] สร้างโพสต์ขาย":
        USER_STATES[user_id] = "CONTENT"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✍️ **โหมดสร้างโพสต์ขาย**\n\nวางข้อมูลทรัพย์ที่ต้องการให้เขียนแคปชันได้เลยครับ"))
        return

    elif user_text == "[MENU] คำนวณค่าโอน":
        USER_STATES[user_id] = "TAX"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🧮 **โหมดคำนวณค่าโอน**\n\nพิมพ์ตัวเลขราคาขาย, ราคาประเมิน และปีที่ถือครองได้เลยครับ"))
        return

    elif user_text == "[MENU] ประเมินราคา":
        USER_STATES[user_id] = "VALUATION"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📊 **โหมดประเมินราคา**\n\nวางข้อมูลทรัพย์ที่ต้องการให้ประเมินเทียบกับตลาดได้เลยครับ"))
        return

    elif user_text in ("ยกเลิก", "[MENU] ยกเลิก"):
        if user_id in USER_STATES: del USER_STATES[user_id]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔄 ยกเลิกรายการเรียบร้อย กลับสู่โหมดปกติครับ"))
        return

    # ---------------- โมดูล 1: บันทึกตลาด ----------------
    if current_state == "MARKET_SCOUT" or user_text.startswith("บันทึกตลาด"):
        if user_id in USER_STATES: del USER_STATES[user_id] 
        clean_text = user_text.replace("บันทึกตลาด", "").strip()
        
        prompt = f"""
        สกัดข้อมูลอสังหาริมทรัพย์พื้นที่ปากช่องจากข้อความนี้ ให้อยู่ในรูปแบบ JSON เท่านั้น:
        "{clean_text}"
        
        รูปแบบ:
        {{
            "property_type": "ประเภททรัพย์ ถ้าไม่มีใส่ 'ไม่ระบุ'",
            "location_zone": "ชื่อตำบลในปากช่อง ถ้าไม่มีใส่ 'ไม่ระบุ'",
            "price": ตัวเลขราคาขายรวมเป็นบาท (ถ้าไม่มีใส่ null),
            "size_sq_wah": ตัวเลขขนาดพื้นที่รวมเป็นตารางวา (ถ้าไม่มีใส่ null),
            "source_url": "URL ที่พบ (ถ้าไม่มีใส่ null)",
            "latitude": ตัวเลขพิกัดละติจูด (บังคับ! หากไม่มีตัวเลขพิกัด ให้ประเมินจากจุดสังเกตในข้อความ เช่น 'ธายาม่า', 'คลองม่วง', 'ซีเจ' แล้วใส่ละติจูดของบริเวณนั้น ห้ามใส่ null ถ้ามีเบาะแส),
            "longitude": ตัวเลขพิกัดลองจิจูด (บังคับประเมินจากสถานที่เช่นเดียวกับ latitude)
        }}
        """
        try:
            response = model.generate_content(prompt)
            data = parse_gemini_json(response.text)
            
            price = data.get('price')
            size = data.get('size_sq_wah')
            lat, lng = data.get('latitude'), data.get('longitude')
            
            price_per_sq_wah = float(price) / float(size) if price and size and float(size) > 0 else None
                
            insert_data = {
                "property_type": data.get('property_type', 'ไม่ระบุ'),
                "location_zone": data.get('location_zone', 'ไม่ระบุ'),
                "price": price,
                "size_sq_wah": size,
                "price_per_sq_wah": price_per_sq_wah,
                "source_url": data.get('source_url'),
                "latitude": lat,
                "longitude": lng,
                "status": "ใหม่"
            }
            supabase.table("pakchong_market_scout").insert(insert_data).execute()
            
            lat_lng_msg = f"{lat}, {lng} (AI ประเมินทำเล)" if lat else "ไม่ระบุ"
            
            reply_msg = (f"✅ บันทึกตลาดสำเร็จ!\n📌 {insert_data['property_type']} | ต.{insert_data['location_zone']}\n"
                         f"💰 ราคา: {f'{price:,.0f}' if price else 'ไม่ระบุ'} บาท\n"
                         f"🗺️ พิกัด: {lat_lng_msg}")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ Error: {str(e)}"))

    # ---------------- โมดูล 2: CRM & Matching ----------------
    elif current_state == "CRM" or user_text.startswith(("เพิ่มลูกค้า", "เพิ่มผู้ขาย", "เพิ่มนายหน้า")):
        if user_id in USER_STATES: del USER_STATES[user_id]
        clean_text = user_text
        for w in ["เพิ่มลูกค้า", "เพิ่มผู้ขาย", "เพิ่มนายหน้า"]: clean_text = clean_text.replace(w, "").strip()
        
        contact_type = "ผู้ซื้อ" if "ผู้ซื้อ" in user_text or "ลูกค้า" in user_text else "ผู้ขาย" if "ผู้ขาย" in user_text else "นายหน้า"
        if current_state == "CRM" and contact_type not in ["ผู้ขาย", "นายหน้า"]: contact_type = "ผู้ซื้อ" 
        
        prompt = f"""
        สกัดข้อมูล Lead จากข้อความนี้ให้อยู่ในรูปแบบ JSON เท่านั้น: "{clean_text}"
        รูปแบบ: {{"name": "ชื่อ", "budget_max": ตัวเลขงบสูงสุดเป็นบาท, "property_type": "ประเภท", "location_zone": "ทำเล", "contact_info": "เบอร์/Line", "note": "รายละเอียด"}}
        """
        try:
            response = model.generate_content(prompt)
            data = parse_gemini_json(response.text)
            
            insert_data = {
                "contact_type": contact_type,
                "name": data.get('name', 'ไม่ระบุชื่อ'),
                "budget_max": data.get('budget_max', 0),
                "property_type": data.get('property_type', 'ไม่ระบุ'),
                "location_zone": data.get('location_zone', 'ไม่ระบุ'),
                "contact_info": data.get('contact_info', ''),
                "note": data.get('note', '')
            }
            supabase.table("pakchong_crm").insert(insert_data).execute()
            
            reply_msg = f"👤 บันทึก {contact_type} สำเร็จ: {insert_data['name']}\n🔎 หา: {insert_data['property_type']} โซน {insert_data['location_zone']}\n💰 งบสูงสุด: {f'{insert_data['budget_max']:,.0f}'} บาท\n"
            
            if contact_type == "ผู้ซื้อ" and insert_data['budget_max'] > 0:
                match_response = supabase.table("pakchong_market_scout").select("property_type, location_zone, price").lte("price", insert_data['budget_max']).ilike("location_zone", f"%{insert_data['location_zone']}%").order("price", desc=True).limit(3).execute()
                matches = match_response.data
                if matches:
                    reply_msg += "\n🔥 พบทรัพย์ที่อาจตรงสเปก:\n"
                    for i, m in enumerate(matches, 1):
                        reply_msg += f"{i}. {m['property_type']} ต.{m['location_zone']} - {m['price']:,.0f} บ.\n"

            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ Error CRM: {str(e)}"))

    # ---------------- โมดูล 3: สร้างโพสต์ขาย ----------------
    elif current_state == "CONTENT" or user_text.startswith("โพสต์"):
        if user_id in USER_STATES: del USER_STATES[user_id]
        clean_text = user_text.replace("โพสต์", "").strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⏳ AI กำลังเรียบเรียงแคปชันและดึงจุดขาย กรุณารอสักครู่..."))
        prompt = f"""
        คุณคือนักการตลาดอสังหาริมทรัพย์มืออาชีพ จงเขียนแคปชัน Facebook/TikTok สำหรับขายทรัพย์นี้:
        ข้อมูล: "{clean_text}"
        แบ่งเป็น 3 ส่วน: 1. Headline ดึงดูดใจ, 2. Caption เน้นจุดเด่น (ใช้อีโมจิ), 3. Hashtags
        """
        try:
            response = model.generate_content(prompt)
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=response.text.strip()))
        except Exception as e:
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"❌ Error Content: {str(e)}"))

# ---------------- โมดูล 4: เมนูกฎหมายและสัญญา (PDF) ----------------
    elif user_text == "[MENU] สัญญา":
        quick_reply_buttons = QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="🆕 สร้างสัญญา", text="[CONTRACT] สร้าง")),
            QuickReplyButton(action=MessageAction(label="🔍 ตรวจสอบสัญญา", text="[CONTRACT] ตรวจสอบ")),
            QuickReplyButton(action=MessageAction(label="✏️ แก้ไขสัญญา", text="[CONTRACT] แก้ไข")),
            QuickReplyButton(action=MessageAction(label="❌ ยกเลิก", text="ยกเลิก"))
        ])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📑 **เมนูกฎหมายและสัญญาอสังหาฯ**\nกรุณาเลือกรายการที่ต้องการทำครับ:", quick_reply=quick_reply_buttons))

    elif user_text == "[CONTRACT] สร้าง":
        quick_reply_types = QuickReply(items=[
            QuickReplyButton(action=MessageAction(label="นายหน้าเปิด (Open)", text="[CREATE_PDF] นายหน้าเปิด")),
            QuickReplyButton(action=MessageAction(label="นายหน้าปิด (Exclusive)", text="[CREATE_PDF] นายหน้าปิด")),
            QuickReplyButton(action=MessageAction(label="สัญญาจะซื้อจะขาย", text="[CREATE_PDF] สัญญาจะซื้อจะขาย")),
            QuickReplyButton(action=MessageAction(label="ใบจอง", text="[CREATE_PDF] ใบจอง")),
            QuickReplyButton(action=MessageAction(label="❌ ยกเลิก", text="ยกเลิก"))
        ])
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📝 **เลือกประเภทสัญญาที่ต้องการสร้าง:**", quick_reply=quick_reply_types))

    elif user_text.startswith("[CREATE_PDF]"):
        contract_type = user_text.replace("[CREATE_PDF]", "").strip()
        USER_STATES[user_id] = f"PDF_{contract_type}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📄 **พร้อมสร้าง: {contract_type}**\n\nพิมพ์ข้อมูลดีลได้เลยครับ (ส่วนไหนไม่ระบุ AI จะเว้นช่องว่างให้เติมทีหลัง)"))

    elif user_text == "[CONTRACT] ตรวจสอบ":
        USER_STATES[user_id] = "CONTRACT_CHECK"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔍 **โหมดตรวจสอบสัญญา**\n\nวางข้อความสัญญาที่ต้องการให้ AI เช็กความเสี่ยงได้เลยครับ"))

    elif user_text == "[CONTRACT] แก้ไข":
        USER_STATES[user_id] = "CONTRACT_EDIT"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✏️ **โหมดแก้ไขสัญญา**\n\nวางจุดที่ต้องการปรับแก้หรือเกลาภาษาได้เลยครับ"))

    # ระบบออกไฟล์ PDF โดยอิงตาม CONTRACT_TEMPLATES
    elif current_state and current_state.startswith("PDF_"):
        contract_type = current_state.replace("PDF_", "")
        if user_id in USER_STATES: del USER_STATES[user_id]
        
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"⏳ ทนาย AI กำลังร่าง {contract_type} ให้ถูกต้องตามกฎหมาย และจัดหน้า PDF..."))
        
        # ดึงรายชื่อฟิลด์ที่ต้องการเพื่อสร้าง JSON Prompt ให้ตรงกับ Template
        req_fields = REQUIRED_FIELDS.get(contract_type, [])
        fields_format = ",\n            ".join([f'"{f}": "ข้อมูล (ถ้าไม่ระบุให้ใส่ \'.....................................\')"' for f in req_fields])
        
        prompt = f"""
        สกัดข้อมูลเพื่อทำสัญญาจากข้อความนี้ ให้อยู่ในรูปแบบ JSON เท่านั้น:
        "{user_text}"
        
        รูปแบบ:
        {{
            "contract_date": "วันที่ทำสัญญา (ถ้าไม่ระบุให้ใส่ '.....................................')",
            {fields_format}
        }}
        """
        try:
            response = model.generate_content(prompt)
            extracted_data = parse_gemini_json(response.text)
            
            # นำข้อมูลที่สกัดได้ไปแทนที่ใน Template
            template = CONTRACT_TEMPLATES.get(contract_type, "")
            full_text = template.format(**extracted_data)
            
            # เรียกฟังก์ชันสร้าง PDF (ส่งชื่อสัญญา และข้อความเต็ม)
            pdf_url = create_contract_pdf(contract_type, full_text)
            
            reply_msg = f"✅ **ร่างสัญญาพร้อมใช้งาน!**\n\nดาวน์โหลดไฟล์ PDF ขนาด A4 เพื่อพิมพ์ให้ลูกค้าเซ็นได้ทันที:\n🔗 {pdf_url}"
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=reply_msg))
            
        except Exception as e:
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"❌ เกิดข้อผิดพลาดในการสร้าง PDF: {str(e)}"))

    # ระบบตรวจสอบสัญญา (สวมบททนาย)
    elif current_state == "CONTRACT_CHECK" or user_text.startswith("ตรวจสัญญา"):
        if user_id in USER_STATES: del USER_STATES[user_id]
        clean_text = user_text.replace("ตรวจสัญญา", "").strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⏳ ทนาย AI กำลังสแกนหาช่องโหว่และเงื่อนไขที่เอาเปรียบ..."))
        
        prompt = f"""
        คุณคือทนายความอสังหาริมทรัพย์ที่เชี่ยวชาญกฎหมายไทย ตรวจสอบข้อความนี้: "{clean_text}"
        แสดงผลลัพธ์เป็น Bullet Points ที่อ่านง่ายบนมือถือ:
        1. 🚨 จุดเสี่ยง/ข้อควรระวัง
        2. ⚖️ ความเป็นธรรม (ฝั่งไหนได้เปรียบ/เสียเปรียบ)
        3. 💡 ข้อแนะนำเพิ่มเติมเพื่อปิดช่องโหว่
        """
        try:
            response = model.generate_content(prompt)
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"🔍 **ผลการตรวจสอบสัญญา**\n\n{response.text.strip()}"))
        except Exception as e:
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"❌ Error Check: {str(e)}"))

    # ระบบแก้ไขสัญญา (เกลาภาษา)
    elif current_state == "CONTRACT_EDIT" or user_text.startswith("แก้ไขสัญญา"):
        if user_id in USER_STATES: del USER_STATES[user_id]
        clean_text = user_text.replace("แก้ไขสัญญา", "").strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⏳ ทนาย AI กำลังเกลาภาษากฎหมายให้รัดกุม..."))
        
        prompt = f"""
        คุณคือทนายความอสังหาริมทรัพย์มืออาชีพ แก้ไขเกลาข้อความนี้ให้รัดกุม เป็นทางการ: "{clean_text}"
        แสดงผลลัพธ์:
        ✨ **ข้อความที่แก้ไขแล้ว:** (พร้อมนำไปก๊อปปี้วาง)
        📝 **สิ่งที่ปรับเปลี่ยน:** (อธิบายสั้นๆ ว่าปรับแก้จุดใดเพื่อให้รัดกุมขึ้น)
        """
        try:
            response = model.generate_content(prompt)
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"✏️ **ร่างข้อความใหม่**\n\n{response.text.strip()}"))
        except Exception as e:
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"❌ Error Edit: {str(e)}"))

    # ---------------- โมดูล 5: คำนวณค่าโอน (ปรับเป็นแบบบิลใบเสร็จ) ----------------
    elif current_state == "TAX" or user_text.startswith("ค่าโอน"):
        if user_id in USER_STATES: del USER_STATES[user_id]
        clean_text = user_text.replace("ค่าโอน", "").strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⏳ AI กำลังคำนวณภาษีและค่าธรรมเนียม กรุณารอสักครู่..."))
        prompt = f"""
        คุณคือเจ้าหน้าที่ประเมินอสังหาฯ จงคำนวณค่าใช้จ่ายวันโอนจากข้อมูล: "{clean_text}"
        
        กฎ: ห้ามอธิบายยืดเยื้อ ให้ออกแบบข้อความเหมือน 'บิลใบเสร็จ' ที่อ่านง่ายบนจอมือถือที่สุด ใช้ Emoji ช่วย
        สมมติฐานหากไม่ระบุ: บุคคลธรรมดา, ถือครอง 3 ปี
        
        รูปแบบที่ต้องการ:
        🧾 สรุปค่าโอนกรรมสิทธิ์
        📍 ราคาขาย: ... บ. | ประเมิน: ... บ.
        
        1. ค่าธรรมเนียมโอน (2%): ... บ.
        2. ภาษีธุรกิจเฉพาะ (3.3%) / อากร (0.5%): ... บ. (เลือกอันที่เข้าเงื่อนไข)
        3. ภาษีเงินได้ (หัก ณ ที่จ่าย): ... บ. (ประมาณการ)
        
        💰 รวมต้องเตรียมเงินสดประมาณ: ... บาท
        """
        try:
            response = model.generate_content(prompt)
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=response.text.strip()))
        except Exception as e:
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"❌ Error Tax: {str(e)}"))

    # ---------------- โมดูล 6: ประเมินราคา (อัปเกรดเทียบราคาตลาด + ประเมินราชการ) ----------------
    elif current_state == "VALUATION" or user_text.startswith("ประเมิน"):
        if user_id in USER_STATES: del USER_STATES[user_id]
        clean_text = user_text.replace("ประเมิน", "").strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⏳ AI กำลังวิเคราะห์ราคาตลาดและประเมินส่วนต่าง (Markup) กรุณารอสักครู่..."))
        
        prompt_extract = f"""
        สกัดข้อมูลเพื่อประเมินราคา จากข้อความนี้ให้อยู่ในรูปแบบ JSON เท่านั้น: "{clean_text}"
        รูปแบบ: {{
            "property_type": "ประเภท (เช่น ที่ดิน, บ้าน)", 
            "location_zone": "ทำเล (ตำบล)", 
            "price": 0, 
            "size_sq_wah": 0,
            "gov_price": 0
        }}
        (หมายเหตุ: ถ้าผู้ใช้ไม่ได้ระบุราคาประเมินราชการ ให้ใส่ gov_price เป็น 0)
        """
        try:
            ext_response = model.generate_content(prompt_extract)
            data = parse_gemini_json(ext_response.text)
            
            target_type = data.get('property_type', 'ไม่ระบุ')
            target_zone = data.get('location_zone', 'ไม่ระบุ')
            target_price = data.get('price', 0)
            target_size = data.get('size_sq_wah', 0)
            gov_price = data.get('gov_price', 0)
            
            target_price_per_sqw = target_price / target_size if target_size and target_size > 0 else 0
            
            # 1. เช็กข้อมูลเปรียบเทียบใน Database (ถ้ามี)
            res = supabase.table("pakchong_market_scout").select("price, size_sq_wah, price_per_sq_wah").eq("property_type", target_type).ilike("location_zone", f"%{target_zone}%").execute()
            comparables = [c for c in res.data if c.get('price_per_sq_wah')]
            db_count = len(comparables)
            avg_price_db = sum([c['price_per_sq_wah'] for c in comparables]) / db_count if db_count > 0 else 0
            
            # 2. ให้ AI วิเคราะห์ข้ามมิติ (DB + ความรู้ทำเล + สัดส่วนราคาประเมิน)
            analysis_prompt = f"""
            คุณคือนักประเมินราคาอสังหาฯ ระดับมืออาชีพ พื้นที่ปากช่อง/เขาใหญ่
            จงวิเคราะห์ความคุ้มค่าของทรัพย์นี้ โดยใช้ข้อมูลเบื้องต้นและความเชี่ยวชาญของคุณ:
            
            📍 ทรัพย์: {target_type} ต.{target_zone} ขนาด {target_size} ตร.ว.
            💰 ราคาเสนอขาย: {target_price:,.0f} บาท (ตก {target_price_per_sqw:,.0f} บ./ตร.ว.)
            🏛️ ราคาประเมินราชการ: {gov_price:,.0f} บาท
            📊 ข้อมูลเปรียบเทียบในระบบ: {db_count} แปลง (ราคาเฉลี่ย {avg_price_db:,.0f} บ./ตร.ว.)
            
            วิเคราะห์ 3 ข้อต่อไปนี้ให้อ่านง่าย (เหมือนบิลใบเสร็จ สั้น กระชับ ใช้ Emoji):
            1. ส่วนต่างราคา (Markup): เทียบราคาเสนอขายกับราคาประเมินราชการ (ถ้าระบุ) ว่าแพงกว่ากี่เท่า สมเหตุสมผลกับทำเลปากช่องหรือไม่ (ปกติบวก 1.5 - 3 เท่า)
            2. แนวโน้มตลาด: ราคา {target_price_per_sqw:,.0f} บ./ตร.ว. ใน ต.{target_zone} ถือว่าถูก หรือ แพง กว่าราคาซื้อขายทั่วไปบนเว็บไซต์อสังหาฯ ในปัจจุบัน
            3. สรุปความคุ้มค่า: เป็น Good Deal หรือไม่? ควรต่อรองราคาเหลือเท่าไรเพื่อปิดดีล?
            """
            
            analysis = model.generate_content(analysis_prompt).text.strip()
            reply_msg = f"📊 **รายงานประเมินราคา:** {target_type} ต.{target_zone}\n\n{analysis}"
            
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=reply_msg))
            
        except Exception as e:
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"❌ Error Valuation: {str(e)}"))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="💡 กรุณากดเลือกเมนูจาก Rich Menu ด้านล่างได้เลยครับ"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)