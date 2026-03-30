import streamlit as st
import re
from datetime import date

from src.utils.config import validate_environment
from src.graph.graph_builder import build_legal_graph
from src.graph.state import LegalAgentState
from src.gmail_service import gmail_configured


# Legal notice renderer ────────────────────────────────────────────────────

def render_legal_notice(raw_text: str) -> str:
    import html as html_module

    lines = raw_text.split("\n")

    # Section headings that should be bold + spaced
    SECTION_HEADINGS = {
        "WITHOUT PREJUDICE",
        "FORMAL LEGAL NOTICE",
        "BODY OF THE NOTICE",
        "BODY OF NOTICE",
        "LEGAL DEMAND",
        "LEGAL DEMANDS",
        "COMPLIANCE PERIOD",
        "CONSEQUENCES OF NON-COMPLIANCE",
        "YOURS FAITHFULLY",
        "YOURS TRULY",
    }

    # Center-aligned header lines (first block of notice)
    CENTER_LINES = {"WITHOUT PREJUDICE", "FORMAL LEGAL NOTICE"}

    processed = []
    in_header = True   # First few lines before TO: block are centered
    blank_count = 0

    for raw_line in lines:
        line = raw_line.strip()

        # Skip pure separator lines (dashes, equals)
        if re.match(r"^[-=─═]{4,}$", line):
            continue

        # Collapse excess blank lines — max 1 consecutive blank
        if line == "":
            blank_count += 1
            if blank_count <= 1:
                processed.append("")
            continue
        else:
            blank_count = 0

        escaped = html_module.escape(line)

        upper = line.upper()

        # Header block ───────────────────────────────────────────────────
        if upper in CENTER_LINES:
            processed.append(f'<div class="nl-center nl-heading">{escaped}</div>')
            continue

        # Detect when header ends (TO: line)
        if upper.startswith("TO:") or upper.startswith("TO "):
            in_header = False

        # Section headings ───────────────────────────────────────────────
        if upper in SECTION_HEADINGS:
            processed.append(f'<div class="nl-section">{escaped}</div>')
            continue

        # FROM / TO / DATE / SUBJECT block ──────────────────────────────
        if re.match(r"^(TO|FROM|DATE|SUBJECT)\s*:", line, re.IGNORECASE):
            key, _, val = line.partition(":")
            escaped_key = html_module.escape(key.strip())
            escaped_val = html_module.escape(val.strip())
            processed.append(
                f'<div class="nl-meta"><span class="nl-meta-key">{escaped_key}:</span>'
                f'<span class="nl-meta-val">{escaped_val}</span></div>'
            )
            continue

        # Numbered main paragraphs: 1. / 2. / 3. / 4. ──────────────────
        m = re.match(r"^(\d+)\.\s+(.+)$", line)
        if m:
            num, text = m.group(1), html_module.escape(m.group(2))
            processed.append(
                f'<div class="nl-para"><span class="nl-para-num">{num}.</span>'
                f'<span class="nl-para-text">{text}</span></div>'
            )
            continue

        # Sub-paragraphs: 2(a). / 2(b). / 2a. / a) / b) ────────────────
        m = re.match(r"^(\d*\(?[a-zA-Z]\)?)[\.\)]\s+(.+)$", line)
        if m:
            ref, text = m.group(1), html_module.escape(m.group(2))
            processed.append(
                f'<div class="nl-sub"><span class="nl-sub-ref">{html_module.escape(ref)}.</span>'
                f'<span class="nl-sub-text">{text}</span></div>'
            )
            continue

        # Signature block: Sd/- ──────────────────────────────────────────
        if line.lower().startswith("sd/-") or line == "Sd/-":
            processed.append(f'<div class="nl-sig">{escaped}</div>')
            continue

        # Everything else — body text ────────────────────────────────────
        processed.append(f'<div class="nl-body">{escaped}</div>')

    # Join and wrap
    inner = "\n".join(processed)

    return f"""
<div class="notice-doc">
  <div class="notice-stamp">LEGAL NOTICE</div>
  <div class="notice-body">
    {inner}
  </div>
</div>
"""


