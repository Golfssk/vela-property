# app.py
# Vela Property Agent OS - LINE Bot Backend
# Production-grade build

import os
import re
import json
import uuid
import logging
import datetime
import traceback
from typing import Optional, Dict, Any, List

import requests
from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, ImageMessage, LocationMessage,
    TextSendMessage, QuickReply, QuickReplyButton, MessageAction,
)

from supabase import create_client, Client
import google.generativeai as genai

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

from contract_templates import CONTRACT_TEMPLATES, REQUIRED_FIELDS
from thai_num import baht_text, fmt_money

# ==========================================================
# CONFIG
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("vela")

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

_missing = [k for k, v in {
    "LINE_CHANNEL_SECRET": LINE_CHANNEL_SECRET,
    "LINE_CHANNEL_ACCESS_TOKEN": LINE_CHANNEL_ACCESS_TOKEN,
    "GEMINI_API_KEY": GEMINI_API_KEY,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_KEY": SUPABASE_KEY,
}.items() if not v]
if _missing:
    log.warning("ENV ที่ยังไม่ได้ตั้งค่า: %s", ", ".join(_missing))

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None
supabase: Optional[Client] = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

FONT_URL = os.getenv(
    "THAI_FONT_URL",
    "https://github.com/winitk/thaifonts/raw/master/THSarabunNew.ttf",
)
FONT_PATH = "/tmp/THSarabunNew.ttf"
_FONT_READY = False

DRAFT_EXPIRE_MINUTES = 60
SIGNED_URL_TTL = 60 * 60 * 6  # 6 ชั่วโมง

# ==========================================================
# GEO: พิกัดกลาง 12 ตำบล อ.ปากช่อง (ใช้เมื่อไม่มีพิกัดจริง)
# ==========================================================

TAMBON_CENTROIDS: Dict[str, tuple] = {
    "ปากช่อง":      (14.7050, 101.4160),
    "หมูสี":        (14.5060, 101.3720),
    "กลางดง":       (14.6300, 101.2570),
    "จันทึก":       (14.6820, 101.5540),
    "วังกะทะ":      (14.4340, 101.5000),
    "หนองน้ำแดง":   (14.6110, 101.4020),
    "หนองสาหร่าย":  (14.7360, 101.3680),
    "ขนงพระ":       (14.6250, 101.4600),
    "โป่งตาลอง":    (14.5480, 101.4530),
    "คลองม่วง":     (14.7860, 101.5820),
    "วังไทร":       (14.7620, 101.4820),
    "พญาเย็น":      (14.6190, 101.1820),
}
VALID_TAMBONS = list(TAMBON_CENTROIDS.keys())

# ==========================================================
# STATE STORE (Supabase + fallback RAM)
# ==========================================================

_MEM_STATE: Dict[str, Dict[str, Any]] = {}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def set_state(user_id: str, module: Optional[str], draft: Optional[dict] = None) -> None:
    """บันทึกสถานะผู้ใช้ ลง Supabase ถ้าทำได้ ไม่งั้นเก็บใน RAM"""
    payload = {
        "line_user_id": user_id,
        "current_module": module,
        "draft_data": draft or {},
        "updated_at": _now().isoformat(),
        "expires_at": (_now() + datetime.timedelta(minutes=DRAFT_EXPIRE_MINUTES)).isoformat(),
    }
    _MEM_STATE[user_id] = payload
    if not supabase:
        return
    try:
        supabase.table("user_sessions").upsert(payload, on_conflict="line_user_id").execute()
    except Exception as e:
        log.warning("set_state -> Supabase ล้มเหลว ใช้ RAM แทน: %s", e)


def get_state(user_id: str) -> Dict[str, Any]:
    """อ่านสถานะผู้ใช้ พร้อมเช็กวันหมดอายุ"""
    row = None
    if supabase:
        try:
            res = (supabase.table("user_sessions")
                   .select("*").eq("line_user_id", user_id).limit(1).execute())
            row = res.data[0] if res.data else None
        except Exception as e:
            log.warning("get_state -> Supabase ล้มเหลว: %s", e)
    if row is None:
        row = _MEM_STATE.get(user_id)
    if not row:
        return {"current_module": None, "draft_data": {}}

    exp = row.get("expires_at")
    if exp:
        try:
            exp_dt = datetime.datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if exp_dt < _now():
                clear_state(user_id)
                return {"current_module": None, "draft_data": {}}
        except Exception:
            pass
    return {
        "current_module": row.get("current_module"),
        "draft_data": row.get("draft_data") or {},
    }


def clear_state(user_id: str) -> None:
    _MEM_STATE.pop(user_id, None)
    if not supabase:
        return
    try:
        supabase.table("user_sessions").delete().eq("line_user_id", user_id).execute()
    except Exception as e:
        log.warning("clear_state ล้มเหลว: %s", e)


# ==========================================================
# LINE HELPERS
# ==========================================================

def reply(token: str, text: str, quick: Optional[QuickReply] = None) -> None:
    if not line_bot_api:
        return
    try:
        line_bot_api.reply_message(
            token, TextSendMessage(text=text[:4900], quick_reply=quick)
        )
    except LineBotApiError as e:
        log.error("reply_message ล้มเหลว: %s", e)


def push(user_id: str, text: str, quick: Optional[QuickReply] = None) -> None:
    if not line_bot_api:
        return
    try:
        line_bot_api.push_message(
            user_id, TextSendMessage(text=text[:4900], quick_reply=quick)
        )
    except LineBotApiError as e:
        log.error("push_message ล้มเหลว: %s", e)


def qr(*pairs) -> QuickReply:
    """สร้าง QuickReply จาก tuple (label, text)"""
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label=lb[:20], text=tx))
        for lb, tx in pairs
    ])


MAIN_MENU_HINT = (
    "💡 เลือกเมนูจาก Rich Menu ด้านล่าง หรือพิมพ์คำสั่งได้เลยครับ\n\n"
    "• บันทึกตลาด\n• เพิ่มลูกค้า\n• ประเมิน\n• โพสต์\n• ค่าโอน\n• สัญญา\n• งานวันนี้"
)


# ==========================================================
# GEMINI HELPERS
# ==========================================================

def get_model():
    return genai.GenerativeModel(GEMINI_MODEL)


def ask_gemini(prompt: str, retries: int = 2) -> str:
    """เรียก Gemini พร้อม retry"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = get_model().generate_content(prompt)
            return (resp.text or "").strip()
        except Exception as e:
            last_err = e
            log.warning("Gemini รอบ %s ล้มเหลว: %s", attempt + 1, e)
    raise RuntimeError(f"Gemini ไม่ตอบสนอง: {last_err}")


def parse_gemini_json(raw: str) -> dict:
    """แกะ JSON จากคำตอบ Gemini แบบทนทาน"""
    text = (raw or "").strip()

    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
    text = text.strip()

    # ตัดเอาเฉพาะก้อน { ... } ก้อนแรกสุดถึงปีกกาปิดท้ายสุด
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # ซ่อมเคสที่พบบ่อย: trailing comma, single quote, None/True/False แบบ Python
        fixed = re.sub(r",\s*([}\]])", r"\1", text)
        fixed = fixed.replace("None", "null").replace("True", "true").replace("False", "false")
        try:
            return json.loads(fixed)
        except json.JSONDecodeError as e:
            log.error("parse_gemini_json ล้มเหลว: %s | raw=%s", e, raw[:400])
            raise ValueError("AI ตอบกลับมาในรูปแบบที่อ่านไม่ได้ กรุณาลองส่งใหม่อีกครั้ง")


def ask_gemini_json(prompt: str) -> dict:
    """ขอ JSON จาก Gemini พร้อมพยายามซ่อม 1 รอบถ้าแกะไม่ได้"""
    raw = ask_gemini(prompt)
    try:
        return parse_gemini_json(raw)
    except ValueError:
        repair = (
            "แปลงข้อความต่อไปนี้ให้เป็น JSON ที่ถูกต้องตามมาตรฐาน "
            "ตอบกลับเฉพาะ JSON เท่านั้น ห้ามมีข้อความอื่น:\n\n" + raw
        )
        return parse_gemini_json(ask_gemini(repair, retries=1))


# ==========================================================
# UTILITIES
# ==========================================================

def to_float(v) -> Optional[float]:
    """แปลงค่าเป็น float อย่างปลอดภัย"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d.\-]", "", str(v))
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def normalize_tambon(name: Optional[str]) -> Optional[str]:
    """จับคู่ชื่อตำบลให้ตรงกับ 12 ตำบลจริง"""
    if not name:
        return None
    clean = str(name).replace("ต.", "").replace("ตำบล", "").strip()
    if clean in TAMBON_CENTROIDS:
        return clean
    for t in VALID_TAMBONS:
        if t in clean or clean in t:
            return t
    return None


