import streamlit as st
from supabase import create_client, Client
import time

# --- INITIALIZATION ---
st.set_page_config(page_title="StreamChat", layout="centered")

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL_STREAMCHAT"]
    key = st.secrets["SUPABASE_KEY_STREAMCHAT"]
    return create_client(url, key)

supabase = init_supabase()

# Initialize session states
if 'user' not in st.session_state:
    st.session_state.user = None
if 'profile' not in st.session_state:
    st.session_state.profile = None
if 'chat_with' not in st.session_state:
    st.session_state.chat_with = None

# --- AUTHENTICATION FUNCTIONS ---
def get_email_from_username(username):
    response = supabase.table("profiles").select("email").eq("username", username).execute()
    if response.data:
        return response.data[0]['email']
    return None

def login(username, password):
    email = get_email_from_username(username)
    if not email:
        st.error("Username not found.")
        return
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state.user = res.user
        # Fetch profile
        prof_res = supabase.table("profiles").select("*").eq("id", res.user.id).execute()
        st.session_state.profile = prof_res.data[0]
        st.success("Logged in successfully!")
        st.rerun()
    except Exception as e:
        st.error(f"Login failed: Invalid credentials.")

def register(email, username, password):
    # Check if username exists
    if get_email_from_username(username):
        st.error("Username already taken. Please choose another.")
        return
    
    try:
        # 1. Sign up user in Supabase Auth
        res = supabase.auth.sign_up({"email": email, "password": password})
        if res.user:
            # 2. Add user to our public profiles table
            supabase.table("profiles").insert({
                "id": res.user.id,
                "username": username,
                "email": email
            }).execute()
            st.success("Registration successful! You can now log in.")
    except Exception as e:
        st.error(f"Registration failed: {str(e)}")

def reset_password(username):
    email = get_email_from_username(username)
    if not email:
        st.error("Username not found.")
        return
    try:
        supabase.auth.reset_password_for_email(email)
        st.success(f"Password reset link sent to the email associated with '{username}'.")
    except Exception as e:
        st.error(f"Failed to send reset link: {str(e)}")

# --- APP ROUTING ---

if not st.session_state.user:
    st.title("Welcome to StreamChat 💬")
    tab1, tab2, tab3 = st.tabs(["Login", "Register", "Forgot Password"])
    
    with tab1:
        st.subheader("Login")
        l_username = st.text_input("Username", key="l_user")
        l_password = st.text_input("Password", type="password", key="l_pass")
        if st.button("Login"):
            login(l_username, l_password)
            
    with tab2:
        st.subheader("Register")
        r_email = st.text_input("Email", key="r_email")
        r_username = st.text_input("Choose a Username", key="r_user")
        r_password = st.text_input("Choose a Password", type="password", key="r_pass")
        if st.button("Register"):
            register(r_email, r_username, r_password)
            
    with tab3:
        st.subheader("Forgot Password")
        f_username = st.text_input("Enter your Username", key="f_user")
        if st.button("Send Reset Link"):
            reset_password(f_username)

