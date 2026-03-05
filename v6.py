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
if st.session_state.user:
    my_id = st.session_state.user.id
    
    # 1. Update Profile & Sync
    supabase.table("profiles").update({"last_seen": "now()"}).eq("id", my_id).execute()
    my_prof = supabase.table("profiles").select("username").eq("id", my_id).single().execute()
    my_username = my_prof.data['username']

    # 2. SIDEBAR ORGANIZATION
    st.sidebar.title("🛡️ PerzChat")
    
    # --- SECTION A: PRIVATE ROOMS ---
    st.sidebar.subheader("📁 Private Rooms")
    # Fetch only groups where I am a member
    groups_res = supabase.table("groups").select("id, name").execute()
    group_dict = {f"👥 {g['name']}": g['id'] for g in groups_res.data}
    
    # --- SECTION B: DIRECT MESSAGES ---
    st.sidebar.subheader("👤 People")
    users_res = supabase.table("profiles").select("id, username, last_seen").execute()
    all_users = sorted(users_res.data, key=lambda x: x['last_seen'] or "", reverse=True)
    contact_dict = {f"💬 {u['username']}": u['id'] for u in all_users if u['id'] != my_id}

    # Combined Selection
    nav_options = list(group_dict.keys()) + list(contact_dict.keys())
    
    if not nav_options:
        st.sidebar.info("Start by inviting family!")
        selection = None
    else:
        selection = st.sidebar.radio("Select Conversation:", nav_options, label_visibility="collapsed")

    # --- SECTION C: TOOLS ---
    st.sidebar.markdown("---")
    with st.sidebar.expander("➕ Create New Room"):
        new_gp_name = st.text_input("Room Name", placeholder="e.g. Weekend Plans")
        # Multiselect users to invite (excluding yourself)
        potential_members = [u['username'] for u in all_users if u['id'] != my_id]
        invited = st.multiselect("Invite Family Members", potential_members)
        
        if st.button("Create Room", use_container_width=True):
            if new_gp_name and invited:
                # 1. Create the Group
                gp = supabase.table("groups").insert({"name": new_gp_name, "created_by": my_id}).execute()
                gp_id = gp.data[0]['id']
                # 2. Add Members (Self + Invited)
                member_data = [{"group_id": gp_id, "user_id": my_id}]
                for name in invited:
                    u_id = next(u['id'] for u in all_users if u['username'] == name)
                    member_data.append({"group_id": gp_id, "user_id": u_id})
                supabase.table("group_members").insert(member_data).execute()
                st.success(f"Room '{new_gp_name}' Created!")
                time.sleep(1)
                st.rerun()

    if st.sidebar.button("Logout", type="tertiary"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

    # 3. MAIN CHAT LOGIC
    if selection:
        is_room = selection.startswith("👥")
        display_title = selection[2:] # Strip the emoji
        
        if is_room:
            target_id = group_dict[selection]
            st.title(f"👥 {display_title}")
        else:
            target_id = contact_dict[selection]
            st.title(f"👤 {display_title}")
            # Mark DM as read
            supabase.table("messages").update({"is_read": True}).eq("user_id", target_id).eq("receiver_id", my_id).execute()

        @st.fragment(run_every=4)
        def chat_window():
            if is_room:
                # Fetch messages for this specific group
                res = supabase.table("messages").select("*").eq("group_id", target_id).order("created_at", desc=True).limit(50).execute()
            else:
                # Fetch private messages between Me and Them
                res = supabase.table("messages").select("*").or_(
                    f"and(user_id.eq.{my_id},receiver_id.eq.{target_id}),"
                    f"and(user_id.eq.{target_id},receiver_id.eq.{my_id})"
                ).order("created_at", desc=True).limit(50).execute()
            
            for m in reversed(res.data):
                is_me = m['user_id'] == my_id
                # Only show read receipts for 1-on-1 chats
                status = ""
                if not is_room and is_me:
                    status = " ✓✓" if m.get('is_read') else " ✓"
                
                with st.chat_message("user" if is_me else "assistant"):
                    st.write(f"**{m['username']}**: {m['content']}")
                    st.caption(f"{m['created_at'][11:16]}{status}")

        chat_window()

        # 4. SENDING LOGIC
        if prompt := st.chat_input(f"Message {display_title}..."):
            payload = {
                "user_id": my_id,
                "username": my_username,
                "content": prompt
            }
            if is_room:
                payload["group_id"] = target_id
            else:
                payload["receiver_id"] = target_id
            
            supabase.table("messages").insert(payload).execute()
            st.rerun()
    else:
        st.title("Welcome to PerzChat")
        st.info("👈 Select a Person or a Room from the sidebar to start chatting.")