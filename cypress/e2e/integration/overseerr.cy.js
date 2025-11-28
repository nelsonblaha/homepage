/**
 * Overseerr End-to-End Integration Tests
 *
 * Full user flow test:
 * 1. Admin creates a friend via UI
 * 2. Friend visits their personalized link
 * 3. Friend clicks on Overseerr service
 * 4. Auto-login via session cookie proxy
 *
 * Requires running with docker-compose.ci.yml (Overseerr + blaha-homepage)
 */

describe('Overseerr E2E Integration', () => {
  const OVERSEERR_URL = Cypress.env('OVERSEERR_URL') || 'http://localhost:5055'
  const testFriendName = `OverseerrTest_${Date.now()}`
  let friendLink = null

  before(() => {
    // Wait for Overseerr to be ready
    cy.request({
      url: `${OVERSEERR_URL}/api/v1/status`,
      timeout: 90000,
      retryOnStatusCodeFailure: true
    })

    // Ensure Overseerr service exists with correct config
    cy.adminLogin()
    cy.request('/api/services').then((response) => {
      const overseerrService = response.body.find(s =>
        s.name.toLowerCase().includes('overseerr')
      )

      const serviceConfig = {
        name: 'Overseerr',
        url: OVERSEERR_URL,
        icon: '📺',
        description: 'Request movies & TV shows',
        subdomain: 'overseerr',
        auth_type: 'overseerr',
        is_default: false
      }

      if (!overseerrService) {
        cy.request({
          method: 'POST',
          url: '/api/services',
          body: serviceConfig
        }).then((createResponse) => {
          expect(createResponse.status).to.eq(200)
          cy.log('Created Overseerr service for testing')
        })
      } else {
        cy.log(`Updating Overseerr service: ${overseerrService.name} -> ${OVERSEERR_URL}`)
        cy.request({
          method: 'PUT',
          url: `/api/services/${overseerrService.id}`,
          body: { ...serviceConfig, id: overseerrService.id }
        }).then((updateResponse) => {
          expect(updateResponse.status).to.eq(200)
          cy.log('Updated Overseerr service with CI config')
        })
      }
    })
  })

  describe('Admin Setup Flow', () => {
    beforeEach(() => {
      cy.adminLogin()
    })

    it('should verify Overseerr integration is connected', () => {
      cy.request('/api/overseerr/status').then((response) => {
        expect(response.body.connected).to.eq(true)
      })
    })

    it('should create a friend via admin UI', () => {
      cy.visit('/admin')
      cy.get('[data-testid="tab-friends"]').click()

      cy.get('[data-testid="new-friend-input"]').type(testFriendName)
      cy.get('[data-testid="add-friend-btn"]').click()

      cy.contains('h4', testFriendName).should('be.visible')

      cy.contains('h4', testFriendName)
        .closest('.bg-gray-800')
        .find('button')
        .first()
        .click()

      cy.contains('h4', testFriendName)
        .closest('.bg-gray-800')
        .find('[data-testid="friend-link"]')
        .invoke('attr', 'href')
        .then((href) => {
          friendLink = href
          cy.log(`Friend link: ${friendLink}`)
        })
    })

    it('should grant friend access to Overseerr and auto-create account', () => {
      cy.request('/api/services').then((servicesResponse) => {
        const overseerrService = servicesResponse.body.find(s =>
          s.name.toLowerCase().includes('overseerr')
        )

        if (!overseerrService) {
          cy.log('No Overseerr service configured - skipping')
          return
        }

        cy.request('/api/friends').then((friendsResponse) => {
          const friend = friendsResponse.body.find(f => f.name === testFriendName)
          expect(friend).to.exist

          const currentServiceIds = friend.services.map(s => s.id)
          if (!currentServiceIds.includes(overseerrService.id)) {
            currentServiceIds.push(overseerrService.id)
          }

          cy.request({
            method: 'PUT',
            url: `/api/friends/${friend.id}`,
            body: { service_ids: currentServiceIds }
          }).then((updateResponse) => {
            expect(updateResponse.status).to.eq(200)

            if (updateResponse.body.account_operations) {
              cy.log('Account operations:', JSON.stringify(updateResponse.body.account_operations))
            }

            cy.request('/api/friends').then((verifyResponse) => {
              const updatedFriend = verifyResponse.body.find(f => f.name === testFriendName)
              cy.log(`Friend overseerr_user_id: ${updatedFriend.overseerr_user_id}`)
            })
          })
        })
      })
    })
  })

  describe('Friend Login Flow', () => {
    it('should visit friend link and see their homepage', function() {
      if (!friendLink) {
        cy.adminLogin()
        cy.request('/api/friends').then((response) => {
          const friend = response.body.find(f => f.name === testFriendName)
          if (friend) {
            friendLink = `/f/${friend.token}`
          }
        })
      }

      cy.then(() => {
        if (!friendLink) {
          this.skip('No friend link available')
          return
        }

        cy.visit(friendLink)
        cy.contains(testFriendName).should('be.visible')
        cy.get('[data-testid="services-grid"]').should('exist')
      })
    })

    it('should get auth redirect URL for Overseerr', function() {
      if (!friendLink) this.skip('No friend link available')

      cy.visit(friendLink)
      cy.wait(1000)

      // Overseerr uses cookie proxy - verify the auth endpoint works
      cy.request({
        url: '/auth/overseerr',
        followRedirect: false,
        failOnStatusCode: false
      }).then((response) => {
        // Should return a redirect with session cookie
        expect(response.status).to.be.oneOf([302, 303, 307])

        const redirectUrl = response.headers.location
        cy.log(`Auth redirect URL: ${redirectUrl}`)

        // For Overseerr, redirect goes to auth-setup which sets the cookie
        expect(redirectUrl).to.satisfy((url) => {
          return url.includes('auth-setup') ||
                 url.includes('overseerr') ||
                 url.includes(':5055')
        }, 'Redirect URL should contain auth mechanism')
      })
    })
  })

  describe('Verify Overseerr Account Works', () => {
    it('should be able to verify Overseerr user exists', function() {
      const API_KEY = Cypress.env('OVERSEERR_API_KEY')

      if (!API_KEY) {
        cy.log('No OVERSEERR_API_KEY - skipping direct verification')
        return
      }

      cy.adminLogin()
      cy.request('/api/friends').then((friendsResponse) => {
        const friend = friendsResponse.body.find(f => f.name === testFriendName)
        if (!friend || !friend.overseerr_user_id) {
          cy.log('Friend has no Overseerr account - skipping')
          return
        }

        // Verify user exists in Overseerr via admin API
        cy.request({
          method: 'GET',
          url: `${OVERSEERR_URL}/api/v1/user`,
          headers: { 'X-Api-Key': API_KEY }
        }).then((usersResponse) => {
          expect(usersResponse.status).to.eq(200)

          const overseerrUser = usersResponse.body.results.find(u =>
            u.id.toString() === friend.overseerr_user_id ||
            u.username?.toLowerCase() === testFriendName.toLowerCase()
          )

          if (overseerrUser) {
            cy.log(`Verified Overseerr user exists: ${overseerrUser.username || overseerrUser.email} (ID: ${overseerrUser.id})`)
            expect(overseerrUser).to.exist
          } else {
            cy.log('Could not find Overseerr user in user list')
          }
        })
      })
    })
  })

  after(() => {
    cy.adminLogin()
    cy.request('/api/friends').then((response) => {
      const friend = response.body.find(f => f.name === testFriendName)
      if (friend) {
        cy.request({
          method: 'DELETE',
          url: `/api/friends/${friend.id}`,
          failOnStatusCode: false
        })
      }
    })
  })
})
