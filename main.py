import asyncio
import logging
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile, FSInputFile
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import database as db
import keyboards as kb

from typing import Optional

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_TOKEN = os.getenv("BOT_TOKEN", "8860313727:AAE_YmmXzWcXwGF-DKvuK7yC2Op67YLt-HM")
SUPER_ADMIN_ID = int(os.getenv("ADMIN_ID", "6956456422"))

def resolve_book_file(book: dict) -> Optional[str]:
    """
    Fayl Windows, Linux yoki Docker'da bo'lishidan qat'i nazar, uni avtomatik topish:
    1. To'g'ridan-to'g'ri ko'rsatilgan file_path mavjud bo'lsa
    2. Nisbiy yo'l (masalan: 'biznes va moliya/fayl.pdf')
    3. Windows mutlaq yo'li (C:\\...) berilgan bo'lsa, oxirgi 2 ta bo'lakni (janr va fayl) birlashtirish
    4. Fayl nomi bo'yicha loyihaning barcha ichki papkalaridan qidirish
    """
    raw_path = book.get("file_path")
    target_name = book.get("pdf_file_name")

    # 1. To'g'ridan-to'g'ri mavjud bo'lsa
    if raw_path and os.path.exists(raw_path):
        return raw_path

    # 2. Nisbiy yo'l yoki Windows formatidan o'girish
    if raw_path:
        norm_path = raw_path.replace("\\", "/").strip("/")
        candidate = os.path.join(BASE_DIR, norm_path)
        if os.path.exists(candidate):
            return candidate

        parts = norm_path.split("/")
        if len(parts) >= 2:
            rel_candidate = os.path.join(BASE_DIR, parts[-2], parts[-1])
            if os.path.exists(rel_candidate):
                return rel_candidate

    # 3. Fayl nomi bo'yicha qidirish
    search_name = target_name or (os.path.basename(raw_path) if raw_path else None)
    if search_name:
        for root, _, files in os.walk(BASE_DIR):
            if ".venv" in root or ".git" in root or "__pycache__" in root:
                continue
            if search_name in files:
                return os.path.join(root, search_name)
            for f in files:
                if f.lower() == search_name.lower():
                    return os.path.join(root, f)

    return None

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==========================================
# FSM STATES
# ==========================================
class AddBookStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_title = State()
    waiting_for_author = State()
    waiting_for_pdf = State()

class CategoryStates(StatesGroup):
    waiting_for_name = State()

class AIStates(StatesGroup):
    waiting_for_prompt = State()

class BroadcastStates(StatesGroup):
    waiting_for_message = State()

class AdminRoleStates(StatesGroup):
    waiting_for_add_id = State()
    waiting_for_remove_id = State()

class EditBookStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_author = State()
    waiting_for_description = State()
    waiting_for_pages = State()
    waiting_for_pdf = State()

class EditCategoryStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_desc = State()

# ==========================================
# /START HANDLER
# ==========================================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    name = (message.from_user.first_name or "") + (" " + message.from_user.last_name if message.from_user.last_name else "")
    username = message.from_user.username

    user = await db.get_or_create_user(user_id, name.strip(), username)
    is_admin = (user_id == SUPER_ADMIN_ID) or (user["role"] == "ADMIN")

    welcome_text = (
        f"Assalomu alaykum, <b>{message.from_user.first_name}</b>! 🌟\n\n"
        f"<b>\"Kitobxon Club\"</b> rasmiy Telegram botiga xush kelibsiz!\n\n"
    )
    if user_id == SUPER_ADMIN_ID:
        welcome_text += "👑 <b>Siz tizimning Bosh Administratorisiz (Super Admin).</b>\n\n"

    welcome_text += (
        "Bu bot orqali siz:\n"
        "📚 Sara asarlarni <b>PDF formatda</b> to'liq yuklab olib mutolaa qilishingiz,\n"
        "⭐️ Har bir o'qilgan kitob uchun <b>ballar</b> to'plashingiz,\n"
        "🏆 Sovrinli <b>tanlovlar</b> va adabiyot marafonlarida qatnashishingiz,\n"
        "📊 <b>Reyting</b>da eng faol kitobxonlar safidan joy olishingiz,\n"
        "🤖 <b>Sun'iy Intellekt Maslahatchisi</b>dan istalgan janr (masalan: <i>\"drama kitob\"</i>, <i>\"detektiv\"</i>, <i>\"biznes\"</i>) bo'yicha tavsiyalar olishingiz mumkin!\n\n"
        "Pastdagi menyudan kerakli bo'limni tanlang 👇"
    )

    is_locked = await db.is_contests_locked()
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=kb.get_main_menu(is_admin, contests_locked=is_locked))

# ==========================================
# 📚 KUTUBXONA HANDLERS
# ==========================================
@dp.message(F.text == "📚 Kutubxona")
async def show_library(message: Message):
    categories = await db.get_categories()
    await message.answer(
        "📚 <b>Kitobxon Club Kutubxonasi</b>\n\nQaysi adabiyot janridagi kitoblarni mutolaa qilishni istaysiz? Quyidagi toifalardan birini tanlang:",
        parse_mode="HTML",
        reply_markup=kb.get_categories_keyboard(categories)
    )

@dp.callback_query(F.data.startswith("cat_"))
async def show_category_books(callback: CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    books = await db.get_books(category_id=cat_id)
    category = await db.get_category_by_id(cat_id)

    if not books:
        await callback.answer("📭 Ushbu janrda hozircha kitoblar mavjud emas. Yangi kitoblar yuklangach paydo bo'ladi.", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(
        f"📂 <b>{category['name']}</b> bo'limidagi sara kitoblar:\nPDF formatida yuklab olish uchun kitobni tanlang:",
        parse_mode="HTML",
        reply_markup=kb.get_books_keyboard(books)
    )

@dp.callback_query(F.data == "all_books")
async def show_all_books(callback: CallbackQuery):
    books = await db.get_books()
    if not books:
        await callback.answer("📭 Hozircha kutubxonada kitoblar mavjud emas. Yangi kitoblar qo'shilgach bu yerda chiqadi.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        "📚 <b>Barcha sara kitoblar ro'yxati:</b>\nKitobni tanlang:",
        parse_mode="HTML",
        reply_markup=kb.get_books_keyboard(books)
    )

@dp.callback_query(F.data == "back_to_categories")
async def back_to_categories(callback: CallbackQuery):
    categories = await db.get_categories()
    await callback.answer()
    await callback.message.edit_text(
        "📚 <b>Kitobxon Club Kutubxonasi</b>\n\nQuyidagi toifalardan birini tanlang:",
        parse_mode="HTML",
        reply_markup=kb.get_categories_keyboard(categories)
    )

# Kitob tafsilotlari
@dp.callback_query(F.data.startswith("book_"))
async def show_book_details(callback: CallbackQuery):
    book_id = int(callback.data.split("_")[1])
    book = await db.get_book_by_id(book_id)

    if not book:
        await callback.answer("Kitob topilmadi.")
        return

    await callback.answer()
    user = await db.get_or_create_user(callback.from_user.id, callback.from_user.first_name, callback.from_user.username)
    is_admin = (callback.from_user.id == SUPER_ADMIN_ID or user["role"] == "ADMIN")

    has_pdf = bool(book.get("pdf_file_id") or resolve_book_file(book))
    format_info = "📄 Format: <b>PDF kitob</b>\n" if has_pdf else ""

    caption = (
        f"📖 <b>{book['title']}</b>\n"
        f"✍️ <b>Muallif:</b> {book['author']}\n"
        f"📂 <b>Janr:</b> {book.get('category_name', 'Umumiy')}\n"
        f"📑 <b>Hajmi:</b> {book['pages']} sahifa\n"
        f"⭐️ <b>Reyting:</b> {book['rating']} / 5.0\n"
        f"👥 <b>Mutolaa qilingan:</b> {book['read_count']} marta\n"
        f"{format_info}\n"
        f"📝 <b>Qisqacha tavsif:</b>\n"
        f"{book['description']}"
    )

    try:
        await callback.message.answer_photo(
            photo=book["cover_url"],
            caption=caption,
            parse_mode="HTML",
            reply_markup=kb.get_book_details_keyboard(book["id"], is_admin=is_admin)
        )
    except Exception:
        await callback.message.answer(
            caption,
            parse_mode="HTML",
            reply_markup=kb.get_book_details_keyboard(book["id"], is_admin=is_admin)
        )

# 🗑 KITOBNI O'CHIRISH (ADMIN)
@dp.callback_query(F.data.startswith("del_book_"))
async def handle_delete_book(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_or_create_user(user_id, callback.from_user.first_name, callback.from_user.username)
    if user_id != SUPER_ADMIN_ID and user["role"] != "ADMIN":
        await callback.answer("⛔️ Faqat administratorlar kitobni o'chira oladi!", show_alert=True)
        return

    book_id = int(callback.data.split("_")[2])
    book = await db.get_book_by_id(book_id)
    if not book:
        await callback.answer("Kitob topilmadi.", show_alert=True)
        return

    await db.delete_book(book_id)
    await callback.answer(f"🗑 «{book['title']}» o'chirildi!", show_alert=True)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        f"🗑 <b>Kitob muvaffaqiyatli o'chirildi:</b>\n\n"
        f"📖 <b>{book['title']}</b> — <i>{book['author']}</i>\n\n"
        f"<i>Ushbu kitob kutubxonadan barcha foydalanuvchilar uchun butunlay olib tashlandi.</i>",
        parse_mode="HTML"
    )

# 📥 KITOBNI O'QISH / PDF YUKLAB OLISH
@dp.callback_query(F.data.startswith("get_pdf_"))
async def send_book_pdf(callback: CallbackQuery):
    book_id = int(callback.data.split("_")[2])
    book = await db.get_book_by_id(book_id)

    if not book:
        await callback.answer("Kitob topilmadi.")
        return

    user_id = callback.from_user.id
    # Ball berish (+10 ball) va o'qish statistikasini yangilash
    await db.add_user_points(user_id, 10)
    await db.increment_book_read(book_id, user_id)

    await callback.answer("Kitob yuborilmoqda... (+10 Ball hisobingizga qo'shildi!)", show_alert=False)

    caption = (
        f"📖 <b>{book['title']}</b> — <i>{book['author']}</i>\n\n"
        f"Marhamat, kitobni yuklab oling va maroqli mutolaa qiling! ✨\n\n"
        f"⭐️ <i>Mutolaa boshlaganingiz uchun profilingizga +10 ball berildi!</i>"
    )

    # 1. Agar avval yuklangan Telegram file_id mavjud bo'lsa
    if book.get("pdf_file_id"):
        try:
            await callback.message.answer_document(
                document=book["pdf_file_id"],
                caption=caption,
                parse_mode="HTML"
            )
            return
        except Exception as e:
            logging.warning(f"File ID orqali yuborishda xatolik: {e}")

    # 2. Agar papkadagi lokal fayl mavjud bo'lsa (haqiqiy PDF/EPUB)
    resolved_path = resolve_book_file(book)
    if resolved_path and os.path.exists(resolved_path):
        file_size_mb = round(os.path.getsize(resolved_path) / (1024 * 1024), 1)
        if file_size_mb > 50:
            await callback.message.answer(
                f"⚠️ <b>Fayl hajmi katta:</b> {file_size_mb} MB.\n"
                f"Telegram serverlari bot orqali to'g'ridan-to'g'ri 50 MB dan katta fayllarni uzatishni cheklaydi.\n"
                f"Admin bot orqali ushbu kitobni Telegram serveriga yuklab yangilab beradi.",
                parse_mode="HTML"
            )
            return

        try:
            file_name = book.get("pdf_file_name") or os.path.basename(resolved_path)
            input_file = FSInputFile(resolved_path, filename=file_name)
            sent_msg = await callback.message.answer_document(
                document=input_file,
                caption=caption,
                parse_mode="HTML"
            )
            # Kelgusida tezroq yuborish uchun file_id ni bazada saqlab qo'yamiz
            if sent_msg.document:
                await db.update_book_file_id(book_id, sent_msg.document.file_id)
            return
        except Exception as e:
            logging.error(f"Lokal faylni yuborishda xatolik: {e}")
            await callback.message.answer(f"⚠️ Faylni yuklashda xatolik yuz berdi: {e}")
            return

    # 3. Zaxira matnli fayl
    content = f"{book['title']}\nMuallif: {book['author']}\n\nTavsif: {book['description']}\n\n" + ("="*30) + "\n\n1-BOB: MUTOLAA\n\nUshbu asar Kitobxon Club kutubxonasiga muvaffaqiyatli kiritilgan."
    doc_file = BufferedInputFile(content.encode("utf-8"), filename=f"{book['title'].replace(' ', '_')}.txt")
    await callback.message.answer_document(
        document=doc_file,
        caption=caption,
        parse_mode="HTML"
    )

# ==========================================
# 📖 O'QIGAN KITOBLAR
# ==========================================
@dp.message(F.text == "📖 O'qigan kitoblar")
async def show_reading_history(message: Message):
    user_id = message.from_user.id
    history = await db.get_user_reading_history(user_id)

    if not history:
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📚 Kutubxonaga o'tish", callback_data="all_books")]
        ])
        await message.answer(
            "📖 <b>Siz hali birorta kitob mutolaa qilmadingiz.</b>\n\nKutubxonaga o'tib, qiziqarli asarni PDF formatda yuklab oling!",
            parse_mode="HTML",
            reply_markup=inline_kb
        )
        return

    text = "📖 <b>Siz yuklab olgan va mutolaa qilgan kitoblaringiz:</b>\n\n"
    buttons = []

    for b in history:
        text += f"✅ <b>{b['title']}</b> — {b['author']}\n"
        text += f"📑 Hajmi: {b['pages']} sahifa • ⭐️ {b['rating']} ball\n\n"
        buttons.append([
            InlineKeyboardButton(text=f"📥 \"{b['title'][:20]}\"ni qayta yuklash", callback_data=f"get_pdf_{b['id']}")
        ])

    await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# ==========================================
