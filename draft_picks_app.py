import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import gspread
from google.oauth2.service_account import Credentials
import os
import datetime
import pytz

# --- PATH SETUP ---
script_dir = os.path.dirname(os.path.abspath(__file__))
seeds_file = os.path.join(script_dir, "team_seeds.csv")
rosters_file = os.path.join(script_dir, "team_rosters.xlsx")
# This is the file you will upload to GitHub to show standings
results_file = os.path.join(script_dir, "updated_picks_per_round.xlsx")

st.set_page_config(page_title="2026 NCAA Women's Player Pool", page_icon="🏀", layout="wide")

# --- GOOGLE SHEETS SETUP ---
# Ensure your secrets/key are handled here
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# If running locally:
if os.path.exists("ncaa-pool-489213-048a45542e02.json"):
    creds = Credentials.from_service_account_file("ncaa-pool-489213-048a45542e02.json", scopes=scope)
# If running on Streamlit Cloud:
else:
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)

client = gspread.authorize(creds)
SHEET_ID = "1P5-Kc_2X7skNMye3EB-oU-wpc4IsuSI1D9KyY9jW3gU"

# --- DATA LOADING ---
# We set ttl=120 (2 minutes) to prevent hitting Google's 60-request-per-minute limit.
@st.cache_data(ttl=120) 
def load_all_data():
    # 1. Local Files
    seeds_df = pd.read_csv(seeds_file)
    seeds_df['Seed'] = seeds_df['Seed'].astype(int)
    rosters_df = pd.read_excel(rosters_file)
    
    # 2. Google Sheets
    try:
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)
        
        # --- LOAD LEADERBOARD ---
        lb_worksheet = sh.worksheet("Leaderboard")
        lb_raw = lb_worksheet.get_all_values()
        
        if len(lb_raw) > 1:
            leaderboard_df = pd.DataFrame(lb_raw[2:], columns=lb_raw[1])
            leaderboard_df.columns = leaderboard_df.columns.str.strip()
            leaderboard_df = leaderboard_df.loc[:, ~leaderboard_df.columns.duplicated()]
            leaderboard_df = leaderboard_df.loc[:, leaderboard_df.columns != '']
            st.caption(f"📊 {lb_raw[0][0]}")
        else:
            leaderboard_df = pd.DataFrame()

        # --- LOAD PLAYER STATS ---
        ps_worksheet = sh.worksheet("PlayerStats")
        ps_raw = ps_worksheet.get_all_values()
        
        if len(ps_raw) > 1:
            player_stats_df = pd.DataFrame(ps_raw[2:], columns=ps_raw[1])
            player_stats_df.columns = player_stats_df.columns.str.strip()
        else:
            player_stats_df = pd.DataFrame()

        # --- LOAD PICKS (Sheet1) ---
        picks_worksheet = sh.worksheet("Sheet1")
        picks_raw = picks_worksheet.get_all_values()
        
        if len(picks_raw) > 0:
            picks_df = pd.DataFrame(picks_raw[1:], columns=picks_raw[0])
            
            # Clean up whitespace from headers
            picks_df.columns = picks_df.columns.str.strip()
            
            # Standardize 'Name' to 'Contestant'
            if 'Name' in picks_df.columns:
                picks_df = picks_df.rename(columns={'Name': 'Contestant'})
            
            # Remove any empty or duplicate columns
            picks_df = picks_df.loc[:, ~picks_df.columns.duplicated()]
            picks_df = picks_df.loc[:, picks_df.columns != '']
        else:
            picks_df = pd.DataFrame()
            
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
        leaderboard_df = pd.DataFrame()
        player_stats_df = pd.DataFrame()
        picks_df = pd.DataFrame()

    return seeds_df, rosters_df, leaderboard_df, picks_df, player_stats_df

