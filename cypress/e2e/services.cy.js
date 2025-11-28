describe('Service Management', () => {
  beforeEach(() => {
    cy.adminLogin()
    cy.get('[data-testid="tab-services"]').click()
  })

  it('should display services panel', () => {
    cy.get('[data-testid="services-panel"]').should('be.visible')
  })

  it('should show add service form', () => {
    cy.get('[data-testid="services-panel"]').within(() => {
      cy.contains('Add Service').should('be.visible')
      cy.get('input[placeholder="Service name"]').should('be.visible')
    })
  })

  it('should load integration status via API', () => {
    // Integration status is now loaded via API, not a UI element
    cy.request('/api/services/integrations-summary').then((response) => {
      expect(response.status).to.eq(200)
      expect(response.body).to.be.an('object')
    })
  })
})
