// Cypress E2E support file

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
