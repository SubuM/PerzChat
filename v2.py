import streamlit as st
from supabase import create_client

# --- 1. SETUP ---
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

if "user" not in st.session_state:
    st.session_state.user = None

# ... (Include your Login/Registration logic here from previous steps) ...
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


# --- 2. CHAT INTERFACE (Strictly Private DM) ---
if st.session_state.user:
    my_id = st.session_state.user.id
    
    # Get my username from the profiles table
    # Safer way to fetch the username
    try:
        my_profile = supabase.table("profiles").select("username").eq("id", my_id).maybe_single().execute()
        if my_profile.data:
            my_username = my_profile.data['username']
        else:
            # Fallback if profile trigger failed
            my_username = st.session_state.user.email.split('@')[0]
    except Exception as e:
        my_username = "User"

    # SIDEBAR: Contact List
    st.sidebar.title("📇 Contacts")
    
    # Fetch all users from the Profiles table
    users_res = supabase.table("profiles").select("id, username").execute()
    # Filter out yourself so you don't chat with yourself
    contacts = {u['username']: u['id'] for u in users_res.data if u['id'] != my_id}
    
    if not contacts:
        st.sidebar.info("No other users have joined yet!")
        selected_name = None
    else:
        selected_name = st.sidebar.radio("Chat with:", list(contacts.keys()))

    if st.sidebar.button("Logout", type="tertiary"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

    # MAIN CHAT AREA
    if selected_name:
        st.title(f"💬 {selected_name}")
        target_id = contacts[selected_name]

        @st.fragment(run_every=3) # Faster refresh for 1-on-1 feel
        def chat_window():
            # Fetch messages where (Me -> Them) OR (Them -> Me)
            res = supabase.table("messages").select("*").or_(
                f"and(user_id.eq.{my_id},receiver_id.eq.{target_id}),"
                f"and(user_id.eq.{target_id},receiver_id.eq.{my_id})"
            ).order("created_at", desc=True).limit(30).execute()
            
            for m in reversed(res.data):
                is_me = m['user_id'] == my_id
                with st.chat_message("user" if is_me else "assistant"):
                    st.write(f"**{m['username']}**: {m['content']}")

        chat_window()

        if prompt := st.chat_input(f"Message {selected_name}..."):
            supabase.table("messages").insert({
                "user_id": my_id,
                "username": my_username,
                "content": prompt,
                "receiver_id": target_id
            }).execute()
            st.rerun()
    else:
        st.title("Welcome to PerzChat")
        st.info("Select a contact from the sidebar to start a private conversation.")