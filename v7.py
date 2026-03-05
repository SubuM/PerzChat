import streamlit as st
from supabase import create_client
import time

# --- 1. CONFIG & CONNECTION ---
st.set_page_config(page_title="PerzChat Pro", page_icon="🛡️", layout="wide")
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

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


if st.session_state.user:
    my_id = st.session_state.user.id
    
    # Update Active Status
    supabase.table("profiles").update({"last_seen": "now()"}).eq("id", my_id).execute()
    my_prof = supabase.table("profiles").select("username").eq("id", my_id).single().execute()
    my_username = my_prof.data['username']

    # --- 2. SIDEBAR: PRIVATE NETWORK ---
    st.sidebar.title("🛡️ PerzChat")
    
    # SEARCH & ADD CONTACT
    with st.sidebar.expander("🔍 Find Someone"):
        search_query = st.text_input("Enter Email or Username").lower().strip()
        if st.button("Add to Contacts", use_container_width=True):
            # Find the user by email (Auth) or username (Profiles)
            target = None
            if "@" in search_query:
                # This requires a custom RPC or searching profiles if you store email there
                res = supabase.table("profiles").select("id").eq("email", search_query).maybe_single().execute()
                target = res.data
            else:
                res = supabase.table("profiles").select("id").eq("username", search_query).maybe_single().execute()
                target = res.data
            
            if target and target['id'] != my_id:
                supabase.table("private_contacts").insert({"owner_id": my_id, "contact_id": target['id']}).execute()
                st.success("Contact Added!")
                st.rerun()
            else:
                st.error("User not found.")

    # GET ACTIVE CONTACTS (Only those I have added)
    st.sidebar.subheader("💬 Active Chats")
    my_contacts_res = supabase.table("private_contacts").select("contact_id, profiles(username, last_seen)").eq("owner_id", my_id).execute()
    
    contact_dict = {f"👤 {c['profiles']['username']}": c['contact_id'] for c in my_contacts_res.data}
    
    # GET MY GROUPS
    my_groups_res = supabase.table("group_members").select("group_id, groups(name)").eq("user_id", my_id).execute()
    group_dict = {f"👥 {g['groups']['name']}": g['group_id'] for g in my_groups_res.data}

    nav_options = list(group_dict.keys()) + list(contact_dict.keys())
    selection = st.sidebar.radio("Conversations", nav_options, label_visibility="collapsed") if nav_options else None

    # CREATE GROUP TOOL
    with st.sidebar.expander("➕ Create Private Room"):
        new_gp_name = st.text_input("Room Name")
        if st.button("Create Room"):
            gp = supabase.table("groups").insert({"name": new_gp_name, "created_by": my_id}).execute()
            supabase.table("group_members").insert({"group_id": gp.data[0]['id'], "user_id": my_id}).execute()
            st.rerun()

    # --- 3. MAIN CHAT AREA ---
    if selection:
        is_room = selection.startswith("👥")
        target_id = group_dict[selection] if is_room else contact_dict[selection]
        display_name = selection[2:]

        # Header with Group Info
        col_title, col_info = st.columns([0.8, 0.2])
        with col_title:
            st.title(selection)
        with col_info:
            if is_room and st.button("ℹ️ Info"):
                m_res = supabase.table("group_members").select("profiles(username)").eq("group_id", target_id).execute()
                names = [m['profiles']['username'] for m in m_res.data]
                st.info(f"Members: {', '.join(names)}")

        if not is_room:
            # Mark Read
            supabase.table("messages").update({"is_read": True}).eq("user_id", target_id).eq("receiver_id", my_id).execute()

        @st.fragment(run_every=4)
        def chat_window():
            if is_room:
                res = supabase.table("messages").select("*").eq("group_id", target_id).order("created_at", desc=True).limit(50).execute()
            else:
                res = supabase.table("messages").select("*").or_(f"and(user_id.eq.{my_id},receiver_id.eq.{target_id}),and(user_id.eq.{target_id},receiver_id.eq.{my_id})").order("created_at", desc=True).limit(50).execute()
            
            for m in reversed(res.data):
                is_me = m['user_id'] == my_id
                status = (" ✓✓" if m.get('is_read') else " ✓") if is_me and not is_room else ""
                with st.chat_message("user" if is_me else "assistant"):
                    st.write(m['content'])
                    st.caption(f"{m['username']} • {m['created_at'][11:16]}{status}")

        chat_window()

        if prompt := st.chat_input(f"Message {display_name}..."):
            payload = {"user_id": my_id, "username": my_username, "content": prompt}
            if is_room: payload["group_id"] = target_id
            else: payload["receiver_id"] = target_id
            supabase.table("messages").insert(payload).execute()
            st.rerun()

    if st.sidebar.button("Logout", type="tertiary"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()