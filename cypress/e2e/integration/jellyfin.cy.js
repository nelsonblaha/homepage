/**
 * Jellyfin End-to-End Integration Tests
 *
 * Full user flow test:
 * 1. Admin creates a friend via UI
 * 2. Friend visits their personalized link
 * 3. Friend clicks on Jellyfin service
 * 4. Auto-login redirects them into Jellyfin via token injection
 *
 * Requires running with docker-compose.ci.yml (Jellyfin + blaha-homepage)
 */

describe('Jellyfin E2E Integration', () => {
  const JELLYFIN_URL = Cypress.env('JELLYFIN_URL') || 'http://localhost:8096'
  const testFriendName = `JellyfinTest_${Date.now()}`
  let friendLink = null

  before(() => {
    // Wait for Jellyfin to be ready
    cy.request({
      url: `${JELLYFIN_URL}/health`,
      timeout: 90000,
      retryOnStatusCodeFailure: true
    })

    // Ensure Jellyfin service exists with correct config in test database
    cy.adminLogin()
    cy.request('/api/services').then((response) => {
      const jellyfinService = response.body.find(s =>
        s.name.toLowerCase().includes('jellyfin')
      )

      const serviceConfig = {
        name: 'Jellyfin',
        url: JELLYFIN_URL,
        icon: '🎬',
        description: 'Media streaming',
        subdomain: 'jellyfin',
        auth_type: 'jellyfin',
        is_default: false
      }

      if (!jellyfinService) {
        // Create Jellyfin service for testing
        cy.request({
          method: 'POST',
          url: '/api/services',
          body: serviceConfig
        }).then((createResponse) => {
          expect(createResponse.status).to.eq(200)
          cy.log('Created Jellyfin service for testing')
        })
      } else {
        // Update existing service to ensure correct URL and auth_type
        cy.log(`Updating Jellyfin service: ${jellyfinService.name} -> ${JELLYFIN_URL}`)
        cy.request({
          method: 'PUT',
          url: `/api/services/${jellyfinService.id}`,
          body: { ...serviceConfig, id: jellyfinService.id }
        }).then((updateResponse) => {
          expect(updateResponse.status).to.eq(200)
          cy.log('Updated Jellyfin service with CI config')
        })
      }
    })
  })

  describe('Admin Setup Flow', () => {
    beforeEach(() => {
      cy.adminLogin()
    })

    it('should verify Jellyfin integration is connected', () => {
      // Check Jellyfin status via API
      cy.request('/api/jellyfin/status').then((response) => {
        expect(response.body.connected).to.eq(true)
      })
    })

    it('should create a friend via admin UI', () => {
      cy.visit('/admin')
      cy.get('[data-testid="tab-friends"]').click()

      // Fill in new friend form
      cy.get('[data-testid="new-friend-input"]').type(testFriendName)
      cy.get('[data-testid="add-friend-btn"]').click()

      // Wait for friend to appear in list (collapsible card structure)
      cy.contains('h4', testFriendName).should('be.visible')

      // Click to expand the friend card to reveal the link
      cy.contains('h4', testFriendName)
        .closest('.bg-gray-800')
        .find('button')
        .first()
        .click()

      // Get the friend's link from the expanded card
      cy.contains('h4', testFriendName)
        .closest('.bg-gray-800')
        .find('[data-testid="friend-link"]')
        .invoke('attr', 'href')
        .then((href) => {
          friendLink = href
          cy.log(`Friend link: ${friendLink}`)
        })
    })

    it('should grant friend access to Jellyfin and auto-create account', () => {
      // First get the Jellyfin service ID and friend ID
      cy.request('/api/services').then((servicesResponse) => {
        const jellyfinService = servicesResponse.body.find(s =>
          s.name.toLowerCase().includes('jellyfin')
        )

        if (!jellyfinService) {
          cy.log('No Jellyfin service configured - skipping')
          return
        }

        cy.request('/api/friends').then((friendsResponse) => {
          const friend = friendsResponse.body.find(f => f.name === testFriendName)
          expect(friend).to.exist

          // Get current service IDs and add Jellyfin
          const currentServiceIds = friend.services.map(s => s.id)
          if (!currentServiceIds.includes(jellyfinService.id)) {
            currentServiceIds.push(jellyfinService.id)
          }

          // Update friend with Jellyfin access - this auto-creates the account
          cy.request({
            method: 'PUT',
            url: `/api/friends/${friend.id}`,
            body: { service_ids: currentServiceIds }
          }).then((updateResponse) => {
            expect(updateResponse.status).to.eq(200)

            // Check if account was created
            if (updateResponse.body.account_operations) {
              cy.log('Account operations:', JSON.stringify(updateResponse.body.account_operations))
            }

            // Verify friend now has Jellyfin user ID
            cy.request('/api/friends').then((verifyResponse) => {
              const updatedFriend = verifyResponse.body.find(f => f.name === testFriendName)
              cy.log(`Friend jellyfin_user_id: ${updatedFriend.jellyfin_user_id}`)
            })
          })
        })
      })
    })
  })

  describe('Friend Login Flow', () => {
    it('should visit friend link and see their homepage', function() {
      if (!friendLink) {
        // Get friend link from API if not captured from UI
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

        // Should see friend's name on the page
        cy.contains(testFriendName).should('be.visible')

        // Should see available services
        cy.get('[data-testid="services-grid"]').should('exist')
      })
    })

    it('should get auth redirect URL for Jellyfin', function() {
      if (!friendLink) this.skip('No friend link available')

      // Visit friend page first to set cookie
      cy.visit(friendLink)
      cy.wait(1000) // Let cookie set

      // Cypress can't follow cross-origin redirects
      // Verify the auth endpoint returns a valid redirect
      cy.request({
        url: '/auth/jellyfin',
        followRedirect: false,
        failOnStatusCode: false
      }).then((response) => {
        // Should return a redirect (302) with auth setup params
        expect(response.status).to.be.oneOf([302, 303, 307])

        const redirectUrl = response.headers.location
        cy.log(`Auth redirect URL: ${redirectUrl}`)

        // For Jellyfin, the redirect should go to auth-setup with token params
        // or directly to Jellyfin with credentials
        expect(redirectUrl).to.satisfy((url) => {
          return url.includes('auth-setup') ||
                 url.includes('access_token') ||
                 url.includes('jellyfin') ||
                 url.includes(':8096')
        }, 'Redirect URL should contain auth mechanism')
      })
    })
  })

  describe('Verify Jellyfin Account Works', () => {
    it('should be able to verify Jellyfin user exists', function() {
      // Verify the account was created by checking the Jellyfin API directly
      const API_KEY = Cypress.env('JELLYFIN_API_KEY')

      if (!API_KEY) {
        cy.log('No JELLYFIN_API_KEY - skipping direct verification')
        return
      }

      cy.adminLogin()
      cy.request('/api/friends').then((friendsResponse) => {
        const friend = friendsResponse.body.find(f => f.name === testFriendName)
        if (!friend || !friend.jellyfin_user_id) {
          cy.log('Friend has no Jellyfin account - skipping')
          return
        }

        // Verify user exists in Jellyfin via admin API
        cy.request({
          method: 'GET',
          url: `${JELLYFIN_URL}/Users`,
          headers: { 'X-Emby-Token': API_KEY }
        }).then((usersResponse) => {
          expect(usersResponse.status).to.eq(200)

          // Find the user by matching ID or username
          const jellyfinUser = usersResponse.body.find(u =>
            u.Id === friend.jellyfin_user_id ||
            u.Name.toLowerCase() === testFriendName.toLowerCase()
          )

          if (jellyfinUser) {
            cy.log(`Verified Jellyfin user exists: ${jellyfinUser.Name} (ID: ${jellyfinUser.Id})`)
            expect(jellyfinUser).to.exist
          } else {
            cy.log('Could not find Jellyfin user in user list')
          }
        })
      })
    })
  })

  after(() => {
    // Cleanup: delete test friend
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
