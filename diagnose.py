#!/usr/bin/env python3
"""
Simplified diagnostic - uses direct "Remix this project" menu item.
"""
from playwright.sync_api import sync_playwright
import sys
import time
import re

PROJECT_ID = sys.argv[1] if len(sys.argv) > 1 else "65a49f56-9201-4dfc-a559-817c90e2a853"
SESSION_FILE = "session_state/lovable_session.json"

def extract_project_id(url: str):
    match = re.search(r'/projects/([a-f0-9-]+)', url)
    return match.group(1) if match else None

print(f"Starting diagnosis for project: {PROJECT_ID}")
print("=" * 60)

with sync_playwright() as p:
    print("1. Launching browser...")
    browser = p.chromium.launch(headless=False, slow_mo=50)
    print("   ✓ Browser launched")

    print("2. Creating context with session...")
    context = browser.new_context(storage_state=SESSION_FILE)
    print("   ✓ Context created")

    print("3. Opening new page...")
    page = context.new_page()
    print("   ✓ Page opened")

    print(f"4. Navigating to project...")
    page.goto(f"https://lovable.dev/projects/{PROJECT_ID}", wait_until="domcontentloaded")
    print("   ✓ DOM content loaded")

    print("5. Waiting for page to be ready...")
    page.wait_for_timeout(3000)
    print("   ✓ Page ready")

    print("6. Current URL:", page.url)

    # STEP A: Click project menu button
    print("\n" + "=" * 60)
    print("STEP A: Opening project menu...")
    print("=" * 60)

    menu_button = page.locator("button[aria-haspopup='menu']").first
    menu_button.click()
    page.wait_for_timeout(500)
    print("   ✓ Menu opened")

    # STEP B: Click "Remix this project" directly
    print("\n" + "=" * 60)
    print("STEP B: Clicking 'Remix this project'...")
    print("=" * 60)

    # List menu items to confirm
    menu_items = page.locator("[role='menuitem']").all()
    print(f"   Found {len(menu_items)} menu items")

    remix_item = None
    for i, item in enumerate(menu_items):
        try:
            text = item.inner_text(timeout=500).strip()
            if "remix" in text.lower():
                print(f"   [{i}] '{text}' <- FOUND REMIX")
                remix_item = item
            else:
                print(f"   [{i}] '{text}'")
        except:
            pass

    if remix_item is None:
        print("   ✗ No remix menu item found!")
        browser.close()
        sys.exit(1)

    print("\n   Clicking 'Remix this project'...")
    remix_item.click()
    print("   ✓ Clicked!")

    # STEP C: Handle any dialog that appears
    print("\n" + "=" * 60)
    print("STEP C: Checking for confirmation dialog...")
    print("=" * 60)

    page.wait_for_timeout(1000)

    # Check if a dialog appeared
    dialog = page.locator("[role='dialog']")
    if dialog.is_visible(timeout=2000):
        print("   ✓ Dialog appeared")

        # Look for confirm button
        dialog_buttons = page.locator("[role='dialog'] button").all()
        print(f"   Found {len(dialog_buttons)} buttons in dialog:")

        for i, btn in enumerate(dialog_buttons):
            try:
                text = btn.inner_text(timeout=500).strip()
                print(f"      [{i}] '{text}'")
            except:
                pass

        # Find and click the Remix/Confirm button
        confirm_btn = page.locator("[role='dialog'] button:has-text('Remix')").first
        if confirm_btn.is_visible(timeout=1000):
            print("\n   Clicking confirm button...")
            confirm_btn.click()
            print("   ✓ Confirmed!")
        else:
            print("   No confirm button needed")
    else:
        print("   No dialog appeared - remix may start directly")

    # STEP D: Wait for new project
    print("\n" + "=" * 60)
    print("STEP D: Waiting for new project...")
    print("=" * 60)

    print(f"   Original project ID: {PROJECT_ID}")
    new_project_id = None

    # Use wait_for_url - this worked before
    print("   Using Playwright wait_for_url...")
    try:
        page.wait_for_url(
            re.compile(rf"lovable\.dev/projects/(?!{PROJECT_ID})([a-f0-9-]+)"),
            timeout=120000  # 2 minutes
        )
        new_project_id = extract_project_id(page.url)
        print(f"   ✓ URL changed to: {page.url}")
        print(f"   ✓ New project ID: {new_project_id}")
    except Exception as e:
        print(f"   wait_for_url exception: {e}")
        # Fallback: check current URL
        try:
            current_url = page.url
            current_id = extract_project_id(current_url)
            print(f"   Fallback check - URL: {current_url}")
            if current_id and current_id != PROJECT_ID:
                new_project_id = current_id
                print(f"   ✓ Found new project: {new_project_id}")
        except:
            pass

    if new_project_id:
        print(f"\n   ✓ SUCCESS!")
        print(f"   New project URL: https://lovable.dev/projects/{new_project_id}")
    else:
        print(f"\n   ✗ Could not detect new project")

    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)
    browser.close()
