from typing import TypedDict, Optional


class LegalAgentState(TypedDict):

    user_input: str              # Structured prompt from the UI form
    case_type: str               # e.g. "employment", "consumer", "property"
    client_name: str             # Victim / client name
    recipient_name: str          # Accused / opposite party name
    advocate_name: str           # Drafting advocate's name
    notice_date: str             # Formatted date string

    # Email configuration (set by UI checkbox) ─────────────────────────────
    send_email: bool             # Whether to trigger the email node
    recipient_email: str         # Email address of the recipient/notice target

    # Populated by retrieval_node ───────────────────────────────────────────
    retrieved_context: str       # Concatenated relevant legal precedents from Chroma

    # Populated by generation_node ─────────────────────────────────────────
    generated_notice: str        # The full generated legal notice text

    # Populated by email_node ───────────────────────────────────────────────
    email_summary: str           # Internal 3-bullet summary
    email_body: str              # The drafted cover email body
    email_sent: bool             # True if Gmail send succeeded

    # Error handling ────────────────────────────────────────────────────────
    error: Optional[str]         # Set by any node on failure; checked by UI
