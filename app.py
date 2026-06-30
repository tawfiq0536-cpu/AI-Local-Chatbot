import streamlit as st
import sqlite3
import os
from langchain_openai import ChatOpenAI

# 1. إعداد قاعدة البيانات
DB_NAME = "regulations.db"
CHAT_DB = "chatbot_net.db"


def init_chat_db():
    conn = sqlite3.connect(CHAT_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, sender TEXT, message TEXT
        )
    ''')
    conn.commit()
    conn.close()


def save_message(username, sender, message):
    conn = sqlite3.connect(CHAT_DB)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_history (username, sender, message) VALUES (?, ?, ?)", (username, sender, message))
    conn.commit()
    conn.close()


def load_messages(username):
    conn = sqlite3.connect(CHAT_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT sender, message FROM chat_history WHERE username = ? ORDER BY id ASC", (username,))
    rows = cursor.fetchall()
    conn.close()
    return [{"sender": row[0], "message": row[1]} for row in rows]


init_chat_db()


# دالة دمج الملفات مع حفظ اسم الملف كـ "قسم"
def merge_all_excel_files():
    import pandas as pd
    current_dir = os.getcwd()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS legal_articles")
    conn.commit()

    success_count = 0
    for file_name in os.listdir(current_dir):
        if (file_name.endswith('.csv') or file_name.endswith('.xlsx')) and not file_name.startswith('~$'):
            try:
                if file_name.endswith('.csv'):
                    df = pd.read_csv(file_name, encoding='utf-8')
                else:
                    df = pd.read_excel(file_name)

                df.columns = df.columns.str.strip()

                # إخراج اسم القسم من اسم الملف (بدون الامتداد .xlsx أو .csv)
                section_name = os.path.splitext(file_name)[0].replace(".xlsx", "").replace(" - ورقة1", "")

                # إضافة عمود جديد يحتوي على اسم الملف كـ "قسم" لكل الصفوف
                df["اسم القسم"] = section_name

                df.to_sql(name="legal_articles", con=conn, if_exists="append", index=False)
                success_count += 1
            except Exception as e:
                pass
    conn.close()
    return success_count


# تشغيل الدمج تلقائياً عند بدء التطبيق محلياً لتحديث الداتابيز
if not os.path.exists(DB_NAME):
    merge_all_excel_files()

# 2. إعداد عقل الذكاء الاصطناعي
if "OPENAI_API_KEY" in st.secrets:
    openai_api_key = st.secrets["OPENAI_API_KEY"]
else:
    openai_api_key = os.environ.get("OPENAI_API_KEY")

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=openai_api_key)

# 3. بناء الواجهة
st.set_page_config(page_title="AI Database Chatbot", layout="centered")
st.title("🤖 شات بوت الاستعلام من الأقسام واللوائح")

username = st.sidebar.text_input("الرجاء إدخال اسمك لتسجيل الدخول:", value="").strip()

# زر مخصص في القائمة الجانبية لإعادة دمج الملفات إذا أضفت ملفاً جديداً مستقبلاً
if st.sidebar.button("تحديث ودمج الملفات الجديدة"):
    count = merge_all_excel_files()
    st.sidebar.success(f"تم تحديث ودمج {count} ملفات بنجاح!")

if username:
    st.sidebar.success(f"مرحباً بك يا {username}")

    if f"chat_{username}" not in st.session_state:
        st.session_state[f"chat_{username}"] = load_messages(username)

    for msg in st.session_state[f"chat_{username}"]:
        with st.chat_message(msg["sender"]):
            st.write(msg["message"])

    if user_input := st.chat_input("اكتب سؤالك هنا..."):
        with st.chat_message("user"):
            st.write(user_input)
        save_message(username, "user", user_input)
        st.session_state[f"chat_{username}"].append({"sender": "user", "message": user_input})

        with st.chat_message("assistant"):
            with st.spinner("جاري البحث في الأقسام واللوائح..."):
                rows = []
                db_context = "لا توجد بيانات مطابقة."
                try:
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()

                    search_query = f"%{user_input}%"
                    # البحث في نص المادة أو رقم المادة
                    cursor.execute(
                        'SELECT "اسم القسم", "رقم المادة", "نص المادة" FROM legal_articles WHERE "نص المادة" LIKE ? OR "رقم المادة" LIKE ? LIMIT 3',
                        (search_query, search_query))
                    rows = cursor.fetchall()
                    conn.close()

                    if rows:
                        db_context = ""
                        for row in rows:
                            db_context += f"\n- [القسم/الملف]: {row[0]} | المادة: {row[1]} | النص: {row[2]}\n"

                    strict_prompt = f"""أنت مساعد ذكي ومهمتك الإجابة بناءً على 'قاعدة البيانات الملحقة' فقط وحصرياً.
يجب عليك ذكر اسم [القسم/الملف] ورقم المادة بوضوح في بداية إجابتك ليعرف المستخدم مصدر المعلومة.

[قاعدة البيانات الملحقة]:
{db_context}

سؤال المستخدم: {user_input}
الإجابة:"""

                    ai_response = llm.invoke(strict_prompt).content

                except Exception as e:
                    if rows:
                        ai_response = f"⚠️ (تم العثور على المواد التالية):\n{db_context}"
                    else:
                        ai_response = "عذراً، هذه المعلومة غير متوفرة في قاعدة البيانات لدي حالياً."

                st.write(ai_response)

        save_message(username, "assistant", ai_response)
        st.session_state[f"chat_{username}"].append({"sender": "assistant", "message": ai_response})
else:
    st.info("يرجى كتابة اسمك في القائمة الجانبية للبدء.")
