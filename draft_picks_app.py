import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import os
import datetime
import pytz

# Define Timezones (Ensures the server time matches your time)
central = pytz.timezone('US/Central')
now = datetime.datetime.now(central)

# --- PATH SETUP ---
script_dir = os.path.dirname(os.path.abspath(__file__))
seeds_file = os.path.join(script_dir, "team_seeds.csv")
rosters_file = os.path.join(script_dir, "team_rosters.xlsx")

st.set_page_config(page_title="2026 NCAA Men's Player Pool", page_icon="🏀", layout="wide")

conn = st.connection("gsheets", type=GSheetsConnection)

# --- DATA LOADING ---
@st.cache_data(ttl=120)
def load_all_app_data():
    seeds_df = pd.read_csv(seeds_file)
    seeds_df['Seed'] = seeds_df['Seed'].astype(int)
    rosters_df = pd.read_excel(rosters_file)
    
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    try:
        # 1. Load Picks (Sheet1 usually starts at Row 1, no shift needed)
        picks_df = conn.read(worksheet="Sheet1", ttl=0)
        picks_df.columns = [str(c).strip() for c in picks_df.columns]
        
        # 2. Load Leaderboard (Shift headers due to timestamp in Row 1)
        lb_raw = conn.read(worksheet="Leaderboard", ttl=0)
        if not lb_raw.empty:
            leaderboard_df = lb_raw.copy()
            leaderboard_df.columns = [str(c).strip() for c in leaderboard_df.iloc[0]]
            leaderboard_df = leaderboard_df[1:].reset_index(drop=True)
        else:
            leaderboard_df = pd.DataFrame()

        # 3. Load Player Stats (Shift headers due to timestamp in Row 1)
        ps_raw = conn.read(worksheet="PlayerStats", ttl=0)
        if not ps_raw.empty:
            player_stats_df = ps_raw.copy()
            # Set headers to the values found in the second row (index 0 of the dataframe)
            player_stats_df.columns = [str(c).strip() for c in player_stats_df.iloc[0]]
            # Drop the header row from the data and reset index
            player_stats_df = player_stats_df[1:].reset_index(drop=True)
        else:
            player_stats_df = pd.DataFrame()
            
    except Exception as e:
        st.error(f"Error reading Google Sheets: {e}")
        picks_df = pd.DataFrame()
        leaderboard_df = pd.DataFrame()
        player_stats_df = pd.DataFrame()

    return seeds_df, rosters_df, picks_df, leaderboard_df, player_stats_df

# --- LEADERBOARD STYLING FUNCTION ---
def style_leaderboard(df):
    styles = pd.DataFrame('', index=df.index, columns=df.columns)
    
    # 1. Create a quick lookup for player statuses
    status_map = dict(zip(
        player_stats_df['Player Name'].str.strip().str.lower(), 
        player_stats_df['Status'].str.strip().str.lower()
    ))

    for i, row in df.iterrows():
        contestant_name = str(row.get('Contestant', '')).strip()
        user_picks = picks_df[picks_df['Contestant'].str.strip() == contestant_name]
        
        if not user_picks.empty:
            # Get the 8 player names for THIS contestant
            p_names = [str(user_picks.iloc[0].get(f"Slot_{j}_Player", "")).strip().lower() for j in range(1, 9)]
            
            # Get the statuses for these 8 players
            user_player_statuses = [status_map.get(name, 'active') for name in p_names if name]
            
            # --- TIERED COLOR LOGIC ---
            # Priority 1: Any "advanced" or "advancing" player? -> Solid Green
            if any(s in ['advanced', 'advancing'] for s in user_player_statuses):
                bg = '#d4edda' # Light Green
            
            # Priority 2: Any "active" players left? -> Soft Blue
            elif any(s == 'active' for s in user_player_statuses):
                bg = '#d1ecf1' # Soft Blue
            
            # Priority 3: Everyone is "eliminated" -> Light Red
            else:
                bg = '#f8d7da' # Light Red
            
            styles.iloc[i, :] = f'background-color: {bg}; color: black;' # Added black text for readability
            
    return styles

# Execute the load
seeds_df, rosters_df, picks_df, leaderboard_df, player_stats_df = load_all_app_data()

# --- GLOBAL SIDEBAR ---
with st.sidebar:
    st.header("⚙️ App Controls")
    
    # Simple Refresh Button
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    st.divider() # Adds a nice visual line
    
    st.caption(f"Last checked: {now.strftime('%I:%M:%S %p')} CT")

# --- APP TABS ---
tab1, tab2, tab4 = st.tabs(["📝 Enter Player Picks", "🏆 Leaderboard", "📊 View Submissions & Stats"])

# Set your deadline (Year, Month, Day, Hour, Minute)
# Example: March 19, 2026, at 11:00 AM Central
deadline = datetime.datetime(2026, 3, 19, 11, 0, 0)

deadline = central.localize(deadline)
 
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
            st.title("🏀 2026 NCAA Men's Tournament Player Pool")
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

        st.link_button("Go to Women's Tournament Pool 🏀", "https://teletraan1.com/ncaawbbplayerpool/")

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
                    # 1. Prepare the data row
                    new_entry = {"Contestant": user_name}
                    for p in user_selections:
                        new_entry[f"Slot_{p['Slot']}_Player"] = p['Player']
                        new_entry[f"Slot_{p['Slot']}_Team"] = p['Team']
                        new_entry[f"Slot_{p['Slot']}_Seed"] = p['Seed']
                    
                    # 2. Read existing data (ttl=0 ensures no caching issues)
                    existing_data = conn.read(worksheet="Sheet1", ttl=0)
                    existing_data = existing_data.dropna(how="all")
                    
                    # 3. Combine and Update
                    updated_df = pd.concat([existing_data, pd.DataFrame([new_entry])], ignore_index=True)
                    conn.update(worksheet="Sheet1", data=updated_df)
                    
                    st.success(f"🎉 Successfully submitted! Good luck, {user_name}!")
                    st.balloons()
                    
                except Exception as e:
                    st.error(f"Error submitting to Google Sheets: {e}")
                
