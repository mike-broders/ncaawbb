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
        # Re-authorize and open inside the function to be safe
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID) # Make sure SHEET_ID is your long string
        
        # Explicitly get the worksheets
        leaderboard_df = pd.DataFrame(sh.worksheet("Leaderboard").get_all_records())
        picks_df = pd.DataFrame(sh.worksheet("Sheet1").get_all_records())
        
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
        # Provide empty dataframes so the rest of the app doesn't crash
        leaderboard_df = pd.DataFrame(columns=['Contestant', 'Total Points', 'Last Updated'])
        picks_df = pd.DataFrame()

    return seeds_df, rosters_df, leaderboard_df, picks_df

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

        st.markdown("### Rules: Select 8 players to maximize your point total. Each player must come from a unique Seed (1-16).")

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
                    # RE-AUTHORIZE GSPREAD (Ensures the 'client' is fresh)
                    gc = gspread.authorize(creds)
                    sh = gc.open_by_key(SHEET_ID)
                    target_sheet = sh.worksheet("Sheet1")

                    # Prepare the data row
                    # 1. Start with the name
                    row_data = [user_name]
                    # 2. Add player, team, and seed for all 8 slots
                    for p in user_selections:
                        row_data.extend([p['Player'], p['Team'], p['Seed']])

                    # Append the row
                    target_sheet.append_row(row_data)
                    
                    st.success(f"🎉 Successfully submitted! Good luck, {user_name}!")
                    st.balloons()
                    st.cache_data.clear() # Clears the leaderboard cache so it updates
                    
                except Exception as e:
                    st.error(f"Error submitting to Google Sheets: {e}")
                
with tab2:
    st.title("🏆 Current Standings")
    if not leaderboard_df.empty:
        # If your local leaderboard_df was loaded in the load_all_data() function
        st.dataframe(leaderboard_df, use_container_width=True, hide_index=True)
    else:
        st.write("No standings available yet. Points will update once the games begin!")

with tab3:
    st.title("📊 Individual Player Points")
    try:
        # Use the gspread method to read the sheet
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)
        stats_data = sh.worksheet("PlayerStats").get_all_records()
        df_stats = pd.DataFrame(stats_data)
        
        if not df_stats.empty:
            st.dataframe(df_stats.sort_values(by="Points", ascending=False), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Stats Error: {e}")
