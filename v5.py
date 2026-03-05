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

# --- 2. AUTHENTICATION UI (HYBRID LOGIN) ---
if not st.session_state.user:
    st.title("🛡️ PerzChat")
    tabs = st.tabs(["Login", "Create Account"])
    
    with tabs[0]:
        # Accepts either Email or Username
        login_id = st.text_input("Username or Email", key="l_id")
        l_pwd = st.text_input("Password", type="password", key="l_pwd")
        
        if st.button("Sign In", type="primary", use_container_width=True):
            try:
                # Logic: If it's not an email, find the email associated with that username
                target_email = login_id
                if "@" not in login_id:
                    res = supabase.table("profiles").select("id").eq("username", login_id).maybe_single().execute()
                    if res.data:
                        # Find actual email from Auth using the ID (requires a small helper or just attempt login)
                        # For simplicity in this tier, we fetch the email from a hidden field or map it
                        user_res = supabase.rpc("get_email_by_username", {"u_name": login_id}).execute()
                        if user_res.data:
                            target_email = user_res.data
                
                auth_res = supabase.auth.sign_in_with_password({"email": target_email, "password": l_pwd})
                st.session_state.user = auth_res.user
                st.rerun()
            except Exception:
                st.error("Invalid credentials. If using username, ensure it's correct.")

    with tabs[1]:
        st.info("Ask the admin for the Secret Code.")
        r_email = st.text_input("Email", key="r_email")
        r_user = st.text_input("Choose Username (Lowercase/No spaces)", key="r_user").lower().strip()
        r_pwd = st.text_input("Password", type="password", key="r_pwd")
        r_code = st.text_input("Secret Code", type="password")
        
        if st.button("Register", use_container_width=True):
            if r_code != "Family2026": 
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
    
    # Get my username and set active status
    my_prof = supabase.table("profiles").select("username").eq("id", my_id).maybe_single().execute()
    my_username = my_prof.data['username'] if my_prof.data else "User"
    supabase.table("profiles").update({"last_seen": "now()"}).eq("id", my_id).execute()

    # SIDEBAR: Contacts
    st.sidebar.title("📇 Contacts")
    users_res = supabase.table("profiles").select("id, username, last_seen, typing_to").execute()
    all_users = sorted(users_res.data, key=lambda x: x['last_seen'] or "", reverse=True)
    contacts = {u['username']: u['id'] for u in all_users if u['id'] != my_id}

    if not contacts:
        st.sidebar.info("No other users yet.")
        selected_name = None
    else:
        # Build display names with typing indicators
        contact_list = []
        for u in all_users:
            if u['id'] != my_id:
                label = u['username']
                if u.get('typing_to') == my_id:
                    label += " (typing... ✍️)"
                contact_list.append(label)
        
        selected_display = st.sidebar.radio("Select Chat:", contact_list)
        selected_name = selected_display.split(" ")[0]
        target_id = contacts[selected_name]

    if st.sidebar.button("Logout", type="tertiary"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

    # MAIN CHAT
    if selected_name:
        st.title(f"💬 {selected_name}")
        
        # Mark as read
        supabase.table("messages").update({"is_read": True}).eq("user_id", target_id).eq("receiver_id", my_id).eq("is_read", False).execute()

        @st.fragment(run_every=3)
        def chat_window():
            # Show typing indicator in the main window too
            typer = next((u for u in all_users if u['id'] == target_id), None)
            if typer and typer.get('typing_to') == my_id:
                st.caption(f"_{selected_name} is typing..._")

            res = supabase.table("messages").select("*").or_(
                f"and(user_id.eq.{my_id},receiver_id.eq.{target_id}),"
                f"and(user_id.eq.{target_id},receiver_id.eq.{my_id})"
            ).order("created_at", desc=True).limit(40).execute()
            
            for m in reversed(res.data):
                is_me = m['user_id'] == my_id
                status = (" ✓✓" if m.get('is_read') else " ✓") if is_me else ""
                with st.chat_message("user" if is_me else "assistant"):
                    st.write(f"{m['content']}")
                    st.caption(f"{m['created_at'][11:16]}{status}")

        chat_window()

        # Input Area with Typing Logic
        prompt = st.chat_input(f"Message {selected_name}...")
        
        # If the input is active but empty, we can't easily detect "keystrokes" in Streamlit, 
        # but we can set typing status when the user clicks the input.
        if prompt:
            # Reset typing status and insert message
            supabase.table("profiles").update({"typing_to": None}).eq("id", my_id).execute()
            supabase.table("messages").insert({
                "user_id": my_id, "receiver_id": target_id,
                "username": my_username, "content": prompt
            }).execute()
            st.rerun()