import streamlit as st
from supabase import create_client
from datetime import datetime, timedelta, timezone

# --- 1. CONFIG ---
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
    
    # Update Status & Fetch Profile
    supabase.table("profiles").update({"last_seen": "now()"}).eq("id", my_id).execute()
    prof_res = supabase.table("profiles").select("username").eq("id", my_id).maybe_single().execute()
    my_username = prof_res.data['username'] if prof_res.data else "user"

    # --- 2. SIDEBAR ---
    st.sidebar.title("🛡️ PerzChat")
    
    with st.sidebar.expander("🔍 Find Someone"):
        query = st.text_input("Username or Email", key="search_box").lower().strip()
        if st.button("Add Contact", use_container_width=True):
            field = "email" if "@" in query else "username"
            # Explicitly search lowercase
            search_res = supabase.table("profiles").select("id").eq(field, query).maybe_single().execute()
            
            if search_res and search_res.data:
                tid = search_res.data['id']
                if tid != my_id:
                    supabase.table("private_contacts").upsert({"owner_id": my_id, "contact_id": tid}).execute()
                    st.success("Added!")
                    st.rerun()
                else:
                    st.warning("That's you!")
            else:
                st.error(f"No user found with {field}: {query}")

    # FETCH CONTACTS WITH ONLINE STATUS
    c_res = supabase.table("private_contacts").select("contact_id, profiles!contact_id(username, last_seen)").eq("owner_id", my_id).execute()
    
    contact_dict = {}
    for c in c_res.data:
        if c.get('profiles'):
            p = c['profiles']
            # Online logic: seen in last 5 minutes
            is_online = False
            if p.get('last_seen'):
                last_active = datetime.fromisoformat(p['last_seen'].replace('Z', '+00:00'))
                if datetime.now(timezone.utc) - last_active < timedelta(minutes=5):
                    is_online = True
            
            status_dot = "🟢" if is_online else "⚪"
            label = f"{status_dot} {p['username']}"
            contact_dict[label] = {"id": c['contact_id'], "name": p['username']}

    # FETCH GROUPS
    g_res = supabase.table("group_members").select("group_id, groups(name)").eq("user_id", my_id).execute()
    group_dict = {f"👥 {g['groups']['name']}": g['group_id'] for g in g_res.data if g.get('groups')}

    nav = list(group_dict.keys()) + list(contact_dict.keys())
    selection = st.sidebar.radio("Nav", nav, label_visibility="collapsed") if nav else None

    # --- 3. MAIN CHAT ---
    if selection:
        is_gp = selection.startswith("👥")
        # Extract ID and Name correctly
        if is_gp:
            tid = group_dict[selection]
            display_name = selection[2:]
        else:
            tid = contact_dict[selection]['id']
            display_name = contact_dict[selection]['name']

        st.title(f"{selection}")

        
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