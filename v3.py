import streamlit as st
from supabase import create_client
import time

# --- CONFIG ---
st.set_page_config(page_title="PerzChat", page_icon="🛡️")

# Connect to Supabase
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

# Initialize Session States
if "user" not in st.session_state:
    st.session_state.user = None

# --- AUTHENTICATION UI ---
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
        st.info("Ask the admin for the Secret Code to join.")
        r_email = st.text_input("Email", key="r_email")
        r_user = st.text_input("Choose Username", key="r_user")
        r_pwd = st.text_input("Password", type="password", key="r_pwd")
        r_code = st.text_input("Secret Invitation Code", type="password")
        
        if st.button("Register", use_container_width=True):
            if r_code != "Family2026": # CHANGE THIS SECRET CODE
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

# --- AUTHENTICATED CHAT INTERFACE ---
else:
    my_id = st.session_state.user.id
    
    # 1. Update Last Seen & Get Username
    try:
        supabase.table("profiles").update({"last_seen": "now()"}).eq("id", my_id).execute()
        my_profile = supabase.table("profiles").select("username").eq("id", my_id).maybe_single().execute()
        my_username = my_profile.data['username'] if my_profile.data else "User"
    except:
        my_username = "User"

    # 2. Sidebar / Contact List
    st.sidebar.title("📇 Contacts")
    
    users_res = supabase.table("profiles").select("id, username, last_seen").execute()
    # Filter and sort by last active
    all_users = sorted(users_res.data, key=lambda x: x['last_seen'] or "", reverse=True)
    contacts = {u['username']: u['id'] for u in all_users if u['id'] != my_id}

    if not contacts:
        st.sidebar.info("Waiting for others to join...")
        selected_name = None
    else:
        selected_name = st.sidebar.radio("Chat with:", list(contacts.keys()))
        target_data = next(u for u in all_users if u['username'] == selected_name)
        st.sidebar.caption(f"Last active: {target_data['last_seen'][:16].replace('T', ' ')}")

    if st.sidebar.button("Logout", type="tertiary"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

    # 3. Main Chat Area
    if selected_name:
        st.title(f"💬 {selected_name}")
        target_id = contacts[selected_name]

        @st.fragment(run_every=4)
        def chat_window():
            # Fetch private messages between Me and Selected Contact
            res = supabase.table("messages").select("*").or_(
                f"and(user_id.eq.{my_id},receiver_id.eq.{target_id}),"
                f"and(user_id.eq.{target_id},receiver_id.eq.{my_id})"
            ).order("created_at", desc=True).limit(30).execute()
            
            if not res.data:
                st.caption("No messages yet. Start the conversation!")
            
            for m in reversed(res.data):
                is_me = m['user_id'] == my_id
                with st.chat_message("user" if is_me else "assistant"):
                    st.write(f"**{m['username']}**: {m['content']}")

        chat_window()

        # 4. Sending Messages
        if prompt := st.chat_input(f"Message {selected_name}..."):
            try:
                supabase.table("messages").insert({
                    "user_id": my_id,
                    "receiver_id": target_id,
                    "username": my_username,
                    "content": prompt
                }).execute()
                st.rerun()
            except Exception as e:
                st.error(f"Message failed: {e}")
    else:
        st.title("Welcome to PerzChat")
        st.info("Pick a family member from the sidebar to start a private chat.")