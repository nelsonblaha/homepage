describe('Infrastructure Health Tab', () => {
  beforeEach(() => {
    // Mock the health daemon API responses
    cy.intercept('POST', '/api/health/refresh', {
      statusCode: 200,
      body: { status: 'refreshed', checks: 9 }
    }).as('healthRefresh')

    cy.intercept('GET', '/api/health/status', {
      statusCode: 200,
      body: {
        summary: {
          total: 9,
          ok: 6,
          info: 1,
          warning: 2,
          critical: 0
        }
      }
    }).as('healthStatus')

    cy.intercept('GET', '/api/health/infra', {
      statusCode: 200,
      body: {
        infra: [
          {
            check_id: 'infrastructure:disk',
            name: 'Disk Usage',
            severity: 'ok',
            message: '16.9% used (267GB free)',
            timestamp: new Date().toISOString()
          },
          {
            check_id: 'infrastructure:memory',
            name: 'Memory Usage',
            severity: 'ok',
            message: '50.3% used (15GB available)',
            timestamp: new Date().toISOString()
          },
          {
            check_id: 'infrastructure:docker',
            name: 'Docker Daemon',
            severity: 'ok',
            message: 'Docker daemon responding',
            timestamp: new Date().toISOString()
          }
        ]
      }
    }).as('healthInfra')

    cy.intercept('GET', '/api/health/containers', {
      statusCode: 200,
      body: {
        containers: {
          'mattermost': [
            {
              check_id: 'docker_security:mattermost',
              name: 'Security: mattermost',
              severity: 'ok',
              message: 'No security issues',
              container_name: 'mattermost',
              timestamp: new Date().toISOString()
            },
            {
              check_id: 'log_monitor:mattermost',
              name: 'Logs: mattermost',
              severity: 'info',
              message: '9 info items in last 5min',
              container_name: 'mattermost',
              timestamp: new Date().toISOString(),
              details: {
                issues: [
                  { severity: 'info', line: 'Failed to get license from disk' },
                  { severity: 'info', line: 'License key required' },
                  { severity: 'info', line: 'Error loading plugin icon' }
                ],
                issue_count: 9
              }
            }
          ],
          'syncthing': [
            {
              check_id: 'docker_security:syncthing',
              name: 'Security: syncthing',
              severity: 'warning',
              message: 'Using host network (no isolation)',
              container_name: 'syncthing',
              timestamp: new Date().toISOString()
            }
          ],
          'mastodon-sidekiq': [
            {
              check_id: 'docker_security:mastodon-sidekiq',
              name: 'Security: mastodon-sidekiq',
              severity: 'warning',
              message: 'Docker health check failing',
              container_name: 'mastodon-sidekiq',
              timestamp: new Date().toISOString()
            }
          ]
        }
      }
    }).as('healthContainers')

    cy.adminLogin()
  })

  it('should load health checks in background on page load', () => {
    // Wait for background health data to load
    cy.wait('@healthRefresh', { timeout: 10000 })
    cy.wait('@healthStatus')
    cy.wait('@healthInfra')
    cy.wait('@healthContainers')
  })

  it('should display infra tab with health checks', () => {
    // Click on infra tab
    cy.get('[data-testid="tab-infra"]').click()

    // Should show infra panel
    cy.get('[data-testid="infra-panel"]').should('be.visible')

    // Should display checks sorted by severity
    cy.get('[data-testid="infra-panel"]').within(() => {
      // Check that checks are displayed
      cy.contains('Disk Usage').should('be.visible')
      cy.contains('Memory Usage').should('be.visible')
      cy.contains('Docker Daemon').should('be.visible')
      cy.contains('Security: mattermost').should('be.visible')
      cy.contains('Logs: mattermost').should('be.visible')
      cy.contains('Security: syncthing').should('be.visible')
      cy.contains('Security: mastodon-sidekiq').should('be.visible')
    })
  })

  it('should show correct severity indicators', () => {
    cy.get('[data-testid="tab-infra"]').click()

    cy.get('[data-testid="infra-panel"]').within(() => {
      // OK checks should have green circle (●)
      cy.contains('Disk Usage').parent().parent().should('contain', '●')

      // INFO checks should have blue ℹ symbol
      cy.contains('Logs: mattermost').parent().parent().should('contain', 'ℹ')

      // WARNING checks should have yellow ⚠ symbol
      cy.contains('Security: syncthing').parent().parent().should('contain', '⚠')
    })
  })

  it('should sort checks by severity (critical → warning → info → ok)', () => {
    cy.get('[data-testid="tab-infra"]').click()

    // Get all check names in order
    cy.get('[data-testid="infra-panel"] .font-medium').then($checks => {
      const checkTexts = [...$checks].map(el => el.textContent.trim())

      // Warnings should come before info
      const warningIndex1 = checkTexts.indexOf('Security: syncthing')
      const warningIndex2 = checkTexts.indexOf('Security: mastodon-sidekiq')
      const infoIndex = checkTexts.indexOf('Logs: mattermost')

      expect(warningIndex1).to.be.lessThan(infoIndex)
      expect(warningIndex2).to.be.lessThan(infoIndex)
    })
  })

  it('should show summary badge in admin tab bar', () => {
    // Should show warning/critical count badge
    cy.get('[data-testid="tab-infra"]').within(() => {
      // 2 warnings (syncthing + mastodon-sidekiq)
      cy.contains('2').should('be.visible')
    })
  })

  it('should NOT count INFO-level issues in warning badge', () => {
    // The badge should show 2 (only warnings), not 3 (warnings + info)
    cy.get('[data-testid="tab-infra"]').within(() => {
      cy.contains('2').should('be.visible')
      cy.contains('3').should('not.exist')
    })
  })

  it('should refresh health checks on button click', () => {
    cy.get('[data-testid="tab-infra"]').click()

    // Click refresh button
    cy.contains('button', 'Refresh Health Checks').click()

    // Should trigger refresh API calls
    cy.wait('@healthRefresh')
    cy.wait('@healthStatus')
    cy.wait('@healthInfra')
    cy.wait('@healthContainers')
  })

  it('should display INFO issue details when present', () => {
    cy.get('[data-testid="tab-infra"]').click()

    // INFO check should show count in message
    cy.contains('Logs: mattermost')
      .parent()
      .parent()
      .within(() => {
        cy.contains('9 info items in last 5min').should('be.visible')
      })
  })

  it('should show different colors for different severities', () => {
    cy.get('[data-testid="tab-infra"]').click()

    cy.get('[data-testid="infra-panel"]').within(() => {
      // OK - green
      cy.contains('Disk Usage')
        .parent()
        .parent()
        .find('span')
        .first()
        .should('have.class', 'text-green-400')

      // INFO - blue
      cy.contains('Logs: mattermost')
        .parent()
        .parent()
        .find('span')
        .first()
        .should('have.class', 'text-blue-400')

      // WARNING - yellow
      cy.contains('Security: syncthing')
        .parent()
        .parent()
        .find('span')
        .first()
        .should('have.class', 'text-yellow-400')
    })
  })
})

