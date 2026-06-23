import { expect, test } from '@playwright/test'

test('loads standings and navigates to simulator', async ({ page }) => {
  await page.goto('/groups/A')
  await expect(page.getByRole('heading', { name: 'Group A' })).toBeVisible()
  await expect(page.getByText('Mexico', { exact: true }).first()).toBeVisible()
  await page.getByRole('link', { name: 'Simulator' }).click()
  await expect(page.getByRole('heading', { name: 'Tournament simulator' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run simulation' })).toBeEnabled()
})
