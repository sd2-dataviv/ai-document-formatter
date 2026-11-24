from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Template

BUILTIN_TEMPLATES: list[dict] = [
    {
        "slug": "clean-structure",
        "name": "Clean & Structure",
        "icon": "sparkles",
        "description": "General clean-up: title, headings, paragraphs, lists and fixed typos.",
        "instructions": (
            "Produce a clean, general-purpose document. Add a concise H1 title (derive it from the "
            "content if none is given), group related content under H2/H3 headings, split walls of "
            "text into short paragraphs, convert enumerations into bullet or numbered lists, and "
            "turn any tabular data into Markdown tables."
        ),
    },
    {
        "slug": "business-report",
        "name": "Business Report",
        "icon": "briefcase",
        "description": "Executive summary, findings, recommendations and next steps.",
        "instructions": (
            "Format as a professional business report with these sections where the content allows: "
            "H1 title; 'Executive Summary' (3-5 sentences); 'Background'; 'Key Findings' (bulleted, "
            "with bold lead-ins); 'Analysis' (sub-headed as needed, tables for metrics); "
            "'Recommendations' (numbered); 'Next Steps'. Use a formal, concise tone."
        ),
    },
    {
        "slug": "meeting-minutes",
        "name": "Meeting Minutes",
        "icon": "users",
        "description": "Attendees, agenda, discussion, decisions and an action-item table.",
        "instructions": (
            "Format as meeting minutes: H1 with the meeting name; a short metadata block (Date, Time, "
            "Location, Facilitator) using bold labels — only fields present in the source; 'Attendees' "
            "list; 'Agenda' numbered list; 'Discussion' with an H3 per agenda item summarising points; "
            "'Decisions' bullet list; 'Action Items' as a table with columns Owner | Task | Due date "
            "(leave cells blank if unknown)."
        ),
    },
    {
        "slug": "formal-letter",
        "name": "Formal Letter",
        "icon": "mail",
        "description": "Classic business letter layout with salutation and sign-off.",
        "instructions": (
            "Format as a formal business letter: sender details (if present), date, recipient details, "
            "an optional bold 'Subject:' line, salutation, well-formed body paragraphs with a polite "
            "professional tone, closing (e.g. 'Sincerely,') and signature name. Do not use headings."
        ),
    },
    {
        "slug": "professional-email",
        "name": "Professional Email",
        "icon": "send",
        "description": "Clear subject line, greeting, concise body and call to action.",
        "instructions": (
            "Format as a professional email. Start with a line '**Subject:** ...' (write a clear subject "
            "if none exists), then greeting, concise body paragraphs (use bullets for multiple asks or "
            "points), a clear call to action, and a sign-off. Keep it brief and polite."
        ),
    },
    {
        "slug": "resume",
        "name": "Resume / CV",
        "icon": "id-card",
        "description": "Contact header, summary, experience, education and skills.",
        "instructions": (
            "Format as a resume. H1 with the person's name, then a single line of contact details "
            "separated by ' | '. Sections (H2): 'Professional Summary', 'Experience' (H3 per role as "
            "'Job Title — Company', italic date range and location line, then achievement bullets "
            "starting with strong action verbs), 'Education', 'Skills' (grouped by category), and any "
            "other sections present in the source (Certifications, Projects, Languages)."
        ),
    },
    {
        "slug": "technical-doc",
        "name": "Technical Documentation",
        "icon": "code",
        "description": "README-style docs: overview, setup, usage, configuration, troubleshooting.",
        "instructions": (
            "Format as technical documentation / README: H1 title, a one-paragraph overview, then H2 "
            "sections as appropriate: 'Features', 'Requirements', 'Installation', 'Usage', "
            "'Configuration' (tables for options: Option | Default | Description), 'API' / 'Examples', "
            "'Troubleshooting', 'FAQ'. Put every command, code snippet, path or config in fenced code "
            "blocks with the correct language tag, and inline code for identifiers."
        ),
    },
    {
        "slug": "academic-paper",
        "name": "Academic Paper",
        "icon": "graduation-cap",
        "description": "Abstract, introduction, methods, results, discussion, references.",
        "instructions": (
            "Format as an academic paper in an APA-like structure: H1 title; 'Abstract' (single "
            "paragraph); then 'Introduction', 'Literature Review', 'Methodology', 'Results', "
            "'Discussion', 'Conclusion' and 'References' — include only sections supported by the "
            "content. Use a formal academic register, and format references as a list in APA style "
            "when enough detail is present."
        ),
    },
    {
        "slug": "blog-article",
        "name": "Blog Article",
        "icon": "pen-line",
        "description": "Engaging title, hook intro, scannable sections and a takeaway.",
        "instructions": (
            "Format as an engaging blog article: catchy H1 title, a short hook introduction, scannable "
            "H2 sections with descriptive headings, short paragraphs, bullet lists, bold key ideas, "
            "pull quotes with > where a strong sentence exists, and a closing 'Key Takeaways' bullet list."
        ),
    },
    {
        "slug": "policy-legal",
        "name": "Policy / Legal",
        "icon": "scale",
        "description": "Numbered clauses and sub-clauses with defined terms.",
        "instructions": (
            "Format as a policy or legal-style document: H1 title, optional 'Purpose' and 'Scope' "
            "sections, then numbered H2 sections (1., 2., 3.) with numbered sub-clauses (1.1, 1.2, "
            "1.2.1) as plain paragraphs. Bold defined terms where they are defined, and add a "
            "'Definitions' section if terms are defined in the source. Keep wording precise; do not "
            "change legal meaning."
        ),
    },
    {
        "slug": "summary-notes",
        "name": "Summary Notes",
        "icon": "list-checks",
        "description": "Condensed TL;DR plus key points — shortens the text.",
        "instructions": (
            "Condense the text into study/summary notes. Start with an H1 title and a bold 'TL;DR' of "
            "1-2 sentences, then H2 topic sections with concise bullet points (nested where helpful). "
            "End with 'Key Terms' (term — definition) if applicable. Summarising and shortening IS "
            "allowed for this format, but never introduce facts that are not in the source."
        ),
    },
]


async def seed_templates(session: AsyncSession) -> None:
    """Insert or update built-in templates so prompt improvements ship with new releases."""
    existing = {t.slug: t for t in (await session.scalars(select(Template).where(Template.is_builtin))).all()}
    for tpl in BUILTIN_TEMPLATES:
        current = existing.get(tpl["slug"])
        if current is None:
            session.add(Template(**tpl, is_builtin=True))
            continue
        for key in ("name", "description", "icon", "instructions"):
            if getattr(current, key) != tpl[key]:
                setattr(current, key, tpl[key])
    await session.commit()
