SYSTEM_PROMPT = """You are DocFormatter, an expert technical editor and document designer.
Your job is to take raw, messy or unstructured text and return a clean, well-structured,
professionally formatted document in GitHub-Flavored Markdown.

Hard rules:
1. Output ONLY the formatted document. No preamble, no explanations, no closing remarks.
2. Do NOT wrap the whole answer in a code fence.
3. Preserve every fact, name, number, date, link and piece of meaning from the source.
   Never invent information. If the target format expects a field that is missing from the
   source, omit it (do not use placeholders like [Name]) unless the instructions say otherwise.
4. Fix obvious spelling, grammar, punctuation and capitalisation mistakes.
5. Use Markdown structure deliberately: headings (#, ##, ###), short paragraphs, bullet and
   numbered lists, **bold** for key terms, tables for tabular/comparative data, > for quotes,
   and fenced code blocks (with a language tag) for code, commands or config.
6. Write in the same language as the source text unless told to translate.
"""


def build_user_prompt(
    text: str,
    template_instructions: str | None,
    custom_instructions: str,
    title: str,
    part: int = 1,
    total_parts: int = 1,
    previous_outline: str = "",
) -> str:
    sections: list[str] = []

    if template_instructions:
        sections.append(f"## Target format\n{template_instructions.strip()}")
    else:
        sections.append(
            "## Target format\nClean up and structure the text into a well-organised document "
            "with a clear title, logical headings, readable paragraphs and lists where appropriate."
        )

    if custom_instructions.strip():
        sections.append(
            "## Additional instructions from the user (these take priority)\n" f"{custom_instructions.strip()}"
        )

    if title.strip():
        sections.append(f"## Document title\n{title.strip()}")

    if total_parts > 1:
        if part == 1:
            note = (
                f"This is part 1 of {total_parts} of a long document. Format this part, starting the "
                "document normally (title, opening sections). Do not add a conclusion; the document continues."
            )
        elif part == total_parts:
            note = (
                f"This is the final part ({part} of {total_parts}) of a long document whose earlier parts "
                "were already formatted. Continue seamlessly: do NOT repeat the document title or any "
                "front matter, continue with the next headings at the appropriate level, and finish the document."
            )
        else:
            note = (
                f"This is part {part} of {total_parts} of a long document whose earlier parts were already "
                "formatted. Continue seamlessly: do NOT repeat the document title or front matter and do not "
                "add a conclusion; continue with the next headings at the appropriate level."
            )
        if part > 1:
            note += (
                "\nThe target format describes the structure of the WHOLE document, which has already been "
                "started. Do NOT restart that structure and do NOT repeat sections that already exist "
                "(e.g. no second summary/introduction/background). Instead, format the new source content as "
                "additional sections or subsections that naturally follow the existing ones."
            )
            if previous_outline:
                note += f"\n\nOutline of the parts already written:\n{previous_outline}"
        sections.append(f"## Chunking note\n{note}")

    sections.append(f"## Source text\n<<<SOURCE\n{text}\nSOURCE>>>")
    sections.append("Return the formatted Markdown now.")
    return "\n\n".join(sections)
