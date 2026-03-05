import streamlit as st
from supabase import create_client

# --- 1. SETUP ---
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

if "user" not in st.session_state:
    st.session_state.user = None
if "auth_mode" not in st.session_state:
    st.session_state.auth_mode = "login"

# --- 2. AUTHENTICATION UI ---

if not st.session_state.user:
    st.title("🛡️ PerzChat")
    
    tabs = st.tabs(["Login", "Create Account"])
    
    # --- LOGIN TAB ---
    with tabs[0]:
        login_email = st.text_input("Email", key="l_email")
        login_pwd = st.text_input("Password", type="password", key="l_pwd")
        if st.button("Sign In", use_container_width=True):
            try:
                res = supabase.auth.sign_in_with_password({"email": login_email, "password": login_pwd})
                st.session_state.user = res.user
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")
        
        if st.button("Forgot Password?", type="tertiary"):
            # You can trigger the reset flow here
            supabase.auth.reset_password_for_email(login_email)
            st.info("If that email exists, a reset link was sent!")

    # --- REGISTRATION TAB ---
    with tabs[1]:
        st.info("Pick a username that your family will recognize!")
        new_email = st.text_input("Email", key="r_email")
        new_user = st.text_input("Choose Username", key="r_user")
        new_pwd = st.text_input("Password", type="password", key="r_pwd")

        invitation_code = st.text_input("Family Secret Code", type="password")

        if st.button("Register Account", use_container_width=True):
            if invitation_code != "YourSecretWord2026": # Change this!
                st.error("Incorrect Invitation Code. You cannot register.")
            else:
                try:
                    res = supabase.auth.sign_up({
                        "email": new_email, 
                        "password": new_pwd,
                        "options": {"data": {"display_name": new_user}}
                    })
                    st.success("Account created! Check your email if confirmation is required.")
                except Exception as e:
                    st.error(f"Registration failed: {e}")

# --- 3. CHAT INTERFACE (Private DM Mode) ---
else:
    meta = st.session_state.user.user_metadata
    my_username = meta.get("display_name", st.session_state.user.email)
    my_id = st.session_state.user.id

    # SIDEBAR: Contact List
    st.sidebar.title("📇 Contacts")
    
    # Fetch all registered users to build the contact list
    # (Note: In a huge app you'd filter this, but for family it's perfect)
    users_res = supabase.table("messages").select("username, user_id").execute()
    # Get unique users from the messages history or a dedicated users table
    all_users = {msg['username']: msg['user_id'] for msg in users_res.data if msg['user_id'] != my_id}
    
    contact_names = list(all_users.keys())
    selected_contact = st.sidebar.radio("Chat with:", ["Global Square"] + contact_names)

    if st.sidebar.button("Logout", type="tertiary"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

    st.title(f"💬 {selected_contact}")

    @st.fragment(run_every=5)
    def private_chat_window(target_name):
        if target_name == "Global Square":
            # Show messages where receiver_id is NULL
            res = supabase.table("messages").select("*").is_("receiver_id", "null").order("created_at", desc=True).limit(20).execute()
        else:
            target_id = all_users[target_name]
            # Fetch messages where (Me -> Them) OR (Them -> Me)
            res = supabase.table("messages").select("*").or_(
                f"and(user_id.eq.{my_id},receiver_id.eq.{target_id}),"
                f"and(user_id.eq.{target_id},receiver_id.eq.{my_id})"
            ).order("created_at", desc=True).limit(20).execute()
            
        for m in reversed(res.data):
            is_me = m['user_id'] == my_id
            with st.chat_message("user" if is_me else "assistant"):
                st.write(f"**{m['username']}**: {m['content']}")

    private_chat_window(selected_contact)

    if prompt := st.chat_input(f"Message {selected_contact}..."):
        payload = {
            "user_id": my_id,
            "username": my_username,
            "content": prompt,
            "receiver_id": all_users[selected_contact] if selected_contact != "Global Square" else None
        }
        supabase.table("messages").insert(payload).execute()
        st.rerun()
    
    