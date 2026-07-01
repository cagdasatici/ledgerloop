"""Deterministic prompt assembly."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


def stable_json(value: Any) -> str:
    """Serialize values deterministically for hashing and prompt assembly."""

    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True)


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_block(title: str, payload: Any) -> str:
    body = payload if isinstance(payload, str) else stable_json(payload)
    return "### %s ###\n%s\n" % (title, body)


@dataclass(frozen=True)
class PromptSection:
    name: str
    content: str
    cache_candidate: bool

    @property
    def content_hash(self) -> str:
        return sha256_text(self.content)


@dataclass(frozen=True)
class PromptBundle:
    sections: List[PromptSection]

    @property
    def full_prompt(self) -> str:
        return "\n".join(section.content for section in self.sections)

    @property
    def full_hash(self) -> str:
        return sha256_text(self.full_prompt)

    @property
    def cacheable_prefix(self) -> str:
        return "\n".join(
            section.content for section in self.sections if section.cache_candidate
        )

    @property
    def cacheable_hash(self) -> str:
        return sha256_text(self.cacheable_prefix)

    def section_hashes(self) -> Dict[str, str]:
        return {section.name: section.content_hash for section in self.sections}


def assemble_prompt_bundle(
    system_contract: Any,
    project_summary: Any,
    memory_summary: Any,
    dynamic_context: Any,
    current_task_payload: Any,
) -> PromptBundle:
    """Build the five-section prompt bundle from the functional spec."""

    sections = [
        PromptSection(
            "STATIC SYSTEM CONTRACT",
            render_block("STATIC SYSTEM CONTRACT", system_contract),
            True,
        ),
        PromptSection(
            "STABLE PROJECT SUMMARY",
            render_block("STABLE PROJECT SUMMARY", project_summary),
            True,
        ),
        PromptSection(
            "CACHEABLE MEMORY SUMMARY",
            render_block("CACHEABLE MEMORY SUMMARY", memory_summary),
            True,
        ),
        PromptSection(
            "DYNAMIC RETRIEVED CONTEXT",
            render_block("DYNAMIC RETRIEVED CONTEXT", dynamic_context),
            False,
        ),
        PromptSection(
            "CURRENT TASK PAYLOAD",
            render_block("CURRENT TASK PAYLOAD", current_task_payload),
            False,
        ),
    ]
    return PromptBundle(sections=sections)


def stable_memory_summary(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return memory records ordered by stable identifiers."""

    return sorted(items, key=lambda item: (item.get("scope", ""), item.get("id", "")))