# 🏆 TANLOVLAR (QULFLANGAN HOLAT BILAN)
# ==========================================
@dp.message(F.text.in_(["🏆 Tanlovlar", "🔒 Tanlovlar"]))
async def show_contests(message: Message):
    is_locked = await db.is_contests_locked()
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, message.from_user.first_name, message.from_user.username)
    is_admin = (user_id == SUPER_ADMIN_ID or user["role"] == "ADMIN")

    if is_locked:
        text = (
            "🔒 <b>Tanlovlar va Marafonlar bo'limi hozircha qulflangan!</b>\n\n"
            "🏆 <i>Ushbu bo'limda tez kunda katta sovrinli adabiyot marafonlari, qimmatbaho kitoblar to'plami va maxsus sovg'alar tanlovi start oladi!</i>\n\n"
            "💡 <b>Tanlovlarda g'olib bo'lish uchun hozirdan tayyorlaning:</b>\n"
            "• Kutubxonadagi sara asarlarni PDF formatda o'qing;\n"
            "• Har bir mutolaa uchun <b>+10 ball</b> oling;\n"
            "• Umumiy reytingda yuqori o'rinlarni egallang!\n\n"
            "🔔 <i>Tanlovlar start olganda bot orqali barcha kitobxonlarga xabarnoma yuboriladi.</i>"
        )
        buttons = [
            [InlineKeyboardButton(text="📚 Hozirdan kitob o'qish (Ball to'plash)", callback_data="all_books")]
        ]
        if is_admin:
            buttons.append([InlineKeyboardButton(text="🔓 Qulfni ochish (Admin)", callback_data="admin_toggle_contests_lock")])

        await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return

    # Agar ochiq bo'lsa
    contests = await db.get_contests()
    if not contests:
        await message.answer("🏆 Hozircha faol tanlovlar mavjud emas. Tez orada yangi marafonlar boshlanadi!", parse_mode="HTML")
        return

    text = "🏆 <b>Kitobxon Club Faol Tanlovlari va Marafonlari:</b>\n\n"
    buttons = []

    for c in contests:
        text += f"🎯 <b>{c['title']}</b>\n"
        text += f"🎁 Sovrin: <b>+{c['reward_points']} Ball</b>\n"
        text += f"👥 Ishtirokchilar: <b>{c['participants_count']} nafar</b>\n"
        text += f"📝 {c['description']}\n\n"
        buttons.append([
            InlineKeyboardButton(text=f"🏆 Qatnashish: \"{c['title'][:20]}...\"", callback_data=f"join_contest_{c['id']}")
        ])

    await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("join_contest_"))
async def handle_join_contest(callback: CallbackQuery):
    contest_id = int(callback.data.split("_")[2])
    await db.join_contest(contest_id)
    await callback.answer("🎉 Siz tanlovga muvaffaqiyatli qo'shildingiz! Kitob o'qishni boshlang va ballar yuting.", show_alert=True)

# ==========================================
# ⭐️ BALLAR
# ==========================================
@dp.message(F.text == "⭐️ Ballar")
async def show_points(message: Message):
    user_id = message.from_user.id
    name = message.from_user.first_name or "Kitobxon"
    user = await db.get_or_create_user(user_id, name, message.from_user.username)

    text = (
        f"⭐️ <b>Sizning Ballar va Yutuqlar Balansingiz:</b>\n\n"
        f"💰 Jami to'plangan ball: <b>{user['points']} ball</b>\n"
        f"🎖 Daraja: <b>{user['level']}-Daraja</b>\n"
        f"🔥 Uzluksiz mutolaa: <b>{user['streak_days']} kunlik streak!</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Ball to'plash qoidalari:</b>\n"
        f"📥 Kitobni PDF yuklab olib o'qish = <b>+10 ball</b>\n"
        f"🏆 Marafon va tanlovlarda ishtirok = <b>+500 ball</b>\n"
        f"🔥 Har kungi mutolaa odati (Streak) = <b>+20 ball bonus</b>\n\n"
        f"<i>Ballaringiz qancha ko'p bo'lsa, umumiy reytingda shuncha yuqorilab borasiz!</i>"
    )
    await message.answer(text, parse_mode="HTML")

# ==========================================
# 📊 REYTING
# ==========================================
@dp.message(F.text == "📊 Reyting")
async def show_leaderboard(message: Message):
    users = await db.get_all_users()
    top_users = users[:10]

    text = "📊 <b>Kitobxon Club Peshqadamlar Reytingi (Top 10):</b>\n\n"
    for idx, u in enumerate(top_users):
        medal = f"{idx + 1}."
        if idx == 0:
            medal = "🥇 1."
        elif idx == 1:
            medal = "🥈 2."
        elif idx == 2:
            medal = "🥉 3."

        text += f"{medal} <b>{u['name']}</b> — <b>{u['points']} ball</b> ({u['level']}-daraja)\n"

    text += "\n<i>Ko'proq kitob mutolaa qiling va reytingda 1-o'ringa chiqing!</i>"
    await message.answer(text, parse_mode="HTML")

