from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any, Optional

def get_main_menu(is_admin: bool = False, contests_locked: bool = True) -> ReplyKeyboardMarkup:
    contest_btn = "🔒 Tanlovlar" if contests_locked else "🏆 Tanlovlar"
    buttons = [
        [KeyboardButton(text="📚 Kutubxona"), KeyboardButton(text="📖 O'qigan kitoblar")],
        [KeyboardButton(text=contest_btn), KeyboardButton(text="⭐️ Ballar")],
        [KeyboardButton(text="📊 Reyting"), KeyboardButton(text="🤖 AI Maslahatchi")],
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="⚙️ Admin Panel")])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        persistent=True
    )

def get_categories_keyboard(categories: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    inline_keyboard = []
    for cat in categories:
        inline_keyboard.append([
            InlineKeyboardButton(text=f"📂 {cat['name']}", callback_data=f"cat_{cat['id']}")
        ])
    inline_keyboard.append([
        InlineKeyboardButton(text="🔍 Barcha kitoblar", callback_data="all_books")
    ])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def get_books_keyboard(books: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    inline_keyboard = []
    for b in books:
        inline_keyboard.append([
            InlineKeyboardButton(text=f"📖 {b['title']} — {b['author']}", callback_data=f"book_{b['id']}")
        ])
    inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Janrlarga qaytish", callback_data="back_to_categories")
    ])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def get_book_details_keyboard(book_id: int, is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📥 Kitobni o'qish (PDF yuklab olish)", callback_data=f"get_pdf_{book_id}")],
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton(text="✏️ Kitobni tahrirlash (Admin)", callback_data=f"edit_book_{book_id}"),
            InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_book_{book_id}")
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Kutubxonaga qaytish", callback_data="all_books")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_edit_book_keyboard(book_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✏️ Nomi", callback_data=f"edit_bfield_{book_id}_title"),
            InlineKeyboardButton(text="✍️ Muallifi", callback_data=f"edit_bfield_{book_id}_author")
        ],
        [
            InlineKeyboardButton(text="📂 Janri (Toifasi)", callback_data=f"edit_bfield_{book_id}_category"),
            InlineKeyboardButton(text="🔢 Sahifalar soni", callback_data=f"edit_bfield_{book_id}_pages")
        ],
        [
            InlineKeyboardButton(text="📑 Tavsifi (Izohi)", callback_data=f"edit_bfield_{book_id}_description")
        ],
        [
            InlineKeyboardButton(text="🖼 Muqova rasmini o'zgartirish", callback_data=f"edit_bfield_{book_id}_cover"),
            InlineKeyboardButton(text="📄 PDF faylni yangilash", callback_data=f"edit_bfield_{book_id}_pdf")
        ],
        [
            InlineKeyboardButton(text="🗑 Kitobni butunlay o'chirish", callback_data=f"del_book_{book_id}")
        ],
        [
            InlineKeyboardButton(text="🔙 Kitob kartasiga qaytish", callback_data=f"book_{book_id}"),
            InlineKeyboardButton(text="📚 Kitoblar ro'yxatiga", callback_data="admin_manage_books")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_menu_keyboard(is_super_admin: bool = False, contests_locked: bool = True) -> InlineKeyboardMarkup:
    lock_text = "🔒 Tanlovlar: Qulflangan (Ochish)" if contests_locked else "🔓 Tanlovlar: Ochiq (Qulflash)"
    buttons = [
        [InlineKeyboardButton(text="📊 Bot statistikasi (Jonli hisobot)", callback_data="admin_stats")],
        [InlineKeyboardButton(text="➕ Yangi kitob qo'shish (PDF yuklash)", callback_data="admin_add_book")],
        [InlineKeyboardButton(text="📚 Kitoblarni boshqarish (Tahrirlash & O'chirish)", callback_data="admin_manage_books")],
        [InlineKeyboardButton(text="📂 Toifalar (Janrlar) boshqaruvi", callback_data="admin_categories")],
        [InlineKeyboardButton(text=lock_text, callback_data="admin_toggle_contests_lock")],
    ]
    if is_super_admin:
        buttons.append([InlineKeyboardButton(text="👑 Admin qo'shish / chiqarish (Super Admin)", callback_data="admin_users")])
    buttons.append([InlineKeyboardButton(text="📢 Barcha kitobxonlarga xabar jo'natish", callback_data="admin_broadcast")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_genre_choice_keyboard(
    categories: List[Dict[str, Any]], 
    for_book_wizard: bool = True,
    prefix: str = "genre_sel_",
    cancel_callback: str = "back_to_admin"
) -> InlineKeyboardMarkup:
    inline_keyboard = []
    for cat in categories:
        inline_keyboard.append([
            InlineKeyboardButton(text=f"📂 {cat['name']}", callback_data=f"{prefix}{cat['id']}")
        ])
    if for_book_wizard:
        inline_keyboard.append([
            InlineKeyboardButton(text="➕ Yangi toifa (janr) yaratish", callback_data="add_category_wizard")
        ])
    inline_keyboard.append([
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data=cancel_callback)
    ])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def get_categories_manage_keyboard(categories: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    inline_keyboard = []
    for cat in categories:
        count = cat.get("book_count", 0)
        inline_keyboard.append([
            InlineKeyboardButton(text=f"📂 {cat['name']} ({count} ta)", callback_data=f"cat_info_{cat['id']}"),
            InlineKeyboardButton(text="✏️ Tahrir", callback_data=f"edit_cat_{cat['id']}"),
            InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_cat_{cat['id']}")
        ])
    inline_keyboard.append([
        InlineKeyboardButton(text="➕ Yangi toifa qo'shish", callback_data="admin_add_new_cat")
    ])
    inline_keyboard.append([
        InlineKeyboardButton(text="🔙 Admin menyusiga qaytish", callback_data="back_to_admin")
    ])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def get_edit_category_keyboard(cat_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="✏️ Toifa nomini o'zgartirish", callback_data=f"edit_cfield_{cat_id}_name")
        ],
        [
            InlineKeyboardButton(text="📝 Tavsifini o'zgartirish", callback_data=f"edit_cfield_{cat_id}_desc")
        ],
        [
            InlineKeyboardButton(text="🗑 Ushbu toifani o'chirish", callback_data=f"del_cat_{cat_id}")
        ],
        [
            InlineKeyboardButton(text="🔙 Toifalar ro'yxatiga qaytish", callback_data="admin_categories")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
