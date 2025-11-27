// Cypress E2E support file

// Custom command for admin login
Cypress.Commands.add('adminLogin', (password) => {
  const adminPassword = password || Cypress.env('ADMIN_PASSWORD') || 'testpassword'
  cy.visit('/admin')
  cy.get('input[type="password"]').type(adminPassword)
  cy.get('button[type="submit"]').click()
  cy.url().should('include', '/admin')
})

// Custom command to check if app is healthy
Cypress.Commands.add('healthCheck', () => {
  cy.request('/api/admin/verify').its('status').should('be.oneOf', [200, 401])
})