# ==========================================
# 🤖 SUN'IY INTELLEKT MASLAXATCHI
# ==========================================
@dp.message(F.text == "🤖 AI Maslahatchi")
async def ai_advisor_start(message: Message, state: FSMContext):
    await state.set_state(AIStates.waiting_for_prompt)
    text = (
        "🤖 <b>Kitobxon Club Sun'iy Intellekt Maslahatchisi</b>\n\n"
        "Sizga qanday kitob kerak? Janr, mavzu, kayfiyat yoki muallif nomini yozing.\n"
        "Masalan:\n"
        "• <i>\"Drama kitoblar tavsiya qil\"</i>\n"
        "• <i>\"Detektiv va triller asarlar bormi?\"</i>\n"
        "• <i>\"Biznes va moliya bo'yicha eng yaxshi kitob\"</i>\n"
        "• <i>\"O'zbek adabiyoti durdonalari\"</i>\n"
        "• <i>\"Odatlar va shaxsiy rivojlanish haqida kitob\"</i>\n\n"
        "Savolingiz yoki so'rovingizni yozib yuboring 👇"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(AIStates.waiting_for_prompt)
async def ai_advisor_process(message: Message, state: FSMContext):
    await state.clear()
    query = message.text.strip().lower()

    await message.answer("🤖 <i>AI kutubxonadagi kitoblarni tahlil qilmoqda...</i>", parse_mode="HTML")

    categories = await db.get_categories()
    all_books = await db.get_books()

    matched_books = []
    reason_text = ""

    # 1. DRAMA va TEATR
    if any(word in query for word in ["drama", "dramatik", "pyesa", "teatr", "fojia", "tragediya", "fitrat", "abulfayzxon", "romeo"]):
        matched_books = [b for b in all_books if b["category_id"] == 1 or "drama" in b["title"].lower() or "drama" in b["description"].lower() or "fojia" in b["description"].lower()]
        reason_text = (
            "Siz <b>Drama va Teatr</b> janriga oid asarlarni so'radingiz!\n"
            "Dramatik asarlar insoniy kechinmalar, taqdir ziddiyatlari va fojiaviy to'qnashuvlarni yorqin ochib beradi. "
            "Kutubxonamizdagi quyidagi sara dramalarni <b>PDF formatda</b> mutolaa qilishingiz mumkin:"
        )
    # 2. DETEKTIV va SARGUZASHT
    elif any(word in query for word in ["detektiv", "jinoyat", "sherlok", "triller", "sarguzasht", "tergov"]):
        matched_books = [b for b in all_books if b["category_id"] == 2 or "sherlok" in b["title"].lower() or "detektiv" in b["description"].lower()]
        reason_text = (
            "Siz <b>Detektiv va Sarguzasht</b> yo'nalishiga qiziqmoqdasiz!\n"
            "Kutilmagan burilishlar, sirli jumboqlar va mantiqiy xulosalar uchun quyidagi sara kitoblarni tavsiya qilaman:"
        )
    # 3. BIZNES va MOLIYA
    elif any(word in query for word in ["biznes", "pul", "moliya", "investitsiya", "boy", "kiyosaki", "daromad"]):
        matched_books = [b for b in all_books if b["category_id"] == 5 or "boy" in b["title"].lower()]
        reason_text = (
            "Moliyaviy erkinlik, aktivlar yaratish va boylik psixologiyasini o'rganish uchun ushbu kitoblar tengsiz qo'llanmadir:"
        )
    # 4. PSIXOLOGIYA va ODATLAR
    elif any(word in query for word in ["odat", "psixologiya", "vaqt", "intizom", "rivojlanish", "clear", "maqsad"]):
        matched_books = [b for b in all_books if b["category_id"] == 6 or "odat" in b["title"].lower()]
        reason_text = (
            "O'z ustingizda ishlash, har kuni 1% o'sish va intizomli odatlarni shakllantirish uchun quyidagi durdonalarni o'qishni maslahat beraman:"
        )
    # 5. O'ZBEK ADABIYOTI va TARIX
    elif any(word in query for word in ["o'zbek", "tarix", "tarixiy", "bobur", "qodiriy", "otabek", "kumush", "sevgi", "muhabbat"]):
        matched_books = [b for b in all_books if b["category_id"] == 3 or "o'tkan" in b["title"].lower() or "yulduzli" in b["title"].lower()]
        reason_text = (
            "Buyuk ajdodlarimiz hayoti, sof sevgi va yuksak ma'naviyat aks etgan o'zbek adabiyoti durdonalari:"
        )
    # 6. UMUMIY QIDIRUV
    else:
        matched_books = [b for b in all_books if query in b["title"].lower() or query in b["author"].lower() or query in b["description"].lower()]
        if matched_books:
            reason_text = f"Sizning <b>\"{message.text}\"</b> so'rovingiz bo'yicha mos kelgan sara asarlar:"
        elif all_books:
            matched_books = all_books[:3]
            reason_text = "Sizning qiziqishingizdan kelib chiqib, kutubxonamizdagi eng yuqori reytingli kitoblarni tavsiya qilaman:"
        else:
            matched_books = []
            reason_text = ""

    if not matched_books:
        reply_msg = (
            f"🤖 <b>AI Maslahatchi:</b>\n\n"
            f"Siz so'ragan mavzu bo'yicha hozircha kutubxonada kitoblar mavjud emas.\n"
            f"Adminlar tez orada yangi kitoblar va PDF fayllarni yuklashadi! 📚"
        )
        buttons = [[InlineKeyboardButton(text="🤖 Qayta savol berish", callback_data="ai_ask_again")]]
        await message.answer(reply_msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return

    reply_msg = f"🤖 <b>AI Maslahatchi Tavsiyasi:</b>\n\n{reason_text}\n\n"
    buttons = []

    for idx, b in enumerate(matched_books):
        reply_msg += f"{idx + 1}. 📖 <b>{b['title']}</b> — <i>{b['author']}</i>\n"
        reply_msg += f"   💡 {b['description'][:85]}...\n\n"
        buttons.append([
            InlineKeyboardButton(text=f"📥 \"{b['title'][:20]}\"ni o'qish (PDF)", callback_data=f"get_pdf_{b['id']}")
        ])

    buttons.append([InlineKeyboardButton(text="🤖 Boshqa janr yoki savol berish", callback_data="ai_ask_again")])

    await message.answer(reply_msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "ai_ask_again")
async def ai_ask_again(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AIStates.waiting_for_prompt)
    await callback.answer()
    await callback.message.answer(
        "🤖 Savolingiz yoki qiziqishingizni yozing (masalan: <i>\"drama kitoblar\"</i>, <i>\"detektiv\"</i>, <i>\"biznes kitoblar\"</i>):",
        parse_mode="HTML"
    )

# ==========================================
# ⚙️ ADMIN PANEL HANDLERS
# ==========================================
@dp.message(F.text == "⚙️ Admin Panel")
async def show_admin_panel(message: Message):
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, message.from_user.first_name, message.from_user.username)
    is_super = (user_id == SUPER_ADMIN_ID)

    if not is_super and user["role"] != "ADMIN":
        await message.answer("⛔️ Ushbu bo'lim faqat administratorlar uchun mo'ljallangan.")
        return

    admin_title = "👑 Bosh Administrator (Super Admin)" if is_super else "⭐️ Administrator"
    is_locked = await db.is_contests_locked()
    await message.answer(
        f"⚙️ <b>Kitobxon Club — Boshqaruv Markazi (Admin Panel)</b>\n"
        f"Mansabingiz: <b>{admin_title}</b>\n\n"
        f"Kerakli amalni tanlang:",
        parse_mode="HTML",
        reply_markup=kb.get_admin_menu_keyboard(is_super_admin=is_super, contests_locked=is_locked)
    )

@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: CallbackQuery):
    is_super = (callback.from_user.id == SUPER_ADMIN_ID)
    admin_title = "👑 Bosh Administrator (Super Admin)" if is_super else "⭐️ Administrator"
    is_locked = await db.is_contests_locked()
    await callback.answer()
    await callback.message.edit_text(
        f"⚙️ <b>Kitobxon Club — Boshqaruv Markazi (Admin Panel)</b>\n"
        f"Mansabingiz: <b>{admin_title}</b>\n\n"
        f"Kerakli amalni tanlang:",
        parse_mode="HTML",
        reply_markup=kb.get_admin_menu_keyboard(is_super_admin=is_super, contests_locked=is_locked)
    )

@dp.callback_query(F.data == "admin_toggle_contests_lock")
async def handle_admin_toggle_contests_lock(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_or_create_user(user_id, callback.from_user.first_name, callback.from_user.username)
    if user_id != SUPER_ADMIN_ID and user["role"] != "ADMIN":
        await callback.answer("⛔️ Faqat administratorlar uchun!", show_alert=True)
        return

    new_is_locked = await db.toggle_contests_lock()
    status_msg = "🔒 Tanlovlar bo'limi QULFLANDI!" if new_is_locked else "🔓 Tanlovlar bo'limi OCHILDI!"
    await callback.answer(status_msg, show_alert=True)

    is_super = (user_id == SUPER_ADMIN_ID)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=kb.get_admin_menu_keyboard(is_super_admin=is_super, contests_locked=new_is_locked)
        )
    except Exception:
        pass

