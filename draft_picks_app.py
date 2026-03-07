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
# This also saves your local computer/GitHub from unnecessary reads.
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
            # Row 0 is Timestamp, Row 1 is Headers, Row 2+ is Data
            leaderboard_df = pd.DataFrame(lb_raw[2:], columns=lb_raw[1])
            # Clean up: Remove empty columns or duplicates
            leaderboard_df = leaderboard_df.loc[:, ~leaderboard_df.columns.duplicated()]
            leaderboard_df = leaderboard_df.loc[:, leaderboard_df.columns != '']
            
            # Display the timestamp from the sheet
            st.caption(f"📊 {lb_raw[0][0]}")
        else:
            leaderboard_df = pd.DataFrame()

        # --- LOAD PLAYER STATS ---
        ps_worksheet = sh.worksheet("PlayerStats")
        ps_raw = ps_worksheet.get_all_values()
        
        if len(ps_raw) > 1:
            # Row 1 is Headers for Player Stats
            player_stats_df = pd.DataFrame(ps_raw[2:], columns=ps_raw[1])
        else:
            player_stats_df = pd.DataFrame()

        # --- LOAD PICKS (Sheet1) ---
        picks_worksheet = sh.worksheet("Sheet1")
        picks_raw = picks_worksheet.get_all_values()
        
        if len(picks_raw) > 0:
            picks_df = pd.DataFrame(picks_raw[1:], columns=picks_raw[0])
            picks_df = picks_df.loc[:, ~picks_df.columns.duplicated()]
        else:
            picks_df = pd.DataFrame()
            
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
        leaderboard_df = pd.DataFrame()
        player_stats_df = pd.DataFrame()
        picks_df = pd.DataFrame()

    return seeds_df, rosters_df, leaderboard_df, picks_df, player_stats_df

# Call the function once
seeds_df, rosters_df, leaderboard_df, picks_df = load_all_data()

# --- GOOGLE SHEETS CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- APP TABS ---
tab1, tab2, tab3 = st.tabs(["📝 Enter Player Picks", "🏆 Leaderboard", "📊 Player Stats"])

# 1. Set your deadline (Year, Month, Day, Hour, Minute)
# Example: March 19, 2026, at 11:00 AM Central
deadline = datetime.datetime(2026, 3, 20, 11, 0, 0)

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
    st.title("🏆 Current Standings")
    
    try:
        if not leaderboard_df.empty:
            # 1. Define the ideal tournament order
            ideal_order = ['Contestant', '1st Round', '2nd Round', 'Sweet 16', 'Elite 8', 'Final Four', "Nat'l Champ", 'Total']
            
            # 2. Safety Check: Only include columns that actually exist in your Google Sheet right now
            # This prevents the "KeyError" before the Sweet 16 starts
            display_cols = [c for c in ideal_order if c in leaderboard_df.columns]
            
            # 3. Data Cleaning: Ensure 'Total' is treated as a number so sorting works correctly
            if 'Total' in leaderboard_df.columns:
                leaderboard_df['Total'] = pd.to_numeric(leaderboard_df['Total'], errors='coerce').fillna(0)
                leaderboard_final = leaderboard_df.sort_values(by='Total', ascending=False)
            else:
                leaderboard_final = leaderboard_df

            # 4. Display the table
            st.dataframe(
                leaderboard_final[display_cols], 
                use_container_width=True, 
                hide_index=True
            )
        else:
            st.info("The leaderboard is currently empty. It will populate once the first round begins on March 20th!")
            
    except Exception as e:
        st.error(f"Leaderboard Display Error: {e}")

with tab3:
    st.title("📊 Individual Player Points")
    
    try:
        # Note: player_stats_df is now loaded in your main load_all_data() function 
        # using the safer get_all_values() method to avoid duplicate header errors.
        
        if not player_stats_df.empty:
            # Define ideal order for player stats
            ps_ideal = ["Player Name", "Team", "1st Round", "2nd Round", "Sweet 16", "Elite 8", "Final Four", "Nat'l Champ", "Total"]
            ps_display = [c for c in ps_ideal if c in player_stats_df.columns]
            
            # Ensure Total is numeric for sorting
            if 'Total' in player_stats_df.columns:
                player_stats_df['Total'] = pd.to_numeric(player_stats_df['Total'], errors='coerce').fillna(0)
                player_stats_final = player_stats_df.sort_values(by="Total", ascending=False)
            else:
                player_stats_final = player_stats_df

            st.dataframe(
                player_stats_final[ps_display], 
                use_container_width=True, 
                hide_index=True
            )
        else:
            st.info("Player stats will be available here starting March 20th.")
            
    except Exception as e:
        st.error(f"Stats Error: {e}")
