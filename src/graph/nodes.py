"""
The four nodes that make up the VIDHI LangGraph workflow.

Execution order:
  retrieval_node → generation_node → [decision] → email_node (optional) → END

"""
from langchain_groq import ChatGroq
from langchain_core.output_parsers import StrOutputParser

from .state import LegalAgentState
from ..rag.vector_store import get_retriever
from ..prompts import get_legal_prompt_template, get_email_draft_prompt
from ..utils.config import groq_api_key


#  LLM  ────────────────────────────────────────────────────────
def _get_llm(temperature: float = 0) -> ChatGroq:
    return ChatGroq(
        temperature=temperature,
        model_name="llama-3.3-70b-versatile",
        groq_api_key=groq_api_key(),
        max_tokens=4096,   
    )


# Node 1: Retrieval ─────────────────────────────────────────────────────────

def retrieval_node(state: LegalAgentState) -> dict:
    """
    Queries Chroma vector store for relevant legal precedents from PDFs.
    If no relevant documents are found, flags context as insufficient.
    """
    try:
        retriever = get_retriever(k=5)
        docs = retriever.invoke(state["user_input"])

        if not docs:
            return {
                "retrieved_context": "DATA INSUFFICIENT: No relevant legal provisions found in the uploaded PDFs for this query.",
                "error": None,
            }

        context_parts = []
        for i, doc in enumerate(docs, 1):
            meta = doc.metadata
            source = meta.get('source', 'Unknown')
            page = meta.get('page', '?')
            header = f"[Reference {i} — Source: {source}, Page {page}]"
            context_parts.append(f"{header}\n{doc.page_content.strip()}")

        context = "\n\n" + "\n\n".join(context_parts)

        return {"retrieved_context": context, "error": None}

    except FileNotFoundError as e:
        # Vector store not built yet
        return {
            "retrieved_context": "DATA INSUFFICIENT: Knowledge base not built. Run 'python setup_rag.py' first.",
            "error": f"[RAG Warning] {str(e)}",
        }
    except Exception as e:
        return {
            "retrieved_context": "DATA INSUFFICIENT: Retrieval failed.",
            "error": f"[Retrieval Error] {str(e)}",
        }


# Node 2: Generation ────────────────────────────────────────────────────────

def generation_node(state: LegalAgentState) -> dict:
    """
    Generates the formal legal notice using the RAG-augmented prompt.
    Injects retrieved legal context into the {context} slot.

    """
    try:
        llm = _get_llm(temperature=0)
        prompt = get_legal_prompt_template()
        chain = prompt | llm | StrOutputParser()

        # Pass context as-is — if it says DATA INSUFFICIENT, the prompt
        # instructs the LLM to output the insufficient data message
        context = state.get("retrieved_context", "").strip()
        if not context:
            context = "DATA INSUFFICIENT: No context was retrieved."

        notice = chain.invoke({
            "input": state["user_input"],
            "context": context,
        })

        # Safety check - if output is suspiciously short, warn
        if len(notice.strip()) < 300:
            return {
                "generated_notice": notice,
                "error": "[Warning] Notice appears incomplete. Check GROQ_API_KEY.",
            }

        return {"generated_notice": notice, "error": None}

    except Exception as e:
        return {
            "generated_notice": "",
            "error": f"[Generation Error] {str(e)}",
        }


# Node 3 (Decision): Conditional edge function ──────────────────────────────

def decision_node(state: LegalAgentState) -> str:
    """
    This is a conditional edge function, not a state-modifying node.
    LangGraph calls this after generation_node and uses the return
    value to pick the next node.

    Returns:
        "email"  — if user requested email AND a valid address is set
        "end"    — otherwise (notice-only flow)
    """
    if (
        state.get("send_email")
        and state.get("recipient_email", "").strip()
        and "@" in state.get("recipient_email", "")
        and not state.get("error")
    ):
        return "email"
    return "end"


# Node 4: Email ─────────────────────────────────────────────────────────────

def email_node(state: LegalAgentState) -> dict:
    """
    1. Drafts a 3-bullet internal summary + professional cover email.
    2. Sends the email via Gmail API directly.
    """
    try:
        # Step 1: Draft summary and email body
        llm = _get_llm(temperature=0.4)
        prompt = get_email_draft_prompt()
        chain = prompt | llm | StrOutputParser()

        draft = chain.invoke({
            "notice": state["generated_notice"],
            "recipient_name": state["recipient_name"],
            "client_name": state["client_name"],
        })

        # Parse the draft: split on PART 2 header to separate summary from email
        if "PART 2" in draft or "Cover Email" in draft.title():
            parts = draft.split("PART 2", 1) if "PART 2" in draft else draft.split("Cover Email", 1)
            summary = parts[0].replace("PART 1", "").replace("INTERNAL SUMMARY", "").strip()
            email_body = parts[1].strip() if len(parts) > 1 else draft
        else:
            summary = "Summary not parsed."
            email_body = draft

        # Step 2: Send via Gmail API directly
        email_sent = False
        try:
            from ..gmail_service import send_email
            subject = f"Legal Notice — Action Required | {state.get('case_type', 'Legal Matter').replace('_', ' ').title()}"
            full_body = f"{email_body}\n\n---\n\n{state['generated_notice']}"
            email_sent = send_email(
                to=state["recipient_email"],
                subject=subject,
                body=full_body,
            )
        except Exception as gmail_err:
            summary += f"\n\n[Gmail send failed: {str(gmail_err)}]"

        return {
            "email_summary": summary,
            "email_body": email_body,
            "email_sent": email_sent,
            "error": None,
        }

    except Exception as e:
        return {
            "email_summary": "",
            "email_body": "",
            "email_sent": False,
            "error": f"[Email Error] {str(e)}",
        }