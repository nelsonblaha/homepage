// Cypress E2E support file

// Ignore uncaught exceptions from cross-origin scripts (Alpine.js, Tailwind CDN)
// These external scripts can throw errors that aren't related to our tests
Cypress.on('uncaught:exception', (err, runnable) => {
  // Return false to prevent Cypress from failing the test
  // when third-party scripts throw errors
  if (err.message.includes('Script error') ||
      err.message.includes('cross origin') ||
      err.message.includes('ResizeObserver') ||
      err.message.includes('Cannot read properties of null')) {
    return false
  }
  // Let other errors fail the test
  return true
})

// Custom command for admin login via API (more reliable)
Cypress.Commands.add('adminLogin', (password) => {
  const adminPassword = password || Cypress.env('ADMIN_PASSWORD') || 'testpassword'

  // Login via API to get session cookie
  cy.request({
    method: 'POST',
    url: '/api/admin/login',
    body: { password: adminPassword, remember: true }
  }).then((response) => {
    expect(response.status).to.eq(200)
  })

  // Now visit admin page
  cy.visit('/admin')
  cy.url().should('include', '/admin')

  // Wait for admin panel to load (tabs should be visible)
  cy.get('[data-testid="tab-friends"]', { timeout: 10000 }).should('be.visible')
})

// Custom command to check if app is healthy
Cypress.Commands.add('healthCheck', () => {
  cy.request('/api/admin/verify').its('status').should('be.oneOf', [200, 401])
})