def safe_fill(template_str: str, data: dict) -> dict:
    """สร้าง dict ที่มีครบทุก placeholder ใน template ป้องกัน KeyError 100%"""
    needed = re.findall(r"\{(\w+)\}", template_str)
    blank = "....................................."
    out = {}
    for key in needed:
        val = data.get(key)
        out[key] = str(val).strip() if val not in (None, "", "null") else blank
    return out


def extract_url(text: str) -> Optional[str]:
    m = re.search(r"https?://[^\s]+", text or "")
    return m.group(0) if m else None


def parse_maps_coords(text: str) -> Optional[tuple]:
    """ดึงพิกัดจากลิงก์ Google Maps หรือข้อความ lat,lng"""
    if not text:
        return None
    m = re.search(r"@(-?\d+\.\d+),\s*(-?\d+\.\d+)", text)
    if not m:
        m = re.search(r"(?:q=|ll=)(-?\d+\.\d+),\s*(-?\d+\.\d+)", text)
    if not m:
        m = re.search(r"\b(1[3-5]\.\d{4,})\s*,\s*(10[01]\.\d{4,})\b", text)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


# ==========================================================
# PDF GENERATOR
# ==========================================================

def ensure_thai_font() -> None:
    global _FONT_READY
    if _FONT_READY and os.path.exists(FONT_PATH):
        return
    if not os.path.exists(FONT_PATH):
        log.info("กำลังดาวน์โหลดฟอนต์ไทย...")
        r = requests.get(FONT_URL, allow_redirects=True, timeout=30)
        r.raise_for_status()
        with open(FONT_PATH, "wb") as f:
            f.write(r.content)
    pdfmetrics.registerFont(TTFont("THSarabun", FONT_PATH))
    _FONT_READY = True


def _page_decoration(canvas_obj, doc):
    """วาดเลขหน้าและหมายเหตุท้ายกระดาษ"""
    canvas_obj.saveState()
    canvas_obj.setFont("THSarabun", 12)
    canvas_obj.setFillGray(0.45)
    canvas_obj.drawCentredString(A4[0] / 2, 12 * mm, f"- หน้า {doc.page} -")
    canvas_obj.drawRightString(
        A4[0] - 18 * mm, 12 * mm,
        "เอกสารร่างโดยระบบ Vela Property Agent OS"
    )
    canvas_obj.restoreState()


def create_contract_pdf(contract_type: str, full_text: str) -> str:
    """สร้าง PDF A4 จากข้อความสัญญาเต็ม แล้วอัปโหลด Supabase Storage คืน signed URL"""
    ensure_thai_font()

    file_name = f"{contract_type.replace(' ', '_')}_{uuid.uuid4().hex[:8]}.pdf"
    file_path = f"/tmp/{file_name}"

    doc = SimpleDocTemplate(
        file_path, pagesize=A4,
        topMargin=20 * mm, bottomMargin=22 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
        title=contract_type, author="Vela Property Agent OS",
    )

    st_title = ParagraphStyle("T", fontName="THSarabun", fontSize=22,
                              leading=30, alignment=TA_CENTER, spaceAfter=10)
    st_body = ParagraphStyle("B", fontName="THSarabun", fontSize=16,
                             leading=24, alignment=TA_JUSTIFY)
    st_center = ParagraphStyle("C", fontName="THSarabun", fontSize=16,
                               leading=24, alignment=TA_CENTER)
    st_sign = ParagraphStyle("S", fontName="THSarabun", fontSize=16,
                             leading=26, alignment=TA_CENTER, spaceBefore=6)
    st_note = ParagraphStyle("N", fontName="THSarabun", fontSize=13,
                             leading=18, textColor="#8a8a8a", alignment=TA_CENTER)

    def esc(s: str) -> str:
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    story = []
    lines = full_text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            story.append(Spacer(1, 7))
            continue
        if i == 0:
            story.append(Paragraph(esc(stripped), st_title))
        elif stripped.startswith("ลงชื่อ"):
            story.append(Paragraph(esc(stripped), st_sign))
        elif stripped.startswith(("ทำที่", "วันที่")):
            story.append(Paragraph(esc(stripped), st_center))
        else:
            story.append(Paragraph(esc(stripped), st_body))

    story.append(Spacer(1, 16))
    story.append(Paragraph(
        "หมายเหตุ: เอกสารฉบับนี้เป็นร่างที่จัดทำโดยระบบอัตโนมัติ "
        "โปรดตรวจทานความถูกต้องและปรึกษาผู้เชี่ยวชาญด้านกฎหมายก่อนลงนามใช้จริง",
        st_note,
    ))

    doc.build(story, onFirstPage=_page_decoration, onLaterPages=_page_decoration)

    if not supabase:
        raise RuntimeError("ยังไม่ได้เชื่อมต่อ Supabase")

    with open(file_path, "rb") as f:
        supabase.storage.from_("contracts").upload(
            file_name, f, {"content-type": "application/pdf"}
        )

    try:
        signed = supabase.storage.from_("contracts").create_signed_url(file_name, SIGNED_URL_TTL)
        url = signed.get("signedURL") or signed.get("signedUrl")
        if url:
            return url if url.startswith("http") else f"{SUPABASE_URL}{url}"
    except Exception as e:
        log.warning("create_signed_url ล้มเหลว fallback public url: %s", e)

    return supabase.storage.from_("contracts").get_public_url(file_name)


# ==========================================================
# MODULE 1: MARKET SCOUT
# ==========================================================

