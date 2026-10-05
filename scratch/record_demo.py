import os
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\Sivanesh\.gemini\antigravity-ide\brain\92574fee-ac6b-4e41-9a77-6c90109d696b"
VIDEO_DIR = os.path.join(ARTIFACT_DIR, "video_recordings")
os.makedirs(VIDEO_DIR, exist_ok=True)

def record_walkthrough():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            record_video_dir=VIDEO_DIR,
            record_video_size={"width": 1366, "height": 768}
        )
        page = context.new_page()

        print("1. Navigating to AI QA Studio...")
        page.goto("http://127.0.0.1:8000/review", wait_until="networkidle")
        page.wait_for_timeout(2000)

        # 2. Showcase Requirements Hub
        print("2. Exploring Requirements Hub...")
        page.wait_for_timeout(2500)

        # 3. Test Studio
        print("3. Navigating to Test Studio...")
        test_studio_nav = page.locator("nav .nav-item:has-text('Test Studio')")
        if test_studio_nav.count() > 0:
            test_studio_nav.click()
            page.wait_for_timeout(2000)
            page.mouse.wheel(0, 300)
            page.wait_for_timeout(2000)
            page.mouse.wheel(0, -300)
            page.wait_for_timeout(1000)

            # Inspect first chunk if button exists
            chunk_btn = page.locator("button:has-text('Inspect Chunks')").first
            if chunk_btn.count() > 0:
                chunk_btn.click()
                page.wait_for_timeout(2500)
                page.locator("#chunkModal button:has-text('Close')").click()
                page.wait_for_timeout(1000)

        # 4. Traceability Matrix
        print("4. Viewing Traceability Matrix...")
        trace_nav = page.locator("nav .nav-item:has-text('Traceability')")
        if trace_nav.count() > 0:
            trace_nav.click()
            page.wait_for_timeout(3000)

        # 5. Playwright E2E Runner
        print("5. Viewing Playwright E2E Runner...")
        playwright_nav = page.locator("nav .nav-item:has-text('Playwright E2E')")
        if playwright_nav.count() > 0:
            playwright_nav.click()
            page.wait_for_timeout(2000)
            
            # Click View Playwright Code
            view_code_btn = page.locator("button:has-text('View Playwright Code')")
            if view_code_btn.count() > 0:
                view_code_btn.click()
                page.wait_for_timeout(2500)
                page.mouse.wheel(0, 400)
                page.wait_for_timeout(2000)
                page.mouse.wheel(0, -400)
                page.wait_for_timeout(1000)

        # 6. REST API Testing Lab (Option B)
        print("6. Demonstrating REST API Testing Lab...")
        api_nav = page.locator("nav .nav-item:has-text('API Testing Lab')")
        if api_nav.count() > 0:
            api_nav.click()
            page.wait_for_timeout(2000)

            # Click Run Live API Suite
            run_api_btn = page.locator("#runApiSuiteBtn")
            if run_api_btn.count() > 0:
                run_api_btn.click()
                page.wait_for_timeout(4000)

            # Open Details & cURL modal if present
            curl_btn = page.locator("button:has-text('Details & cURL')").first
            if curl_btn.count() > 0:
                curl_btn.click()
                page.wait_for_timeout(3000)
                page.locator("#apiPayloadModal button:has-text('Close')").click()
                page.wait_for_timeout(1500)

        # 7. AI QA Copilot Sidecar
        print("7. Opening AI QA Copilot Sidecar...")
        copilot_toggle = page.locator("button:has-text('AI QA Copilot')")
        if copilot_toggle.count() > 0:
            copilot_toggle.click()
            page.wait_for_timeout(2000)

            # Send prompt or click quick chip
            quick_chip = page.locator(".quick-chip").first
            if quick_chip.count() > 0:
                quick_chip.click()
                page.wait_for_timeout(3500)
            else:
                copilot_input = page.locator("#copilotInput")
                if copilot_input.count() > 0:
                    copilot_input.fill("What is the current test coverage for authentication?")
                    page.locator("#copilotSendBtn").click()
                    page.wait_for_timeout(3500)

        page.wait_for_timeout(2000)

        # Close page and context to finalize video recording
        video_path = page.video.path()
        context.close()
        browser.close()

        final_dest = os.path.join(ARTIFACT_DIR, "qa_app_demo.webm")
        if os.path.exists(final_dest):
            try:
                os.remove(final_dest)
            except Exception:
                pass
        os.rename(video_path, final_dest)
        print(f"SUCCESS: Video saved to {final_dest}")
        return final_dest

if __name__ == "__main__":
    record_walkthrough()
