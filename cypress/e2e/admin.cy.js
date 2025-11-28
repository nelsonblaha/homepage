describe('Admin Authentication', () => {
  beforeEach(() => {
    cy.visit('/')
  })

  it('should show login form on root page', () => {
    cy.get('input[type="password"]').should('be.visible')
    cy.get('button[type="submit"]').should('be.visible')
  })

  it('should show error on invalid password', () => {
    cy.get('input[type="password"]').type('wrongpassword')
    cy.get('[data-testid="login-btn"]').click()
    cy.get('[data-testid="error"]').should('be.visible')
  })
})

describe('Admin Dashboard', () => {
  beforeEach(() => {
    cy.adminLogin()
  })

  it('should login with valid password via API', () => {
    cy.url().should('include', '/admin')
    cy.get('[data-testid="tab-friends"]').should('be.visible')
  })

  it('should show admin dashboard tabs', () => {
    cy.get('[data-testid="tab-friends"]').should('be.visible')
    cy.get('[data-testid="tab-services"]').should('be.visible')
  })

  it('should switch between tabs', () => {
    cy.get('[data-testid="tab-services"]').click()
    cy.get('[data-testid="services-panel"]').should('be.visible')
    cy.get('[data-testid="tab-friends"]').click()
    cy.get('[data-testid="friends-panel"]').should('be.visible')
  })

  it('should logout successfully', () => {
    cy.get('[data-testid="logout-btn"]').click()
    cy.get('input[type="password"]', { timeout: 10000 }).should('be.visible')
  })
})