MARKET_PROMPT = """คุณคือระบบสกัดข้อมูลอสังหาริมทรัพย์ อำเภอปากช่อง จังหวัดนครราชสีมา
อ่านข้อความต่อไปนี้แล้วตอบกลับเป็น JSON เท่านั้น ห้ามมีคำอธิบายอื่น

ข้อความ:
\"\"\"{text}\"\"\"

รูปแบบ JSON:
{{
  "property_type": "ที่ดิน | บ้านเดี่ยว | พูลวิลล่า | คอนโด | ทาวน์โฮม | รีสอร์ต | อาคารพาณิชย์ | ไม่ระบุ",
  "project_name": "ชื่อโครงการ ถ้าไม่มีใส่ null",
  "location_zone": "ชื่อตำบล เลือกจาก [{tambons}] เท่านั้น ถ้าไม่พบในข้อความให้ใส่ null",
  "landmark": "จุดสังเกตที่กล่าวถึง เช่น ชื่อถนน ร้าน โรงเรียน ถ้าไม่มีใส่ null",
  "price": ตัวเลขราคารวมเป็นบาท ถ้าไม่มีใส่ null,
  "size_sq_wah": ตัวเลขขนาดที่ดินรวมเป็นตารางวา ถ้าไม่มีใส่ null,
  "usable_area_sqm": ตัวเลขพื้นที่ใช้สอยเป็นตารางเมตร ถ้าไม่มีใส่ null,
  "bedrooms": ตัวเลขจำนวนห้องนอน ถ้าไม่มีใส่ null,
  "contact_info": "เบอร์โทรหรือ LINE ถ้าถูกเซ็นเซอร์หรือไม่มีใส่ null",
  "seller_type": "เจ้าของ | นายหน้า | โครงการ",
  "highlights": "จุดเด่นสรุปสั้นไม่เกิน 120 ตัวอักษร"
}}

กฎเหล็ก:
- 1 ไร่ = 400 ตารางวา, 1 งาน = 100 ตารางวา ให้แปลงเป็นตารางวารวมเสมอ
- ห้ามนำข้อความใน hashtag (#) มาใช้เป็นข้อมูล
- ห้ามเดาข้อมูลที่ไม่มีในข้อความ ให้ใส่ null
- ห้ามสร้างค่าพิกัด latitude/longitude ขึ้นมาเอง
- ถ้าพบคำว่า รับฝากขาย, ค่าคอม, ทีมงาน ให้ seller_type เป็น "นายหน้า"
"""


def handle_market_scout(user_id: str, text: str, reply_token: str) -> None:
    clean = re.sub(r"^บันทึกตลาด", "", text).strip()
    if len(clean) < 15:
        reply(reply_token, "⚠️ ข้อความสั้นเกินไปครับ กรุณาวางเนื้อหาโพสต์ขายให้ครบถ้วน")
        return

    reply(reply_token, "⏳ กำลังแกะข้อมูลทรัพย์...")

    try:
        data = ask_gemini_json(MARKET_PROMPT.format(
            text=clean[:6000], tambons=", ".join(VALID_TAMBONS)
        ))
    except Exception as e:
        push(user_id, f"❌ แกะข้อมูลไม่สำเร็จ: {e}")
        return

    price = to_float(data.get("price"))
    size = to_float(data.get("size_sq_wah"))
    tambon = normalize_tambon(data.get("location_zone"))
    ppw = (price / size) if (price and size and size > 0) else None

    # --- จัดการพิกัดแบบมีชั้นความเชื่อมั่น ---
    coords = parse_maps_coords(clean)
    if coords:
        lat, lng = coords
        loc_conf, loc_src = "exact", "google_maps_url"
    elif tambon:
        lat, lng = TAMBON_CENTROIDS[tambon]
        loc_conf, loc_src = "estimated", "tambon_center"
    else:
        lat = lng = None
        loc_conf, loc_src = "unknown", "none"

    row = {
        "property_type": data.get("property_type") or "ไม่ระบุ",
        "project_name": data.get("project_name"),
        "location_zone": tambon or "ไม่ระบุ",
        "landmark": data.get("landmark"),
        "price": price,
        "size_sq_wah": size,
        "usable_area_sqm": to_float(data.get("usable_area_sqm")),
        "bedrooms": to_float(data.get("bedrooms")),
        "price_per_sq_wah": ppw,
        "source_url": extract_url(clean),
        "contact_info": data.get("contact_info"),
        "seller_type": data.get("seller_type") or "ไม่ระบุ",
        "highlights": data.get("highlights"),
        "latitude": lat,
        "longitude": lng,
        "location_confidence": loc_conf,
        "location_source": loc_src,
        "raw_text": clean[:4000],
        "status": "ใหม่",
    }

    try:
        res = supabase.table("pakchong_market_scout").insert(row).execute()
        rec_id = res.data[0].get("id") if res.data else None
    except Exception as e:
        push(user_id, f"❌ บันทึกฐานข้อมูลไม่สำเร็จ: {e}")
        return

    conf_label = {
        "exact": "✅ พิกัดจริงจากลิงก์",
        "estimated": "🟡 ประมาณจากตำบล (ยังไม่ใช่ตำแหน่งจริง)",
        "unknown": "❌ ยังไม่มีพิกัด",
    }[loc_conf]

    msg = (
        f"✅ บันทึกข้อมูลตลาดสำเร็จ\n"
        f"━━━━━━━━━━━━━━\n"
        f"🏷️ {row['property_type']}"
        + (f" | {row['project_name']}" if row["project_name"] else "") + "\n"
        f"📍 ต.{row['location_zone']}\n"
        f"💰 {fmt_money(price) if price else 'ไม่ระบุ'} บาท\n"
        f"📐 {fmt_money(size) if size else 'ไม่ระบุ'} ตร.ว.\n"
        f"📊 {fmt_money(ppw) if ppw else '-'} บาท/ตร.ว.\n"
        f"👤 {row['seller_type']}\n"
        f"🗺️ {conf_label}\n"
    )
    if loc_conf != "exact":
        msg += "\n💡 ส่งตำแหน่ง (Location) หรือวางลิงก์ Google Maps เพื่อปักหมุดให้แม่นยำครับ"

    set_state(user_id, "AWAIT_PIN", {"record_id": rec_id} if rec_id else {})
    push(user_id, msg, qr(("📍 ปักหมุดเพิ่ม", "ปักหมุด"), ("➕ บันทึกรายการต่อไป", "บันทึกตลาด")))


def handle_location_pin(user_id: str, lat: float, lng: float, reply_token: str) -> None:
    """รับพิกัดจริงจาก LINE Location แล้วอัปเดตรายการล่าสุด"""
    st = get_state(user_id)
    rec_id = (st.get("draft_data") or {}).get("record_id")

    if not rec_id:
        try:
            res = (supabase.table("pakchong_market_scout")
                   .select("id").order("created_at", desc=True).limit(1).execute())
            rec_id = res.data[0]["id"] if res.data else None
        except Exception:
            rec_id = None

    if not rec_id:
        reply(reply_token, "⚠️ ไม่พบรายการที่จะปักหมุด กรุณาบันทึกทรัพย์ก่อนครับ")
        return

    try:
        supabase.table("pakchong_market_scout").update({
            "latitude": lat, "longitude": lng,
            "location_confidence": "exact",
            "location_source": "line_location",
        }).eq("id", rec_id).execute()
        clear_state(user_id)
        reply(reply_token,
              f"📍 ปักหมุดสำเร็จ!\nพิกัด: {lat:.6f}, {lng:.6f}\n"
              f"ตอนนี้ทรัพย์รายการนี้มีตำแหน่งจริงบนแผนที่แล้วครับ")
    except Exception as e:
        reply(reply_token, f"❌ อัปเดตพิกัดไม่สำเร็จ: {e}")


def handle_image(user_id: str, message_id: str, reply_token: str) -> None:
    """OCR รูปโพสต์ขาย/โฉนด ด้วย Gemini Vision"""
    reply(reply_token, "🖼️ กำลังอ่านข้อความจากรูปภาพ...")
    try:
        content = line_bot_api.get_message_content(message_id)
        img_bytes = b"".join(chunk for chunk in content.iter_content())

        resp = get_model().generate_content([
            {"mime_type": "image/jpeg", "data": img_bytes},
            "อ่านข้อความภาษาไทยทั้งหมดในภาพนี้ แล้วพิมพ์ออกมาตามที่เห็น "
            "ห้ามสรุป ห้ามเพิ่มความเห็น ถ้าไม่มีข้อความให้ตอบว่า 'ไม่พบข้อความ'",
        ])
        ocr_text = (resp.text or "").strip()

        if not ocr_text or "ไม่พบข้อความ" in ocr_text:
            push(user_id, "⚠️ อ่านข้อความจากภาพไม่ได้ กรุณาส่งภาพที่ชัดขึ้น หรือพิมพ์ข้อความมาแทนครับ")
            return

        push(user_id,
             f"📄 ข้อความที่อ่านได้:\n━━━━━━━━━━━━━━\n{ocr_text[:1200]}\n━━━━━━━━━━━━━━\n"
             f"ต้องการให้บันทึกเป็นข้อมูลตลาดไหมครับ?",
             qr(("✅ บันทึกเลย", f"บันทึกตลาด {ocr_text[:1500]}"), ("❌ ไม่ต้อง", "ยกเลิก")))
    except Exception as e:
        log.error("OCR ล้มเหลว: %s", e)
        push(user_id, f"❌ อ่านภาพไม่สำเร็จ: {e}")