# --- LEADERBOARD STYLING FUNCTION ---
def style_leaderboard(df):
    styles = pd.DataFrame('', index=df.index, columns=df.columns)
    
    # Pre-clean the Player Stats names for faster matching
    stats_names = player_stats_df['Player Name'].str.strip().str.lower().tolist()
    stats_statuses = player_stats_df['Status'].str.strip().str.lower().tolist()
    status_map = dict(zip(stats_names, stats_statuses))

    for i, row in df.iterrows():
        contestant_name = str(row.get('Contestant', '')).strip()
        user_picks = picks_df[picks_df['Contestant'] == contestant_name]
        
        if not user_picks.empty:
            # Get the 8 player names for THIS contestant
            p_names = [str(user_picks.iloc[0].get(f"Slot_{j}_Player", "")).strip().lower() for j in range(1, 9)]
            
            # Check the status for these 8 specific players
            user_player_statuses = [status_map.get(name, 'eliminated') for name in p_names if name]
            
            # If ANY player is active or advanced, the contestant is still "alive"
            is_alive = any(s in ['active', 'advanced'] for s in user_player_statuses)
            
            if is_alive:
                bg = 'rgba(0, 255, 0, 0.05)' # Green
            else:
                bg = 'rgba(255, 0, 0, 0.08)'  # Red
            
            styles.iloc[i, :] = f'background-color: {bg}'
            
    return styles

# Call the function once
seeds_df, rosters_df, leaderboard_df, picks_df, player_stats_df = load_all_data()
# --- GOOGLE SHEETS CONNECTION ---
# conn = st.connection("gsheets", type=GSheetsConnection)

# --- GLOBAL SIDEBAR ---
with st.sidebar:
    st.header("⚙️ App Controls")
    
    # Simple Refresh Button
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    st.divider() # Adds a nice visual line
    
    # Optional: Display the last time data was updated
    # (Only works if you're not using 'now' for the tournament deadline)
    import datetime
    st.caption(f"Last checked: {datetime.datetime.now().strftime('%I:%M:%S %p')}")

# --- APP TABS ---
tab1, tab2, tab4 = st.tabs(["📝 Enter Player Picks", "🏆 Leaderboard", "📊 View Submissions & Stats"])

# 1. Set your deadline (Year, Month, Day, Hour, Minute)
# Example: March 19, 2026, at 11:00 AM Central
deadline = datetime.datetime(2026, 3, 20, 10, 15, 0)

# 2. Define Timezones (Ensures the server time matches your time)
central = pytz.timezone('US/Central')
deadline = central.localize(deadline)
now = datetime.datetime.now(central)

