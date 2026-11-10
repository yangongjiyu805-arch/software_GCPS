"""Capture real UI evidence from a running demo server with Chromium."""
import asyncio, os
from pathlib import Path
from playwright.async_api import async_playwright

OUT=Path('docs/evidence');OUT.mkdir(exist_ok=True,parents=True)


async def login(page, username):
    await page.fill('#username', username)
    await page.fill('#password', os.getenv('DEMO_PASSWORD', 'Demo@123456'))
    await page.click('#login-form button[type=submit]')


async def click_and_wait_for_post(page, selector, path_suffix):
    async with page.expect_response(
        lambda response: response.request.method == 'POST' and response.url.endswith(path_suffix)
    ) as request:
        await page.locator(selector).first.click()
    response = await request.value
    if not response.ok:
        raise RuntimeError(f'{response.url} returned HTTP {response.status}')


async def main():
    async with async_playwright() as p:
        executable=os.getenv('DEMO_CHROMIUM_PATH')
        if not executable and Path('/usr/bin/chromium').is_file():
            executable='/usr/bin/chromium'
        browser=await p.chromium.launch(headless=True, executable_path=executable,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1440,'height':900},device_scale_factor=1,locale='zh-CN')
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(os.getenv('DEMO_BASE_URL','http://127.0.0.1:8000')+'/',wait_until='networkidle')
        await page.screenshot(path=str(OUT/'01-login.png'),full_page=True)
        await login(page, 'resident')
        await page.wait_for_selector('#hero-go:visible')
        await page.screenshot(path=str(OUT/'02-dashboard.png'),full_page=True)
        await page.click('#hero-go')
        await page.wait_for_selector('#trip-form:visible')
        await page.select_option('#trip-form select[name=mode]','bike')
        await page.fill('#trip-form input[name=distance]','20')
        await page.screenshot(path=str(OUT/'03-journey.png'),full_page=True)
        await click_and_wait_for_post(page, '#trip-form button[type=submit]', '/api/trips')
        await page.locator('[data-page=mall]').click()
        await page.wait_for_selector('.product-card')
        await page.screenshot(path=str(OUT/'04-mall.png'),full_page=True)
        await click_and_wait_for_post(page, '[data-buy="1"]', '/api/redemptions')
        await page.locator('[data-page=wallet]').click()
        await page.wait_for_selector('#wallet-rows tr')
        await page.screenshot(path=str(OUT/'05-wallet.png'),full_page=True)
        await page.click('#logout')
        await login(page, 'merchant')
        await page.wait_for_selector('#merchant h1:visible')
        await page.screenshot(path=str(OUT/'06-merchant.png'),full_page=True)
        await click_and_wait_for_post(page, '[data-fulfill]', '/fulfill')
        await page.click('#logout')
        await login(page, 'admin')
        await page.wait_for_selector('#admin h1:visible')
        await page.screenshot(path=str(OUT/'07-admin.png'),full_page=True)
        settle = page.locator('[data-settle]').first
        redemption_id = await settle.get_attribute('data-settle')
        await click_and_wait_for_post(page, '[data-settle]', '/settle')
        await page.wait_for_selector(f'[data-settle="{redemption_id}"]', state='detached')
        await page.screenshot(path=str(OUT/'08-settled.png'),full_page=True)
        print('Browser JS errors:',errors)
        print('Screenshots:',[p.name for p in OUT.glob('*.png')]);await browser.close()
        if errors:raise RuntimeError('Browser JS errors')
asyncio.run(main())
