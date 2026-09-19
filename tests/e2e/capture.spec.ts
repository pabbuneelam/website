import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

// Screenshots land here, named "<project>-<step>.png" (project is "desktop"
// or "mobile", from playwright.config.ts). review.py reads every PNG in this
// directory, so don't rename the folder without updating that script too.
const SCREENSHOT_DIR = path.join(import.meta.dirname, 'screenshots')
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })

function shot(project: string, step: string) {
  return path.join(SCREENSHOT_DIR, `${project}-${step}.png`)
}

test('build a card end to end and browse the collection', async ({ page }, testInfo) => {
  const project = testInfo.project.name
  const creator = `qa-${Date.now()}`

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Slate' })).toBeVisible()

  const slotPickers = page.locator('.slot-picker')
  await expect(slotPickers).toHaveCount(6)
  await page.screenshot({ path: shot(project, '01-initial-load'), fullPage: true })

  // This is the state that caught the real bug: an open dropdown painting
  // underneath the slots below it. Every element still exists in the DOM
  // and every assertion here still passes -- only the pixels show the
  // defect, which is exactly what the AI review step is for. Open the
  // FIRST slot's dropdown (not the last) so there's maximum content below
  // it for the menu to wrongly render under.
  const firstPicker = slotPickers.nth(0)
  await firstPicker.locator('.dropdown__trigger').click()
  // toBeVisible() resolves the moment visibility:visible applies -- it does NOT
  // wait for the opacity and max-height transitions. Screenshotting there
  // catches the menu half-expanded and half-faded, which reads as a clipping
  // and transparency bug that is not real. Wait for the transition to settle.
  const menu = firstPicker.locator('.dropdown__menu--open')
  await expect(menu).toBeVisible()
  await expect(menu).toHaveCSS('opacity', '1')
  await page.screenshot({ path: shot(project, '02-dropdown-open'), fullPage: true })

  await firstPicker.locator('.dropdown__option:not(.dropdown__option--empty)').first().click()

  for (let i = 1; i < 6; i++) {
    const picker = slotPickers.nth(i)
    await picker.locator('.dropdown__trigger').click()
    await picker.locator('.dropdown__option:not(.dropdown__option--empty)').first().click()
  }

  await page.getByLabel('Creator name').fill(creator)
  await page.screenshot({ path: shot(project, '03-all-slots-filled'), fullPage: true })

  await page.getByRole('button', { name: 'Build card' }).click()
  await expect(page.locator('.card-result')).toBeVisible({ timeout: 10_000 })
  await page.screenshot({ path: shot(project, '04-card-result'), fullPage: true })

  await page.getByRole('button', { name: 'My Collection' }).click()
  await expect(page.locator('.collection')).toBeVisible()
  await page.screenshot({ path: shot(project, '05-my-collection'), fullPage: true })
})