with tab1:
    if now > deadline:
        # --- THE LOCKDOWN MESSAGE ---
        st.error("🔒 Player selection is now CLOSED.")
        st.subheader("The tournament has tipped off!")
        st.write("Submissions are no longer being accepted. Head over to the **Leaderboard** tab to track the scores!")
        
    else:
        # --- THE ORIGINAL SELECTION FORM ---
        # (Put your current selection loop and submit button code here)
        st.info(f"⏳ Player selection is OPEN! Submissions close at {deadline.strftime('%I:%M %p on %m/%d/%Y')}")
        col_header, col_reset = st.columns([5, 1])
        with col_header:
            st.title("🏀 2026 NCAA Women's Tournament Player Pool")
        with col_reset:
            if st.button("🔄 Reset Form"):
                st.rerun()

        st.markdown("""
        ### RULES:
        * **Select 8 players** to maximize your point total.
        * Each selected player must come from a **unique seed (1-16)**.
        * You may select a player from teams participating in the First Four round, but points scored in the First Four games **will not count** toward your total.
        * The person with the highest point total at the conclusion of the tournament wins.
        """)

        st.link_button("Go to Men's Tournament Pool 🏀", "https://teletraan1.com/ncaaplayerpool/")

        user_name = st.text_input("Enter Your Name / Team Name")
        
        user_selections = []
        chosen_seeds = []

        # Row-based layout to fix the 1-5-2-6 mobile bug
        for row_range in [range(1, 5), range(5, 9)]:
            cols = st.columns(4)
            for i in row_range:
                with cols[i - (row_range.start)]:
                    st.subheader(f"Player {i}")
                    selected_seed = st.selectbox(f"Seed", options=sorted(seeds_df['Seed'].unique()), index=i-1, key=f"s{i}")
                    chosen_seeds.append(selected_seed)
                    
                    teams = sorted(seeds_df[seeds_df['Seed'] == selected_seed]['Team'].unique())
                    selected_team = st.selectbox(f"Team", options=teams, key=f"t{i}")
                    
                    players = sorted(rosters_df[rosters_df['Team'] == selected_team]['Player Name'].unique())
                    selected_player = st.selectbox(f"Player", options=players, key=f"p{i}")
                    
                    user_selections.append({"Slot": i, "Seed": selected_seed, "Team": selected_team, "Player": selected_player})
            st.divider()

        # Validation
        st.sidebar.header("Selection Status")
        
        # Check for Duplicate Seeds
        duplicate_seeds = [seed for seed in set(chosen_seeds) if chosen_seeds.count(seed) > 1]
        is_valid = True

        if not user_name:
            st.sidebar.warning("⚠️ Enter a Name to Submit")
            is_valid = False

        if duplicate_seeds:
            st.sidebar.error(f"❌ Duplicate Seeds detected")
            st.sidebar.info("Each of your 8 players must come from a different seed.")
            is_valid = False
        else:
            st.sidebar.success("✅ Seeds are unique!")

        # THE SUBMIT BUTTON (Connected to Google Sheets)
        if st.button("Submit My Player Picks", disabled=not is_valid, use_container_width=True, type="primary"):
            with st.spinner("Submitting to Google Sheets..."):
                try:
                    # 1. Authorize and Open
                    gc = gspread.authorize(creds)
                    sh = gc.open_by_key(SHEET_ID)
                    target_sheet = sh.worksheet("Sheet1")

                    # 2. Prepare the data row
                    row_data = [user_name]
                    for p in user_selections:
                        # Convert everything to standard Python types (str and int)
                        # This fixes the 'int64' error!
                        row_data.append(str(p['Player']))
                        row_data.append(str(p['Team']))
                        row_data.append(int(p['Seed'])) # Forces int64 -> standard int

                    # 3. Append to Google Sheets
                    target_sheet.append_row(row_data)
                    
                    st.success(f"🎉 Successfully submitted! Good luck, {user_name}!")
                    st.balloons()
                    
                    # Force a cache clear so the new user shows up immediately
                    st.cache_data.clear() 
                    
                except Exception as e:
                    # If it still fails, this will tell us exactly which part
                    st.error(f"Error submitting to Google Sheets: {e}")

with tab2:
    st.info(f"Press Refresh Data button in the sidebar to the left to grab most current available data.")
    st.title("🏆 Current Standings")
    if not leaderboard_df.empty:
        # The styling function handles the logic
        st.dataframe(
            leaderboard_df.style.apply(style_leaderboard, axis=None), 
            use_container_width=True, 
            hide_index=True
        )
    else:
        st.error("No leaderboard data found.")
                