with tab2:
    st.info(f"Press Refresh Data button in the sidebar to the left to grab most current available data.")
    st.title("🏆 Current Standings")
    try:
        # 1. Read the sheet
        df_leaderboard = conn.read(worksheet="Leaderboard", ttl=0)
        
        if not df_leaderboard.empty:
            # 2. Extract timestamp
            timestamp_str = str(df_leaderboard.columns[0])
            st.info(f"🕒 {timestamp_str}")
            
            # 3. Fix Headers
            actual_data = df_leaderboard.copy()
            actual_data.columns = [str(c).strip() for c in actual_data.iloc[0]]
            actual_data = actual_data[1:].reset_index(drop=True)
            
            # 4. Data Type Cleanup
            actual_data = actual_data.apply(pd.to_numeric, errors='ignore')
            
            # 5. Sorting
            if 'Total' in actual_data.columns:
                actual_data = actual_data.sort_values(by='Total', ascending=False)
            
            # 6. Final Display with Auto-Styling
            st.dataframe(
                actual_data.style.apply(style_leaderboard, axis=None), 
                use_container_width=True, 
                hide_index=True
            )
            
    except Exception as e:
        st.error(f"Leaderboard Error: {e}")

with tab4:
    st.info(f"Press Refresh Data button in the sidebar to the left to grab most current available data.")
    st.title("📝 Contestant Rosters & Stats")
    
    if now < deadline:
        st.info(f"🔒 Roster stats are hidden until the tournament begins ({deadline.strftime('%I:%M %p on %m/%d')}).")
    else:
        try:
            # We read with ttl=0 to ensure we get the fresh timestamp from the header
            df_player_stats = conn.read(worksheet="PlayerStats", ttl=0)
            if not df_player_stats.empty:
                timestamp_str = str(df_player_stats.columns[0])
                st.info(f"🕒 {timestamp_str} using most recent data from collegebasketballdata.com API")
        except Exception:
            pass # Silently skip if the sheet is temporarily unavailable
        
        if not picks_df.empty and 'Contestant' in picks_df.columns:
            contestants = [c for c in picks_df['Contestant'].unique() if str(c).strip() != ""]
            selected_user = st.selectbox("Select a Contestant:", ["All"] + contestants, key="mens_roster_select")
            display_list = contestants if selected_user == "All" else [selected_user]

            stat_columns = ['1st Round', '2nd Round', 'Sweet 16', 'Elite 8', 'Final Four', "Nat'l Champ", 'Total']

            for user in display_list:
                with st.expander(f"👤 {user}'s Live Roster", expanded=(selected_user != "All")):
                    user_row = picks_df[picks_df['Contestant'] == user].iloc[0]
                    user_players = []
                    
                    for i in range(1, 9):
                        p_name = user_row.get(f"Slot_{i}_Player")
                        
                        if p_name and str(p_name).strip() != "":
                            display_name = str(p_name).strip()
                            
                            try:
                                clean_seed = int(float(user_row.get(f"Slot_{i}_Seed", 0)))
                            except:
                                clean_seed = "-"

                            # Default entry
                            player_entry = {
                                "Player": display_name,
                                "Team": user_row.get(f"Slot_{i}_Team", "N/A"),
                                "Seed": clean_seed,
                                "Status": "active" 
                            }

                            # Lookup logic
                            if not player_stats_df.empty and 'Player Name' in player_stats_df.columns:
                                search_name = display_name.lower().strip()
                                match_mask = player_stats_df['Player Name'].astype(str).str.lower().str.strip() == search_name
                                p_stats = player_stats_df[match_mask]
                                
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

                        # Styling function defined locally
                        def style_roster_internal(df):
                            styles = pd.DataFrame('', index=df.index, columns=df.columns)
                            for idx, row in df.iterrows():
                                # 1. Style the "TOTALS" row (Bold + Border)
                                if idx == len(df) - 1:
                                    styles.iloc[idx, :] = 'font-weight: bold; border-top: 2px solid #888; background-color: #f0f2f6;'
                                    continue
                                
                                # 2. Extract and Normalize Status
                                status = str(row.get('Status', '')).lower().strip()
                                
                                # 3. TIERED HEX COLOR LOGIC
                                if any(s in status for s in ['advanced', 'advancing']):
                                    bg = '#d4edda' # Clean Green
                                elif 'active' in status:
                                    bg = '#d1ecf1' # Soft Blue
                                elif 'eliminated' in status:
                                    bg = '#f8d7da' # Light Red
                                else:
                                    bg = ''
                                
                                # 4. Apply Background and ensure text is readable (black)
                                if bg:
                                    styles.iloc[idx, :] = f'background-color: {bg}; color: #000000;'
                                    
                            return styles

                        # DISPLAY: Keep 'Status' in the dataframe but hide it from the UI
                        st.dataframe(
                            df_with_total.style.apply(style_roster_internal, axis=None),
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Status": None # THIS IS THE KEY: Hides column but leaves data for styling
                            }
                        )
                    else:
                        st.write("No picks recorded.")
        else:
            st.warning("Could not find the 'Contestant' column.")
