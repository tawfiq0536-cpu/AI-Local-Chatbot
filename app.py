import streamlit as st
import sqlite3
import os
from langchain_openai import ChatOpenAI

# 1. إعداد مفتاح OpenAI (استبدله بمفتاحك الخاص أو وضعه في البيئة)
# يمكنك الحصول عليه من منصة OpenAI
os.environ["OPENAI_API_KEY"] = "ضع_مفتاح_الـ_API_الخاص_بـ_OpenAI_هنا"

# 2. إعداد قاعدة البيانات المحلية (تخزين الذاكرة لكل يوزر)
DB_NAME = "chatbot_net.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # جدول لحفظ رسائل كل يوزر بناءً على اسمه
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
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_history (username, sender, message) VALUES (?, ?, ?)", (username, sender, message))
    conn.commit()
    conn.close()


def load_messages(username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT sender, message FROM chat_history WHERE username = ? ORDER BY id ASC", (username,))
    rows = cursor.fetchall()
    conn.close()
    return [{"sender": row[0], "message": row[1]} for row in rows]


# تشغيل دالة إنشاء قاعدة البيانات فوراً
init_db()

# 3. إعداد عقل الذكاء الاصطناعي
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)

# 4. بناء واجهة المستخدم بـ Streamlit
st.set_page_config(page_title="AI Local Chatbot", layout="centered")
st.title("🤖 شات بوت الذكاء الاصطناعي للشبكة المحلية")

# نظام تعدد المستخدمين (كل شخص يدخل يكتب اسمه لتفصل محادثته)
username = st.sidebar.text_input("الرجاء إدخال اسمك لتسجيل الدخول:", value="").strip()

if username:
    st.sidebar.success(f"مرحباً بك يا {username}!")

    # تحميل تاريخ محادثات هذا اليوزر من قاعدة البيانات
    if f"chat_{username}" not in st.session_state:
        st.session_state[f"chat_{username}"] = load_messages(username)

    # عرض المحادثات السابقة لليوزر الحالي
    for msg in st.session_state[f"chat_{username}"]:
        with st.chat_message(msg["sender"]):
            st.write(msg["message"])

    # استقبال الرسائل الجديدة
    if user_input := st.chat_input("اكتب رسالتك هنا..."):
        # 1. عرض رسالة اليوزر وحفظها
        with st.chat_message("user"):
            st.write(user_input)
        save_message(username, "user", user_input)
        st.session_state[f"chat_{username}"].append({"sender": "user", "message": user_input})

        # 2. توليد رد الذكاء الاصطناعي
        with st.chat_message("assistant"):
            with st.spinner("جاري التفكير..."):
                try:
                    # نمرر المحادثة السابقة لتكون للبوت "ذاكرة"
                    history_context = "\n".join(
                        [f"{m['sender']}: {m['message']}" for m in st.session_state[f"chat_{username}"][-5:]])
                    prompt = f"سياق المحادثة الأخيرة:\n{history_context}\n\nالمستخدم {username} يقول الآن: {user_input}\nرد عليه باللغة العربية بشكل ذكي ومناسب."

                    ai_response = llm.invoke(prompt).content
                except Exception as e:
                    ai_response = "حدث خطأ أثناء الاتصال بالذكاء الاصطناعي، يرجى التحقق من مفتاح الـ API."

                st.write(ai_response)

        # 3. حفظ رد البوت في قاعدة البيانات والـ Session
        save_message(username, "assistant", ai_response)
        st.session_state[f"chat_{username}"].append({"sender": "assistant", "message": ai_response})
else:
    st.info("يرجى كتابة اسمك في القائمة الجانبية للبدء بالمحادثة.")