else:
    # --- PRE-PROCESSING: MARK AS READ ---
    # We do this BEFORE drawing the UI so the unread count is perfectly accurate
    if st.session_state.chat_with:
        my_id = st.session_state.user.id
        their_id = st.session_state.chat_with['id']
        try:
            supabase.table("messages").update({"is_read": True}).eq("sender_id", their_id).eq("receiver_id", my_id).eq("is_read", False).execute()
        except:
            pass # Failsafe just in case there are no messages yet

    # --- MAIN CHAT INTERFACE ---
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.write(f"👤 **{st.session_state.profile['username']}**")
        
        # --- LOGOUT ---
        if st.button("Logout"):
            supabase.auth.sign_out()
            st.session_state.user = None
            st.session_state.profile = None
            st.session_state.chat_with = None
            st.rerun()
        
        st.divider()
        
        # --- SEARCH & ADD CONTACTS ---
        st.write("**🔍 Add a Contact**")
        search_query = st.text_input("Search by exact Username or Email")
        
        if st.button("Search"):
            if search_query:
                search_res = supabase.table("profiles").select("*").or_(f"username.eq.{search_query},email.eq.{search_query}").execute()
                
                if search_res.data:
                    found_user = search_res.data[0]
                    if found_user['id'] == st.session_state.user.id:
                        st.warning("You can't add yourself!")
                    else:
                        st.session_state.found_user = found_user
                else:
                    st.error("User not found.")
                    st.session_state.found_user = None

        if 'found_user' in st.session_state and st.session_state.found_user:
            st.success(f"Found: {st.session_state.found_user['username']}")
            
            if st.button(f"➕ Add to Contacts"):
                my_id_add = st.session_state.user.id
                their_id_add = st.session_state.found_user['id']
                try:
                    supabase.rpc("add_mutual_contact", {"user_a": my_id_add, "user_b": their_id_add}).execute()
                    st.success("Added successfully!")
                    st.session_state.found_user = None 
                    time.sleep(1) 
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to add contact: {str(e)}")
                    
        st.divider()
        
        # --- NOTIFICATION SYSTEM: Fetch Unread Counts ---
        unread_res = supabase.table("messages").select("sender_id").eq("receiver_id", st.session_state.user.id).eq("is_read", False).execute()
        
        unread_counts = {}
        for msg in unread_res.data:
            sender = msg['sender_id']
            unread_counts[sender] = unread_counts.get(sender, 0) + 1

        # --- PRIVATE CONTACT LIST ---
        st.write("**📇 My Contacts**")
        
        contacts_res = supabase.table("contacts").select("contact_id").eq("user_id", st.session_state.user.id).execute()
        contact_ids = [c['contact_id'] for c in contacts_res.data]
        
        if contact_ids:
            my_contacts_profiles = supabase.table("profiles").select("*").in_("id", contact_ids).execute()
            for contact in my_contacts_profiles.data:
                count = unread_counts.get(contact['id'], 0)
                btn_text = f"{contact['username']} (🟢 {count})" if count > 0 else contact['username']
                
                if st.button(btn_text, key=contact['id'], use_container_width=True):
                    st.session_state.chat_with = contact
                    st.rerun()
        else:
            st.info("No contacts yet. Search for a friend above!")

        st.divider()
        
        # --- DELETE ACCOUNT ---
        if st.button("Delete Account", type="primary"):
            try:
                supabase.rpc("delete_user", {}).execute()
                supabase.auth.sign_out()
                st.session_state.user = None
                st.session_state.profile = None
                st.session_state.chat_with = None
                st.success("Your account and all associated data have been deleted.")
                time.sleep(2)
                st.rerun()
            except Exception as e:
                st.error(f"Failed to delete account: {str(e)}")

    with col2:
        if st.session_state.chat_with:
            st.subheader(f"Chat with {st.session_state.chat_with['username']}")
            
            my_id = st.session_state.user.id
            their_id = st.session_state.chat_with['id']
            
            # --- CUSTOM CSS FOR CHAT BUBBLES ---
            st.markdown("""
            <style>
            .chat-container {
                display: flex;
                flex-direction: column;
                gap: 10px;
                padding-bottom: 20px;
            }
            .msg-bubble {
                max-width: 70%;
                padding: 10px 15px;
                border-radius: 15px;
                margin-bottom: 5px;
                font-family: sans-serif;
                word-wrap: break-word;
            }
            .msg-mine {
                background-color: #dcf8c6;
                color: #000;
                align-self: flex-end;
                border-bottom-right-radius: 0;
            }
            .msg-theirs {
                background-color: #f1f0f0;
                color: #000;
                align-self: flex-start;
                border-bottom-left-radius: 0;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # Fetch messages
            messages_res = supabase.table("messages").select("*") \
                .or_(f"and(sender_id.eq.{my_id},receiver_id.eq.{their_id}),and(sender_id.eq.{their_id},receiver_id.eq.{my_id})") \
                .order("created_at", desc=False).execute()
            
            # --- DISPLAY MESSAGES WITH CUSTOM HTML ---
            chat_html = '<div class="chat-container">'
            for msg in messages_res.data:
                is_me = msg['sender_id'] == my_id
                bubble_class = "msg-mine" if is_me else "msg-theirs"
                chat_html += f'<div class="msg-bubble {bubble_class}">{msg["content"]}</div>'
            chat_html += '</div>'
            
            chat_container = st.container(height=400)
            with chat_container:
                st.markdown(chat_html, unsafe_allow_html=True)
            
            # Input new message
            new_message = st.chat_input("Type your message here...")
            if new_message:
                supabase.table("messages").insert({
                    "sender_id": my_id,
                    "receiver_id": their_id,
                    "content": new_message,
                    "is_read": False 
                }).execute()
                st.rerun()
                
            if st.button("🔄 Refresh Messages"):
                st.rerun()
                
        else:
            st.info("👈 Select a contact from the sidebar to start chatting.")

