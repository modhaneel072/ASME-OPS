import { expect, test, type Page } from '@playwright/test'

/** Scenario 1 – an existing user signs in with email or username. */
const EMAIL = process.env.E2E_EMAIL ?? ''
const USERNAME = process.env.E2E_USERNAME ?? ''
const PASSWORD = process.env.E2E_PASSWORD ?? ''

test.skip(!EMAIL || !PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD to an active account on the target server.')

async function signIn(page: Page, identifier: string, password: string) {
  await page.goto('/app/auth/login')
  await page.getByRole('textbox', { name: 'Email or username', exact: true }).fill(identifier)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
}

test.describe('authentication', () => {
  test('signs in with an email address and lands on Work Orders', async ({ page }) => {
    await signIn(page, EMAIL, PASSWORD)
    await expect(page).toHaveURL(/\/app\/work-orders/)
    await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('signs in with a username too', async ({ page }) => {
    test.skip(!USERNAME, 'Set E2E_USERNAME to run the username sign-in check.')
    await signIn(page, USERNAME, PASSWORD)
    await expect(page).toHaveURL(/\/app\/work-orders/)
  })

  test('rejects a wrong password without leaving the form', async ({ page }) => {
    await signIn(page, EMAIL, 'definitely-not-it')
    await expect(page.getByRole('alert')).toContainText(/invalid/i)
    await expect(page).toHaveURL(/\/app\/auth\/login/)
    await expect(page.getByRole('textbox', { name: 'Email or username', exact: true })).toHaveValue(EMAIL)
  })

  test('returns to the requested page after sign-in and can log out', async ({ page }) => {
    await page.goto('/app/locations')
    await expect(page).toHaveURL(/\/app\/auth\/login\?next=%2Flocations/)
    await page.getByRole('textbox', { name: 'Email or username', exact: true }).fill(EMAIL)
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page).toHaveURL(/\/app\/locations/)

    await page.getByRole('button', { name: /Account menu/ }).click()
    await page.getByRole('menuitem', { name: 'Log out' }).click()
    await expect(page).toHaveURL(/\/app\/auth\/login/)
    await page.goto('/app/locations')
    await expect(page).toHaveURL(/\/app\/auth\/login/)
  })

  test('keyboard: Escape closes the account menu and focus returns', async ({ page }) => {
    await signIn(page, EMAIL, PASSWORD)
    const trigger = page.getByRole('button', { name: /Account menu/ })
    await trigger.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('menu')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('menu')).toHaveCount(0)
    await expect(trigger).toBeFocused()
  })
})
