"""Front-end display contract: HTML hidden must beat component display styles."""
from pathlib import Path
import re

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"

def test_css_hidden_attribute_has_priority():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert re.search(r"\[hidden\]\s*\{\s*display\s*:\s*none\s*!important\s*;?\s*\}", css), (
        "All [hidden] elements, including the login grid and pages, must be hidden."
    )

def test_login_is_hidden_on_success_and_restored_on_logout():
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="login-page"' in html
    assert "$('#login-page').hidden=true" in script
    assert "$('#login-page').hidden=false" in script
    assert "await openPage(rolePages[state.user.role][0])" in script
    assert 'id="username" name="username" required' in html
    assert 'id="password" name="password" type="password" required' in html
    assert 'demo-switch' not in html and 'Demo@123456' not in html


def test_login_sets_user_header_for_all_roles():
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "state.user=result.user" in script
    assert "showUser();" in script
    assert "$('#logout').hidden=false" in script

def test_register_and_marketplace_merchant_filters_exist():
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="register-form"' in html
    assert "'/auth/register'" in script
    assert "data-merchant" in script

def test_admin_merchant_creation_is_wired():
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "'/admin/merchants'" in script
    assert "title:'新增商户'" in script
    assert "dialog.showModal()" in script