# Admin Users List & Management (Faqat Super Admin)
@dp.callback_query(F.data == "admin_users")
async def admin_users_list(callback: CallbackQuery):
    if callback.from_user.id != SUPER_ADMIN_ID:
        await callback.answer("⛔️ Faqat Bosh Administrator (Super Admin - 6956456422) admin qo'shishi yoki chiqarishi mumkin!", show_alert=True)
        return

    users = await db.get_all_users()
    text = (
        "👑 <b>Adminlar va Foydalanuvchilar Boshqaruvi</b>\n\n"
        f"⭐️ <b>Asosiy Super Admin ID:</b> <code>{SUPER_ADMIN_ID}</code>\n"
        "<i>(Faqat siz yangi admin tayinlash va ularni lavozimidan ozod etish huquqiga egasiz)</i>\n\n"
        "📋 <b>A'zolar ro'yxati:</b>\n"
    )
    buttons = []

    for u in users:
        is_owner = (u["id"] == SUPER_ADMIN_ID)
        role_icon = "👑 [SUPER ADMIN]" if is_owner else ("⭐️ [ADMIN]" if u["role"] == "ADMIN" else "👤 [USER]")
        text += f"{role_icon} <b>{u['name']}</b> (ID: <code>{u['id']}</code>) — {u['points']} ball\n"

        if not is_owner:
            toggle_text = f"🔻 Adminlikdan olish ({u['name'][:12]})" if u["role"] == "ADMIN" else f"⭐️ Admin qilish ({u['name'][:12]})"
            new_role = "USER" if u["role"] == "ADMIN" else "ADMIN"
            buttons.append([
                InlineKeyboardButton(text=toggle_text, callback_data=f"role_{u['id']}_{new_role}")
            ])

    # Maxsus ID orqali qo'shish va chiqarish tugmalari
    buttons.append([
        InlineKeyboardButton(text="➕ ID orqali yangi Admin tayinlash", callback_data="add_admin_by_id")
    ])
    buttons.append([
        InlineKeyboardButton(text="➖ ID orqali Adminlikdan olish", callback_data="remove_admin_by_id")
    ])
    buttons.append([InlineKeyboardButton(text="🔙 Admin menyusiga qaytish", callback_data="back_to_admin")])

    await callback.answer()
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("role_"))
async def handle_toggle_role(callback: CallbackQuery):
    if callback.from_user.id != SUPER_ADMIN_ID:
        await callback.answer("⛔️ Faqat Bosh Administrator (Super Admin) admin qo'shishi yoki chiqarishi mumkin!", show_alert=True)
        return

    parts = callback.data.split("_")
    target_id = int(parts[1])
    new_role = parts[2]

    if target_id == SUPER_ADMIN_ID:
        await callback.answer("⛔️ Super Admin huquqini o'zgartirib bo'lmaydi!", show_alert=True)
        return

    await db.update_user_role(target_id, new_role)
    status_msg = "Admin etib tayinlandi! ⭐️" if new_role == "ADMIN" else "Adminlikdan olindi va oddiy foydalanuvchi qilindi. 👤"
    await callback.answer(f"✅ ID {target_id} {status_msg}", show_alert=True)
    await admin_users_list(callback)

# ID orqali Admin tayinlash
@dp.callback_query(F.data == "add_admin_by_id")
async def start_add_admin_by_id(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != SUPER_ADMIN_ID:
        await callback.answer("⛔️ Faqat Super Admin foydalana oladi!", show_alert=True)
        return
    await state.set_state(AdminRoleStates.waiting_for_add_id)
    await callback.answer()
    cancel_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_users")]
    ])
    await callback.message.edit_text(
        "👑 <b>Yangi Administrator tayinlash</b>\n\n"
        "Admin qilmoqchi bo'lgan foydalanuvchining <b>Telegram ID raqamini</b> yozib yuboring:\n"
        "<i>(Masalan: 123456789)</i>",
        parse_mode="HTML",
        reply_markup=cancel_btn
    )

@dp.message(AdminRoleStates.waiting_for_add_id)
async def process_add_admin_by_id(message: Message, state: FSMContext):
    if message.from_user.id != SUPER_ADMIN_ID:
        await message.answer("⛔️ Faqat Super Admin admin tayinlashi mumkin!")
        await state.clear()
        return

    text = message.text.strip()
    if not text.isdigit():
        await message.answer("⚠️ Iltimos, faqat raqamlardan iborat Telegram ID kiriting:")
        return

    target_id = int(text)
    await db.set_user_role_by_id(target_id, "ADMIN")
    await state.clear()

    back_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Adminlar ro'yxatiga qaytish", callback_data="admin_users")]
    ])
    await message.answer(
        f"✅ <b>Foydalanuvchi muvaffaqiyatli ADMIN qilindi!</b>\n\n"
        f"🆔 ID: <code>{target_id}</code>\n"
        f"⭐️ Huquqi: Administrator (kitoblar qo'shish va xabarnoma yuborish imkoni berildi).",
        parse_mode="HTML",
        reply_markup=back_btn
    )

# ID orqali Adminlikdan olish
@dp.callback_query(F.data == "remove_admin_by_id")
async def start_remove_admin_by_id(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != SUPER_ADMIN_ID:
        await callback.answer("⛔️ Faqat Super Admin foydalana oladi!", show_alert=True)
        return
    await state.set_state(AdminRoleStates.waiting_for_remove_id)
    await callback.answer()
    cancel_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_users")]
    ])
    await callback.message.edit_text(
        "🔻 <b>Administratorni lavozimidan ozod etish</b>\n\n"
        "Adminlikdan olmoqchi bo'lgan foydalanuvchining <b>Telegram ID raqamini</b> yozib yuboring:",
        parse_mode="HTML",
        reply_markup=cancel_btn
    )

@dp.message(AdminRoleStates.waiting_for_remove_id)
async def process_remove_admin_by_id(message: Message, state: FSMContext):
    if message.from_user.id != SUPER_ADMIN_ID:
        await message.answer("⛔️ Faqat Super Admin foydalana oladi!")
        await state.clear()
        return

    text = message.text.strip()
    if not text.isdigit():
        await message.answer("⚠️ Iltimos, faqat raqamlardan iborat Telegram ID kiriting:")
        return

    target_id = int(text)
    if target_id == SUPER_ADMIN_ID:
        await message.answer("⛔️ Siz Bosh Administratorsiz (Super Admin), o'zingizni o'chira olmaysiz!")
        return

    await db.set_user_role_by_id(target_id, "USER")
    await state.clear()

    back_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Adminlar ro'yxatiga qaytish", callback_data="admin_users")]
    ])
    await message.answer(
        f"✅ <b>Foydalanuvchi lavozimidan ozod etildi!</b>\n\n"
        f"🆔 ID: <code>{target_id}</code>\n"
        f"👤 Huquqi: Oddiy foydalanuvchi (USER) darajasiga tushirildi.",
        parse_mode="HTML",
        reply_markup=back_btn
    )

# ==========================================
# 📂 ADABIYOT TOIFALARI (JANRLAR) BOSHQARUVI
# ==========================================
@dp.callback_query(F.data == "admin_categories")
async def admin_categories_panel(callback: CallbackQuery):
    categories = await db.get_categories_with_count()
    await callback.answer()
    await callback.message.edit_text(
        "📂 <b>Adabiyot toifalari (Janrlar) boshqaruvi:</b>\n\n"
        "Mavjud toifalar va ulardagi kitoblar soni:\n"
        "<i>(Har bir toifa kitob qo'shish vaqtida tanlanadi)</i>",
        parse_mode="HTML",
        reply_markup=kb.get_categories_manage_keyboard(categories)
    )

@dp.callback_query(F.data.startswith("cat_info_"))
async def admin_cat_info(callback: CallbackQuery):
    cat_id = int(callback.data.split("_")[2])
    cat = await db.get_category_by_id(cat_id)
    if cat:
        await callback.answer(f"📂 {cat['name']}\n{cat['description'] or ''}", show_alert=True)
    else:
        await callback.answer()

@dp.callback_query(F.data.startswith("del_cat_"))
async def admin_del_category(callback: CallbackQuery):
    cat_id = int(callback.data.split("_")[2])
    cat = await db.get_category_by_id(cat_id)
    if not cat:
        await callback.answer("Toifa topilmadi.", show_alert=True)
        return

    await db.delete_category(cat_id)
    await callback.answer(f"🗑 \"{cat['name']}\" toifasi o'chirildi!", show_alert=True)
    categories = await db.get_categories_with_count()
    await callback.message.edit_text(
        "📂 <b>Adabiyot toifalari (Janrlar) boshqaruvi:</b>\n\n"
        f"✅ <b>\"{cat['name']}\"</b> toifasi muvaffaqiyatli o'chirildi!\n\n"
        "Yangilangan toifalar ro'yxati:",
        parse_mode="HTML",
        reply_markup=kb.get_categories_manage_keyboard(categories)
    )

@dp.callback_query(F.data.startswith("edit_cat_"))
async def admin_edit_category_panel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    cat_id = int(callback.data.split("_")[2])
    cat = await db.get_category_by_id(cat_id)
    if not cat:
        await callback.answer("Toifa topilmadi.", show_alert=True)
        return

    await callback.answer()
    text = (
        f"⚙️ <b>Toifani (Janrni) tahrirlash:</b>\n\n"
        f"📂 <b>Nomi:</b> {cat['name']}\n"
        f"📝 <b>Tavsifi:</b> <i>{cat['description'] or 'Mavjud emas'}</i>\n"
        f"🔗 <b>Slug:</b> <code>{cat['slug']}</code>\n\n"
        f"👇 <i>Qaysi ma'lumotni o'zgartirmoqchisiz?</i>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.get_edit_category_keyboard(cat_id))

@dp.callback_query(F.data.startswith("edit_cfield_"))
async def admin_edit_category_field(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    cat_id = int(parts[2])
    field = parts[3]

    cat = await db.get_category_by_id(cat_id)
    if not cat:
        await callback.answer("Toifa topilmadi.", show_alert=True)
        return

    await state.update_data(cat_id=cat_id)
    cancel_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"edit_cat_{cat_id}")]
    ])

    if field == "name":
        await state.set_state(EditCategoryStates.waiting_for_name)
        await callback.answer()
        await callback.message.edit_text(
            f"✏️ <b>Toifa nomini o'zgartirish</b>\n\n"
            f"Hozirgi nomi: <b>{cat['name']}</b>\n\n"
            f"Yangi toifa nomini yozib yuboring:",
            parse_mode="HTML",
            reply_markup=cancel_btn
        )
    elif field == "desc":
        await state.set_state(EditCategoryStates.waiting_for_desc)
        await callback.answer()
        await callback.message.edit_text(
            f"📝 <b>Toifa tavsifini o'zgartirish</b>\n\n"
            f"Toifa: <b>{cat['name']}</b>\n"
            f"Hozirgi tavsifi: <i>{cat['description'] or 'Mavjud emas'}</i>\n\n"
            f"Yangi tavsif matnini yozib yuboring:",
            parse_mode="HTML",
            reply_markup=cancel_btn
        )

