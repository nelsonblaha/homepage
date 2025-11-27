describe('API Endpoints', () => {
  describe('Public endpoints', () => {
    it('GET /api/admin/verify returns authenticated: false when not logged in', () => {
      cy.request('/api/admin/verify').then((response) => {
        expect(response.status).to.eq(200)
        expect(response.body.authenticated).to.eq(false)
      })
    })

    it('GET /api/f/{invalid} returns 404', () => {
      cy.request({
        url: '/api/f/invalidtoken123',
        failOnStatusCode: false
      }).then((response) => {
        expect(response.status).to.eq(404)
      })
    })
  })

  describe('Protected endpoints', () => {
    it('GET /api/services returns 401 when not authenticated', () => {
      cy.request({
        url: '/api/services',
        failOnStatusCode: false
      }).then((response) => {
        expect(response.status).to.eq(401)
      })
    })

    it('GET /api/friends returns 401 when not authenticated', () => {
      cy.request({
        url: '/api/friends',
        failOnStatusCode: false
      }).then((response) => {
        expect(response.status).to.eq(401)
      })
    })

    it('POST /api/admin/login rejects invalid password', () => {
      cy.request({
        method: 'POST',
        url: '/api/admin/login',
        body: { password: 'wrongpassword' },
        failOnStatusCode: false
      }).then((response) => {
        expect(response.status).to.eq(401)
      })
    })
  })

  // Skip authenticated tests until CI env var issue is resolved
  describe.skip('Authenticated endpoints', () => {
    beforeEach(() => {
      cy.adminLogin()
    })

    it('GET /api/admin/verify returns authenticated: true', () => {
      cy.request('/api/admin/verify').then((response) => {
        expect(response.status).to.eq(200)
        expect(response.body.authenticated).to.eq(true)
        expect(response.body.type).to.eq('admin')
      })
    })

    it('GET /api/services returns service list', () => {
      cy.request('/api/services').then((response) => {
        expect(response.status).to.eq(200)
        expect(response.body).to.be.an('array')
      })
    })

    it('GET /api/friends returns friends list', () => {
      cy.request('/api/friends').then((response) => {
        expect(response.status).to.eq(200)
        expect(response.body).to.be.an('array')
      })
    })
  })
})
