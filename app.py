import streamlit as st
import sqlite3
import os
from langchain_openai import ChatOpenAI

# 1. إعداد قاعدة بيانات الأنظمة والمواد المستوردة من الإكسل
DB_NAME = "regulations.db"
CHAT_DB = "chatbot_net.db"

def init_chat_db():
    """إنشاء قاعدة بيانات فرعية لحفظ محادثات المستخدمين وفصل الجلسات"""
    conn = sqlite3.connect(CHAT_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            sender TEXT,
            message TEXT
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

# تشغيل قاعدة بيانات الذاكرة فوراً
init_chat_db()

# 2. جلب مفتاح الـ API بأمان من إعدادات Secrets في Streamlit Cloud
if "OPENAI_API_KEY" in st.secrets:
    openai_api_key = st.secrets["OPENAI_API_KEY"]
else:
    openai_api_key = os.environ.get("OPENAI_API_KEY")

# 3. إعداد عقل الذكاء الاصطناعي
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=openai_api_key)

# 4. بناء واجهة المستخدم بـ Streamlit
st.set_page_config(page_title="AI Database Chatbot", layout="centered")
st.title("🤖 شات بوت الاستعلام من قاعدة البيانات")

# نظام تعدد المستخدمين
username = st.sidebar.text_input("الرجاء إدخل اسمك لتسجيل الدخول:", value="").strip()

if username:
    st.sidebar.success(f"مرحباً بك يا {username}!")

    # تحميل الذاكرة الخاصة باليوزر
    if f"chat_{username}" not in st.session_state:
        st.session_state[f"chat_{username}"] = load_messages(username)

    # عرض المحادثات السابقة
    for msg in st.session_state[f"chat_{username}"]:
        with st.chat_message(msg["sender"]):
            st.write(msg["message"])

    # استقبال الرسائل الجديدة
    if user_input := st.chat_input("اكتب سؤالك للاستعلام من اللوائح والأنظمة..."):
        # عرض رسالة اليوزر وحفظها
        with st.chat_message("user"):
            st.write(user_input)
        save_message(username, "user", user_input)
        st.session_state[f"chat_{username}"].append({"sender": "user", "message": user_input})

        # توليد رد الذكاء الاصطناعي المقيّد
        with st.chat_message("assistant"):
            with st.spinner("جاري البحث في قاعدة البيانات..."):
                rows = []
                db_context = "لا توجد بيانات مطابقة نهائياً في قاعدة البيانات."
                try:
                    # أ. الاتصال بقاعدة بيانات الإكسل والبحث عن الكلمات المفتاحية
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    
                    # قراءة أسماء الأعمدة الموجودة في الجدول لتجنب الأخطاء الإملائية
                    cursor.execute("PRAGMA table_info(legal_articles)")
                    columns_info = cursor.fetchall()
                    
                    if columns_info:
                        # بناء استعلام ديناميكي يبحث في كل الأعمدة النصية المتوفرة داخل الجدول
                        search_conditions = []
                        search_params = []
                        search_query = f"%{user_input}%"
                        
                        for col in columns_info:
                            col_name = col[1]
                            search_conditions.append(f'"{col_name}" LIKE ?')
                            search_params.append(search_query)
                        
                        # دمج الشروط بـ OR للبحث في كل مكان
                        where_clause = " OR ".join(search_conditions)
                        sql_statement = f"SELECT * FROM legal_articles WHERE {where_clause} LIMIT 3"
                        
                        cursor.execute(sql_statement, search_params)
                        rows = cursor.fetchall()
                    conn.close()
                    
                    # تجميع سياق البيانات المستخرجة بشكل مرن متوافق مع أي هيكلة
                    if rows:
                        db_context = ""
                        for row in rows:
                            # دمج بيانات الصف بالكامل مع فلترة القيم الفارغة بشكل صحيح بنظام بايثون
                            row_text = " | ".join([str(item) for item in row if item is not None])
                            db_context += f"\n- البيانات المستخرجة: {row_text}\n"
                    
                    # ب. صياغة التوجيه الصارم (System Prompt) لتقييد البوت
                    strict_prompt = f"""أنت مساعد ذكي ومهمتك هي الإجابة على أسئلة المستخدم بناءً على 'قاعدة البيانات الملحقة' فقط وحصرياً.

[قاعدة البيانات الملحقة]:
{db_context}

[شروط صارمة جداً]:
1. إذا كانت الإجابة على سؤال المستخدم موجودة في [قاعدة البيانات الملحقة]، صغ الإجابة بشكل واضح ومؤدب باللغة العربية مع ذكر تفاصيل المادة المرفقة.
2. إذا لم تكن الإجابة موجودة بشكل واضح، أو إذا سألك المستخدم عن أي معلومات عامة خارج نطاق النص الملحق، يجب عليك الرد بالعبارة التالية نصاً ودون أي زيادة: "عذراً، هذه المعلومة غير متوفرة في قاعدة البيانات لدي حالياً."
3. لا تخترع، لا تخمن، ولا تستخدم معلوماتك العامة السابقة أبداً تحت أي ظرف.

سؤال المستخدم: {user_input}
الإجابة:"""

                    # استدعاء النموذج
                    ai_response = llm.invoke(strict_prompt).content
                    
                except Exception as e:
                    # حل بديل في حال وجود مشكلة بالـ API: يعرض النص المستعلم مباشرة
                    if rows:
                        ai_response = f"⚠️ (تم العثور على المواد التالية في قاعدة البيانات):\n{db_context}"
                    else:
                        ai_response = "عذراً، هذه المعلومة غير متوفرة في قاعدة البيانات لدي حالياً."

                st.write(ai_response)

        # حفظ رد البوت في قاعدة البيانات والـ Session
        save_message(username, "assistant", ai_response)
        st.session_state[f"chat_{username}"].append({"sender": "assistant", "message": ai_response})
else:
    st.info("يرجى كتابة اسمك في القائمة الجانبية للبدء بالمحادثة.")
