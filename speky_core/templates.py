"""Starting text for new changes. Lite for small work, full for bigger changes (progressive rigor)."""

LITE = """# {title}

## Why
<!-- One or two sentences: the problem and who has it. -->

## Capabilities
<!-- What is true when this is done. -->

## Non-goals
<!-- At least one thing this change deliberately does not do. -->

## Requirements

### R1: {title}
<!-- The system SHALL ... -->

#### Scenario: Main path
- GIVEN <starting state>
- WHEN <action>
- THEN <observable result>

## Assumptions
<!-- Informed guesses made instead of asking. Delete the section if there are none. -->
"""

FULL = """# {title}

## Why
<!-- The problem, who has it, and why now. -->

## Capabilities
<!-- What is true when this is done, one line each. -->

## Constraints
<!-- Only constraints that rule something out. -->

## Non-goals
<!-- What this change deliberately does not do. -->

## Success signal
<!-- How we will know it worked: something you can test or demonstrate. -->

## Requirements

### R1: <first requirement>
The system SHALL ...

#### Scenario: Main path
- GIVEN <starting state>
- WHEN <action>
- THEN <observable result>

#### Scenario: Error or empty state
- GIVEN <starting state>
- WHEN <action that fails>
- THEN <what the user sees>

## Assumptions
<!-- Informed guesses made instead of asking (keep [NEEDS CLARIFICATION] markers to 3 or fewer). -->

## Open Questions
<!-- Only questions whose answer changes what gets built. -->
"""


def change_template(title: str, size: str = "change", kind: str = "spec") -> str:
    template = LITE if size in ("quick", "small") or kind == "story" else FULL
    return template.format(title=title)


CAPABILITY = """# {name}

## Purpose
{purpose}

## Requirements
"""


# Placeholder text from the templates above; a document still containing any of it is unfinished
PLACEHOLDERS = ["<first requirement>", "<starting state>", "<action>", "<observable result>",
                "<action that fails>", "<what the user sees>", "The system SHALL ...",
                "<!-- The system SHALL ... -->"]


def unfilled_placeholders(text: str) -> list:
    import re
    visible = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return [p for p in PLACEHOLDERS if not p.startswith("<!--") and p in visible]