# ==========================================================
# MODULE 2: CRM & MATCHING
# ==========================================================

CRM_PROMPT = """สกัดข้อมูลผู้ติดต่อจากข้อความนี้ ตอบเป็น JSON เท่านั้น

ข้อความ: \"\"\"{text}\"\"\"

รูปแบบ:
{{
  "name": "ชื่อ ถ้าไม่มีใส่ null",
  "budget_min": ตัวเลขงบต่ำสุดเป็นบาท ถ้าไม่มีใส่ null,
  "budget_max": ตัวเลขงบสูงสุดเป็นบาท ถ้าไม่มีใส่ null,
  "property_type": "ประเภททรัพย์ที่สนใจ ถ้าไม่มีใส่ null",
  "location_zone": "ตำบลที่สนใจ เลือกจาก [{tambons}] ถ้าไม่พบใส่ null",
  "contact_info": "เบอร์โทร/LINE ถ้าไม่มีใส่ null",
  "purpose": "วัตถุประสงค์ เช่น อยู่เอง ลงทุน ปล่อยเช่า ถ้าไม่มีใส่ null",
  "note": "รายละเอียดเพิ่มเติมสรุปสั้น"
}}
ห้ามเดาข้อมูลที่ไม่มีในข้อความ"""


def handle_crm(user_id: str, text: str, reply_token: str, forced_type: Optional[str] = None) -> None:
    clean = text
    for w in ("เพิ่มลูกค้า", "เพิ่มผู้ขาย", "เพิ่มนายหน้า"):
        clean = clean.replace(w, "")
    clean = clean.strip()

    if forced_type:
        contact_type = forced_type
    elif "ผู้ขาย" in text:
        contact_type = "ผู้ขาย"
    elif "นายหน้า" in text:
        contact_type = "นายหน้า"
    else:
        contact_type = "ผู้ซื้อ"

    reply(reply_token, f"⏳ กำลังบันทึกข้อมูล{contact_type}...")

    try:
        data = ask_gemini_json(CRM_PROMPT.format(
            text=clean[:4000], tambons=", ".join(VALID_TAMBONS)
        ))
    except Exception as e:
        push(user_id, f"❌ แกะข้อมูลไม่สำเร็จ: {e}")
        return

    budget_max = to_float(data.get("budget_max")) or 0
    zone = normalize_tambon(data.get("location_zone"))

    row = {
        "contact_type": contact_type,
        "name": data.get("name") or "ไม่ระบุชื่อ",
        "budget_min": to_float(data.get("budget_min")),
        "budget_max": budget_max,
        "property_type": data.get("property_type") or "ไม่ระบุ",
        "location_zone": zone or "ไม่ระบุ",
        "contact_info": data.get("contact_info") or "",
        "purpose": data.get("purpose") or "",
        "note": data.get("note") or "",
        "status": "ใหม่",
    }

    try:
        supabase.table("pakchong_crm").insert(row).execute()
    except Exception as e:
        push(user_id, f"❌ บันทึกฐานข้อมูลไม่สำเร็จ: {e}")
        return

    budget_text = fmt_money(budget_max) if budget_max else "ไม่ระบุ"
    msg = (
        f"👤 บันทึก{contact_type}สำเร็จ\n"
        f"━━━━━━━━━━━━━━\n"
        f"ชื่อ: {row['name']}\n"
        f"🔎 ต้องการ: {row['property_type']} | ต.{row['location_zone']}\n"
        f"💰 งบสูงสุด: {budget_text} บาท\n"
    )
    if row["contact_info"]:
        msg += f"📞 {row['contact_info']}\n"

    # จับคู่ทรัพย์ให้ผู้ซื้อ
    if contact_type == "ผู้ซื้อ" and budget_max > 0:
        try:
            q = (supabase.table("pakchong_market_scout")
                 .select("property_type, project_name, location_zone, price, size_sq_wah")
                 .lte("price", budget_max).gt("price", 0))
            if zone:
                q = q.ilike("location_zone", f"%{zone}%")
            matches = q.order("price", desc=True).limit(3).execute().data or []

            if matches:
                msg += "\n🔥 ทรัพย์ที่อาจตรงสเปก:\n"
                for i, m in enumerate(matches, 1):
                    name = m.get("project_name") or m.get("property_type")
                    msg += (f"{i}. {name} | ต.{m.get('location_zone')}\n"
                            f"    💰 {fmt_money(m.get('price'))} บ."
                            + (f" | {fmt_money(m.get('size_sq_wah'))} ตร.ว." if m.get("size_sq_wah") else "")
                            + "\n")
            else:
                msg += "\n📭 ยังไม่มีทรัพย์ในระบบที่ตรงเงื่อนไขนี้ครับ"
        except Exception as e:
            log.warning("matching ล้มเหลว: %s", e)

    push(user_id, msg)


# ==========================================================
# MODULE 3: CONTENT STUDIO
# ==========================================================

def handle_content(user_id: str, text: str, reply_token: str) -> None:
    clean = re.sub(r"^โพสต์", "", text).strip()
    if len(clean) < 10:
        reply(reply_token, "⚠️ กรุณาวางรายละเอียดทรัพย์ให้ครบถ้วนก่อนครับ")
        return

    reply(reply_token, "✍️ กำลังเรียบเรียงแคปชันขาย...")

    prompt = f"""คุณคือนักการตลาดอสังหาริมทรัพย์มืออาชีพในพื้นที่เขาใหญ่-ปากช่อง
เขียนคอนเทนต์ขายทรัพย์นี้:
\"\"\"{clean[:4000]}\"\"\"

ตอบตามโครงสร้างนี้ กระชับ อ่านง่ายบนมือถือ:

🎯 หัวข้อดึงดูด (3 แบบให้เลือก)
1. ...
2. ...
3. ...

📝 แคปชันหลัก
(ความยาว 5-8 บรรทัด ใช้อีโมจิพอดี เน้นภาพที่ลูกค้าจะได้รับ ปิดท้ายด้วย CTA นัดชม)

💎 จุดขายสำคัญ
- ...

📸 มุมถ่ายที่ควรมี
- ...

#️⃣ แฮชแท็ก
...

กฎ: ใช้เฉพาะข้อมูลที่มีในข้อความเท่านั้น ห้ามแต่งข้อมูลที่ไม่มี เช่น ห้ามอ้างผลตอบแทนการลงทุน
หากข้อมูลไม่พอในจุดใด ให้ระบุว่า 'ควรเพิ่มข้อมูล: ...'"""

    try:
        push(user_id, ask_gemini(prompt))
    except Exception as e:
        push(user_id, f"❌ สร้างคอนเทนต์ไม่สำเร็จ: {e}")


# ==========================================================
# MODULE 4: LEGAL & CONTRACT
# ==========================================================

CONTRACT_LABELS = {
    "นายหน้าเปิด": "สัญญานายหน้าแบบเปิด",
    "นายหน้าปิด": "สัญญานายหน้าแบบปิด",
    "ใบจอง": "สัญญาจองซื้อ",
    "สัญญาจะซื้อจะขาย": "สัญญาจะซื้อจะขาย",
}


