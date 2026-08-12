from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from race_parser import parse_race
from class_model import (
    analyse_race,
    _current_reference_level,
    _effective_level,
    _reference_label,
    _family,
)

st.set_page_config(
    page_title='Class-Only Race Analyser',
    page_icon='🏇',
    layout='wide',
    initial_sidebar_state='collapsed',
)

st.markdown(
    '''
<style>
:root { --mobile-max: 1500px; }
.block-container {
  padding-top: .9rem;
  padding-bottom: 2.5rem;
  max-width: var(--mobile-max);
}
.stTabs [data-baseweb="tab-list"] {
  overflow-x: auto;
  flex-wrap: nowrap;
  scrollbar-width: thin;
  gap: .2rem;
  padding-bottom: .15rem;
}
.stTabs [data-baseweb="tab"] {
  white-space: nowrap;
  flex: 0 0 auto;
}
.stTabs [data-baseweb="tab-panel"] {
  padding-top: .75rem;
}
div[data-testid="stDataFrame"] { width: 100%; }
.small-note { font-size: .86rem; opacity: .78; }
.mobile-card-title { font-size: 1.08rem; font-weight: 700; margin-bottom: .15rem; }
.mobile-muted { font-size: .9rem; opacity: .78; }
.mobile-rank { font-size: 1.25rem; font-weight: 800; }
[data-testid="stMetricValue"] { font-size: 1.15rem; }

/* Larger touch targets */
.stButton > button, .stDownloadButton > button {
  min-height: 2.75rem;
  border-radius: .65rem;
}

@media (max-width: 760px) {
  .block-container {
    padding-left: .55rem;
    padding-right: .55rem;
    padding-top: .45rem;
  }
  h1 { font-size: 1.55rem !important; line-height: 1.15 !important; }
  h2, h3 { font-size: 1.16rem !important; }
  p, li { font-size: .94rem; }
  .stTabs [data-baseweb="tab"] { font-size: .82rem; padding-left: .65rem; padding-right: .65rem; }
  div[data-testid="stDataFrame"] { overflow-x: auto; }
  [data-testid="stMetricValue"] { font-size: 1.02rem; }
  [data-testid="column"] { min-width: 0 !important; }
  .mobile-card-title { font-size: 1rem; }
}
</style>
''',
    unsafe_allow_html=True,
)

st.title('🏇 Class-Only Race Analyser')
st.caption(
    'Mobile-ready Streamlit edition for Racing & Sports race pages. '
    'France and Australia use separate class semantics; odds are display-only.'
)