##with tab2:
##    st.title("🏆 Current Standings")
##    try:
##        # 1. Read the sheet (ttl=0 so the Refresh button works instantly)
##        df_leaderboard = conn.read(worksheet="Leaderboard", ttl=0)
##        
##        if not df_leaderboard.empty:
##            # 2. Extract timestamp from the very first header
##            timestamp_str = str(df_leaderboard.columns[0])
##            st.info(f"🕒 {timestamp_str}")
##            
##            # 3. Fix Headers: Skip the 'Last Updated' row and set real headers
##            actual_data = df_leaderboard.copy()
##            actual_data.columns = [str(c).strip() for c in actual_data.iloc[0]]
##            actual_data = actual_data[1:].reset_index(drop=True)
##            
##            # 4. Data Type Cleanup (Force numbers to be numeric)
##            actual_data = actual_data.apply(pd.to_numeric, errors='ignore')
##            
##            # 5. Sorting: Highest points at the top
##            if 'Total' in actual_data.columns:
##                actual_data = actual_data.sort_values(by='Total', ascending=False)
##            
##            # 6. Final Display with Auto-Styling
##            # This uses the style_leaderboard function defined outside the tabs
##            st.dataframe(
##                actual_data.style.apply(style_leaderboard, axis=None), 
##                use_container_width=True, 
##                hide_index=True
##            )
##        else:
##            st.warning("Leaderboard data is currently empty.")
##            
##    except Exception as e:
##        st.error(f"Leaderboard Error: {e}")
##with tab3:
##    st.title("📊 Individual Player Points")
##    
##    try:
##        # Note: player_stats_df is now loaded in your main load_all_data() function 
##        # using the safer get_all_values() method to avoid duplicate header errors.
##        
##        if not player_stats_df.empty:
##            # Define ideal order for player stats
##            ps_ideal = ["Player Name", "Team", "1st Round", "2nd Round", "Sweet 16", "Elite 8", "Final Four", "Nat'l Champ", "Total"]
##            ps_display = [c for c in ps_ideal if c in player_stats_df.columns]
##            
##            # Ensure Total is numeric for sorting
##            if 'Total' in player_stats_df.columns:
##                player_stats_df['Total'] = pd.to_numeric(player_stats_df['Total'], errors='coerce').fillna(0)
##                player_stats_final = player_stats_df.sort_values(by="Total", ascending=False)
##            else:
##                player_stats_final = player_stats_df
##
##            st.dataframe(
##                player_stats_final[ps_display], 
##                use_container_width=True, 
##                hide_index=True
##            )
##        else:
##            st.info("Player stats will be available here starting March 20th.")
##            
##    except Exception as e:
##        st.error(f"Stats Error: {e}")

with tab4:
    st.info(f"Press Refresh Data button in the sidebar to the left to grab most current available data.")
    st.title("📊 Contestant Rosters & Live Stats")
    
    if now < deadline:
        st.info(f"🔒 Roster stats are hidden until the tournament begins ({deadline.strftime('%I:%M %p on %m/%d')}).")
