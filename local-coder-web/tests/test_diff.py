"""
Tests for Diff utilities.
"""
import pytest

from core.tools.diff_utils import (
    generate_unified_diff,
    parse_unified_diff,
    apply_unified_diff,
    get_diff_stats,
)


def test_generate_unified_diff():
    """Test generating unified diff."""
    old = "line1\nline2\nline3\n"
    new = "line1\nline2 modified\nline3\n"
    
    diff = generate_unified_diff(old, new)
    
    assert "---" in diff
    assert "+++" in diff
    assert "@@" in diff
    assert "line2 modified" in diff


def test_generate_unified_diff_add_lines():
    """Test diff when adding lines."""
    old = "line1\nline2\n"
    new = "line1\nline2\nline3\n"
    
    diff = generate_unified_diff(old, new)
    
    assert "+line3" in diff


def test_generate_unified_diff_remove_lines():
    """Test diff when removing lines."""
    old = "line1\nline2\nline3\n"
    new = "line1\nline3\n"
    
    diff = generate_unified_diff(old, new)
    
    assert "-line2" in diff


def test_parse_unified_diff():
    """Test parsing unified diff."""
    diff_text = """--- a/file.py
+++ b/file.py
@@ -1,3 +1,4 @@
 line1
-line2
+line2 modified
+line3
 line3
"""
    
    patches = parse_unified_diff(diff_text)
    
    assert len(patches) >= 1
    assert "hunks" in patches[0]


def test_apply_unified_diff():
    """Test applying unified diff."""
    original = "line1\nline2\nline3\n"
    
    diff = """--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
 line1
-line2
+line2 modified
 line3
"""
    
    result = apply_unified_diff(original, diff)
    
    assert "line2 modified" in result
    assert "line1" in result
    assert "line3" in result


def test_apply_unified_diff_add():
    """Test applying diff that adds lines."""
    original = "line1\nline2\n"
    
    diff = """--- a/file.py
+++ b/file.py
@@ -1,2 +1,3 @@
 line1
 line2
+line3
"""
    
    result = apply_unified_diff(original, diff)
    
    assert "line3" in result


def test_apply_unified_diff_remove():
    """Test applying diff that removes lines."""
    original = "line1\nline2\nline3\n"
    
    diff = """--- a/file.py
+++ b/file.py
@@ -1,3 +1,2 @@
 line1
-line2
 line3
"""
    
    result = apply_unified_diff(original, diff)
    
    assert "line2" not in result
    assert "line1" in result
    assert "line3" in result


def test_get_diff_stats():
    """Test getting diff statistics."""
    old = "line1\nline2\nline3\nline4\n"
    new = "line1\nline2 modified\nline3\nline4\n"
    
    stats = get_diff_stats(old, new)
    
    assert stats["added"] >= 0
    assert stats["removed"] >= 0
    assert stats["unchanged"] >= 0
    assert stats["total_old"] == 4
    assert stats["total_new"] == 4
    assert 0 < stats["similarity"] <= 1


def test_get_diff_stats_no_change():
    """Test diff stats when no changes."""
    content = "line1\nline2\nline3\n"
    
    stats = get_diff_stats(content, content)
    
    assert stats["added"] == 0
    assert stats["removed"] == 0
    assert stats["similarity"] == 1.0


def test_get_diff_stats_major_change():
    """Test diff stats with major changes."""
    old = "a\nb\nc\nd\ne\nf\ng\nh\n"
    new = "1\n2\n3\n4\n5\n6\n7\n8\n"
    
    stats = get_diff_stats(old, new)
    
    # Should show low similarity
    assert stats["similarity"] < 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])