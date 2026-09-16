import aiosqlite
import os
import re
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "kitobxon.db")
def get_super_admin_ids() -> List[int]:
    raw = os.getenv("ADMIN_ID", "6956456422,906787629")
    ids = []
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if item.isdigit():
            ids.append(int(item))
    for default_id in [6956456422, 906787629]:
        if default_id not in ids:
            ids.append(default_id)
    return ids

SUPER_ADMIN_IDS = get_super_admin_ids()
SUPER_ADMIN_ID = SUPER_ADMIN_IDS[0]

async def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON;")

        # Foydalanuvchilar
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT,
            role TEXT DEFAULT 'USER',
            points INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            streak_days INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Janrlar / Kategoriyalar
        await db.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT
        );
        """)

        # Kitoblar (PDF fayli bilan)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            category_id INTEGER,
            description TEXT,
            pdf_file_id TEXT,
            pdf_file_name TEXT,
            file_path TEXT,
            cover_url TEXT,
            pages INTEGER DEFAULT 150,
            read_count INTEGER DEFAULT 0,
            rating REAL DEFAULT 5.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL
        );
        """)
        try:
            await db.execute("ALTER TABLE books ADD COLUMN file_path TEXT;")
        except Exception:
            pass

        # Mutolaa tarixi
        await db.execute("""
        CREATE TABLE IF NOT EXISTS reading_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            book_id INTEGER NOT NULL,
            status TEXT DEFAULT 'READING',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE,
            UNIQUE(user_id, book_id)
        );
        """)

        # Tanlovlar
        await db.execute("""
        CREATE TABLE IF NOT EXISTS contests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            reward_points INTEGER DEFAULT 500,
            participants_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Xabarlar / Broadcasts
        await db.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content TEXT NOT NULL,
            sender_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Tizim sozlamalari (Masalan: Tanlovlarga qulf)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)
        await db.execute("""
        INSERT OR IGNORE INTO settings (key, value) VALUES ('contests_locked', '1');
        """)

        # Super Adminlarni yaratish / tasdiqlash
        for sa_id in SUPER_ADMIN_IDS:
            await db.execute("""
            INSERT INTO users (id, name, role, points, level, streak_days)
            VALUES (?, 'Super Admin', 'ADMIN', 1000, 5, 1)
            ON CONFLICT(id) DO UPDATE SET role = 'ADMIN';
            """, (sa_id,))

        # Boshlang'ich janrlarni kiritish
        default_categories = [
            ("Drama va Teatr", "drama", "Dramatik asarlar, fojia va teatr pyesalari"),
            ("Detektiv va Sarguzasht", "detektiv", "Sirli jinoyatlar, mantiqiy qidiruvlar va triller"),
            ("O'zbek adabiyoti", "ozbek-adabiyoti", "Mumtoz va zamonaviy o'zbek adabiyoti durdonalari"),
            ("Jahon adabiyoti", "jahon-adabiyoti", "Dunyo klassik va zamonaviy asarlari"),
            ("Biznes va Moliya", "biznes-va-moliya", "Biznes, yetakchilik, marketing va investitsiya"),
            ("Psixologiya va Rivojlanish", "psixologiya-rivojlanish", "Shaxsiy rivojlanish, motivatsiya va odatlar"),
            ("Ilmiy-Ommabop", "ilmiy-ommabop", "Texnologiya, tarix va koinot sirlari")
        ]

        for name, slug, desc in default_categories:
            cursor = await db.execute("SELECT id FROM categories WHERE name = ? OR slug = ?;", (name, slug))
            existing = await cursor.fetchone()
            if not existing:
                try:
                    await db.execute("""
                    INSERT INTO categories (name, slug, description)
                    VALUES (?, ?, ?);
                    """, (name, slug, desc))
                except Exception:
                    pass
        await db.commit()

# === FOYDALANUVCHILAR ===
async def get_or_create_user(user_id: int, name: str, username: Optional[str] = None) -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
        user = await cursor.fetchone()

        is_super = (user_id in SUPER_ADMIN_IDS)
        role = "ADMIN" if is_super else "USER"

        if not user:
            await db.execute("""
            INSERT INTO users (id, name, username, role, points, level, streak_days)
            VALUES (?, ?, ?, ?, 0, 1, 1);
            """, (user_id, name, username, role))
            await db.commit()
            cursor = await db.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
            user = await cursor.fetchone()
        elif is_super and user["role"] != "ADMIN":
            await db.execute("UPDATE users SET role = 'ADMIN' WHERE id = ?;", (user_id,))
            await db.commit()
            cursor = await db.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
            user = await cursor.fetchone()

        return dict(user)

async def get_all_users() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users ORDER BY points DESC, created_at ASC;")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def update_user_role(user_id: int, role: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET role = ? WHERE id = ?;", (role, user_id))
        await db.commit()
        return True

async def set_user_role_by_id(user_id: int, role: str, name: Optional[str] = None) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM users WHERE id = ?;", (user_id,))
        existing = await cursor.fetchone()
        if existing:
            await db.execute("UPDATE users SET role = ? WHERE id = ?;", (role, user_id))
        else:
            display_name = name or f"Foydalanuvchi_{user_id}"
            await db.execute("""
            INSERT INTO users (id, name, role, points, level, streak_days)
            VALUES (?, ?, ?, 0, 1, 1);
            """, (user_id, display_name, role))
        await db.commit()
        return True

async def add_user_points(user_id: int, points: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        UPDATE users 
        SET points = points + ?, 
            level = MAX(1, (points + ?) / 200 + 1)
        WHERE id = ?;
        """, (points, points, user_id))
        await db.commit()