# -- Legal references extractor + renderer --

def parse_legal_references(context):
    if not context or 'No relevant precedents' in context:
        return {}
    laws = []
    forum = ''
    urgency = 'medium'
    categories = []
    blocks = re.split(r'\[Reference \d+', context)
    for block in blocks:
        if not block.strip():
            continue
        cat_m = re.search(r'[^\w]([A-Z_]{3,})\s*/\s*([a-z_]+)\]', block)
        if cat_m:
            cat = cat_m.group(1).replace('_', ' ').title()
            if cat not in categories:
                categories.append(cat)
        lm = re.search(r'Applicable Laws?\s*:\s*(.+?)(?=Key Demands?|Precedent|Forum|Limitation|$)',
                        block, re.IGNORECASE | re.DOTALL)
        if lm:
            for raw in re.split(r',\s*\n?|\n', lm.group(1).strip()):
                raw = raw.strip().rstrip(',.')
                if len(raw) < 5:
                    continue
                sm = re.search(r'\(([^)]+)\)', raw)
                sections, act_name = [], raw
                if sm:
                    sections = re.findall(
                        r'(?:Section|Rule|Article|Order)?\s*([0-9]+[A-Za-z]*(?:\([a-z0-9]+\))?)',
                        sm.group(1), re.IGNORECASE)
                    sections = [s.strip() for s in sections if s.strip()][:4]
                    act_name = raw[:sm.start()].strip().rstrip('(')
                act_name = act_name.strip()
                if act_name and not any(l['name'] == act_name for l in laws):
                    laws.append({'name': act_name, 'sections': sections})
        fm = re.search(r'Forum\s*:\s*(.+?)(?=Limitation|Note|$)', block, re.IGNORECASE | re.DOTALL)
        if fm and not forum:
            forum = fm.group(1).strip().split('.')[0].strip().rstrip(',')
        um = re.search(r'"urgency":\s*"([^"]+)"', block)
        if um and urgency == 'medium':
            urgency = um.group(1)
    seen, deduped = set(), []
    for law in laws:
        if law['name'] not in seen and len(law['name']) > 4:
            seen.add(law['name']); deduped.append(law)
    return {'laws': deduped[:6], 'forum': forum, 'urgency': urgency, 'categories': categories[:3]}