def handle_contract_extract(user_id: str, contract_type: str, text: str, reply_token: str) -> None:
    """ขั้นที่ 1: แกะข้อมูล แล้วส่ง Preview ให้ตรวจก่อน"""
    req_fields = REQUIRED_FIELDS.get(contract_type, [])
    if not req_fields:
        reply(reply_token, "⚠️ ไม่รู้จักประเภทสัญญานี้ครับ")
        clear_state(user_id)
        return

    reply(reply_token, f"⏳ กำลังแกะข้อมูลสำหรับ{CONTRACT_LABELS.get(contract_type, contract_type)}...")

    fields_json = ",\n  ".join([f'"{f}": "ข้อมูลที่พบ หรือค่าว่าง"' for f in req_fields])
    prompt = f"""สกัดข้อมูลสำหรับจัดทำสัญญาจากข้อความนี้ ตอบเป็น JSON เท่านั้น

ข้อความ: \"\"\"{text[:4000]}\"\"\"

รูปแบบ:
{{
  "contract_date": "วันที่ทำสัญญา รูปแบบ วว/ดด/ปปปป หรือค่าว่าง",
  {fields_json}
}}

กฎ:
- ห้ามเดาข้อมูลที่ไม่มีในข้อความ ให้ใส่ค่าว่าง "" แทน
- ตัวเลขเงินให้ใส่รูปแบบมี comma เช่น 5,000,000
- ฟิลด์ที่ลงท้ายด้วย _ตัวอักษร ให้ใส่ค่าว่าง ระบบจะสร้างเอง
- ฟิลด์รายละเอียดทรัพย์ให้สรุปครบถ้วนในบรรทัดเดียว"""

    try:
        data = ask_gemini_json(prompt)
    except Exception as e:
        push(user_id, f"❌ แกะข้อมูลไม่สำเร็จ: {e}")
        clear_state(user_id)
        return

    if not str(data.get("contract_date", "")).strip():
        data["contract_date"] = datetime.date.today().strftime("%d/%m/%Y")

    # สร้างคำอ่านไทยเองจากตัวเลข ไม่ให้ AI เดา
    for money_key, text_key in (("เงินจอง", "เงินจอง_ตัวอักษร"),
                                ("เงินมัดจำ", "เงินมัดจำ_ตัวอักษร"),
                                ("ราคาขาย", "ราคาขาย_ตัวอักษร")):
        if text_key in req_fields or text_key in data:
            amount = to_float(data.get(money_key))
            if amount:
                data[text_key] = baht_text(amount)

    set_state(user_id, f"CONFIRM_{contract_type}", {"contract_data": data})

    preview = f"📋 ตรวจสอบข้อมูลก่อนออกเอกสาร\n"
    preview += f"📄 {CONTRACT_LABELS.get(contract_type, contract_type)}\n"
    preview += "━━━━━━━━━━━━━━\n"
    preview += f"📅 วันที่: {data.get('contract_date')}\n"

    missing: List[str] = []
    for f in req_fields:
        val = str(data.get(f, "")).strip()
        if not val:
            missing.append(f.replace("_", " "))
            val = "— ยังไม่มีข้อมูล —"
        label = f.replace("_", " ")
        preview += f"• {label}: {val}\n"

    preview += "━━━━━━━━━━━━━━\n"
    if missing:
        preview += (f"⚠️ ยังขาด {len(missing)} รายการ\n"
                    f"พิมพ์ข้อมูลเพิ่มแล้วส่งใหม่ หรือกดยืนยันเพื่อเว้นเป็นช่องว่างให้กรอกด้วยมือครับ")
    else:
        preview += "✅ ข้อมูลครบถ้วน พร้อมออกเอกสาร"

    push(user_id, preview, qr(
        ("✅ ยืนยันออก PDF", f"[CONFIRM_PDF] {contract_type}"),
        ("✏️ กรอกใหม่", f"[CREATE_PDF] {contract_type}"),
        ("❌ ยกเลิก", "ยกเลิก"),
    ))


def handle_contract_confirm(user_id: str, contract_type: str, reply_token: str) -> None:
    """ขั้นที่ 2: ยืนยันแล้วสร้าง PDF จริง"""
    st = get_state(user_id)
    data = (st.get("draft_data") or {}).get("contract_data")

    if not data:
        reply(reply_token, "⚠️ ไม่พบข้อมูลร่างสัญญา (อาจหมดอายุแล้ว) กรุณาเริ่มใหม่ครับ")
        return

    reply(reply_token, "📄 กำลังจัดหน้าเอกสาร A4 และสร้างไฟล์ PDF...")

    try:
        template = CONTRACT_TEMPLATES[contract_type]
        filled = safe_fill(template, data)
        full_text = template.format(**filled)

        pdf_url = create_contract_pdf(contract_type, full_text)

        try:
            supabase.table("contract_logs").insert({
                "line_user_id": user_id,
                "contract_type": contract_type,
                "contract_data": data,
                "pdf_path": pdf_url.split("?")[0].split("/")[-1],
            }).execute()
        except Exception as e:
            log.warning("บันทึก contract_logs ล้มเหลว: %s", e)

        clear_state(user_id)

        push(user_id,
             f"✅ เอกสารพร้อมใช้งานแล้ว\n"
             f"📄 {CONTRACT_LABELS.get(contract_type, contract_type)}\n"
             f"━━━━━━━━━━━━━━\n"
             f"🔗 {pdf_url}\n"
             f"━━━━━━━━━━━━━━\n"
             f"⏰ ลิงก์มีอายุ 6 ชั่วโมง\n"
             f"⚠️ กรุณาตรวจทานและให้ผู้เชี่ยวชาญกฎหมายพิจารณาก่อนลงนามจริงครับ")
    except Exception as e:
        log.error("สร้าง PDF ล้มเหลว: %s\n%s", e, traceback.format_exc())
        push(user_id, f"❌ สร้าง PDF ไม่สำเร็จ: {e}")


def handle_contract_check(user_id: str, text: str, reply_token: str) -> None:
    clean = re.sub(r"^ตรวจสัญญา", "", text).strip()
    reply(reply_token, "🔍 กำลังตรวจหาช่องโหว่และเงื่อนไขที่เสียเปรียบ...")

    prompt = f"""คุณคือที่ปรึกษาด้านสัญญาอสังหาริมทรัพย์ในประเทศไทย
ตรวจสอบร่างสัญญานี้:
\"\"\"{clean[:6000]}\"\"\"

ตอบตามโครงสร้าง อ่านง่ายบนมือถือ:

🚨 จุดเสี่ยงที่พบ
- (เรียงจากร้ายแรงที่สุด)

⚖️ ความสมดุลของสัญญา
- ฝ่ายใดได้เปรียบ และเพราะเหตุใด

📌 ข้อที่ควรเพิ่มเติม
- (ข้อความที่แนะนำให้ใส่)

✅ สรุป
- ใช้ได้เลย / ควรแก้ก่อน / ควรให้ทนายตรวจ

กฎ: หากข้อมูลไม่พอให้ระบุชัดว่าต้องดูเอกสารใดเพิ่ม
ปิดท้ายด้วยข้อความเตือนว่าความเห็นนี้เป็นการวิเคราะห์เบื้องต้น ไม่ใช่คำแนะนำทางกฎหมายที่ใช้แทนทนายความได้"""

    try:
        push(user_id, f"🔍 ผลการตรวจสอบ\n━━━━━━━━━━━━━━\n\n{ask_gemini(prompt)}")
    except Exception as e:
        push(user_id, f"❌ ตรวจสอบไม่สำเร็จ: {e}")