# -----------------------------------------------------------------------------
# State
# -----------------------------------------------------------------------------
for key, default in {
    'raw_text': '',
    'input_area': '',
    'race': None,
    'analyses': None,
    'uploader_nonce': 0,
    'last_upload_sig': '',
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def clear_race_input():
    """Clear text, upload widget and current analysis."""
    st.session_state.raw_text = ''
    st.session_state.input_area = ''
    st.session_state.race = None
    st.session_state.analyses = None
    st.session_state.last_upload_sig = ''
    st.session_state.uploader_nonce += 1


def _analysis_dataframe(analyses):
    return pd.DataFrame([
        {
            'Rank': a.rank,
            'No.': a.number,
            'Horse': a.horse,
            'Odds': a.odds,
            'Relevant Previous Class': a.relevant_previous_class,
            'Today vs Proven Level': a.movement,
            'Class Assessment': a.assessment,
            'Class Score /10': a.score,
        }
        for a in analyses
    ])


def _render_prediction_card(a):
    with st.container(border=True):
        c1, c2 = st.columns([4, 1.35])
        with c1:
            st.markdown(
                f'<div class="mobile-rank">#{a.rank} · {a.number}. {a.horse}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(f'**{a.movement}**')
        with c2:
            st.metric('Score', f'{a.score:.1f}/10')

        m1, m2 = st.columns(2)
        m1.metric('Odds', f'{a.odds:.2f}' if a.odds is not None else 'N/A')
        m2.metric('Confidence', a.confidence)
        st.markdown(f'**Assessment:** {a.assessment}')
        st.markdown(f'<div class="mobile-muted">{a.relevant_previous_class}</div>', unsafe_allow_html=True)
        with st.expander('Why this score'):
            st.write(a.explanation)
            if a.evidence_lines:
                st.markdown('**Evidence used**')
                for line in a.evidence_lines:
                    st.markdown(f'- {line}')


input_tab, pred_tab, explain_tab, parsed_tab, feedback_tab, method_tab, deploy_tab = st.tabs([
    '1. Input',
    '2. Predictions',
    '3. Explanations',
    '4. Parsed Data',
    '5. Model Updates',
    '6. Method',
    '7. Mobile / Deploy',
])

# -----------------------------------------------------------------------------
# Input
# -----------------------------------------------------------------------------
with input_tab:
    st.subheader('Race input')
    st.info(
        'Paste the full Racing & Sports race page, or upload a .txt/.md copy. '
        'Navigation/footer clutter is ignored and scratched/NON PARTANT runners are excluded.'
    )

    uploaded = st.file_uploader(
        'Upload Racing & Sports text/markdown',
        type=['txt', 'md'],
        key=f"race_uploader_{st.session_state.uploader_nonce}",
    )
    if uploaded is not None:
        raw_bytes = uploaded.getvalue()
        sig = f'{uploaded.name}:{len(raw_bytes)}:{hashlib.sha1(raw_bytes).hexdigest()}'
        if sig != st.session_state.last_upload_sig:
            try:
                decoded = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                decoded = raw_bytes.decode('latin-1')
            st.session_state.raw_text = decoded
            st.session_state.input_area = decoded
            st.session_state.last_upload_sig = sig

    raw = st.text_area(
        'Paste race data here',
        height=360,
        key='input_area',
        placeholder='Paste the full Racing & Sports race page here…',
    )
    st.session_state.raw_text = raw

    b1, b2 = st.columns(2)
    with b1:
        analyse = st.button('Analyse Race', type='primary', use_container_width=True)
    with b2:
        st.button('Clear', use_container_width=True, on_click=clear_race_input)

    if analyse:
        if not raw.strip():
            st.error('Paste or upload a race page first.')
        else:
            race = parse_race(raw)
            analyses = analyse_race(race)
            st.session_state.race = race
            st.session_state.analyses = analyses
            if not race.runners:
                st.error('No active runners were parsed. Check that the field and horse names are included.')
            else:
                ref = _current_reference_level(race)
                st.success(f'Parsed {len(race.runners)} active runners. Open the Predictions tab.')
                st.write(
                    f"**Race:** {race.race_no or '-'} — {race.name or 'Unnamed race'}  \n"
                    f"**Type:** {race.race_type or '-'} · **Distance:** {race.distance_m or '-'}m · "
                    f"**Country:** {race.country or '-'}"
                )
                if ref is not None:
                    st.write(
                        f"**Effective class-strength benchmark:** {ref:.2f} "
                        f"({_reference_label(race, ref)})"
                    )

# -----------------------------------------------------------------------------
# Prediction output
# -----------------------------------------------------------------------------
with pred_tab:
    race = st.session_state.race
    analyses = st.session_state.analyses
    if not race or not analyses:
        st.warning('Analyse a race in the Input tab first.')
    else:
        st.subheader(f"Race {race.race_no or ''} — {race.name}")
        ref = _current_reference_level(race)
        proxy = f" · Strength {ref:.2f} ({_reference_label(race, ref)})" if ref is not None else ''
        st.caption(
            f"{race.race_type} · {race.distance_m or '-'}m {race.surface} {race.going} · "
            f"Prize {race.prize_raw or '-'}{proxy}"
        )

        top = analyses[0]
        s1, s2, s3 = st.columns(3)
        s1.metric('Top class pick', f'{top.number}. {top.horse}')
        s2.metric('Top score', f'{top.score:.1f}/10')
        s3.metric('Active runners', len(analyses))

        view_mode = st.radio(
            'Prediction view',
            ['📱 Mobile cards', '📊 Sortable table'],
            horizontal=True,
            key='prediction_view_mode',
        )

        df = _analysis_dataframe(analyses)
        if view_mode.startswith('📱'):
            for a in analyses:
                _render_prediction_card(a)
        else:
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                height=min(720, 84 + 36 * len(df)),
                column_config={
                    'Odds': st.column_config.NumberColumn('Odds', format='%.2f'),
                    'Class Score /10': st.column_config.ProgressColumn(
                        'Class Score /10', min_value=0, max_value=10, format='%.1f'
                    ),
                },
            )
            st.markdown(
                '<div class="small-note">Tap/click a column header to sort. Odds are numeric and have zero influence on the class score.</div>',
                unsafe_allow_html=True,
            )

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            'Export prediction table CSV',
            csv,
            file_name=f'Race_{race.race_no or "X"}_class_predictions.csv',
            mime='text/csv',
            use_container_width=True,
        )

        st.markdown('### Pure class order')
        st.write(' → '.join(f"**{a.number}. {a.horse} ({a.score:.1f})**" for a in analyses))

