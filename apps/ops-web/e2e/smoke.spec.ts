import { expect, test } from '@playwright/test'

/**
 * Quick end-to-end check against a running server: sign in with the local
 * development account, open Locations, create a location through the
 * right-side pane. Credentials come from the environment so nothing real is
 * ever committed.
 */
const EMAIL = process.env.E2E_EMAIL ?? 'smoke@uiowa.edu'
const PASSWORD = process.env.E2E_PASSWORD ?? 'SmokeTest123!'

test('sign in, open Locations and create one', async ({ page }) => {
  await page.goto('/app/locations')
  await expect(page).toHaveURL(/\/app\/auth\/login/)
  await page.getByRole('textbox', { name: 'Email or username', exact: true }).fill(EMAIL)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL(/\/app\/locations/)
  await expect(page.getByRole('heading', { level: 1, name: 'Locations' })).toBeVisible()
  await expect(page.getByRole('link', { name: /General/ }).first()).toBeVisible()
  await page.screenshot({ path: 'test-results/smoke-locations.png' })

  const name = `Smoke Bench ${Date.now()}`
  await page.getByRole('button', { name: 'New Location', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'New Location' })).toBeVisible()
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(name)
  await page.getByRole('textbox', { name: 'Room', exact: true }).fill('1245')
  await page.screenshot({ path: 'test-results/smoke-location-pane.png' })
  await page.getByRole('button', { name: 'Create Location' }).click()
  await expect(page.getByText('Location created')).toBeVisible()
  await expect(page.getByRole('heading', { level: 2, name: name })).toBeVisible()
  await page.screenshot({ path: 'test-results/smoke-location-created.png' })

  // validation round trip: empty name is rejected client-side
  await page.getByRole('button', { name: 'New Location', exact: true }).click()
  await page.getByRole('button', { name: 'Create Location' }).click()
  await expect(page.getByText('Give the location a name.')).toBeVisible()
  await page.keyboard.press('Escape')
})
