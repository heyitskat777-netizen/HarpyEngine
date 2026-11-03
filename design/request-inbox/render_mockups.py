"""Render and exercise the standalone offline mockup; never connects to Discord."""

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent


def main() -> None:
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route(
            "**/*",
            lambda route: (
                route.continue_() if route.request.url.startswith("file:") else route.abort()
            ),
        )
        page.set_content((ROOT / "index.html").read_text(), wait_until="load")
        page.wait_for_function("window.mockup && document.querySelector('#request-select')")
        assert page.evaluate("window.mockup.snapshot().counts.pending") == 8
        page.select_option("#request-select", "bond-start")
        page.locator('[data-action="primary-action"]').click()
        assert page.evaluate("window.mockup.snapshot().counts.pending") == 7
        assert page.evaluate("window.mockup.snapshot().counts.history") == 2
        page.locator('[data-filter="waiting"]').click()
        page.select_option("#request-select", "callsign")
        assert page.locator('[data-action="primary-action"]').count() == 0
        page.locator('[data-action="withdraw"]').click()
        assert page.evaluate("window.mockup.snapshot().counts.pending") == 6
        page.click("#reset")
        page.select_option("#type", "callsigns")
        assert page.evaluate("window.mockup.snapshot().counts.waiting") == 1
        assert page.evaluate("window.mockup.snapshot().counts.you") == 0
        page.click("#reset")
        page.select_option("#request-select", "elevation")
        assert page.locator('[data-action="primary-action"]').is_disabled()
        page.click("#stale-demo")
        assert page.locator('[data-action="primary-action"]').is_disabled()
        assert "new proposal" in page.locator(".notice").inner_text()
        page.screenshot(path=str(ROOT / "changed-request.png"), full_page=True)
        page.click("#empty-demo")
        assert "caught up" in page.locator(".empty").inner_text()
        page.screenshot(path=str(ROOT / "empty-inbox.png"), full_page=True)
        page.click("#reset")
        page.select_option("#request-select", "pair")
        page.locator('[data-action="primary-action"]').click()
        assert "wizard would open" in page.locator("#toast").inner_text()
        assert page.evaluate("window.mockup.snapshot().counts.pending") == 8
        page.click("#reset")
        for concept in ("inbox", "guided", "cards"):
            page.evaluate("concept => window.mockup.setDesign(concept)", concept)
            page.screenshot(path=str(ROOT / f"{concept}.png"), full_page=True)
        page.evaluate("window.mockup.setDesign('inbox')")
        page.select_option("#request-select", "court")
        page.screenshot(path=str(ROOT / "request-detail.png"), full_page=True)
        page.click("#reset")
        page.set_viewport_size({"width": 390, "height": 1000})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(ROOT / "mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1500, "height": 1250})
        overview = (ROOT / "overview.html").read_text()
        import re

        overview = re.sub(r' src="index.html[^"]*"', "", overview)
        page.set_content(overview, wait_until="load")
        source = (ROOT / "index.html").read_text()
        frames = [
            source.replace(
                "new URLSearchParams(location.search)",
                f"new URLSearchParams('?concept={kind}&compact')",
            )
            for kind in ("inbox", "guided", "cards")
        ]
        page.evaluate(
            "frames => document.querySelectorAll('iframe')"
            ".forEach((node, i) => node.srcdoc = frames[i])",
            frames,
        )
        page.wait_for_function(
            "Array.from(document.querySelectorAll('iframe')).every(x => x.contentWindow.mockup)"
        )
        page.screenshot(path=str(ROOT / "overview.png"), full_page=True)
        browser.close()
    assert not errors, errors
    print(
        "Offline browser checks PASS: filters, acceptance, outgoing withdrawal, "
        "planned/stale blocking, empty state, wizard routing, three layouts, "
        "mobile fit. No page errors."
    )
    print(f"Rendered 8 PNG previews in {ROOT}")


if __name__ == "__main__":
    main()