# -----------------------------------------------------------------------------
# Explanations - selectbox is much easier on a phone than 10-16 nested tabs
# -----------------------------------------------------------------------------
with explain_tab:
    race = st.session_state.race
    analyses = st.session_state.analyses
    if not race or not analyses:
        st.warning('Analyse a race in the Input tab first.')
    else:
        st.subheader('Horse-by-horse explanation')
        labels = [f'{a.rank}. {a.number}. {a.horse}' for a in analyses]
        selected_label = st.selectbox('Choose a horse', labels)
        a = analyses[labels.index(selected_label)]

        with st.container(border=True):
            st.markdown(f'### #{a.rank} · {a.number}. {a.horse}')
            m1, m2 = st.columns(2)
            m1.metric('Class Score', f'{a.score:.1f}/10')
            m2.metric('Odds', f'{a.odds:.2f}' if a.odds is not None else 'N/A')
            m3, m4 = st.columns(2)
            m3.metric('Rank', f'#{a.rank}')
            m4.metric('Confidence', a.confidence)
            st.markdown(f'**Movement:** {a.movement}')
            st.markdown(f'**Relevant class history:** {a.relevant_previous_class}')
            st.markdown(f'**Proven level:** {a.proven_level}')
            st.markdown(f'**Assessment:** {a.assessment}')
            st.markdown('#### Explanation')
            st.write(a.explanation)
            if a.evidence_lines:
                st.markdown('#### Evidence used')
                for line in a.evidence_lines:
                    st.markdown(f'- {line}')

# -----------------------------------------------------------------------------
# Parsed data
# -----------------------------------------------------------------------------
with parsed_tab:
    race = st.session_state.race
    if not race:
        st.warning('Analyse a race in the Input tab first.')
    else:
        race_meta, runner_data = st.tabs(['Race Metadata', 'Runner Past Races'])
        with race_meta:
            ref = _current_reference_level(race)
            meta = {
                'Race No': race.race_no,
                'Time': race.time,
                'Name': race.name,
                'Age': race.age,
                'Country': race.country,
                'Race Type': race.race_type,
                'Parsed French Class': race.current_class,
                'Benchmark Rating': getattr(race, 'benchmark_rating', None),
                'Grade Label': getattr(race, 'grade_label', ''),
                'Effective Strength': round(ref, 3) if ref is not None else None,
                'Race Family': _family(race.race_type, race.is_handicap, race.is_claiming),
                'Discipline': race.discipline,
                'Prize': race.prize_raw,
                'Prize Amount': getattr(race, 'prize_amount', None) or race.prize_eur,
                'Currency': race.prize_currency,
                'Distance': race.distance_m,
                'Surface': race.surface,
                'Going': race.going,
                'Active Runner Count': len(race.runners),
            }
            st.dataframe(pd.DataFrame([meta]), use_container_width=True, hide_index=True)

        with runner_data:
            runner_labels = [f'{r.number}. {r.horse}' for r in race.runners]
            selected_runner = st.selectbox('Choose runner', runner_labels, key='parsed_runner_selector')
            r = race.runners[runner_labels.index(selected_runner)]
            st.write(f"**Current odds:** {format(r.odds, '.2f') if r.odds is not None else 'N/A'}")
            pr = []
            for x in r.past_races:
                eff = _effective_level(x)
                pr.append({
                    'Date': x.date_raw,
                    'Finish': x.finish_status or x.finish_pos,
                    'Field': x.field_size,
                    'Margin': x.margin,
                    'Track': x.track,
                    'Race': x.race_desc,
                    'Class / Grade': x.grade_label or x.level_label,
                    'BM': getattr(x, 'benchmark_rating', None),
                    'Strength': round(eff, 3) if eff is not None else None,
                    'Prize': x.prize_raw,
                    'Distance': x.distance_m,
                    'Surface': x.surface,
                    'Going': x.going,
                })
            st.dataframe(pd.DataFrame(pr), use_container_width=True, hide_index=True, height=460)

