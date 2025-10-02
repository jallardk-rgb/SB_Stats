import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import urllib3
import sys

# --- App Konfiguration ---
st.set_page_config(page_title="World Athletics Analyse", layout="wide")

# --- KERNELOGIK ---

DISCIPLINER = [
    ('sprints', '100-metres', 'both'), ('sprints', '200-metres', 'both'), ('sprints', '400-metres', 'both'),
    ('middlelong', '800-metres', 'both'), ('middlelong', '1500-metres', 'both'), ('middlelong', '5000-metres', 'both'),
    ('middlelong', '10000-metres', 'both'), ('middlelong', '3000-metres-steeplechase', 'both'),
    ('road-running', 'marathon', 'both'),
    ('race-walks', '20-kilometres-race-walk', 'both'), ('race-walks', '35-kilometres-race-walk', 'both'),
    ('hurdles', '100-metres-hurdles', 'women'), ('hurdles', '110-metres-hurdles', 'men'), ('hurdles', '400-metres-hurdles', 'both'),
    ('jumps', 'high-jump', 'both'), ('jumps', 'pole-vault', 'both'), ('jumps', 'long-jump', 'both'), ('jumps', 'triple-jump', 'both'),
    ('throws', 'shot-put', 'both'), ('throws', 'discus-throw', 'both'), ('throws', 'hammer-throw', 'both'), ('throws', 'javelin-throw', 'both'),
    ('combined-events', 'heptathlon', 'women'), ('combined-events', 'decathlon', 'men'),
]
SEASON = 2025

@st.cache_data(ttl=3600)
def run_full_process():
    """Kører hele processen med skrabning og analyse."""
    
    # DEL 1: SKRABNING
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
    
    all_data_frames = []
    progress_bar = st.progress(0, "Starter...")
    total_tasks = sum(1 for _, _, scope in DISCIPLINER for g in ['women', 'men'] if scope == g or scope == 'both')
    completed_tasks = 0
    status_text = st.empty()

    for gender in ['women', 'men']:
        for kategori, disciplin_slug, gender_scope in DISCIPLINER:
            if gender_scope != 'both' and gender_scope != gender:
                continue
            completed_tasks += 1
            status_text.info(f"Henter data for: {gender.upper()} - {disciplin_slug.replace('-', ' ').title()}")
            try:
                url = f"https://worldathletics.org/records/toplists/{kategori}/{disciplin_slug}/all/{gender}/senior/{SEASON}"
                response = requests.get(url, headers=headers, verify=False, timeout=30)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'lxml')
                    table = soup.find('table', class_='records-table')
                    if table:
                        table_headers = [header.text.strip() for header in table.find_all('th')]
                        rows = []
                        for row in table.find('tbody').find_all('tr'):
                            cols = [col.text.strip() for col in row.find_all('td')]
                            rows.append(cols)
                        df_scraped = pd.DataFrame(rows, columns=table_headers)
                        if not df_scraped.empty:
                            df_scraped['Discipline'] = disciplin_slug
                            df_scraped['Gender'] = gender
                            all_data_frames.append(df_scraped)
            except Exception as e:
                st.warning(f"Kunne ikke hente data for {disciplin_slug} ({gender}). Fejl: {e}")
            progress_bar.progress(completed_tasks / total_tasks, f"Henter data... ({completed_tasks}/{total_tasks})")

    status_text.empty()
    progress_bar.empty()

    if not all_data_frames:
        st.error("Ingen data blev fundet under skrabningen.")
        return None

    # DEL 2: ANALYSE
    combined_df = pd.concat(all_data_frames, ignore_index=True)
    
    # --- DEN ENDELIGE RETTELSE: Håndter duplikerede blanke kolonnenavne ---
    # Vi finder den første kolonne med et blankt navn og omdøber den til 'Nat'.
    cols = list(combined_df.columns)
    try:
        first_blank_index = cols.index('')
        cols[first_blank_index] = 'Nat'
        combined_df.columns = cols
        nat_col = 'Nat'
    except ValueError:
        # Hvis der ingen blank kolonne er, så led efter 'Nat' som normalt
        if 'Nat' in cols:
            nat_col = 'Nat'
        else:
            st.error("Kritisk Fejl: Kunne slet ikke finde nationalitetskolonnen.")
            return None
    # -------------------------------------------------------------------------

    combined_df['Rank'] = pd.to_numeric(combined_df['Rank'], errors='coerce')
    combined_df.dropna(subset=['Rank', 'Competitor', 'DOB', nat_col], inplace=True)
    combined_df['Rank'] = combined_df['Rank'].astype(int)

    # Beregninger
    combined_df['Placement_Points'] = 101 - combined_df['Rank']
    nation_points = combined_df.groupby(nat_col)['Placement_Points'].sum()
    combined_df['Athlete_ID'] = combined_df['Competitor'].str.strip() + '*' + combined_df['DOB'].str.strip()
    nation_unique_athletes = combined_df.groupby(nat_col)['Athlete_ID'].nunique()
    nation_disciplines = combined_df.groupby(nat_col)['Discipline'].nunique()

    # Samling af resultater
    summary_df = pd.DataFrame({
        'Total_Placement_Points': nation_points,
        'Unique_Athletes': nation_unique_athletes,
        'Disciplines_Count': nation_disciplines
    })
    summary_df.index.name = 'Nation'
    summary_df.sort_values(by=['Total_Placement_Points', 'Unique_Athletes'], ascending=[False, False], inplace=True)
    summary_df.fillna(0, inplace=True)
    
    for col in summary_df.columns:
        summary_df[col] = summary_df[col].astype(int)

    return summary_df

# --- App'ens brugerflade ---
st.title("📊 World Athletics - National Analyse")
st.write(f"Dette er en app til at hente og analysere de seneste top 100-lister for sæsonen **{SEASON}** fra World Athletics' hjemmeside.")

if 'result_df' not in st.session_state:
    st.session_state.result_df = None

if st.button("Hent og analyser seneste data", type="primary"):
    result = run_full_process()
    if result is not None:
        st.session_state.result_df = result
        st.success("Processen er fuldført!")

if st.session_state.result_df is not None:
    st.header("Resultater")
    st.dataframe(st.session_state.result_df, use_container_width=True)
    
    csv = st.session_state.result_df.to_csv(index=True).encode('utf-8')
    st.download_button(
       label="Download resultat som CSV",
       data=csv,
       file_name=f"nation_summary_{SEASON}.csv",
       mime="text/csv",
    )