def handle_contract_edit(user_id: str, text: str, reply_token: str) -> None:
    clean = re.sub(r"^แก้ไขสัญญา", "", text).strip()
    reply(reply_token, "✏️ กำลังเกลาภาษากฎหมายให้รัดกุม...")

    prompt = f"""คุณคือผู้เชี่ยวชาญด้านการร่างสัญญาภาษาไทย
ปรับข้อความนี้ให้รัดกุม ชัดเจน และเป็นทางการ:
\"\"\"{clean[:5000]}\"\"\"

ตอบตามนี้:

✨ ข้อความที่ปรับแล้ว
(พร้อมคัดลอกไปใช้ได้ทันที)

📝 สิ่งที่เปลี่ยนและเหตุผล
- ...

⚠️ จุดที่ยังต้องตัดสินใจเพิ่ม
- ...

กฎ: ห้ามเพิ่มเงื่อนไขใหม่ที่ไม่มีในต้นฉบับ ทำได้เพียงปรับถ้อยคำให้ชัดเจนขึ้นเท่านั้น"""

    try:
        push(user_id, f"✏️ ร่างข้อความใหม่\n━━━━━━━━━━━━━━\n\n{ask_gemini(prompt)}")
    except Exception as e:
        push(user_id, f"❌ แก้ไขไม่สำเร็จ: {e}")


# ==========================================================
# MODULE 5: TAX & TRANSFER COST
# ==========================================================

def handle_tax(user_id: str, text: str, reply_token: str) -> None:
    clean = re.sub(r"^ค่าโอน", "", text).strip()
    if len(clean) < 5:
        reply(reply_token,
              "🧮 โหมดคำนวณค่าโอน\n\nพิมพ์ข้อมูลตามนี้ครับ:\n"
              "• ราคาซื้อขาย\n• ราคาประเมินราชการ\n• ระยะเวลาถือครอง\n"
              "• ผู้ขายเป็นบุคคลธรรมดาหรือนิติบุคคล\n• ข้อตกลงว่าใครออกค่าใช้จ่าย")
        return

    reply(reply_token, "🧮 กำลังคำนวณค่าธรรมเนียมและภาษี...")

    prompt = f"""คุณคือผู้เชี่ยวชาญด้านค่าธรรมเนียมการโอนอสังหาริมทรัพย์ในประเทศไทย
คำนวณประมาณการค่าใช้จ่ายวันโอนจากข้อมูลนี้:
\"\"\"{clean[:2000]}\"\"\"

สมมติฐานหากไม่ระบุ: ผู้ขายเป็นบุคคลธรรมดา ถือครอง 3 ปี ไม่มีจำนอง

ตอบในรูปแบบใบสรุปค่าใช้จ่าย:

🧾 ประมาณการค่าใช้จ่ายวันโอน
━━━━━━━━━━━━━━
📍 ราคาซื้อขาย: ... บาท
🏛️ ราคาประเมิน: ... บาท
⏳ ถือครอง: ... ปี

1️⃣ ค่าธรรมเนียมโอน
2️⃣ ภาษีธุรกิจเฉพาะ หรือ อากรแสตมป์ (เลือกกรณีที่เข้าเงื่อนไข พร้อมบอกเหตุผล)
3️⃣ ภาษีเงินได้หัก ณ ที่จ่าย
4️⃣ ค่าจดจำนอง (ถ้ามี)
━━━━━━━━━━━━━━
💰 รวมประมาณ: ... บาท
👤 ผู้ซื้อจ่าย: ... บาท
👤 ผู้ขายจ่าย: ... บาท

⚠️ ปิดท้ายเตือนเสมอว่า ตัวเลขนี้เป็นประมาณการ ตัวเลขจริงต้องยึดการคำนวณของสำนักงานที่ดิน ณ วันโอน

กฎ: แสดงฐานที่ใช้คำนวณของแต่ละรายการให้เห็นชัด และหากข้อมูลไม่พอให้ระบุว่าต้องการข้อมูลใดเพิ่ม"""

    try:
        push(user_id, ask_gemini(prompt))
    except Exception as e:
        push(user_id, f"❌ คำนวณไม่สำเร็จ: {e}")


# ==========================================================
# MODULE 6: VALUATION (อิง comparables จาก DB เท่านั้น)
# ==========================================================

VAL_EXTRACT_PROMPT = """สกัดข้อมูลเพื่อประเมินราคา ตอบเป็น JSON เท่านั้น

ข้อความ: \"\"\"{text}\"\"\"

รูปแบบ:
{{
  "property_type": "ประเภททรัพย์ ถ้าไม่มีใส่ null",
  "location_zone": "ตำบล เลือกจาก [{tambons}] ถ้าไม่พบใส่ null",
  "price": ตัวเลขราคาเสนอขายเป็นบาท ถ้าไม่มีใส่ null,
  "size_sq_wah": ตัวเลขขนาดเป็นตารางวา ถ้าไม่มีใส่ null,
  "gov_price": ตัวเลขราคาประเมินราชการ ถ้าไม่มีใส่ null
}}
1 ไร่ = 400 ตารางวา ห้ามเดาข้อมูลที่ไม่มี"""