# -----------------------------------------------------------------------------
# Existing model notes
# -----------------------------------------------------------------------------
with feedback_tab:
    st.subheader('Model updates — France + Australia')
    st.markdown('''
**Australian support (v4 model):**
- BM ratings are parsed directly (`BM52`, `BM56`, `BM62`, `BM64`, `BM66`, `BM70`, `BM78`, etc.);
- `BM0-X` is treated by its upper benchmark ceiling with a small allowance;
- Australian `CL1/CL2/CL3` is treated as a restricted-win ladder, **not** as French CL numbering;
- AUD prize money is parsed and used as a modest within-grade strength proxy;
- Maiden, Open, Listed/Group and generic Australian purse fallbacks are recognised;
- France and Australia use separate class semantics while keeping the same 0–10 class-only output scale.

**French result calibration retained:** the Deauville feedback and the earlier Vittel worked examples remain built into the supplied v4 model. Odds remain display-only.
''')
    st.info(
        'This package preserves the supplied class-only model. The mobile conversion changes the interface and deployment packaging, not the scoring formula.'
    )

with method_tab:
    st.subheader('Class scoring method')
    st.markdown('''
1. **Country-specific class semantics come first.** France and Australia are interpreted differently.
2. **Prize money is a class-strength proxy**, but does not override explicit Australian BM ratings.
3. **Race type matters:** handicap, claiming, conditions, maiden and open races are not treated as identical.
4. **Actual competitiveness matters more than entry.** Higher-grade exposure only earns strong credit when the horse performed there.
5. **Field size, margin and recency** help determine how convincing a previous class performance was.
6. **Latest class and proven ceiling are separate concepts.**
7. **Jump disciplines remain separated** for French hurdle/steeple analysis.
8. **Scratched runners are automatically removed.**
9. **Odds have zero weight** and are only displayed/sorted.
''')
    st.warning(
        'This is intentionally a class-only model. Speed, fitness, distance suitability, going suitability, pace, draw, jockey and trainer are not part of the score in this version.'
    )

# -----------------------------------------------------------------------------
# Deployment help inside the app
# -----------------------------------------------------------------------------
with deploy_tab:
    st.subheader('Use this app on your phone')
    st.markdown('''
This edition is designed to be hosted on **Streamlit Community Cloud** from a **GitHub repository**.

**Repository entry point:** `app.py`

After deployment, open the resulting `streamlit.app` address in your phone browser. You can then save the page to your phone's home screen using your browser's normal **Add to Home Screen / Install** option when available.
''')
    st.markdown('### GitHub / Streamlit deployment checklist')
    st.markdown('''
1. Create a new GitHub repository.
2. Upload **the contents of this package** to the repository root, including the hidden `.streamlit` folder.
3. Sign in to Streamlit Community Cloud with GitHub.
4. Choose **Create app** and select your repository and branch.
5. Set the main file / entry point to **`app.py`**.
6. Deploy the app.
7. Open the generated Streamlit URL on your phone and bookmark or add it to the home screen.
''')
    st.success('No Windows run.bat is needed on the phone. The included run.bat is only for running the same app locally on a Windows computer.')
