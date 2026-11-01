from rice_market.ui import _html, month_label, tonnes


def test_html_helper_converts_bold_and_code_inside_html_blocks():
    assert _html("a **bold** and `code`") == "a <b>bold</b> and <code>code</code>"
    assert "**" not in _html("**x** and **y**")


def test_formatters_handle_missing():
    assert tonnes(None) == "n/a" and tonnes(float("nan")) == "n/a"
    assert tonnes(1500.0) == "1.5 kt" and tonnes(900.0) == "900 t"
    assert month_label(None) == "n/a"