describe('Infrastructure Health - Streaming Behavior', () => {
  it('should handle incremental health check updates', () => {
    // Mock streaming behavior - checks arrive one by one
    const checks = [
      { check_id: 'infra:disk', name: 'Disk Usage', severity: 'ok', message: 'OK' },
      { check_id: 'infra:memory', name: 'Memory Usage', severity: 'ok', message: 'OK' },
      { check_id: 'sec:mattermost', name: 'Security: mattermost', severity: 'ok', message: 'OK' }
    ]

    let checkIndex = 0

    // Intercept with dynamic response
    cy.intercept('POST', '/api/health/refresh', { statusCode: 200, body: {} })
    cy.intercept('GET', '/api/health/status', (req) => {
      req.reply({
        statusCode: 200,
        body: {
          summary: {
            total: checkIndex + 1,
            ok: checkIndex + 1,
            info: 0,
            warning: 0,
            critical: 0
          }
        }
      })
    })

    cy.intercept('GET', '/api/health/infra', (req) => {
      const currentChecks = checks.slice(0, checkIndex + 1).map(c => ({
        ...c,
        container_name: null,
        timestamp: new Date().toISOString()
      }))
      checkIndex = Math.min(checkIndex + 1, checks.length - 1)

      req.reply({
        statusCode: 200,
        body: { infra: currentChecks }
      })
    })

    cy.intercept('GET', '/api/health/containers', { statusCode: 200, body: { containers: {} } })

    cy.adminLogin()
    cy.get('[data-testid="tab-infra"]').click()

    // Should show checks appearing incrementally
    cy.contains('Disk Usage', { timeout: 5000 }).should('be.visible')
  })
})
