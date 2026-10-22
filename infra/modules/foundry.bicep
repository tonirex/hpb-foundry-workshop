// Microsoft Foundry resource (AIServices account) + project + model deployments + project connections.
param location string
param tags object
param accountName string
param projectName string

@description('Model deployments: Global Standard only, capacity = TPM cap in thousands. No PTU.')
param deployments deploymentType[]

param appInsightsId string
@secure()
param appInsightsConnectionString string
param searchId string
param searchEndpoint string
param storageId string
param storageBlobEndpoint string
param acrId string
param acrLoginServer string

param searchConnectionName string
param storageConnectionName string
param acrConnectionName string
param appInsightsConnectionName string

@description('Link the blocklist to the guardrail policy. False on the first provision of an environment (see main.bicep).')
param linkBlocklist bool = true

type deploymentType = {
  name: string
  model: {
    format: string
    name: string
    version: string
  }
  sku: {
    name: 'GlobalStandard'
    @minValue(1)
    @maxValue(1000)
    capacity: int
  }
}

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      virtualNetworkRules: []
      ipRules: []
    }
    disableLocalAuth: true
  }
}

@batchSize(1)
resource modelDeployments 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = [
  for d in deployments: {
    parent: account
    name: d.name
    sku: d.sku
    properties: {
      model: d.model
      versionUpgradeOption: 'NoAutoUpgrade'
      raiPolicyName: contains(guardrail.attach_to, d.name) ? raiPolicy.name : guardrail.deployment_policy
    }
  }
]

// Lab 2 guardrail: medication-dosage blocklist + RAI policy `livewell-guardrails`, defined once in
// content/config/guardrails.yaml. Deployments keep `deployment_policy` (Microsoft.DefaultV2); agents attach
// livewell-guardrails through rai_config (ASSUMPTIONS.md 6.1).
var guardrail = loadYamlContent('../../content/config/guardrails.yaml')

resource blocklist 'Microsoft.CognitiveServices/accounts/raiBlocklists@2025-06-01' = {
  parent: account
  name: guardrail.blocklist.name
  properties: {
    description: guardrail.blocklist.description
  }
}

// Blocklist items are NOT declared here: the RP returns 400 on GET of a single raiBlocklistItems
// resource, which breaks what-if. The azd postprovision hook (scripts/apply-guardrail.py) syncs them.

resource raiPolicy 'Microsoft.CognitiveServices/accounts/raiPolicies@2025-06-01' = {
  parent: account
  name: guardrail.policy_name
  properties: {
    basePolicyName: guardrail.base_policy
    mode: guardrail.mode
    contentFilters: guardrail.content_filters
    customBlocklists: linkBlocklist ? [
      {
        blocklistName: blocklist.name
        blocking: true
        source: guardrail.blocklist.source
      }
    ] : []
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: projectName
    description: 'LiveWell Coach workshop project (shared by all attendees).'
  }
  dependsOn: [
    modelDeployments
  ]
}

resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: appInsightsConnectionName
  properties: {
    category: 'AppInsights'
    target: appInsightsId
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: appInsightsConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsightsId
    }
  }
}

resource searchConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: searchConnectionName
  properties: {
    category: 'CognitiveSearch'
    target: searchEndpoint
    authType: 'AAD'
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: searchId
      type: 'azure_ai_search'
    }
  }
}

resource storageConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: storageConnectionName
  properties: {
    category: 'AzureStorageAccount'
    target: storageBlobEndpoint
    authType: 'AAD'
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: storageId
    }
  }
}

resource acrConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: acrConnectionName
  properties: {
    category: 'ContainerRegistry'
    target: acrLoginServer
    authType: 'ManagedIdentity'
    isSharedToAll: true
    credentials: {
      clientId: project.identity.principalId
      resourceId: acrId
    }
    metadata: {
      ResourceId: acrId
    }
  }
}

output accountId string = account.id
output accountName string = account.name
output accountPrincipalId string = account.identity.principalId
output accountEndpoint string = account.properties.endpoint
output openAiEndpoint string = account.properties.endpoints['OpenAI Language Model Instance API']
output projectId string = project.id
output projectName string = project.name
output projectPrincipalId string = project.identity.principalId
output projectEndpoint string = project.properties.endpoints['AI Foundry API']
output searchConnectionId string = searchConnection.id
output appInsightsConnectionId string = appInsightsConnection.id
output raiPolicyName string = raiPolicy.name
output raiPolicyId string = raiPolicy.id