def handle_valuation(user_id: str, text: str, reply_token: str) -> None:
    clean = re.sub(r"^ประเมิน", "", text).strip()
    if len(clean) < 10:
        reply(reply_token,
              "📊 โหมดประเมินราคา\n\nพิมพ์ข้อมูลตามนี้ครับ:\n"
              "• ประเภททรัพย์\n• ตำบล\n• ขนาดที่ดิน\n• ราคาที่เสนอขาย\n• ราคาประเมินราชการ (ถ้ามี)")
        return

    reply(reply_token, "📊 กำลังดึงข้อมูลเปรียบเทียบจากฐานข้อมูล...")

    try:
        d = ask_gemini_json(VAL_EXTRACT_PROMPT.format(
            text=clean[:3000], tambons=", ".join(VALID_TAMBONS)
        ))
    except Exception as e:
        push(user_id, f"❌ แกะข้อมูลไม่สำเร็จ: {e}")
        return

    p_type = d.get("property_type") or "ไม่ระบุ"
    zone = normalize_tambon(d.get("location_zone"))
    price = to_float(d.get("price")) or 0
    size = to_float(d.get("size_sq_wah")) or 0
    gov = to_float(d.get("gov_price")) or 0
    ppw = (price / size) if size > 0 else 0

    # ดึง comparable จาก DB
    comps = []
    try:
        q = (supabase.table("pakchong_market_scout")
             .select("property_type, location_zone, price, size_sq_wah, price_per_sq_wah")
             .not_.is_("price_per_sq_wah", "null"))
        if zone:
            q = q.ilike("location_zone", f"%{zone}%")
        if p_type != "ไม่ระบุ":
            q = q.ilike("property_type", f"%{p_type}%")
        comps = [c for c in (q.limit(60).execute().data or []) if c.get("price_per_sq_wah")]
    except Exception as e:
        log.warning("ดึง comparables ล้มเหลว: %s", e)

    n = len(comps)
    if n == 0:
        push(user_id,
             f"📊 รายงานประเมินราคา\n━━━━━━━━━━━━━━\n"
             f"🏷️ {p_type} | ต.{zone or 'ไม่ระบุ'}\n"
             f"💰 เสนอขาย: {fmt_money(price)} บาท"
             + (f" ({fmt_money(ppw)} บ./ตร.ว.)" if ppw else "") + "\n\n"
             f"⚠️ ยังไม่มีข้อมูลเปรียบเทียบในระบบสำหรับทรัพย์ประเภทนี้ในทำเลนี้\n\n"
             f"ระบบจะไม่ประเมินราคาโดยการคาดเดา กรุณาบันทึกข้อมูลตลาดในโซนนี้เพิ่มอย่างน้อย 3 รายการ "
             f"แล้วประเมินอีกครั้งครับ\n\n"
             f"💡 ใช้เมนู 'บันทึกตลาด' เพื่อเก็บข้อมูลได้เลย")
        return

    values = sorted([c["price_per_sq_wah"] for c in comps])
    avg = sum(values) / n
    median = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
    low, high = values[0], values[-1]

    comp_lines = "\n".join([
        f"- {c.get('property_type')} ต.{c.get('location_zone')} | "
        f"{fmt_money(c.get('price'))} บ. | {fmt_money(c.get('price_per_sq_wah'))} บ./ตร.ว."
        for c in comps[:8]
    ])

    reliability = "สูง" if n >= 8 else ("ปานกลาง" if n >= 3 else "ต่ำ")

    prompt = f"""คุณคือนักวิเคราะห์ราคาอสังหาริมทรัพย์ พื้นที่ปากช่อง-เขาใหญ่

ทรัพย์ที่ต้องประเมิน:
- ประเภท: {p_type}
- ทำเล: ต.{zone or 'ไม่ระบุ'}
- ขนาด: {fmt_money(size)} ตร.ว.
- ราคาเสนอขาย: {fmt_money(price)} บาท ({fmt_money(ppw)} บาท/ตร.ว.)
- ราคาประเมินราชการ: {fmt_money(gov) if gov else 'ไม่ระบุ'}

ข้อมูลเปรียบเทียบจากฐานข้อมูลของเราเท่านั้น ({n} รายการ | ความน่าเชื่อถือ: {reliability}):
- ค่าเฉลี่ย: {fmt_money(avg)} บาท/ตร.ว.
- ค่ากลาง: {fmt_money(median)} บาท/ตร.ว.
- ช่วงราคา: {fmt_money(low)} - {fmt_money(high)} บาท/ตร.ว.

รายการเทียบ:
{comp_lines}

วิเคราะห์ตามโครงสร้างนี้ สั้น กระชับ อ่านง่ายบนมือถือ:

📊 ตำแหน่งราคาในตลาด
(ราคานี้อยู่ตรงไหนเทียบค่ากลาง คิดเป็นกี่เปอร์เซ็นต์)

🏛️ เทียบราคาประเมินราชการ
(ถ้ามีข้อมูล คำนวณว่าสูงกว่ากี่เท่า ถ้าไม่มีให้บอกว่าควรขอข้อมูลนี้เพิ่ม)

💡 ข้อสรุปและกลยุทธ์ต่อรอง
(ราคาที่ควรเสนอ และเหตุผล)

⚠️ ข้อจำกัดของการประเมินนี้
(ระบุเสมอ)

กฎเหล็ก:
- ใช้เฉพาะตัวเลขที่ให้มาข้างบนเท่านั้น ห้ามอ้างอิงราคาตลาดจากแหล่งภายนอกหรือความทรงจำ
- ข้อมูลทั้งหมดเป็น 'ราคาเสนอขาย' ไม่ใช่ราคาปิดจริง ต้องระบุข้อจำกัดนี้ทุกครั้ง
- หากจำนวนรายการเทียบน้อยกว่า 3 ให้เน้นย้ำว่าผลประเมินยังเชื่อถือได้ต่ำ
- ห้ามรับประกันผลตอบแทนหรือกำไรใด ๆ"""

    try:
        analysis = ask_gemini(prompt)
        push(user_id,
             f"📊 รายงานประเมินราคา\n"
             f"🏷️ {p_type} | ต.{zone or 'ไม่ระบุ'}\n"
             f"📁 อ้างอิง {n} รายการ (ความน่าเชื่อถือ: {reliability})\n"
             f"━━━━━━━━━━━━━━\n\n{analysis}")
    except Exception as e:
        push(user_id, f"❌ วิเคราะห์ไม่สำเร็จ: {e}")


# ==========================================================
# MODULE 7: DAILY REPORT
# ==========================================================

def handle_report(user_id: str, reply_token: str) -> None:
    reply(reply_token, "📈 กำลังรวบรวมรายงาน...")
    try:
        since = (_now() - datetime.timedelta(days=7)).isoformat()

        market = supabase.table("pakchong_market_scout").select(
            "location_zone, price, price_per_sq_wah, created_at"
        ).gte("created_at", since).execute().data or []

        crm = supabase.table("pakchong_crm").select(
            "contact_type, created_at"
        ).gte("created_at", since).execute().data or []

        total_all = supabase.table("pakchong_market_scout").select(
            "id", count="exact"
        ).execute()

        zones: Dict[str, int] = {}
        for m in market:
            z = m.get("location_zone") or "ไม่ระบุ"
            zones[z] = zones.get(z, 0) + 1
        top = sorted(zones.items(), key=lambda x: x[1], reverse=True)[:5]

        buyers = len([c for c in crm if c.get("contact_type") == "ผู้ซื้อ"])
        sellers = len([c for c in crm if c.get("contact_type") == "ผู้ขาย"])

        msg = (
            f"📈 รายงาน 7 วันล่าสุด\n━━━━━━━━━━━━━━\n"
            f"🏘️ ทรัพย์ที่บันทึกใหม่: {len(market)} รายการ\n"
            f"👥 ผู้ซื้อใหม่: {buyers} | ผู้ขายใหม่: {sellers}\n"
            f"📦 ทรัพย์สะสมทั้งหมด: {getattr(total_all, 'count', 0)} รายการ\n"
        )
        if top:
            msg += "\n🔥 โซนที่มีของเข้าเยอะสุด\n"
            for i, (z, c) in enumerate(top, 1):
                msg += f"{i}. ต.{z} — {c} รายการ\n"
        push(user_id, msg)
    except Exception as e:
        push(user_id, f"❌ ดึงรายงานไม่สำเร็จ: {e}")


# ==========================================================
# ROUTES
# ==========================================================

@app.route("/")
def home():
    return {
        "service": "Vela Property Agent OS",
        "status": "running",
        "modules": ["market_scout", "crm", "content", "contract", "tax", "valuation", "report"],
    }, 200


@app.route("/health")
def health():
    return {
        "line": bool(line_bot_api),
        "gemini": bool(GEMINI_API_KEY),
        "supabase": bool(supabase),
        "time": _now().isoformat(),
    }, 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        log.warning("Signature ไม่ถูกต้อง")
        abort(400)
    except Exception as e:
        log.error("callback error: %s\n%s", e, traceback.format_exc())
    return "OK", 200


# ==========================================================
# EVENT HANDLERS
# ==========================================================

