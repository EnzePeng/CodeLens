"""
Diff utilities - Generate and apply unified diffs.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Optional


def generate_unified_diff(
    old_content: str,
    new_content: str,
    old_path: str = "a",
    new_path: str = "b",
    context_lines: int = 3,
) -> str:
    """Generate unified diff format.
    
    Args:
        old_content: Original file content
        new_content: New file content
        old_path: Original file path (for diff header)
        new_path: New file path (for diff header)
        context_lines: Number of context lines
        
    Returns:
        Unified diff string
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=old_path,
        tofile=new_path,
        lineterm="",
        n=context_lines,
    )
    
    return "\n".join(diff)


def parse_unified_diff(diff_text: str) -> list[dict]:
    """Parse unified diff into structured format.
    
    Returns:
        List of file patches, each containing hunks
    """
    patches = []
    current_file = None
    current_hunk = None
    current_hunk_lines = []
    
    for line in diff_text.splitlines():
        # File header
        if line.startswith("--- ") or line.startswith("+++ "):
            if current_file and current_hunk:
                if current_hunk_lines:
                    current_hunk["lines"] = current_hunk_lines
                    current_file["hunks"].append(current_hunk)
                patches.append(current_file)
            
            path = line[4:].split("\t")[0]
            if line.startswith("--- "):
                current_file = {"old_path": path, "new_path": "", "hunks": []}
            else:
                if current_file:
                    current_file["new_path"] = path
        # Hunk header
        elif line.startswith("@@"):
            if current_hunk and current_hunk_lines:
                current_hunk["lines"] = current_hunk_lines
                current_file["hunks"].append(current_hunk)
            
            # Parse @@ -start,count +start,count @@
            parts = line[3:].split(" @@")[0]
            # Handle both " -1,3 +1,4" and " -1 +1" formats
            old_match = re.search(r'-\d+(?:,\d+)?\s+(\+\d+(?:,\d+)?)', parts)
            if old_match:
                old_start = int(parts.split()[0].lstrip('-').split(',')[0])
                new_start = int(old_match.group(1).lstrip('+').split(',')[0])
            else:
                continue  # Skip unparseable hunk headers
            
            current_hunk = {
                "old_start": old_start,
                "new_start": new_start,
                "lines": [],
            }
            current_hunk_lines = []
        # Content lines
        elif current_hunk is not None:
            current_hunk_lines.append(line)
    
    # Add last file/hunk
    if current_file:
        if current_hunk and current_hunk_lines:
            current_hunk["lines"] = current_hunk_lines
            current_file["hunks"].append(current_hunk)
        patches.append(current_file)
    
    return patches


def apply_unified_diff(original: str, diff_text: str) -> str:
    """Apply unified diff to original content.
    
    Args:
        original: Original file content
        diff_text: Unified diff text
        
    Returns:
        Patched content
    """
    lines = original.splitlines(keepends=True)
    patches = parse_unified_diff(diff_text)
    
    for patch in patches:
        for hunk in patch.get("hunks", []):
            old_start = hunk["old_start"] - 1  # Convert to 0-indexed
            new_lines = []
            old_lines = []
            
            for line in hunk.get("lines", []):
                if line.startswith("+") and not line.startswith("+++"):
                    new_lines.append(line[1:] + "\n")
                elif line.startswith("-") and not line.startswith("---"):
                    old_lines.append(line[1:] + "\n")
                elif line.startswith(" "):
                    new_lines.append(line[1:] + "\n")
                    old_lines.append(line[1:] + "\n")
            
            # Replace old lines with new lines
            # Find the position in original
            insert_pos = old_start
            for i, ol in enumerate(old_lines):
                if insert_pos + i < len(lines) and lines[insert_pos + i].rstrip() == ol.rstrip():
                    continue
                # Try to find matching context
                found = False
                for j in range(max(0, old_start - 3), min(len(lines), old_start + len(old_lines) + 3)):
                    if lines[j:j+len(old_lines)] == old_lines:
                        insert_pos = j
                        found = True
                        break
                if not found:
                    # Fallback: insert at old_start
                    pass
                break
            
            # Apply the patch
            lines[insert_pos:insert_pos + len(old_lines)] = new_lines
    
    return "".join(lines)


def generate_fuzzy_diff(
    old_content: str,
    new_content: str,
    threshold: float = 0.8,
) -> Optional[str]:
    """Generate diff with fuzzy matching when exact match fails.
    
    Args:
        old_content: Original content
        new_content: New content
        threshold: Similarity threshold for fuzzy matching
        
    Returns:
        Unified diff or None if too different
    """
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    
    # Use SequenceMatcher for line-by-line diff
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    
    # If too different, return None
    if matcher.ratio() < threshold:
        return None
    
    # Generate unified diff
    return generate_unified_diff(old_content, new_content)


def preview_diff(
    old_content: str,
    new_content: str,
    max_lines: int = 100,
) -> dict:
    """Generate diff preview with statistics.
    
    Returns:
        Dict with diff stats and preview
    """
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    
    diff_lines = []
    added = 0
    removed = 0
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in old_lines[i1:i2]:
                diff_lines.append(f"  {line}")
        elif tag == "replace":
            for line in old_lines[i1:i2]:
                diff_lines.append(f"- {line}")
                removed += 1
            for line in new_lines[j1:j2]:
                diff_lines.append(f"+ {line}")
                added += 1
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                diff_lines.append(f"- {line}")
                removed += 1
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                diff_lines.append(f"+ {line}")
                added += 1
    
    # Truncate if too long
    preview = "\n".join(diff_lines[:max_lines])
    if len(diff_lines) > max_lines:
        preview += f"\n... ({len(diff_lines) - max_lines} more lines)"
    
    return {
        "added": added,
        "removed": removed,
        "total_changes": added + removed,
        "preview": preview,
    }


# Helper for preview
def get_diff_stats(old_content: str, new_content: str) -> dict:
    """Get diff statistics without full diff."""
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    
    added = 0
    removed = 0
    unchanged = 0
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            unchanged += (i2 - i1)
        elif tag == "replace":
            removed += (i2 - i1)
            added += (j2 - j1)
        elif tag == "delete":
            removed += (i2 - i1)
        elif tag == "insert":
            added += (j2 - j1)
    
    return {
        "added": added,
        "removed": removed,
        "unchanged": unchanged,
        "total_old": len(old_lines),
        "total_new": len(new_lines),
        "similarity": round(matcher.ratio(), 3),
    }