@dp.message(EditCategoryStates.waiting_for_name)
async def process_edit_category_name(message: Message, state: FSMContext):
    data = await state.get_data()
    cat_id = data.get("cat_id")
    new_name = message.text.strip()

    if len(new_name) < 2:
        await message.answer("⚠️ Nom juda qisqa. Iltimos, to'liqroq nom kiriting:")
        return

    await db.update_category(cat_id, name=new_name)
    await state.clear()
    cat = await db.get_category_by_id(cat_id)

    text = (
        f"✅ <b>Toifa nomi muvaffaqiyatli yangilandi!</b>\n\n"
        f"📂 <b>Nomi:</b> {cat['name']}\n"
        f"📝 <b>Tavsifi:</b> <i>{cat['description'] or 'Mavjud emas'}</i>\n"
        f"🔗 <b>Slug:</b> <code>{cat['slug']}</code>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=kb.get_edit_category_keyboard(cat_id))

@dp.message(EditCategoryStates.waiting_for_desc)
async def process_edit_category_desc(message: Message, state: FSMContext):
    data = await state.get_data()
    cat_id = data.get("cat_id")
    new_desc = message.text.strip()

    await db.update_category(cat_id, description=new_desc)
    await state.clear()
    cat = await db.get_category_by_id(cat_id)

    text = (
        f"✅ <b>Toifa tavsifi muvaffaqiyatli yangilandi!</b>\n\n"
        f"📂 <b>Nomi:</b> {cat['name']}\n"
        f"📝 <b>Tavsifi:</b> <i>{cat['description'] or 'Mavjud emas'}</i>\n"
        f"🔗 <b>Slug:</b> <code>{cat['slug']}</code>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=kb.get_edit_category_keyboard(cat_id))

@dp.callback_query(F.data == "admin_add_new_cat")
async def admin_add_new_cat_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CategoryStates.waiting_for_name)
    await state.update_data(return_to_wizard=False)
    await callback.answer()
    cancel_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_categories")]
    ])
    await callback.message.edit_text(
        "📂 <b>Yangi toifa (janr) qo'shish</b>\n\n"
        "Yangi toifa nomini yozib yuboring:\n"
        "<i>(Masalan: Fantastika, Tarixiy asarlar, Bolalar adabiyoti, Diniy-ma'rifiy)</i>",
        parse_mode="HTML",
        reply_markup=cancel_btn
    )

# ==========================================
# ➕ KITOB QO'SHISH (1-BOSQICH: TOIFA TANLASH)
# ==========================================
@dp.callback_query(F.data == "admin_add_book")
async def admin_add_book_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AddBookStates.waiting_for_category)
    categories = await db.get_categories()
    await callback.answer()
    await callback.message.edit_text(
        "➕ <b>Yangi kitob qo'shish jarayoni</b>\n\n"
        "1️⃣-Qadam: Kitob qaysi <b>adabiyot janri (toifa)</b>ga mansub? Quyidagilardan birini tanlang:\n\n"
        "<i>(Agar kerakli toifa ro'yxatda bo'lmasa, «➕ Yangi toifa yaratish» tugmasini bosing)</i>",
        parse_mode="HTML",
        reply_markup=kb.get_genre_choice_keyboard(categories, for_book_wizard=True)
    )

@dp.callback_query(AddBookStates.waiting_for_category, F.data.startswith("genre_sel_"))
async def admin_book_category_selected(callback: CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[2])
    cat = await db.get_category_by_id(cat_id)
    cat_name = cat["name"] if cat else "Boshqa"

    await state.update_data(category_id=cat_id, category_name=cat_name)
    await state.set_state(AddBookStates.waiting_for_title)
    await callback.answer()
    await callback.message.edit_text(
        f"✅ Tanlangan toifa: <b>{cat_name}</b>\n\n"
        f"2️⃣-Qadam: Endi <b>Kitob nomini</b> kiriting:\n"
        f"<i>(Masalan: Kecha va Kunduz, Gamlet, Boy ota kambag'al ota)</i>",
        parse_mode="HTML"
    )

@dp.callback_query(AddBookStates.waiting_for_category, F.data == "add_category_wizard")
async def admin_book_add_category_wizard(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CategoryStates.waiting_for_name)
    await state.update_data(return_to_wizard=True)
    await callback.answer()
    await callback.message.edit_text(
        "📂 <b>Yangi adabiyot toifasini yaratish:</b>\n\n"
        "Toifa (janr) nomini yozib yuboring:\n"
        "<i>(Masalan: Fantastika, Dasturlash, She'riyat)</i>",
        parse_mode="HTML"
    )

# Yangi toifa nomini qabul qilish
@dp.message(CategoryStates.waiting_for_name)
async def process_category_name(message: Message, state: FSMContext):
    cat_name = message.text.strip()
    if len(cat_name) < 2:
        await message.answer("⚠️ Toifa nomi juda qisqa. Iltimos, to'liqroq nom kiriting:")
        return

    new_cat_id = await db.add_category(cat_name)
    data = await state.get_data()
    return_to_wizard = data.get("return_to_wizard", False)

    if return_to_wizard:
        # Kitob qo'shish bosqichini davom ettiramiz
        await state.update_data(category_id=new_cat_id, category_name=cat_name)
        await state.set_state(AddBookStates.waiting_for_title)
        await message.answer(
            f"🎉 Yangi toifa <b>\"{cat_name}\"</b> muvaffaqiyatli saqlandi va kitobga biriktirildi!\n\n"
            f"2️⃣-Qadam: Endi <b>Kitob nomini</b> kiriting:\n"
            f"<i>(Masalan: Kecha va Kunduz, Gamlet, Boy ota kambag'al ota)</i>",
            parse_mode="HTML"
        )
    else:
        # Toifalar boshqaruviga qaytish
        await state.clear()
        categories = await db.get_categories_with_count()
        await message.answer(
            f"✅ Yangi toifa <b>\"{cat_name}\"</b> muvaffaqiyatli qo'shildi!\n\n"
            f"Barcha toifalar ro'yxati yangilandi:",
            parse_mode="HTML",
            reply_markup=kb.get_categories_manage_keyboard(categories)
        )

# 2-Qadam: Kitob nomi
@dp.message(AddBookStates.waiting_for_title)
async def admin_add_book_title(message: Message, state: FSMContext):
    title = message.text.strip()
    await state.update_data(title=title)
    await state.set_state(AddBookStates.waiting_for_author)
    await message.answer(
        f"📖 Kitob nomi: <b>{title}</b>\n\n"
        f"3️⃣-Qadam: Kitob <b>muallifi</b>ni kiriting:\n"
        f"<i>(Masalan: Cho'lpon, Abdulla Qodiriy, Shekspir)</i>",
        parse_mode="HTML"
    )

CATEGORY_FOLDERS = {
    1: "drama va teatr",
    2: "Dewtektiv asar",
    3: "ozbek adabiyoti",
    4: "jaxon adabiyoti",
    5: "biznes va moliya",
    6: "psixologik",
    7: "ilmiy-ommabop"
}

