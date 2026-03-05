import streamlit as st
from supabase import create_client
import time

# --- 1. CONFIG & CONNECTION ---
st.set_page_config(page_title="PerzChat Pro", page_icon="🛡️", layout="wide")

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

if "user" not in st.session_state:
    st.session_state.user = None

# --- 2. AUTHENTICATION UI ---
if not st.session_state.user:
    st.title("🛡️ PerzChat")
    tabs = st.tabs(["Login", "Create Account"])
    
    with tabs[0]:
        l_email = st.text_input("Email", key="l_email")
        l_pwd = st.text_input("Password", type="password", key="l_pwd")
        if st.button("Sign In", type="primary", use_container_width=True):
            try:
                res = supabase.auth.sign_in_with_password({"email": l_email, "password": l_pwd})
                st.session_state.user = res.user
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    with tabs[1]:
        st.info("Enter the family secret code to register.")
        r_email = st.text_input("Email", key="r_email")
        r_user = st.text_input("Choose Username", key="r_user")
        r_pwd = st.text_input("Password", type="password", key="r_pwd")
        r_code = st.text_input("Secret Code", type="password")
        
        if st.button("Register", use_container_width=True):
            if r_code != "Family2026": # CHANGE THIS
                st.error("Invalid Secret Code.")
            else:
                try:
                    supabase.auth.sign_up({
                        "email": r_email, 
                        "password": r_pwd,
                        "options": {"data": {"display_name": r_user}}
                    })
                    st.success("Account created! You can now log in.")
                except Exception as e:
                    st.error(f"Registration failed: {e}")

# --- 3. AUTHENTICATED INTERFACE ---
else:
    my_id = st.session_state.user.id
    
    # Update Last Seen & Get Username
    try:
        supabase.table("profiles").update({"last_seen": "now()"}).eq("id", my_id).execute()
        my_prof = supabase.table("profiles").select("username").eq("id", my_id).maybe_single().execute()
        my_username = my_prof.data['username'] if my_prof.data else "User"
    except:
        my_username = "User"

    # SIDEBAR: Contacts
    st.sidebar.title("📇 Contacts")
    users_res = supabase.table("profiles").select("id, username, last_seen").execute()
    all_users = sorted(users_res.data, key=lambda x: x['last_seen'] or "", reverse=True)
    contacts = {u['username']: u['id'] for u in all_users if u['id'] != my_id}

    if not contacts:
        st.sidebar.info("No other users yet.")
        selected_name = None
    else:
        selected_name = st.sidebar.radio("Select Chat:", list(contacts.keys()))
        target_data = next(u for u in all_users if u['username'] == selected_name)
        st.sidebar.caption(f"Active: {target_data['last_seen'][:16].replace('T', ' ')}")

    if st.sidebar.button("Logout", type="tertiary"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

    # MAIN CHAT
    if selected_name:
        st.title(f"💬 {selected_name}")
        target_id = contacts[selected_name]

        # AUTO-MARK AS READ: Mark messages sent TO me BY this user as read
        supabase.table("messages").update({"is_read": True}).eq("user_id", target_id).eq("receiver_id", my_id).eq("is_read", False).execute()

        @st.fragment(run_every=4)
        def chat_window():
            res = supabase.table("messages").select("*").or_(
                f"and(user_id.eq.{my_id},receiver_id.eq.{target_id}),"
                f"and(user_id.eq.{target_id},receiver_id.eq.{my_id})"
            ).order("created_at", desc=True).limit(40).execute()
            
            for m in reversed(res.data):
                is_me = m['user_id'] == my_id
                # Seen indicator logic
                status = ""
                if is_me:
                    status = " ✓✓" if m.get('is_read') else " ✓"
                
                with st.chat_message("user" if is_me else "assistant"):
                    st.write(f"**{m['username']}**: {m['content']}")
                    st.caption(f"{m['created_at'][11:16]}{status}")

        chat_window()

        if prompt := st.chat_input(f"Message {selected_name}..."):
            supabase.table("messages").insert({
                "user_id": my_id,
                "receiver_id": target_id,
                "username": my_username,
                "content": prompt
            }).execute()
            st.rerun()
    else:
        st.title("Welcome to PerzChat")
        st.info("Pick someone to chat with!")