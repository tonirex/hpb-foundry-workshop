// Lab 4 DevUI in a browser (LAB4_DEVUI, optional): demos/lab4-devui.py on the workshop Container Apps environment,
// so participants explore the sequential and hand-off workflows without local Python or Codespaces.
// `azd deploy lab4-devui` replaces the placeholder image (demos/devui-aca/). DevUI is a sample app, not a
// production host: private expiring links exchange into secure browser sessions; the shared bearer stays server-side.
// It runs in developer mode (for the trace panel), keeps conversations in memory (so exactly
// one replica), builds a fresh workflow for every run and caps runs in flight per workflow at LIVEWELL_DEVUI_SEATS.
// Its own identity holds only AcrPull and Foundry User on the project (the same data-plane role as an attendee).
param location string
param tags object
param name string
param identityName string
param environmentId string
param acrName string
param accountName string
param projectName string
param projectEndpoint string

@secure()
@description('Server-only DevUI bearer and launch-ticket signing secret (LIVEWELL_DEVUI_TOKEN). Never distribute it to participants.')
param authToken string

@description('Image last deployed by `azd deploy lab4-devui` (SERVICE_LAB4_DEVUI_IMAGE_NAME). Empty = placeholder.')
param image string = ''

@description('0 = scale to zero between sessions (first page load waits for a replica). Set 1 on the workshop day.')
@minValue(0)
@maxValue(1)
param minReplicas int = 0

@description('Runs of one workflow in flight at once (each run builds a fresh workflow). Each run uses tens of thousands of tokens, so the gpt-5-mini TPM cap is the real limit.')
@minValue(1)
@maxValue(12)
param seats int = 8

var roles = loadYamlContent('../../content/config/workshop.yaml', '$.rbac_roles')

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName

  resource project 'projects' existing = {
    name: projectName
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
  tags: tags
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, identity.id, roles.acr_pull)
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acr_pull)
  }
}

resource foundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: account::project
  name: guid(account::project.id, identity.id, roles.foundry_user)
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.foundry_user)
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: union(tags, { 'azd-service-name': 'lab4-devui' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 80
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: identity.id
        }
      ]
      secrets: [
        {
          name: 'devui-auth-token'
          value: authToken
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'lab4-devui'
          image: empty(image) ? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' : image
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            {
              name: 'DEVUI_AUTH_TOKEN'
              secretRef: 'devui-auth-token'
            }
            {
              name: 'FOUNDRY_PROJECT_ENDPOINT'
              value: projectEndpoint
            }
            {
              // livewell_common uses ManagedIdentityCredential(client_id) when this and IDENTITY_ENDPOINT are set.
              name: 'AZURE_CLIENT_ID'
              value: identity.properties.clientId
            }
            {
              name: 'LIVEWELL_DEVUI_SEATS'
              value: string(seats)
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        // DevUI keeps conversations and run state in memory: a second replica would split the room.
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    acrPull
    foundryUser
  ]
}

output name string = app.name
output fqdn string = app.properties.configuration.ingress.fqdn
output principalId string = identity.properties.principalId