# 3-Qadam: Kitob muallifi
@dp.message(AddBookStates.waiting_for_author)
async def admin_add_book_author(message: Message, state: FSMContext):
    author = message.text.strip()
    await state.update_data(author=author)
    await state.set_state(AddBookStates.waiting_for_pdf)

    data = await state.get_data()
    cat_id = data.get("category_id", 1)
    cat_name = data.get("category_name", "Tanlangan janr")
    title = data.get("title", "")

    buttons = [
        [InlineKeyboardButton(text="📁 PDF yuklash (Fayllar papkasi)", callback_data="open_files_folder")],
        [InlineKeyboardButton(text="📂 Barcha papkalarni ko'rish", callback_data="open_all_folders")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="back_to_admin")]
    ]

    await message.answer(
        f"✅ <b>Kitob ma'lumotlari:</b>\n"
        f"📂 Toifasi: <b>{cat_name}</b>\n"
        f"📖 Nomi: <b>{title}</b>\n"
        f"✍️ Muallifi: <b>{author}</b>\n\n"
        f"📄 <b>4️⃣-Qadam: Kitobning PDF faylini yuklash</b>\n\n"
        f"Pastdagi <b>«📁 PDF yuklash (Fayllar papkasi)»</b> tugmasini bosing — botning o'zida papkadagi fayllar ochiladi va kitobni bir marta bosish bilan tanlashingiz mumkin!\n\n"
        f"💡 <i>Yoki Telegram pastidagi 📎 (skrepka) belgisini bosib, yangi PDF faylni to'g'ridan-to'g'ri tashlashingiz ham mumkin.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

# 4-Qadam: Papkadagi fayllarni ochish
@dp.callback_query(AddBookStates.waiting_for_pdf, F.data == "open_files_folder")
async def handle_open_files_folder(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cat_id = data.get("category_id", 1)
    folder_name = CATEGORY_FOLDERS.get(cat_id, "ozbek adabiyoti")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_folder = os.path.join(base_dir, folder_name)

    files = []
    if os.path.exists(target_folder):
        files = [f for f in os.listdir(target_folder) if f.lower().endswith(('.pdf', '.epub', '.docx', '.txt'))]

    if not files:
        await callback.answer("Ushbu toifa papkasi hozircha bo'sh. Barcha papkalardan tanlang.", show_alert=True)
        await handle_open_all_folders(callback, state)
        return

    buttons = []
    for idx, f in enumerate(files):
        clean_label = f[:32] + "..." if len(f) > 35 else f
        buttons.append([
            InlineKeyboardButton(text=f"📄 {clean_label}", callback_data=f"pick_file_{idx}")
        ])

    await state.update_data(folder_files=files, current_folder=target_folder)
    buttons.append([InlineKeyboardButton(text="📂 Boshqa papkalarni ko'rish", callback_data="open_all_folders")])
    buttons.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="back_to_admin")])

    await callback.answer()
    try:
        await callback.message.edit_text(
            f"📂 <b>[{folder_name}] papkasidagi fayllar ochildi:</b>\n\n"
            f"Kitobga biriktirmoqchi bo'lgan PDF fayl ustiga bosing:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except TelegramBadRequest:
        pass

# Barcha papkalarni ochish
@dp.callback_query(AddBookStates.waiting_for_pdf, F.data == "open_all_folders")
async def handle_open_all_folders(callback: CallbackQuery, state: FSMContext):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    buttons = []
    for cid, fname in CATEGORY_FOLDERS.items():
        fpath = os.path.join(base_dir, fname)
        count = len([f for f in os.listdir(fpath) if f.lower().endswith(('.pdf', '.epub', '.docx'))]) if os.path.exists(fpath) else 0
        buttons.append([
            InlineKeyboardButton(text=f"📁 {fname} ({count} ta fayl)", callback_data=f"pick_folder_{cid}")
        ])

    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="open_files_folder")])
    await callback.answer()
    try:
        await callback.message.edit_text(
            "📂 <b>Barcha mavjud kitob papkalari:</b>\n\n"
            "Kerakli papkani tanlang, ichidagi fayllar ochiladi:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except TelegramBadRequest:
        pass

# Tanlangan papka ichidagi fayllar
@dp.callback_query(AddBookStates.waiting_for_pdf, F.data.startswith("pick_folder_"))
async def handle_pick_folder(callback: CallbackQuery, state: FSMContext):
    cid = int(callback.data.split("_")[2])
    folder_name = CATEGORY_FOLDERS.get(cid, "ozbek adabiyoti")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_folder = os.path.join(base_dir, folder_name)

    files = []
    if os.path.exists(target_folder):
        files = [f for f in os.listdir(target_folder) if f.lower().endswith(('.pdf', '.epub', '.docx', '.txt'))]

    if not files:
        await callback.answer("Bu papkada hozircha fayllar yo'q.", show_alert=True)
        return

    buttons = []
    for idx, f in enumerate(files):
        clean_label = f[:32] + "..." if len(f) > 35 else f
        buttons.append([
            InlineKeyboardButton(text=f"📄 {clean_label}", callback_data=f"pick_file_{idx}")
        ])

    await state.update_data(folder_files=files, current_folder=target_folder)
    buttons.append([InlineKeyboardButton(text="📂 Boshqa papkalarga qaytish", callback_data="open_all_folders")])

    await callback.answer()
    await callback.message.edit_text(
        f"📂 <b>[{folder_name}] papkasidagi fayllar:</b>\n\n"
        f"Biriktirish uchun faylni tanlang:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

# Papkadagi faylni tanlab kitobni saqlash
@dp.callback_query(AddBookStates.waiting_for_pdf, F.data.startswith("pick_file_"))
async def handle_pick_file(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[2])
    data = await state.get_data()
    files = data.get("folder_files", [])
    current_folder = data.get("current_folder", "")

    if idx >= len(files):
        await callback.answer("Fayl topilmadi.", show_alert=True)
        return

    selected_file = files[idx]
    file_path = os.path.join(current_folder, selected_file)
    rel_path = os.path.relpath(file_path, BASE_DIR).replace("\\", "/")
    size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2) if os.path.exists(file_path) else 10

    title = data.get("title", selected_file)
    author = data.get("author", "Noma'lum")
    category_id = data.get("category_id", 1)
    category_name = data.get("category_name", "")

    book_id = await db.add_book(
        title=title,
        author=author,
        category_id=category_id,
        pdf_file_name=selected_file,
        description=f"{title} — {author} qalamiga mansub {category_name.lower()} sara asari.",
        file_path=rel_path
    )

    await state.clear()
    await callback.answer(f"✅ Fayl tanlandi: {selected_file}", show_alert=False)

    success_msg = (
        f"🎉 <b>Yangi kitob va PDF fayli muvaffaqiyatli saqlandi!</b>\n\n"
        f"📂 <b>Toifasi:</b> {category_name}\n"
        f"📖 <b>Nomi:</b> {title}\n"
        f"✍️ <b>Muallifi:</b> {author}\n"
        f"📄 <b>Fayl:</b> {selected_file} ({size_mb} MB)\n\n"
        f"<i>Kitob bazaga biriktirildi va barcha kitobxonlar uni PDF formatda mutolaa qilishlari mumkin!</i>"
    )

    inline_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Kitobni sinab ko'rish (PDF yuklab olish)", callback_data=f"get_pdf_{book_id}")],
        [InlineKeyboardButton(text="➕ Yana kitob qo'shish", callback_data="admin_add_book")],
        [InlineKeyboardButton(text="🔙 Admin menyusiga qaytish", callback_data="back_to_admin")]
    ])

    await callback.message.edit_text(success_msg, parse_mode="HTML", reply_markup=inline_btn)

# Telegram orqali fayl tashlanganda
@dp.message(AddBookStates.waiting_for_pdf, F.document)
async def admin_add_book_pdf(message: Message, state: FSMContext):
    doc = message.document
    file_id = doc.file_id
    file_name = doc.file_name or "kitob.pdf"
    file_size_mb = round(doc.file_size / (1024 * 1024), 2) if doc.file_size else 10

    data = await state.get_data()
    title = data.get("title", "Yangi kitob")
    author = data.get("author", "Noma'lum")
    category_id = data.get("category_id", 1)
    category_name = data.get("category_name", "")

    # Kompyuterdagi tegishli toifa papkasiga ham jismonan saqlab qo'yamiz
    folder_name = CATEGORY_FOLDERS.get(category_id, "ozbek adabiyoti")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cat_dir = os.path.join(base_dir, folder_name)
    os.makedirs(cat_dir, exist_ok=True)
    local_dest = os.path.join(cat_dir, file_name)
    try:
        await bot.download(doc, destination=local_dest)
        saved_file_path = local_dest
    except Exception:
        saved_file_path = None

    book_id = await db.add_book(
        title=title,
        author=author,
        category_id=category_id,
        pdf_file_id=file_id,
        pdf_file_name=file_name,
        description=f"{title} — {author} qalamiga mansub sara asar.",
        file_path=saved_file_path
    )

    await state.clear()

    success_msg = (
        f"🎉 <b>Yangi kitob va PDF fayli muvaffaqiyatli saqlandi!</b>\n\n"
        f"📂 <b>Toifasi:</b> {category_name}\n"
        f"📖 <b>Nomi:</b> {title}\n"
        f"✍️ <b>Muallifi:</b> {author}\n"
        f"📄 <b>Fayl:</b> {file_name} ({file_size_mb} MB)\n"
        f"💾 <b>Kompyuterda saqlandi:</b> <code>{folder_name}/{file_name}</code>\n\n"
        f"<i>Endi barcha foydalanuvchilar ushbu kitobni PDF formatda yuklab olib mutolaa qilishlari mumkin!</i>"
    )

    inline_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Kitobni sinab ko'rish (PDF yuklab olish)", callback_data=f"get_pdf_{book_id}")],
        [InlineKeyboardButton(text="➕ Yana kitob qo'shish", callback_data="admin_add_book")],
        [InlineKeyboardButton(text="🔙 Admin menyusiga qaytish", callback_data="back_to_admin")]
    ])

    await message.answer(success_msg, parse_mode="HTML", reply_markup=inline_btn)

# ==========================================
# ✏️ ADMIN: KITOBLARNI TAHRIRLASH (EDIT BOOKS)
# ==========================================

async def render_edit_book_card(callback_or_message, book_id: int, notice: str = ""):
    book = await db.get_book_by_id(book_id)
    if not book:
        text = "⚠️ Kitob topilmadi yoki o'chirilgan."
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.answer("Kitob topilmadi.", show_alert=True)
            try:
                await callback_or_message.message.edit_text(text)
            except Exception:
                await callback_or_message.message.answer(text)
        else:
            await callback_or_message.answer(text)
        return

    cat_name = book.get("category_name") or "Biriktirilmagan"
    has_pdf = "✅ Biriktirilgan" if (book.get("pdf_file_id") or resolve_book_file(book)) else "❌ Yuklanmagan"
    pdf_name = book.get("pdf_file_name") or "Mavjud emas"

    text = ""
    if notice:
        text += f"{notice}\n\n"

    text += (
        f"⚙️ <b>Kitob ma'lumotlarini tahrirlash (ID: {book['id']}):</b>\n\n"
        f"📖 <b>Nomi:</b> {book['title']}\n"
        f"✍️ <b>Muallifi:</b> {book['author']}\n"
        f"📂 <b>Janri:</b> {cat_name}\n"
        f"🔢 <b>Hajmi:</b> {book['pages']} sahifa\n"
        f"📄 <b>PDF fayli:</b> {pdf_name} ({has_pdf})\n"
        f"📝 <b>Tavsifi:</b> <i>{book['description'] or 'Mavjud emas'}</i>\n\n"
        f"👇 <i>Qaysi ma'lumotni o'zgartirmoqchisiz? Quyidagi tugmalardan birini tanlang:</i>"
    )

    keyboard = kb.get_edit_book_keyboard(book_id)

    if isinstance(callback_or_message, CallbackQuery):
        try:
            await callback_or_message.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except TelegramBadRequest:
            await callback_or_message.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await callback_or_message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("edit_book_"))