def render_legal_references(refs):
    if not refs or not refs.get('laws'):
        return
    laws = refs.get('laws', [])
    forum = refs.get('forum', '')
    urgency = refs.get('urgency', 'medium')
    categories = refs.get('categories', [])
    urg_map = {
        'critical': ('#7f1d1d', '#fca5a5', 'Critical'),
        'high':     ('#78350f', '#fcd34d', 'High Priority'),
        'medium':   ('#1e3a5f', '#93c5fd', 'Standard'),
        'low':      ('#14532d', '#86efac', 'Low'),
    }
    urg_bg, urg_color, urg_label = urg_map.get(urgency, urg_map['medium'])
    badges_html = ''
    for law in laws:
        act = law['name']
        sec_pills = ''.join([
            f'<span style="display:inline-block;background:#1a2540;color:#c8a86b;'
            f'font-size:0.65rem;font-weight:500;padding:2px 7px;border-radius:3px;'
            f'border:1px solid #c8a86b40;margin-left:5px;font-family:monospace;'
            f'white-space:nowrap;">S.{s}</span>'
            for s in law['sections']
        ])
        badges_html += (
            f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;'
            f'padding:8px 12px;background:#0d1220;border:1px solid #1e2a40;'
            f'border-left:3px solid #c8a86b;border-radius:0 6px 6px 0;margin-bottom:6px;">'
            f'<span style="font-family:Times New Roman,serif;font-size:0.82rem;'
            f'font-weight:600;color:#d4c5a0;flex:1;min-width:160px;">{act}</span>'
            f'<div style="display:flex;gap:4px;flex-wrap:wrap;">{sec_pills}</div></div>'
        )
    forum_html = ''
    if forum:
        forum_html = (
            f'<div style="display:flex;align-items:center;gap:8px;margin-top:10px;'
            f'padding:7px 12px;background:#0a1520;border:1px solid #1e2a40;border-radius:6px;">'
            f'<span style="font-size:0.7rem;letter-spacing:0.12em;color:#5c6478;'
            f'text-transform:uppercase;min-width:42px;">Forum</span>'
            f'<span style="font-size:0.8rem;color:#8a9ab8;font-family:Times New Roman,serif;">'
            f'{forum}</span></div>'
        )
    cat_tags = ''.join([
        f'<span style="font-size:0.65rem;letter-spacing:0.1em;text-transform:uppercase;'
        f'color:#5c6478;background:#0d0f14;border:1px solid #1e2330;'
        f'border-radius:4px;padding:2px 8px;">{c}</span>'
        for c in categories
    ])
    urg_badge = (
        f'<span style="font-size:0.65rem;font-weight:500;letter-spacing:0.1em;'
        f'text-transform:uppercase;background:{urg_bg};color:{urg_color};'
        f'border-radius:4px;padding:2px 8px;">{urg_label}</span>'
    )
    noun = 'act' if len(laws) == 1 else 'acts'
    header_html = (
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'margin-bottom:10px;flex-wrap:wrap;gap:6px;">'
        f'<div style="display:flex;align-items:center;gap:8px;">'
        f'<span style="font-size:0.65rem;font-weight:500;letter-spacing:0.18em;'
        f'text-transform:uppercase;color:#c8a86b;">Referenced Laws</span>'
        f'<span style="font-size:0.65rem;color:#2a2e3a;">{len(laws)} {noun} via RAG</span>'
        f'</div><div style="display:flex;gap:6px;flex-wrap:wrap;">'
        f'{cat_tags}{urg_badge}</div></div>'
    )
    st.markdown(
        f'<div style="background:#080c14;border:1px solid #1e2330;'
        f'border-top:2px solid #c8a86b;border-radius:0 0 8px 8px;'
        f'padding:14px 16px 12px;margin-bottom:16px;">'
        f'{header_html}{badges_html}{forum_html}</div>',
        unsafe_allow_html=True
    )


# Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Vidhi — AI Legal Intelligence",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600;700&family=Inter:wght@300;400;500&display=swap');

/* ── Base ── */
.stApp { background: #0d0f14; color: #c8cdd8; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #080a0e;
    border-right: 1px solid #1e2330;
}