##    else:
##        # Match your header: 'Name' (Women's script specific)
##        if not picks_df.empty and 'Name' in picks_df.columns:
##            contestants = [c for c in picks_df['Name'].unique() if str(c).strip() != ""]
##            selected_user = st.selectbox("Select a Contestant:", ["All"] + contestants, key="womens_roster_select")
##            display_list = contestants if selected_user == "All" else [selected_user]
##
##            stat_columns = ['1st Round', '2nd Round', 'Sweet 16', 'Elite 8', 'Final Four', "Nat'l Champ", 'Total']
##
##            for user in display_list:
##                with st.expander(f"👤 {user}'s Live Roster", expanded=(selected_user != "All")):
##                    # Lookup row based on 'Name'
##                    user_row = picks_df[picks_df['Name'] == user].iloc[0]
##                    user_players = []
##                    
##                    for i in range(1, 9):
##                        p_name = user_row.get(f"Slot_{i}_Player")
##                        
##                        if p_name and str(p_name).strip() != "":
##                            display_name = str(p_name).strip()
##                            
##                            try:
##                                clean_seed = int(float(user_row.get(f"Slot_{i}_Seed", 0)))
##                            except:
##                                clean_seed = "-"
##
##                            # Default entry with Status for shading
##                            player_entry = {
##                                "Player": display_name,
##                                "Team": user_row.get(f"Slot_{i}_Team", "N/A"),
##                                "Seed": clean_seed,
##                                "Status": "active" 
##                            }
##
##                            # Lookup logic from PlayerStats
##                            if not player_stats_df.empty and 'Player Name' in player_stats_df.columns:
##                                search_name = display_name.lower().strip()
##                                match_mask = player_stats_df['Player Name'].astype(str).str.lower().str.strip() == search_name
##                                p_stats = player_stats_df[match_mask]

    else:
        # 1. Identify the Contestant Column (Handles 'Name' vs 'Contestant' mismatch)
        # We look for any column that sounds like a user/contestant name
        name_col = next((c for c in picks_df.columns if c in ['Name', 'Contestant', 'User', 'Submitter']), None)

        if not picks_df.empty and name_col:
            # Use the identified name_col for the dropdown
            contestants = [c for c in picks_df[name_col].unique() if str(c).strip() != ""]
            selected_user = st.selectbox("Select a Contestant:", ["All"] + contestants, key="womens_roster_select")
            display_list = contestants if selected_user == "All" else [selected_user]

            stat_columns = ['1st Round', '2nd Round', 'Sweet 16', 'Elite 8', 'Final Four', "Nat'l Champ", 'Total']

            for user in display_list:
                with st.expander(f"👤 {user}'s Live Roster", expanded=(selected_user != "All")):
                    # Use the identified name_col to find the specific user's row
                    user_row = picks_df[picks_df[name_col] == user].iloc[0]
                    user_players = []
                    
                    for i in range(1, 9):
                        p_name = user_row.get(f"Slot_{i}_Player")
                        
                        if p_name and str(p_name).strip() != "":
                            display_name = str(p_name).strip()
                            
                            # ... (keep your existing seed and player_entry logic here) ...

                            # 2. Match against PlayerStats (which uses 'Player Name')
                            if not player_stats_df.empty and 'Player Name' in player_stats_df.columns:
                                search_name = display_name.lower().strip()
                                # We explicitly use 'Player Name' here because that's what the stats sheet uses
                                match_mask = player_stats_df['Player Name'].astype(str).str.lower().str.strip() == search_name
                                p_stats = player_stats_df[match_mask]
                                
                                # ... (keep the rest of your scoring/styling logic) ...
                                
                                if not p_stats.empty:
                                    if 'Status' in p_stats.columns:
                                        player_entry["Status"] = str(p_stats.iloc[0]['Status']).strip().lower()
                                    
                                    for col in stat_columns:
                                        val = p_stats.iloc[0][col] if col in p_stats.columns else 0
                                        player_entry[col] = pd.to_numeric(val, errors='coerce') or 0
                                else:
                                    for col in stat_columns: player_entry[col] = 0
                            else:
                                for col in stat_columns: player_entry[col] = 0
                            
                            user_players.append(player_entry)
                    
                    if user_players:
                        df_display = pd.DataFrame(user_players)
                        
                        # Summary Row
                        summary_data = {"Player": "**ROSTER TOTALS**", "Team": "", "Seed": "", "Status": ""}
                        for col in stat_columns:
                            summary_data[col] = df_display[col].sum()
                        
                        df_with_total = pd.concat([df_display, pd.DataFrame([summary_data])], ignore_index=True)

                        # Local Styling Function
                        def style_roster_internal(df):
                            styles = pd.DataFrame('', index=df.index, columns=df.columns)
                            for idx, row in df.iterrows():
                                if idx == len(df) - 1:
                                    styles.iloc[idx, :] = 'font-weight: bold; border-top: 2px solid #888;'
                                    continue
                                
                                status = str(row.get('Status', '')).lower()
                                if 'eliminated' in status:
                                    bg = 'rgba(255, 0, 0, 0.15)'
                                elif 'advanced' in status:
                                    bg = 'rgba(0, 255, 0, 0.15)'
                                elif 'active' in status:
                                    bg = 'rgba(0, 0, 255, 0.08)'
                                else:
                                    bg = ''
                                
                                if bg:
                                    styles.iloc[idx, :] = f'background-color: {bg}'
                            return styles

                        # DISPLAY: Keep 'Status' for styling but hide from UI via column_config
                        st.dataframe(
                            df_with_total.style.apply(style_roster_internal, axis=None),
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Status": None 
                            }
                        )
                    else:
                        st.write("No picks recorded.")
        else:
            st.warning("Could not find the 'Name' column. Please check your Google Sheet headers.")