async def handle_edit_book_menu(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = await db.get_or_create_user(user_id, callback.from_user.first_name, callback.from_user.username)
    if user_id != SUPER_ADMIN_ID and user["role"] != "ADMIN":
        await callback.answer("⛔️ Faqat administratorlar uchun!", show_alert=True)
        return

    await state.clear()
    book_id = int(callback.data.split("_")[2])
    await callback.answer()
    await render_edit_book_card(callback, book_id)

@dp.callback_query(F.data.startswith("cancel_edit_book_"))
async def handle_cancel_edit_book(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    book_id = int(callback.data.split("_")[3])
    await callback.answer("Tahrirlash bekor qilindi.")
    await render_edit_book_card(callback, book_id)

@dp.callback_query(F.data.startswith("edit_bfield_"))
async def handle_edit_book_field(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = await db.get_or_create_user(user_id, callback.from_user.first_name, callback.from_user.username)
    if user_id != SUPER_ADMIN_ID and user["role"] != "ADMIN":
        await callback.answer("⛔️ Faqat administratorlar uchun!", show_alert=True)
        return

    parts = callback.data.split("_")
    book_id = int(parts[2])
    field = parts[3]

    book = await db.get_book_by_id(book_id)
    if not book:
        await callback.answer("Kitob topilmadi.", show_alert=True)
        return

    await state.update_data(edit_book_id=book_id)
    cancel_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_edit_book_{book_id}")]
    ])

    if field == "title":
        await state.set_state(EditBookStates.waiting_for_title)
        await callback.answer()
        await callback.message.edit_text(
            f"✏️ <b>Kitob nomini o'zgartirish</b>\n\n"
            f"Hozirgi nomi: <b>{book['title']}</b>\n\n"
            f"Yangi nomni yozib yuboring:",
            parse_mode="HTML",
            reply_markup=cancel_btn
        )

    elif field == "author":
        await state.set_state(EditBookStates.waiting_for_author)
        await callback.answer()
        await callback.message.edit_text(
            f"✍️ <b>Kitob muallifini o'zgartirish</b>\n\n"
            f"Kitob: <b>{book['title']}</b>\n"
            f"Hozirgi muallifi: <b>{book['author']}</b>\n\n"
            f"Yangi muallif ism-familiyasini yozib yuboring:",
            parse_mode="HTML",
            reply_markup=cancel_btn
        )

    elif field == "category":
        await state.clear()
        categories = await db.get_categories()
        await callback.answer()
        await callback.message.edit_text(
            f"📂 <b>Kitob toifasini (janrini) o'zgartirish</b>\n\n"
            f"Kitob: <b>{book['title']}</b>\n"
            f"Hozirgi toifasi: <b>{book.get('category_name', 'Biriktirilmagan')}</b>\n\n"
            f"Yangi toifani tanlang:",
            parse_mode="HTML",
            reply_markup=kb.get_genre_choice_keyboard(
                categories, 
                for_book_wizard=False, 
                prefix=f"edit_bcat_{book_id}_", 
                cancel_callback=f"cancel_edit_book_{book_id}"
            )
        )

    elif field == "description":
        await state.set_state(EditBookStates.waiting_for_description)
        await callback.answer()
        await callback.message.edit_text(
            f"📑 <b>Kitob tavsifini o'zgartirish</b>\n\n"
            f"Kitob: <b>{book['title']}</b>\n"
            f"Hozirgi tavsifi: <i>{book['description'] or 'Mavjud emas'}</i>\n\n"
            f"Yangi qisqacha tavsif matnini yozib yuboring:",
            parse_mode="HTML",
            reply_markup=cancel_btn
        )

    elif field == "pages":
        await state.set_state(EditBookStates.waiting_for_pages)
        await callback.answer()
        await callback.message.edit_text(
            f"🔢 <b>Kitob sahifalar sonini o'zgartirish</b>\n\n"
            f"Kitob: <b>{book['title']}</b>\n"
            f"Hozirgi sahifalar soni: <b>{book['pages']}</b>\n\n"
            f"Yangi sahifalar sonini kiriting (faqat raqam):",
            parse_mode="HTML",
            reply_markup=cancel_btn
        )

    elif field == "pdf":
        await state.set_state(EditBookStates.waiting_for_pdf)
        await callback.answer()
        buttons = [
            [InlineKeyboardButton(text="📁 Papkadagi fayllar orasidan tanlash", callback_data=f"edit_pdf_folder_{book_id}")],
            [InlineKeyboardButton(text="📂 Barcha papkalarni ko'rish", callback_data=f"edit_pdf_all_{book_id}")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_edit_book_{book_id}")]
        ]
        await callback.message.edit_text(
            f"📄 <b>Kitobning PDF faylini yangilash</b>\n\n"
            f"Kitob: <b>{book['title']}</b>\n"
            f"Hozirgi fayl: <b>{book.get('pdf_file_name') or 'Yuklanmagan'}</b>\n\n"
            f"Yangi PDF faylni yuklash uchun:\n"
            f"1️⃣ Telegram orqali 📎 (skrepka) tugmasi bilan yangi PDF faylni yuborishingiz mumkin;\n"
            f"2️⃣ Yoki quyidagi tugma orqali kompyuterdagi papkalardan biriktirishingiz mumkin 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )

@dp.callback_query(F.data.startswith("edit_bcat_"))
async def handle_edit_book_category_selected(callback: CallbackQuery):
    parts = callback.data.split("_")
    book_id = int(parts[2])
    cat_id = int(parts[3])

    cat = await db.get_category_by_id(cat_id)
    cat_name = cat["name"] if cat else "Boshqa"

    await db.update_book(book_id, category_id=cat_id)
    await callback.answer(f"Janr «{cat_name}»ga o'zgartirildi!", show_alert=True)
    await render_edit_book_card(callback, book_id, notice=f"✅ Toifa muvaffaqiyatli yangilandi: <b>{cat_name}</b>")

# Kitob nomi qabul qilish
@dp.message(EditBookStates.waiting_for_title)
async def process_edit_book_title(message: Message, state: FSMContext):
    data = await state.get_data()
    book_id = data.get("edit_book_id")
    new_title = message.text.strip()

    if len(new_title) < 2:
        await message.answer("⚠️ Kitob nomi juda qisqa. Iltimos, to'liq nom kiriting:")
        return

    await db.update_book(book_id, title=new_title)
    await state.clear()
    await render_edit_book_card(message, book_id, notice=f"🎉 Kitob nomi muvaffaqiyatli yangilandi: <b>{new_title}</b>")

# Kitob muallifi qabul qilish
@dp.message(EditBookStates.waiting_for_author)
async def process_edit_book_author(message: Message, state: FSMContext):
    data = await state.get_data()
    book_id = data.get("edit_book_id")
    new_author = message.text.strip()

    if len(new_author) < 2:
        await message.answer("⚠️ Muallif nomi juda qisqa. Iltimos, qayta kiriting:")
        return

    await db.update_book(book_id, author=new_author)
    await state.clear()
    await render_edit_book_card(message, book_id, notice=f"🎉 Muallif muvaffaqiyatli yangilandi: <b>{new_author}</b>")

# Kitob tavsifi qabul qilish
@dp.message(EditBookStates.waiting_for_description)
async def process_edit_book_description(message: Message, state: FSMContext):
    data = await state.get_data()
    book_id = data.get("edit_book_id")
    new_desc = message.text.strip()

    await db.update_book(book_id, description=new_desc)
    await state.clear()
    await render_edit_book_card(message, book_id, notice="🎉 Kitob tavsifi muvaffaqiyatli yangilandi!")

# Kitob sahifalari soni qabul qilish
@dp.message(EditBookStates.waiting_for_pages)
async def process_edit_book_pages(message: Message, state: FSMContext):
    data = await state.get_data()
    book_id = data.get("edit_book_id")
    text = message.text.strip()

    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Iltimos, faqat noldan katta butun son kiriting (masalan: 250):")
        return

    pages = int(text)
    await db.update_book(book_id, pages=pages)
    await state.clear()
    await render_edit_book_card(message, book_id, notice=f"🎉 Sahifalar soni yangilandi: <b>{pages} sahifa</b>")

# Telegram orqali yangi PDF tashlanganda
@dp.message(EditBookStates.waiting_for_pdf, F.document)
async def process_edit_book_pdf_upload(message: Message, state: FSMContext):
    data = await state.get_data()
    book_id = data.get("edit_book_id")
    doc = message.document
    file_id = doc.file_id
    file_name = doc.file_name or "kitob.pdf"

    book = await db.get_book_by_id(book_id)
    category_id = book.get("category_id") if book else 1

    folder_name = CATEGORY_FOLDERS.get(category_id, "ozbek adabiyoti")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cat_dir = os.path.join(base_dir, folder_name)
    os.makedirs(cat_dir, exist_ok=True)
    local_dest = os.path.join(cat_dir, file_name)

    try:
        await bot.download(doc, destination=local_dest)
        saved_file_path = os.path.relpath(local_dest, BASE_DIR).replace("\\", "/")
    except Exception:
        saved_file_path = None

    await db.update_book(
        book_id,
        pdf_file_id=file_id,
        pdf_file_name=file_name,
        file_path=saved_file_path
    )
    await state.clear()
    await render_edit_book_card(
        message, 
        book_id, 
        notice=f"🎉 Yangi PDF fayl muvaffaqiyatli saqlandi va kitobga biriktirildi!\n📄 <b>Fayl:</b> {file_name}"
    )

# PDF almashtirish: Papkadagi fayllarni ko'rish
@dp.callback_query(F.data.startswith("edit_pdf_folder_"))
async def handle_edit_pdf_folder(callback: CallbackQuery, state: FSMContext):
    book_id = int(callback.data.split("_")[3])
    book = await db.get_book_by_id(book_id)
    cat_id = book.get("category_id") if book else 1

    folder_name = CATEGORY_FOLDERS.get(cat_id, "ozbek adabiyoti")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_folder = os.path.join(base_dir, folder_name)

    files = []
    if os.path.exists(target_folder):
        files = [f for f in os.listdir(target_folder) if f.lower().endswith(('.pdf', '.epub', '.docx', '.txt'))]

    if not files:
        await callback.answer("Ushbu toifa papkasi hozircha bo'sh. Barcha papkalardan tanlang.", show_alert=True)
        await handle_edit_pdf_all(callback, state)
        return

    buttons = []
    for idx, f in enumerate(files):
        clean_label = f[:32] + "..." if len(f) > 35 else f
        buttons.append([
            InlineKeyboardButton(text=f"📄 {clean_label}", callback_data=f"edit_pick_file_{book_id}_{idx}")
        ])

    await state.update_data(edit_book_id=book_id, edit_folder_files=files, edit_current_folder=target_folder)
    buttons.append([InlineKeyboardButton(text="📂 Boshqa papkalarni ko'rish", callback_data=f"edit_pdf_all_{book_id}")])
    buttons.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_edit_book_{book_id}")])

    await callback.answer()
    await callback.message.edit_text(
        f"📂 <b>[{folder_name}] papkasidagi fayllar:</b>\n\nKitobga yangi fayl sifatida biriktirish uchun tanlang:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

# PDF almashtirish: Barcha papkalar
@dp.callback_query(F.data.startswith("edit_pdf_all_"))
async def handle_edit_pdf_all(callback: CallbackQuery, state: FSMContext):
    book_id = int(callback.data.split("_")[3])
    base_dir = os.path.dirname(os.path.abspath(__file__))
    buttons = []
    for cid, fname in CATEGORY_FOLDERS.items():
        fpath = os.path.join(base_dir, fname)
        count = len([f for f in os.listdir(fpath) if f.lower().endswith(('.pdf', '.epub', '.docx'))]) if os.path.exists(fpath) else 0
        buttons.append([
            InlineKeyboardButton(text=f"📁 {fname} ({count} ta fayl)", callback_data=f"edit_pick_folder_{book_id}_{cid}")
        ])

    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"edit_bfield_{book_id}_pdf")])
    await callback.answer()
    await callback.message.edit_text(
        "📂 <b>Barcha mavjud kitob papkalari:</b>\n\nFaylni tanlash uchun papkani bosing:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

# PDF almashtirish: Tanlangan papka ichidagi fayllar
@dp.callback_query(F.data.startswith("edit_pick_folder_"))
async def handle_edit_pick_folder(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    book_id = int(parts[3])
    cid = int(parts[4])

    folder_name = CATEGORY_FOLDERS.get(cid, "ozbek adabiyoti")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    target_folder = os.path.join(base_dir, folder_name)

    files = []
    if os.path.exists(target_folder):
        files = [f for f in os.listdir(target_folder) if f.lower().endswith(('.pdf', '.epub', '.docx', '.txt'))]

    if not files:
        await callback.answer("Bu papkada fayllar yo'q.", show_alert=True)
        return

    buttons = []
    for idx, f in enumerate(files):
        clean_label = f[:32] + "..." if len(f) > 35 else f
        buttons.append([
            InlineKeyboardButton(text=f"📄 {clean_label}", callback_data=f"edit_pick_file_{book_id}_{idx}")
        ])

    await state.update_data(edit_book_id=book_id, edit_folder_files=files, edit_current_folder=target_folder)
    buttons.append([InlineKeyboardButton(text="📂 Boshqa papkalarga qaytish", callback_data=f"edit_pdf_all_{book_id}")])

    await callback.answer()
    await callback.message.edit_text(
        f"📂 <b>[{folder_name}] papkasidagi fayllar:</b>\n\nBiriktirish uchun faylni tanlang:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

# PDF almashtirish: Tanlangan faylni saqlash
@dp.callback_query(F.data.startswith("edit_pick_file_"))
async def handle_edit_pick_file(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    book_id = int(parts[3])
    idx = int(parts[4])

    data = await state.get_data()
    files = data.get("edit_folder_files", [])
    current_folder = data.get("edit_current_folder", "")

    if idx >= len(files):
        await callback.answer("Fayl topilmadi.", show_alert=True)
        return

    selected_file = files[idx]
    file_path = os.path.join(current_folder, selected_file)
    rel_path = os.path.relpath(file_path, BASE_DIR).replace("\\", "/")

    await db.update_book(
        book_id,
        pdf_file_name=selected_file,
        file_path=rel_path,
        pdf_file_id=None # yangi lokal fayl bo'lgani uchun file_id ni tozalaymiz
    )
    await state.clear()
    await callback.answer(f"✅ Fayl yangilandi: {selected_file}", show_alert=True)
    await render_edit_book_card(
        callback, 
        book_id, 
        notice=f"🎉 Kitobga yangi fayl biriktirildi: <b>{selected_file}</b>"
    )

# Admin: Kitoblarni ko'rish, tahrirlash va o'chirish boshqaruvi
@dp.callback_query(F.data == "admin_manage_books")
async def handle_admin_manage_books(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    user = await db.get_or_create_user(user_id, callback.from_user.first_name, callback.from_user.username)
    if user_id != SUPER_ADMIN_ID and user["role"] != "ADMIN":
        await callback.answer("⛔️ Faqat administratorlar uchun!", show_alert=True)
        return

    books = await db.get_books()
    if not books:
        await callback.answer("Kutubxonada hozircha kitoblar yo'q.", show_alert=True)
        return

    text = (
        f"📚 <b>Kitoblarni boshqarish markazi ({len(books)} ta kitob):</b>\n\n"
        f"Kitob ma'lumotlarini tahrirlash uchun «✏️ Tahrir», butunlay o'chirish uchun «🗑» tugmasini bosing:\n"
    )
    buttons = []
    for b in books:
        buttons.append([
            InlineKeyboardButton(text=f"📖 {b['title'][:16]}", callback_data=f"book_{b['id']}"),
            InlineKeyboardButton(text="✏️ Tahrir", callback_data=f"edit_book_{b['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"del_book_{b['id']}")
        ])

    buttons.append([InlineKeyboardButton(text="➕ Yangi kitob qo'shish", callback_data="admin_add_book")])
    buttons.append([InlineKeyboardButton(text="🔙 Admin menyusiga qaytish", callback_data="back_to_admin")])
    await callback.answer()
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.message(AddBookStates.waiting_for_pdf)
async def admin_add_book_pdf_not_doc(message: Message):
    await message.answer("⚠️ Iltimos, yuqoridagi <b>«📁 PDF yuklash (Fayllar papkasi)»</b> tugmasini bosing yoki kitob faylini 📎 hujjat ko'rinishida yuboring:")

@dp.message(EditBookStates.waiting_for_pdf)
async def admin_edit_book_pdf_not_doc(message: Message):
    await message.answer("⚠️ Iltimos, yangi PDF kitob faylini 📎 hujjat shaklida yuboring yoki yuqoridagi papka tugmasidan tanlang:")

# ==========================================
# 📢 ADMIN BROADCAST
# ==========================================
@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastStates.waiting_for_message)
    await callback.answer()
    await callback.message.answer(
        "📢 <b>Barcha foydalanuvchilarga xabar jo'natish</b>\n\n"
        "Xabar matnini yozib yuboring (bu xabar barcha bot kitobxonlariga to'g'ridan-to'g'ri yetkaziladi):",
        parse_mode="HTML"
    )

@dp.message(BroadcastStates.waiting_for_message)
async def admin_broadcast_send(message: Message, state: FSMContext):
    await state.clear()
    text = message.text.strip()

    await db.create_broadcast("Admin E'loni", text, message.from_user.first_name or "Admin")
    users = await db.get_all_users()

    sent_count = 0
    for u in users:
        if u["id"] != message.from_user.id:
            try:
                await bot.send_message(
                    chat_id=u["id"],
                    text=f"📢 <b>Kitobxon Club E'loni:</b>\n\n{text}",
                    parse_mode="HTML"
                )
                sent_count += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass

    await message.answer(
        f"📢 <b>Xabar barcha kitobxonlarga yuborildi!</b>\n"
        f"Yetkazildi: <b>{sent_count} nafar a'zoga</b>.\n\n"
        f"Matn:\n<i>{text}</i>",
        parse_mode="HTML"
    )

# ==========================================
# MAIN RUNNER
# ==========================================
async def main():
    logging.info("Kitobxon Club Python Boti ishga tushirilmoqda...")
    await db.init_db()
    logging.info("Ma'lumotlar bazasi tayyor!")
    logging.info("Bot polling rejimida ishga tushdi (@kitobxonclub_bot)...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
