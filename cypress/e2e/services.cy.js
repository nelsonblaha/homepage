describe('Service Management', () => {
  beforeEach(() => {
    cy.adminLogin()
    cy.get('[data-testid="tab-services"]').click()
  })

  it('should display services panel', () => {
    cy.get('[data-testid="services-panel"]').should('be.visible')
  })

  it('should show add service form', () => {
    // The add service form is always visible at the bottom of the services panel
    cy.get('[data-testid="services-panel"]').within(() => {
      cy.contains('Add Service').should('be.visible')
      cy.get('input[placeholder="Service name"]').should('be.visible')
    })
  })

  it('should load integration status', () => {
    // Integration status is on the friends tab
    cy.get('[data-testid="tab-friends"]').click()
    cy.get('[data-testid="integrations"]').should('exist')
  })
})
