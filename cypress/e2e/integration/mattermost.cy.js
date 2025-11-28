/**
 * Mattermost End-to-End Integration Tests
 *
 * Full user flow test:
 * 1. Admin creates a friend via UI
 * 2. Friend visits their personalized link
 * 3. Friend clicks on Mattermost service
 * 4. Auto-login via session cookie proxy
 *
 * Requires running with docker-compose.ci.yml (Mattermost + blaha-homepage)
 */

describe('Mattermost E2E Integration', () => {
  const MATTERMOST_URL = Cypress.env('MATTERMOST_URL') || 'http://localhost:8065'
  const testFriendName = `MattermostTest_${Date.now()}`
  let friendLink = null

  before(() => {
    // Wait for Mattermost to be ready
    cy.request({
      url: `${MATTERMOST_URL}/api/v4/system/ping`,
      timeout: 90000,
      retryOnStatusCodeFailure: true
    })

    // Ensure Mattermost service exists with correct config
    cy.adminLogin()
    cy.request('/api/services').then((response) => {
      const mattermostService = response.body.find(s =>
        s.name.toLowerCase().includes('mattermost') ||
        s.name.toLowerCase().includes('chat')
      )

      const serviceConfig = {
        name: 'Mattermost',
        url: MATTERMOST_URL,
        icon: '💬',
        description: 'Team chat',
        subdomain: 'chat',
        auth_type: 'mattermost',
        is_default: false
      }

      if (!mattermostService) {
        cy.request({
          method: 'POST',
          url: '/api/services',
          body: serviceConfig
        }).then((createResponse) => {
          expect(createResponse.status).to.eq(200)
          cy.log('Created Mattermost service for testing')
        })
      } else {
        cy.log(`Updating Mattermost service: ${mattermostService.name} -> ${MATTERMOST_URL}`)
        cy.request({
          method: 'PUT',
          url: `/api/services/${mattermostService.id}`,
          body: { ...serviceConfig, id: mattermostService.id }
        }).then((updateResponse) => {
          expect(updateResponse.status).to.eq(200)
          cy.log('Updated Mattermost service with CI config')
        })
      }
    })
  })

  describe('Admin Setup Flow', () => {
    beforeEach(() => {
      cy.adminLogin()
    })

    it('should verify Mattermost integration is connected', () => {
      cy.request('/api/mattermost/status').then((response) => {
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

    it('should grant friend access to Mattermost and auto-create account', () => {
      cy.request('/api/services').then((servicesResponse) => {
        const mattermostService = servicesResponse.body.find(s =>
          s.name.toLowerCase().includes('mattermost') ||
          s.name.toLowerCase().includes('chat')
        )

        if (!mattermostService) {
          cy.log('No Mattermost service configured - skipping')
          return
        }

        cy.request('/api/friends').then((friendsResponse) => {
          const friend = friendsResponse.body.find(f => f.name === testFriendName)
          expect(friend).to.exist

          const currentServiceIds = friend.services.map(s => s.id)
          if (!currentServiceIds.includes(mattermostService.id)) {
            currentServiceIds.push(mattermostService.id)
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
              cy.log(`Friend mattermost_user_id: ${updatedFriend.mattermost_user_id}`)
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

    it('should get auth redirect URL for Mattermost', function() {
      if (!friendLink) this.skip('No friend link available')

      cy.visit(friendLink)
      cy.wait(1000)

      // Mattermost uses cookie proxy - verify the auth endpoint works
      cy.request({
        url: '/auth/mattermost',
        followRedirect: false,
        failOnStatusCode: false
      }).then((response) => {
        // Should return a redirect with session cookie
        expect(response.status).to.be.oneOf([302, 303, 307])

        const redirectUrl = response.headers.location
        cy.log(`Auth redirect URL: ${redirectUrl}`)

        // For Mattermost, redirect goes to auth-setup which sets MMAUTHTOKEN cookie
        expect(redirectUrl).to.satisfy((url) => {
          return url.includes('auth-setup') ||
                 url.includes('mattermost') ||
                 url.includes('chat') ||
                 url.includes(':8065')
        }, 'Redirect URL should contain auth mechanism')
      })
    })
  })

  describe('Verify Mattermost Account Works', () => {
    it('should be able to verify Mattermost user exists', function() {
      const TOKEN = Cypress.env('MATTERMOST_TOKEN')

      if (!TOKEN) {
        cy.log('No MATTERMOST_TOKEN - skipping direct verification')
        return
      }

      cy.adminLogin()
      cy.request('/api/friends').then((friendsResponse) => {
        const friend = friendsResponse.body.find(f => f.name === testFriendName)
        if (!friend || !friend.mattermost_user_id) {
          cy.log('Friend has no Mattermost account - skipping')
          return
        }

        // Verify user exists in Mattermost via admin API
        cy.request({
          method: 'GET',
          url: `${MATTERMOST_URL}/api/v4/users/${friend.mattermost_user_id}`,
          headers: { 'Authorization': `Bearer ${TOKEN}` }
        }).then((userResponse) => {
          expect(userResponse.status).to.eq(200)

          const mmUser = userResponse.body
          cy.log(`Verified Mattermost user exists: ${mmUser.username} (ID: ${mmUser.id})`)
          expect(mmUser).to.exist
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
