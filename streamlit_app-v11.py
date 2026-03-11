import streamlit as st
from supabase import create_client
from datetime import datetime, timedelta, timezone
import time

# --- 1. CONFIG & CONNECTION ---
st.set_page_config(page_title="PerzChat Pro", page_icon="🛡️", layout="wide")

@st.cache_resource
def init_connection():
    # These must be set in Streamlit Cloud -> Settings -> Secrets
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()

if "user" not in st.session_state:
    st.session_state.user = None

# --- 2. AUTHENTICATION UI ---
if not st.session_state.user:
    st.title("🛡️ PerzChat")
    tabs = st.tabs(["Login", "Create Account"])
    
    with tabs[0]:
        login_id = st.text_input("Username or Email", key="l_id").lower().strip()
        l_pwd = st.text_input("Password", type="password", key="l_pwd")
        
        if st.button("Sign In", type="primary", use_container_width=True):
            try:
                target_email = login_id
                if "@" not in login_id:
                    # Call the SQL function we created in the last step
                    rpc_res = supabase.rpc("get_email_from_username", {"input_username": login_id}).execute()
                    if rpc_res.data:
                        target_email = rpc_res.data
                    else:
                        st.error("Username not found.")
                        st.stop()
                
                auth_res = supabase.auth.sign_in_with_password({"email": target_email, "password": l_pwd})
                st.session_state.user = auth_res.user
                st.rerun()
            except:
                st.error("Login failed. Check your password.")

    with tabs[1]:
        r_email = st.text_input("Email", key="r_email").lower().strip()
        r_user = st.text_input("Username", key="r_user").lower().strip()
        r_pwd = st.text_input("Password", type="password", key="r_pwd")
        r_code = st.text_input("Family Secret Code", type="password")
        if st.button("Register", use_container_width=True):
            if r_code != "Family2026": st.error("Invalid Code")
            else:
                try:
                    supabase.auth.sign_up({"email": r_email, "password": r_pwd, "options": {"data": {"display_name": r_user}}})
                    st.success("Account created! You can now log in.")
                except Exception as e: st.error(f"Error: {e}")

# --- 3. MAIN APP ---
else:
    my_id = st.session_state.user.id
    
    # Update Presence
    supabase.table("profiles").update({"last_seen": "now()"}).eq("id", my_id).execute()
    my_prof = supabase.table("profiles").select("username").eq("id", my_id).maybe_single().execute()
    my_username = my_prof.data['username'] if my_prof.data else "User"

    # --- SIDEBAR ---
    st.sidebar.title("🛡️ PerzChat")
    
    with st.sidebar.expander("🔍 Find Someone"):
        query = st.text_input("Username or Email", key="s").lower().strip()
        if st.button("Add Contact"):
            field = "email" if "@" in query else "username"
            s_res = supabase.table("profiles").select("id").eq(field, query).maybe_single().execute()
            if s_res.data and s_res.data['id'] != my_id:
                supabase.table("private_contacts").upsert({"owner_id": my_id, "contact_id": s_res.data['id']}).execute()
                st.success("Added!")
                st.rerun()
            else: st.error("Not found.")

    # Fetch Contacts & Groups
    c_res = supabase.table("private_contacts").select("contact_id, profiles!contact_id(username, last_seen, typing_to)").eq("owner_id", my_id).execute()
    g_res = supabase.table("group_members").select("group_id, groups(name)").eq("user_id", my_id).execute()

    nav_dict = {}
    for c in c_res.data:
        p = c['profiles']
        is_online = False
        if p.get('last_seen'):
            last_active = datetime.fromisoformat(p['last_seen'].replace('Z', '+00:00'))
            if datetime.now(timezone.utc) - last_active < timedelta(minutes=5): is_online = True
        
        status = "🟢" if is_online else "⚪"
        typing = " ✍️" if p.get('typing_to') == my_id else ""
        nav_dict[f"{status} {p['username']}{typing}"] = {"id": c['contact_id'], "type": "dm", "name": p['username']}
    
    for g in g_res.data:
        nav_dict[f"👥 {g['groups']['name']}"] = {"id": g['group_id'], "type": "room", "name": g['groups']['name']}

    selection = st.sidebar.radio("Chats", list(nav_dict.keys()), label_visibility="collapsed") if nav_dict else None

    with st.sidebar.expander("➕ New Room"):
        gn = st.text_input("Room Name")
        if st.button("Create"):
            gp = supabase.table("groups").insert({"name": gn, "created_by": my_id}).execute()
            supabase.table("group_members").insert({"group_id": gp.data[0]['id'], "user_id": my_id}).execute()
            st.rerun()

    if st.sidebar.button("Logout", type="tertiary"):
        supabase.auth.sign_out(); st.session_state.user = None; st.rerun()

    # --- CHAT AREA ---
    if selection:
        chat = nav_dict[selection]
        
        col_t, col_i = st.columns([0.7, 0.3])
        col_t.title(selection)

        if chat['type'] == "room":
            with col_i.expander("ℹ️ Room Settings"):
                m_res = supabase.table("group_members").select("profiles(username)").eq("group_id", chat['id']).execute()
                st.write(f"**Members:** {', '.join([m['profiles']['username'] for m in m_res.data])}")
        else:
            supabase.table("profiles").update({"typing_to": chat['id']}).eq("id", my_id).execute()
            supabase.table("messages").update({"is_read": True}).eq("user_id", chat['id']).eq("receiver_id", my_id).execute()
        
        @st.fragment(run_every=3)
        def show_msgs():
            if chat['type'] == "room":
                res = supabase.table("messages").select("*").eq("group_id", chat['id']).order("created_at", desc=True).limit(40).execute()
            else:
                res = supabase.table("messages").select("*").or_(f"and(user_id.eq.{my_id},receiver_id.eq.{chat['id']}),and(user_id.eq.{chat['id']},receiver_id.eq.{my_id})").order("created_at", desc=True).limit(40).execute()
            
            for m in reversed(res.data):
                is_me = m['user_id'] == my_id
                tick = (" ✓✓" if m.get('is_read') else " ✓") if is_me and chat['type'] == "dm" else ""
                with st.chat_message("user" if is_me else "assistant"):
                    st.write(m['content'])
                    st.caption(f"{m['username']} • {m['created_at'][11:16]}{tick}")

        show_msgs()

        if prompt := st.chat_input("Message..."):
            supabase.table("profiles").update({"typing_to": None}).eq("id", my_id).execute()
            pld = {"user_id": my_id, "username": my_username, "content": prompt}
            if chat['type'] == "room": pld["group_id"] = chat['id']
            else: pld["receiver_id"] = chat['id']
            supabase.table("messages").insert(pld).execute()
            st.rerun()