# === KATEGORIYALAR ===
def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or "toifa"

async def get_categories() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM categories ORDER BY id ASC;")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def get_categories_with_count() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
        SELECT c.*, COUNT(b.id) as book_count
        FROM categories c
        LEFT JOIN books b ON b.category_id = c.id
        GROUP BY c.id
        ORDER BY c.id ASC;
        """)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def get_category_by_id(cat_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM categories WHERE id = ?;", (cat_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def add_category(name: str, description: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        base_slug = slugify(name)
        slug = base_slug
        counter = 1
        while True:
            cursor = await db.execute("SELECT id FROM categories WHERE slug = ?;", (slug,))
            if not await cursor.fetchone():
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

        cursor = await db.execute("""
        INSERT INTO categories (name, slug, description)
        VALUES (?, ?, ?);
        """, (name.strip(), slug, description.strip() if description else f"{name} janridagi sara asarlar"))
        await db.commit()
        return cursor.lastrowid

async def update_category(cat_id: int, name: Optional[str] = None, description: Optional[str] = None) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        fields = []
        params = []
        if name is not None:
            clean_name = name.strip()
            fields.append("name = ?")
            params.append(clean_name)
            # slugni ham yangilaymiz
            base_slug = slugify(clean_name)
            slug = base_slug
            counter = 1
            while True:
                cursor = await db.execute("SELECT id FROM categories WHERE slug = ? AND id != ?;", (slug, cat_id))
                if not await cursor.fetchone():
                    break
                slug = f"{base_slug}-{counter}"
                counter += 1
            fields.append("slug = ?")
            params.append(slug)
        if description is not None:
            fields.append("description = ?")
            params.append(description.strip())

        if not fields:
            return False

        params.append(cat_id)
        sql = f"UPDATE categories SET {', '.join(fields)} WHERE id = ?;"
        await db.execute(sql, params)
        await db.commit()
        return True

async def delete_category(cat_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM categories WHERE id = ?;", (cat_id,))
        await db.commit()
        return True

# === KITOBLAR ===
async def get_books(category_id: Optional[int] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT b.*, c.name as category_name FROM books b LEFT JOIN categories c ON b.category_id = c.id WHERE 1=1"
        params = []

        if category_id:
            query += " AND b.category_id = ?"
            params.append(category_id)

        if search:
            query += " AND (LOWER(b.title) LIKE ? OR LOWER(b.author) LIKE ? OR LOWER(b.description) LIKE ?)"
            term = f"%{search.lower()}%"
            params.extend([term, term, term])

        query += " ORDER BY b.id DESC;"
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def get_book_by_id(book_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
        SELECT b.*, c.name as category_name 
        FROM books b 
        LEFT JOIN categories c ON b.category_id = c.id 
        WHERE b.id = ?;
        """, (book_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def add_book(
    title: str,
    author: str,
    category_id: int,
    pdf_file_id: Optional[str] = None,
    pdf_file_name: str = "kitob.pdf",
    description: str = "",
    file_path: Optional[str] = None
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        default_cover = "https://images.unsplash.com/photo-1544947950-fa07a98d237f?q=80&w=600&auto=format&fit=crop"
        cursor = await db.execute("""
        INSERT INTO books (title, author, category_id, pdf_file_id, pdf_file_name, description, file_path, cover_url, pages, rating)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 200, 5.0);
        """, (title, author, category_id, pdf_file_id, pdf_file_name, description, file_path, default_cover))
        await db.commit()
        return cursor.lastrowid

async def update_book(book_id: int, **kwargs) -> bool:
    allowed_fields = {
        "title", "author", "category_id", "description", "pages", 
        "rating", "cover_url", "pdf_file_id", "pdf_file_name", "file_path"
    }
    fields = []
    params = []
    for key, value in kwargs.items():
        if key in allowed_fields and value is not None:
            fields.append(f"{key} = ?")
            params.append(value)

    if not fields:
        return False

    params.append(book_id)
    sql = f"UPDATE books SET {', '.join(fields)} WHERE id = ?;"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(sql, params)
        await db.commit()
        return True

async def update_book_file_id(book_id: int, pdf_file_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE books SET pdf_file_id = ? WHERE id = ?;", (pdf_file_id, book_id))
        await db.commit()

async def delete_book(book_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM books WHERE id = ?;", (book_id,))
        await db.commit()
        return True

async def increment_book_read(book_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE books SET read_count = read_count + 1 WHERE id = ?;", (book_id,))
        await db.execute("""
        INSERT INTO reading_history (user_id, book_id, status)
        VALUES (?, ?, 'COMPLETED')
        ON CONFLICT(user_id, book_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP;
        """, (user_id, book_id))
        await db.commit()

# === MUTOLAA TARIXI ===
async def get_user_reading_history(user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
        SELECT b.*, rh.status, rh.updated_at as read_date
        FROM reading_history rh
        JOIN books b ON rh.book_id = b.id
        WHERE rh.user_id = ?
        ORDER BY rh.updated_at DESC;
        """, (user_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

# === TANLOVLAR ===
async def get_contests() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM contests ORDER BY id DESC;")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def join_contest(contest_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE contests SET participants_count = participants_count + 1 WHERE id = ?;", (contest_id,))
        await db.commit()

# === BROADCASTS ===
async def create_broadcast(title: str, content: str, sender_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO broadcasts (title, content, sender_name)
        VALUES (?, ?, ?);
        """, (title, content, sender_name))
        await db.commit()

# === SOZLAMALAR (SETTINGS) ===
async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = ?;", (key,))
        row = await cursor.fetchone()
        return row[0] if row else default

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value;
        """, (key, value))
        await db.commit()

async def is_contests_locked() -> bool:
    val = await get_setting("contests_locked", "1")
    return val == "1"

async def toggle_contests_lock() -> bool:
    current = await is_contests_locked()
    new_val = "0" if current else "1"
    await set_setting("contests_locked", new_val)
    return new_val == "1"

# === STATISTIKA ===
async def get_bot_statistics() -> Dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        # Jami foydalanuvchilar
        cursor = await db.execute("SELECT COUNT(*) FROM users;")
        total_users = (await cursor.fetchone())[0]

        # Bugun qo'shilganlar
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now');")
        today_users = (await cursor.fetchone())[0]

        # Adminlar soni
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE role = 'ADMIN';")
        total_admins = (await cursor.fetchone())[0]

        # Jami kitoblar soni
        cursor = await db.execute("SELECT COUNT(*) FROM books;")
        total_books = (await cursor.fetchone())[0]

        # PDF biriktirilgan kitoblar soni
        cursor = await db.execute("SELECT COUNT(*) FROM books WHERE pdf_file_id IS NOT NULL OR file_path IS NOT NULL;")
        books_with_pdf = (await cursor.fetchone())[0]

        # Janrlar soni
        cursor = await db.execute("SELECT COUNT(*) FROM categories;")
        total_categories = (await cursor.fetchone())[0]

        # Jami mutolaalar / o'qilishlar soni
        cursor = await db.execute("SELECT COALESCE(SUM(read_count), 0) FROM books;")
        row = await cursor.fetchone()
        total_reads = row[0] if row else 0

        # Eng ko'p o'qilgan 3 ta kitob
        cursor = await db.execute("SELECT title, author, read_count FROM books ORDER BY read_count DESC LIMIT 3;")
        top_books = await cursor.fetchall()

        return {
            "total_users": total_users,
            "today_users": today_users,
            "total_admins": total_admins,
            "total_books": total_books,
            "books_with_pdf": books_with_pdf,
            "total_categories": total_categories,
            "total_reads": total_reads,
            "top_books": [{"title": b[0], "author": b[1], "read_count": b[2]} for b in top_books]
        }