/* ── Header ── */
.vidhi-header {
    text-align: center;
    padding: 2.5rem 0 1.5rem;
    border-bottom: 1px solid #1e2330;
    margin-bottom: 2rem;
}
.vidhi-wordmark {
    font-family: 'Cormorant Garamond', serif;
    font-size: 4rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    background: linear-gradient(135deg, #c8a86b 0%, #f0d898 45%, #b8924a 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1;
    margin-bottom: 0.4rem;
}
.vidhi-tagline {
    font-family: 'Inter', sans-serif;
    font-size: 0.7rem;
    font-weight: 300;
    letter-spacing: 0.35em;
    text-transform: uppercase;
    color: #5c6478;
    margin-bottom: 0.5rem;
}
.vidhi-rule {
    width: 60px;
    height: 1px;
    background: linear-gradient(90deg, transparent, #c8a86b, transparent);
    margin: 0.8rem auto 0;
}

/* ── Section labels ── */
.section-label {
    font-family: 'Inter', sans-serif;
    font-size: 0.65rem;
    font-weight: 500;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: #c8a86b;
    margin-bottom: 0.75rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #1e2330;
}

/* ── Input fields ── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > div {
    background: #111520 !important;
    border: 1px solid #1e2330 !important;
    border-radius: 6px !important;
    color: #c8cdd8 !important;
    font-family: 'Inter', sans-serif !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #c8a86b !important;
    box-shadow: 0 0 0 1px #c8a86b20 !important;
}
.stDateInput > div > div > input {
    background: #111520 !important;
    border: 1px solid #1e2330 !important;
    color: #c8cdd8 !important;
}

/* ── Primary button ── */
.stButton > button[kind="primary"],
.stButton > button {
    background: linear-gradient(135deg, #b8924a, #c8a86b) !important;
    color: #0d0f14 !important;
    border: none !important;
    border-radius: 6px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.08em !important;
    padding: 0.6rem 2rem !important;
    transition: opacity 0.2s !important;
}
.stButton > button:hover { opacity: 0.88 !important; }

/* ── Legal notice document ── */
.notice-doc {
    position: relative;
    background: #fdfbf5;
    border-left: 8px solid #b8924a;
    border-top: 1px solid #e8e0cc;
    border-right: 1px solid #e8e0cc;
    border-bottom: 1px solid #e8e0cc;
    border-radius: 0 2px 2px 0;
    margin-bottom: 1.5rem;
    overflow: hidden;
}
.notice-stamp {
    position: absolute;
    top: 18px;
    right: 18px;
    font-family: 'Inter', sans-serif;
    font-size: 0.55rem;
    font-weight: 500;
    letter-spacing: 0.22em;
    color: #b8924a;
    border: 1px solid #b8924a;
    padding: 3px 8px;
    border-radius: 2px;
    opacity: 0.6;
    text-transform: uppercase;
}
.notice-body {
    padding: 44px 52px 48px 48px;
    font-family: 'Times New Roman', Times, serif;
    color: #111111;
}
/* Center block — WITHOUT PREJUDICE, FORMAL LEGAL NOTICE */
.nl-center {
    text-align: center;
    margin: 0 0 4px;
}
.nl-heading {
    font-size: 1rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #111111;
    margin-bottom: 2px;
}
/* TO / FROM / DATE / SUBJECT */
.nl-meta {
    display: flex;
    gap: 0;
    margin: 3px 0;
    font-size: 0.9rem;
    line-height: 1.5;
}
.nl-meta-key {
    font-weight: 700;
    min-width: 90px;
    flex-shrink: 0;
    color: #111111;
}
.nl-meta-val {
    color: #1a1a1a;
}
/* Section headings: BODY OF THE NOTICE, LEGAL DEMAND, etc. */
.nl-section {
    font-size: 0.88rem;
    font-weight: 700;
    font-family: 'Inter', sans-serif;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #111111;
    border-bottom: 1.5px solid #c8a86b;
    padding-bottom: 4px;
    margin: 22px 0 12px;
}
/* Numbered paragraphs: 1. 2. 3. */
.nl-para {
    display: flex;
    gap: 12px;
    margin: 10px 0;
    font-size: 0.91rem;
    line-height: 1.75;
    text-align: justify;
}
.nl-para-num {
    font-weight: 700;
    min-width: 22px;
    flex-shrink: 0;
    color: #111111;
    padding-top: 1px;
}
.nl-para-text {
    flex: 1;
    color: #1a1a1a;
}
/* Sub-paragraphs: 2(a). a). */
.nl-sub {
    display: flex;
    gap: 10px;
    margin: 5px 0 5px 36px;
    font-size: 0.91rem;
    line-height: 1.7;
    text-align: justify;
}
.nl-sub-ref {
    font-weight: 600;
    min-width: 32px;
    flex-shrink: 0;
    color: #333;
}
.nl-sub-text {
    flex: 1;
    color: #1a1a1a;
}
/* Signature block */
.nl-sig {
    font-size: 0.9rem;
    font-weight: 700;
    color: #111111;
    margin: 6px 0 2px;
}
/* Generic body line */
.nl-body {
    font-size: 0.91rem;
    line-height: 1.7;
    color: #1a1a1a;
    margin: 4px 0;
    text-align: justify;
}
/* Blank line spacer */
.nl-body:empty {
    height: 8px;
}

/* ── Status cards ── */
.status-card {
    background: #111520;
    border: 1px solid #1e2330;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.75rem;
}
.status-card.success { border-left: 3px solid #3d9970; }
.status-card.warning { border-left: 3px solid #c8a86b; }
.status-card.error   { border-left: 3px solid #c0392b; }

/* ── Sidebar pills ── */
.pipeline-step {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    margin-bottom: 0.4rem;
    font-size: 0.8rem;
    font-family: 'Inter', sans-serif;
    color: #5c6478;
    background: #0d0f14;
    border: 1px solid #1e2330;
    transition: all 0.3s;
}
.pipeline-step.active  { color: #c8a86b; border-color: #c8a86b40; background: #c8a86b08; }
.pipeline-step.done    { color: #3d9970; border-color: #3d997040; background: #3d997008; }
.pipeline-step.pending { color: #2a2e3a; border-color: #1e2330; }

/* ── Divider ── */
.gold-divider {
    border: none;
    height: 1px;
    background: linear-gradient(90deg, transparent, #c8a86b40, transparent);
    margin: 2rem 0;
}

/* ── Checkbox ── */
.stCheckbox > label { color: #8a91a4 !important; font-size: 0.875rem !important; }

/* ── Labels ── */
label, .stSelectbox label, .stTextInput label, .stTextArea label, .stDateInput label {
    color: #5c6478 !important;
    font-size: 0.75rem !important;
    font-weight: 400 !important;
    font-family: 'Inter', sans-serif !important;
    letter-spacing: 0.05em !important;
}
</style>
""", unsafe_allow_html=True)

# Session state ─────────────────────────────────────────────────────────────
defaults = {
    "last_notice": None,
    "email_summary": None,
    "email_body": None,
    "email_sent": False,
    "pipeline_stage": "idle",  # idle | retrieving | generating | emailing | done
    "last_error": None,
    "retrieved_context_preview": None,
    "legal_references": None,

}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚖️ VIDHI")
    st.markdown("---")

    # Pipeline status
    st.markdown("**Pipeline Status**")

    stages = {
        "retrieving": ("RAG Retrieval", "Fetching legal precedents"),
        "generating": ("LLM Generation", "Drafting notice"),
        "emailing":   ("Email Dispatch", "Sending via Gmail"),
        "done":       ("Complete", ""),
    }

    current = st.session_state.pipeline_stage
    stage_keys = list(stages.keys())

    for key, (label, sub) in stages.items():
        if current == "idle":
            css = "pending"
        elif current == key:
            css = "active"
        elif stage_keys.index(key) < stage_keys.index(current) if current in stage_keys else False:
            css = "done"
        else:
            css = "pending"

        icon = "●" if css == "active" else ("✓" if css == "done" else "○")
        st.markdown(
            f'<div class="pipeline-step {css}">{icon} &nbsp; {label}</div>',
            unsafe_allow_html=True
        )

    st.markdown("---")

    # RAG status indicator
    try:
        from src.rag.vector_store import load_vector_store
        load_vector_store()
        st.success("Knowledge base: Ready", icon="✅")
    except FileNotFoundError:
        st.warning("Knowledge base not built.\nRun `python setup_rag.py`", icon="⚠️")

    # Gmail status
    if gmail_configured():
        from src.gmail_service import gmail_authenticated, pre_authenticate
        if gmail_authenticated():
            st.success("Gmail: Connected ✅", icon="📧")
        else:
            st.warning("Gmail: Needs login", icon="📧")
            if st.button("🔐 Connect Gmail", use_container_width=True):
                with st.spinner("Opening browser for Google login..."):
                    if pre_authenticate():
                        st.success("Gmail connected!")
                        st.rerun()
                    else:
                        st.error("Gmail auth failed. Check credentials.json")
    else:
        st.info("Gmail: Not configured\n(add credentials.json)", icon="ℹ️")

    st.markdown("---")

    st.markdown("---")
    if st.button("↺  Reset Case", use_container_width=True):
        for k, v in defaults.items():
            st.session_state[k] = v
        st.rerun()

# Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="vidhi-header">
    <div class="vidhi-wordmark">VIDHI</div>
    <div class="vidhi-tagline">AI Legal Intelligence &nbsp;·&nbsp; RAG + LangGraph</div>
    <div class="vidhi-rule"></div>
</div>
""", unsafe_allow_html=True)

# Main form ─────────────────────────────────────────────────────────────────
def main():
    col_form, col_output = st.columns([1, 1], gap="large")

    with col_form:
        st.markdown('<div class="section-label">Case Details</div>', unsafe_allow_html=True)

        case_type = st.selectbox(
            "Legal Category",
            options=[
                "employment",
                "consumer",
                "property",
                "cheque_bounce",
                "defamation",
                "recovery",
                "medical_negligence",
                "cyber_crime",
                "ip",
                "family_law",
                "other",
            ],
            format_func=lambda x: {
                "employment":         "⚖ Employment Dispute",
                "consumer":           "🛒 Consumer Dispute",
                "property":           "🏠 Property Dispute",
                "cheque_bounce":      "🏦 Cheque Bounce (S.138 NI Act)",
                "defamation":         "📢 Defamation",
                "recovery":           "💰 Recovery of Money",
                "medical_negligence": "🏥 Medical Negligence",
                "cyber_crime":        "💻 Cyber Crime",
                "ip":                 "©️ Intellectual Property",
                "family_law":         "👨‍👩‍👧 Family Law / Maintenance",
                "other":              "📋 Other",
            }.get(x, x),
        )

        col1, col2 = st.columns(2)
        with col1:
            client_name = st.text_input("Client / Victim Name", placeholder="e.g. Rajesh Kumar")
        with col2:
            recipient_name = st.text_input("Opposite Party Name", placeholder="e.g. ABC Pvt. Ltd.")

        col3, col4 = st.columns(2)
        with col3:
            advocate_name = st.text_input("Advocate Name", placeholder="e.g. Priya Sharma, Adv.")
        with col4:
            notice_date = st.date_input("Date of Notice", value=date.today())

        st.markdown('<div class="section-label" style="margin-top:1.25rem">Statement of Facts</div>', unsafe_allow_html=True)
        facts = st.text_area(
            "Describe the grievance in detail",
            height=180,
            placeholder=(
                "Include: what happened, key dates, amounts involved, "
                "prior communications, and any evidence. "
                "The more detail you provide, the more precise the notice will be."
            ),
        )

        st.markdown('<div class="gold-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="section-label">Email Dispatch (Optional)</div>', unsafe_allow_html=True)

        email_disabled = not gmail_configured()
        send_email = st.checkbox(
            "Send notice via email after generation",
            disabled=email_disabled,
            help="Requires Gmail credentials. See .env.example for setup." if email_disabled else "",
        )
        recipient_email = ""
        if send_email:
            recipient_email = st.text_input(
                "Recipient's Email Address",
                placeholder="accused@example.com",
            )

        st.markdown("<br>", unsafe_allow_html=True)
        generate_clicked = st.button("⚖ Generate Legal Notice", use_container_width=True)

    # Generation logic ──────────────────────────────────────────────────────
    if generate_clicked:
        # Validation
        missing = []
        if not client_name:   missing.append("Client Name")
        if not recipient_name: missing.append("Opposite Party Name")
        if not advocate_name:  missing.append("Advocate Name")
        if not facts:          missing.append("Statement of Facts")
        if send_email and not recipient_email:
            missing.append("Recipient Email")

        if missing:
            with col_output:
                st.error(f"Please fill in: {', '.join(missing)}")
            return

        try:
            validate_environment()
        except EnvironmentError as e:
            with col_output:
                st.error(str(e))
            return

        # Build structured prompt
        structured_prompt = f"""ADVOCATE NAME: {advocate_name}
CLIENT NAME: {client_name}
RECIPIENT TYPE: {case_type.replace('_', ' ').title()}
RECIPIENT NAME AND DESIGNATION: {recipient_name}
DATE: {notice_date.strftime('%d %B %Y')}
LEGAL CATEGORY: {case_type}

FACTS AND GRIEVANCE:
{facts}
"""

        # Invoke LangGraph
        graph = build_legal_graph()

        initial_state: LegalAgentState = {
            "user_input": structured_prompt,
            "case_type": case_type,
            "client_name": client_name,
            "recipient_name": recipient_name,
            "advocate_name": advocate_name,
            "notice_date": notice_date.strftime("%d %B %Y"),
            "send_email": send_email,
            "recipient_email": recipient_email,
            "retrieved_context": "",
            "generated_notice": "",
            "email_summary": "",
            "email_body": "",
            "email_sent": False,
            "error": None,
        }

        with col_output:
            with st.spinner("⚖️ Running VIDHI pipeline…"):
                st.session_state.pipeline_stage = "retrieving"
                result = graph.invoke(initial_state)
                st.session_state.pipeline_stage = "done"

            # Store results
            st.session_state.last_notice = result.get("generated_notice", "")
            st.session_state.email_summary = result.get("email_summary", "")
            st.session_state.email_body = result.get("email_body", "")
            st.session_state.email_sent = result.get("email_sent", False)
            st.session_state.last_error = result.get("error")
            full_context = result.get("retrieved_context", "")
            st.session_state.retrieved_context_preview = full_context[:400]
            st.session_state.legal_references = parse_legal_references(full_context)

        st.rerun()

    # Output panel ──────────────────────────────────────────────────────────
    with col_output:
        if st.session_state.last_notice:
            st.markdown('<div class="section-label">Generated Notice</div>', unsafe_allow_html=True)

            # Warnings
            if st.session_state.last_error and "Warning" in str(st.session_state.last_error):
                st.warning(st.session_state.last_error, icon="⚠️")
            elif st.session_state.last_error:
                st.error(st.session_state.last_error, icon="🚨")

            # ── Legal References panel ────────────────────────────────────
            if st.session_state.legal_references:
                render_legal_references(st.session_state.legal_references)

            # ── Render notice as formatted legal document ──────────────────
            rendered_html = render_legal_notice(st.session_state.last_notice)
            st.markdown(rendered_html, unsafe_allow_html=True)

            # Actions row
            col_dl, col_gap = st.columns([1, 1])
            with col_dl:
                st.download_button(
                    "⬇ Download Notice (.txt)",
                    data=st.session_state.last_notice,
                    file_name=f"legal_notice_{date.today()}.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

            if st.session_state.email_sent:
                st.success("✅ Email dispatched to recipient via Gmail.")

            if st.session_state.email_summary:
                with st.expander("📋 Internal Summary + Email Draft", expanded=False):
                    st.markdown("**Internal Summary**")
                    st.markdown(st.session_state.email_summary)
                    if st.session_state.email_body:
                        st.markdown("---")
                        st.markdown("**Cover Email Draft**")
                        st.text(st.session_state.email_body)

        else:
            # Empty state
            st.markdown("""
<div style="
    height: 400px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    border: 1px dashed #1e2330;
    border-radius: 8px;
    color: #2a2e3a;
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.1rem;
    letter-spacing: 0.05em;
">
    <div style="font-size: 2rem; margin-bottom: 0.75rem; opacity: 0.3;">⚖</div>
    <div>Fill in case details and generate</div>
</div>
""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()