describe('Service Management', () => {
  beforeEach(() => {
    cy.adminLogin()
    cy.get('[data-testid="tab-services"]').click()
  })

  it('should display services panel', () => {
    cy.get('[data-testid="services-panel"]').should('be.visible')
  })

  it('should show add service form', () => {
    cy.get('[data-testid="add-service-btn"]').click()
    cy.get('[data-testid="service-form"]').should('be.visible')
  })

  it('should load integration status', () => {
    // Check that integration status section exists
    cy.get('[data-testid="integrations"]').should('exist')
  })
})