if handler:

    @handler.add(MessageEvent, message=LocationMessage)
    def on_location(event):
        try:
            handle_location_pin(
                event.source.user_id,
                event.message.latitude,
                event.message.longitude,
                event.reply_token,
            )
        except Exception as e:
            log.error("on_location error: %s", e)

    @handler.add(MessageEvent, message=ImageMessage)
    def on_image(event):
        try:
            handle_image(event.source.user_id, event.message.id, event.reply_token)
        except Exception as e:
            log.error("on_image error: %s", e)

    @handler.add(MessageEvent, message=TextMessage)
    def on_text(event):
        user_id = event.source.user_id
        token = event.reply_token
        text = (event.message.text or "").strip()

        try:
            st = get_state(user_id)
            state = st.get("current_module")

            # ---------- ยกเลิก ----------
            if text in ("ยกเลิก", "[MENU] ยกเลิก", "เริ่มใหม่"):
                clear_state(user_id)
                reply(token, "🔄 ยกเลิกรายการแล้ว กลับสู่โหมดปกติครับ")
                return

            if text in ("เมนู", "help", "ช่วยเหลือ", "[MENU] เมนู"):
                clear_state(user_id)
                reply(token, MAIN_MENU_HINT)
                return

            # ---------- ปุ่มเมนูหลัก ----------
            MENU_MAP = {
                "[MENU] บันทึกตลาด": ("MARKET_SCOUT",
                    "📍 โหมดบันทึกตลาด\n\nวางข้อความโพสต์ขาย ลิงก์ หรือส่งรูปภาพได้เลยครับ\n"
                    "💡 ถ้ามีลิงก์ Google Maps แปะมาด้วย ระบบจะปักหมุดแม่นยำขึ้น"),
                "[MENU] เพิ่มลูกค้า": ("CRM_BUYER",
                    "👥 โหมดเพิ่มผู้ซื้อ\n\nพิมพ์ชื่อ งบประมาณ ทำเลที่สนใจ และเบอร์ติดต่อได้เลยครับ"),
                "[MENU] เพิ่มผู้ขาย": ("CRM_SELLER",
                    "🏠 โหมดเพิ่มผู้ขาย\n\nพิมพ์ชื่อเจ้าของ ทรัพย์ที่ฝากขาย ราคา และเบอร์ติดต่อครับ"),
                "[MENU] สร้างโพสต์ขาย": ("CONTENT",
                    "✍️ โหมดสร้างโพสต์ขาย\n\nวางข้อมูลทรัพย์ที่ต้องการให้เขียนแคปชันครับ"),
                "[MENU] คำนวณค่าโอน": ("TAX",
                    "🧮 โหมดคำนวณค่าโอน\n\nพิมพ์ราคาซื้อขาย ราคาประเมิน และระยะเวลาถือครองครับ"),
                "[MENU] ประเมินราคา": ("VALUATION",
                    "📊 โหมดประเมินราคา\n\nวางข้อมูลทรัพย์ที่ต้องการประเมินครับ\n"
                    "💡 ระบบจะเทียบกับข้อมูลจริงในฐานข้อมูลเท่านั้น"),
            }

            if text in MENU_MAP:
                mod, msg = MENU_MAP[text]
                set_state(user_id, mod)
                reply(token, msg)
                return

            if text in ("[MENU] รายงาน", "งานวันนี้", "รายงาน"):
                clear_state(user_id)
                handle_report(user_id, token)
                return

            # ---------- เมนูสัญญา ----------
            if text == "[MENU] สัญญา":
                clear_state(user_id)
                reply(token, "📑 เมนูกฎหมายและสัญญา\nเลือกรายการที่ต้องการครับ",
                      qr(("🆕 สร้างสัญญา", "[CONTRACT] สร้าง"),
                         ("🔍 ตรวจสอบสัญญา", "[CONTRACT] ตรวจสอบ"),
                         ("✏️ แก้ไขสัญญา", "[CONTRACT] แก้ไข"),
                         ("❌ ยกเลิก", "ยกเลิก")))
                return

            if text == "[CONTRACT] สร้าง":
                reply(token, "📝 เลือกประเภทสัญญาที่ต้องการสร้างครับ",
                      qr(("นายหน้าเปิด", "[CREATE_PDF] นายหน้าเปิด"),
                         ("นายหน้าปิด", "[CREATE_PDF] นายหน้าปิด"),
                         ("ใบจอง", "[CREATE_PDF] ใบจอง"),
                         ("จะซื้อจะขาย", "[CREATE_PDF] สัญญาจะซื้อจะขาย"),
                         ("❌ ยกเลิก", "ยกเลิก")))
                return

            if text.startswith("[CREATE_PDF]"):
                ctype = text.replace("[CREATE_PDF]", "").strip()
                if ctype not in CONTRACT_TEMPLATES:
                    reply(token, "⚠️ ไม่รู้จักประเภทสัญญานี้ครับ")
                    return
                set_state(user_id, f"PDF_{ctype}")
                fields = REQUIRED_FIELDS.get(ctype, [])
                hint = "\n".join([f"• {f.replace('_', ' ')}" for f in fields])
                reply(token,
                      f"📄 {CONTRACT_LABELS.get(ctype, ctype)}\n"
                      f"━━━━━━━━━━━━━━\n"
                      f"พิมพ์ข้อมูลดีลมาได้เลยครับ ข้อมูลที่ควรมี:\n{hint}\n\n"
                      f"💡 ส่วนที่ไม่ระบุ ระบบจะเว้นเป็นช่องว่างให้กรอกด้วยปากกาภายหลัง")
                return

            if text.startswith("[CONFIRM_PDF]"):
                ctype = text.replace("[CONFIRM_PDF]", "").strip()
                handle_contract_confirm(user_id, ctype, token)
                return

            if text == "[CONTRACT] ตรวจสอบ":
                set_state(user_id, "CONTRACT_CHECK")
                reply(token, "🔍 โหมดตรวจสอบสัญญา\n\nวางข้อความสัญญาที่ต้องการตรวจครับ")
                return

            if text == "[CONTRACT] แก้ไข":
                set_state(user_id, "CONTRACT_EDIT")
                reply(token, "✏️ โหมดแก้ไขสัญญา\n\nวางข้อความที่ต้องการเกลาครับ")
                return

            # ---------- ทำงานตาม state ----------
            if state and state.startswith("PDF_"):
                ctype = state.replace("PDF_", "")
                handle_contract_extract(user_id, ctype, text, token)
                return

            if state and state.startswith("CONFIRM_"):
                # ผู้ใช้พิมพ์ข้อมูลเพิ่มระหว่างรอยืนยัน = แกะใหม่
                ctype = state.replace("CONFIRM_", "")
                handle_contract_extract(user_id, ctype, text, token)
                return

            if state == "CONTRACT_CHECK" or text.startswith("ตรวจสัญญา"):
                clear_state(user_id)
                handle_contract_check(user_id, text, token)
                return

            if state == "CONTRACT_EDIT" or text.startswith("แก้ไขสัญญา"):
                clear_state(user_id)
                handle_contract_edit(user_id, text, token)
                return

            if state == "MARKET_SCOUT" or text.startswith("บันทึกตลาด"):
                clear_state(user_id)
                handle_market_scout(user_id, text, token)
                return

            if state == "AWAIT_PIN" and text == "ปักหมุด":
                reply(token, "📍 กรุณากดปุ่ม + แล้วเลือก 'ตำแหน่ง' เพื่อส่งพิกัดเข้ามา "
                             "หรือวางลิงก์ Google Maps ได้เลยครับ")
                return

            if state == "CRM_BUYER":
                clear_state(user_id)
                handle_crm(user_id, text, token, forced_type="ผู้ซื้อ")
                return

            if state == "CRM_SELLER":
                clear_state(user_id)
                handle_crm(user_id, text, token, forced_type="ผู้ขาย")
                return

            if text.startswith(("เพิ่มลูกค้า", "เพิ่มผู้ขาย", "เพิ่มนายหน้า")):
                clear_state(user_id)
                handle_crm(user_id, text, token)
                return

            if state == "CONTENT" or text.startswith("โพสต์"):
                clear_state(user_id)
                handle_content(user_id, text, token)
                return

            if state == "TAX" or text.startswith("ค่าโอน"):
                clear_state(user_id)
                handle_tax(user_id, text, token)
                return

            if state == "VALUATION" or text.startswith("ประเมิน"):
                clear_state(user_id)
                handle_valuation(user_id, text, token)
                return

            # ---------- ไม่เข้าเงื่อนไขใด ----------
            reply(token, MAIN_MENU_HINT)

        except Exception as e:
            log.error("on_text error: %s\n%s", e, traceback.format_exc())
            try:
                push(user_id, f"❌ เกิดข้อผิดพลาดในระบบ\n{str(e)[:300]}\n\nพิมพ์ 'ยกเลิก' เพื่อเริ่มใหม่ครับ")
            except Exception:
                pass


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)