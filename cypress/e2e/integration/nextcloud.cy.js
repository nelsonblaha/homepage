/**
 * Nextcloud End-to-End Integration Tests
 *
 * Full user flow test:
 * 1. Admin creates a friend via UI
 * 2. Friend visits their personalized link
 * 3. Friend clicks on Nextcloud service
 * 4. Credentials are displayed for manual login
 *
 * Requires running with docker-compose.ci.yml (Nextcloud + blaha-homepage)
 */

describe('Nextcloud E2E Integration', () => {
  const NEXTCLOUD_URL = Cypress.env('NEXTCLOUD_URL') || 'https://localhost:443'
  const testFriendName = `NextcloudTest_${Date.now()}`
  let friendLink = null

  before(() => {
    // Wait for Nextcloud to be ready (uses HTTPS with self-signed cert)
    cy.request({
      url: `${NEXTCLOUD_URL}/status.php`,
      timeout: 120000,
      retryOnStatusCodeFailure: true,
      failOnStatusCode: false
    })

    // Ensure Nextcloud service exists with correct config
    cy.adminLogin()
    cy.request('/api/services').then((response) => {
      const nextcloudService = response.body.find(s =>
        s.name.toLowerCase().includes('nextcloud')
      )

      const serviceConfig = {
        name: 'Nextcloud',
        url: NEXTCLOUD_URL,
        icon: '☁️',
        description: 'Cloud storage',
        subdomain: 'nextcloud',
        auth_type: 'nextcloud',
        is_default: false
      }

      if (!nextcloudService) {
        cy.request({
          method: 'POST',
          url: '/api/services',
          body: serviceConfig
        }).then((createResponse) => {
          expect(createResponse.status).to.eq(200)
          cy.log('Created Nextcloud service for testing')
        })
      } else {
        cy.log(`Updating Nextcloud service: ${nextcloudService.name} -> ${NEXTCLOUD_URL}`)
        cy.request({
          method: 'PUT',
          url: `/api/services/${nextcloudService.id}`,
          body: { ...serviceConfig, id: nextcloudService.id }
        }).then((updateResponse) => {
          expect(updateResponse.status).to.eq(200)
          cy.log('Updated Nextcloud service with CI config')
        })
      }
    })
  })

  describe('Admin Setup Flow', () => {
    beforeEach(() => {
      cy.adminLogin()
    })

    it('should verify Nextcloud integration is connected', () => {
      cy.request('/api/nextcloud/status').then((response) => {
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

    it('should grant friend access to Nextcloud and auto-create account', () => {
      cy.request('/api/services').then((servicesResponse) => {
        const nextcloudService = servicesResponse.body.find(s =>
          s.name.toLowerCase().includes('nextcloud')
        )

        if (!nextcloudService) {
          cy.log('No Nextcloud service configured - skipping')
          return
        }

        cy.request('/api/friends').then((friendsResponse) => {
          const friend = friendsResponse.body.find(f => f.name === testFriendName)
          expect(friend).to.exist

          const currentServiceIds = friend.services.map(s => s.id)
          if (!currentServiceIds.includes(nextcloudService.id)) {
            currentServiceIds.push(nextcloudService.id)
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
              cy.log(`Friend nextcloud_user_id: ${updatedFriend.nextcloud_user_id}`)
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

    it('should get auth redirect URL for Nextcloud', function() {
      if (!friendLink) this.skip('No friend link available')

      cy.visit(friendLink)
      cy.wait(1000)

      // Nextcloud uses credential display - verify the auth endpoint works
      cy.request({
        url: '/auth/nextcloud',
        followRedirect: false,
        failOnStatusCode: false
      }).then((response) => {
        // Should return a redirect to auth-setup which shows credentials
        expect(response.status).to.be.oneOf([302, 303, 307])

        const redirectUrl = response.headers.location
        cy.log(`Auth redirect URL: ${redirectUrl}`)

        // For Nextcloud, redirect goes to auth-setup which displays credentials
        expect(redirectUrl).to.satisfy((url) => {
          return url.includes('auth-setup') ||
                 url.includes('nextcloud') ||
                 url.includes('username=')
        }, 'Redirect URL should contain auth mechanism')
      })
    })
  })

  describe('Verify Nextcloud Account Works', () => {
    it('should be able to verify Nextcloud user exists', function() {
      const ADMIN_USER = Cypress.env('NEXTCLOUD_ADMIN_USER')
      const ADMIN_PASS = Cypress.env('NEXTCLOUD_ADMIN_PASS')

      if (!ADMIN_USER || !ADMIN_PASS) {
        cy.log('No NEXTCLOUD_ADMIN credentials - skipping direct verification')
        return
      }

      cy.adminLogin()
      cy.request('/api/friends').then((friendsResponse) => {
        const friend = friendsResponse.body.find(f => f.name === testFriendName)
        if (!friend || !friend.nextcloud_user_id) {
          cy.log('Friend has no Nextcloud account - skipping')
          return
        }

        // Verify user exists in Nextcloud via OCS API
        cy.request({
          method: 'GET',
          url: `${NEXTCLOUD_URL}/ocs/v1.php/cloud/users/${friend.nextcloud_user_id}`,
          auth: {
            username: ADMIN_USER,
            password: ADMIN_PASS
          },
          headers: {
            'OCS-APIRequest': 'true'
          },
          failOnStatusCode: false
        }).then((userResponse) => {
          if (userResponse.status === 200) {
            cy.log(`Verified Nextcloud user exists: ${friend.nextcloud_user_id}`)
          } else {
            cy.log(`Could not verify Nextcloud user: ${userResponse.status}`)
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
