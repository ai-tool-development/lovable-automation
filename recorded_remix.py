import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(storage_state="session_state/lovable_session.json")
    page = context.new_page()
    page.goto("https://lovable.dev/projects/65a49f56-9201-4dfc-a559-817c90e2a853")
    page.get_by_role("button", name="Remix Playground Loading Live").click()
    page.get_by_role("menuitem", name="Settings ⌘").click()
    page.get_by_role("button", name="Remix").click()
    page.get_by_role("switch", name="Include project history").click()
    page.get_by_role("button", name="Remix").click()
    page.goto("https://lovable.dev/projects/a0b4acdf-5479-4dc5-af4f-f896dc575779?remixed=true")

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
