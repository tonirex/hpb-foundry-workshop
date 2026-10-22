// LiveWell Coach workshop — one resource group, one region, every resource (SPEC.md §8).
// Names come from content/config/workshop.yaml (`names:` / `models:`), with <env> = environmentName.
// Per-environment values live in infra/env/<env>.bicepparam (copied to infra/main.bicepparam by the
// azd preprovision hook, scripts/select-params.py).
targetScope = 'resourceGroup'

@description('azd environment name: mcaps (dry run) or sponsor (delivery).')
@allowed([
  'mcaps'
  'sponsor'
])
param environmentName string

@description('Single region for EVERY resource, Fabric capacity included. Validated: swedencentral (default), northcentralus (fallback). Never Southeast Asia.')
@allowed([
  'swedencentral'
  'northcentralus'
])
param location string = 'swedencentral'

@description('Object ID of the identity running azd (facilitator). Set by scripts/provision.sh / the preprovision hook.')
param principalId string = ''

@allowed([
  'User'
  'ServicePrincipal'
])
param principalType string = 'User'

@description('Object IDs of additional facilitators (Foundry Project Manager + data-plane contributor roles).')
param facilitatorPrincipalIds array = []

@description('Fabric capacity admins: UPNs of MEMBER accounts in this tenant.')
param fabricAdminMembers array

@description('FABRIC_BRIDGE. false = no Fabric capacity; the profile tool reads citizens.json and the Fabric step is skipped.')
param fabricBridge bool = true

@description('Link the medication blocklist to livewell-guardrails. False on the first provision of an environment: ARM preflight rejects a policy whose blocklist does not exist yet, and the postprovision hook (scripts/apply-guardrail.py) adds the link.')
param guardrailLinkBlocklist bool = true

@allowed([
  'F2'
  'F4'
])
param fabricSku string = 'F2'

@description('MODE. shared-project (default): attendees own livewell-<INITIALS>-<role> agents in one project.')
@allowed([
  'shared-project'
  'project-per-attendee'
])
param projectMode string = 'shared-project'

@description('Search tier. basic (default) or serverless (Serverless Developer, preview). Never S1+.')
@allowed([
  'basic'
  'serverless'
  'free'
])
param searchSku string = 'basic'

@description('Region for the search service ONLY when the main region is capacity-blocked for new search services (empty = location). Exception to the one-region rule, recorded in ASSUMPTIONS.md.')
param searchLocation string = ''
@description('TPM cap (thousands) for the default deployment (gpt-5-mini: Labs 0-2, Lab 3 specialists, memory store, KB planner). Global Standard only (pay per token, so the cap has no fixed cost). 400K keeps 6 participants plus a facilitator demo out of throttling.')
@minValue(10)
@maxValue(1000)
param chatTpmCapThousands int = 400

@description('TPM cap (thousands) for the tools deployment (gpt-4.1-mini: Lab 3 coach on, Lab 2 judges). gpt-5-mini does not support OpenAPI, A2A, Fabric or function tools.')
@minValue(10)
@maxValue(1000)
param toolsTpmCapThousands int = 200

@description('TPM cap (thousands) for the embeddings deployment.')
@minValue(10)
@maxValue(150)
param embeddingTpmCapThousands int = 100

param defaultModelVersion string = '2025-08-07'
param toolsModelVersion string = '2025-04-14'
param embeddingModelVersion string = '1'

@description('MCP server min replicas. 0 between sessions; 1 on the workshop day.')
@minValue(0)
@maxValue(2)
param mcpMinReplicas int = 0

@description('Last deployed MCP server image (azd writes SERVICE_MCP_ACTIVITIES_IMAGE_NAME after `azd deploy`). Empty = placeholder.')
param mcpImage string = ''

@description('LAB4_DEVUI. true = host the Lab 4 DevUI (demos/lab4-devui.py) on the Container Apps environment so participants explore both workflows in a browser, no local Python (`azd deploy lab4-devui`). false = no DevUI app.')
param lab4DevUi bool = true

@secure()
@description('Bearer token for the hosted DevUI (LIVEWELL_DEVUI_TOKEN, generated once by scripts/select-params.py, printed on the values sheet). Empty = no DevUI app.')
param devuiToken string = ''

@description('Last deployed DevUI image (SERVICE_LAB4_DEVUI_IMAGE_NAME). Empty = placeholder.')
param devuiImage string = ''

@description('DevUI min replicas. 0 between sessions; 1 on the workshop day (DEVUI_MIN_REPLICAS=1). Max is always 1.')
@minValue(0)
@maxValue(1)
param devuiMinReplicas int = 0

@description('Runs of one Lab 4 workflow in flight at once in the hosted DevUI; each run builds a fresh workflow (DEVUI_SEATS).')
@minValue(1)
@maxValue(12)
param devuiSeats int = 8

param budgetAmountUsd int = 300
param budgetAlertThresholdsUsd array = [
  150
  300
]
param budgetContactEmails array = []

@description('Budget start (yyyy-MM-01). Empty = first of the current month. scripts/select-params.py pins it in the azd env (BUDGET_START_DATE) on first provision because an existing budget cannot move its start date.')
param budgetStartDate string = ''

@description('Do not set: first of the current month, used when budgetStartDate is empty.')
param currentMonthStart string = utcNow('yyyy-MM-01')

@description('Extra tags (e.g. cost centre). workshop / env / azd-env-name are always applied.')
param extraTags object = {}

@description('Tag that opts the knowledge storage account out of a tenant policy forcing publicNetworkAccess=Disabled (MCAPS: {SecurityControl: \'Ignore\'}). See ASSUMPTIONS.md 4.4.')
param storagePolicyOptOutTag object = {}

@description('Knowledge storage firewall default action. Allow: Entra-only public access, so Lab 2 can publish evaluation runs from laptops (decided 2026-09-30). Deny: Search + trusted services only (ASSUMPTIONS.md 4.15).')
@allowed([
  'Allow'
  'Deny'
])
param storageNetworkDefaultAction string = 'Allow'

// -------------------------------------------------------------------------------------------------

var names = loadYamlContent('../content/config/workshop.yaml', '$.names')
var models = loadYamlContent('../content/config/workshop.yaml', '$.models')
var n = {
  foundryAccount: replace(names.foundry_account, '<env>', environmentName)
  foundryProject: names.foundry_project
  search: replace(names.search_service, '<env>', environmentName)
  fabricCapacity: replace(names.fabric_capacity, '<env>', environmentName)
  mcpApp: replace(names.mcp_app, '<env>', environmentName)
  devuiApp: replace(names.devui_app, '<env>', environmentName)
  budget: replace(names.budget, '<env>', environmentName)
  knowledgeContainer: names.knowledge_container
  searchConnection: names.search_connection
  storageConnection: names.storage_connection
  acrConnection: names.acr_connection
  appInsightsConnection: names.appinsights_connection
}
var token = take(uniqueString(subscription().id, resourceGroup().id, environmentName), 6)
var tags = union(extraTags, {
  workshop: 'livewell'
  env: environmentName
  'azd-env-name': environmentName
})

var facilitators = filter(union(empty(principalId) ? [] : [principalId], facilitatorPrincipalIds), p => !empty(p))
var deployDevUi = lab4DevUi && !empty(devuiToken)

var deployments = [
  {
    name: models.default
    model: {
      format: 'OpenAI'
      name: models.default
      version: defaultModelVersion
    }
    sku: {
      name: models.deployment_type
      capacity: chatTpmCapThousands
    }
  }
  {
    name: models.tools
    model: {
      format: 'OpenAI'
      name: models.tools
      version: toolsModelVersion
    }
    sku: {
      name: models.deployment_type
      capacity: toolsTpmCapThousands
    }
  }
  {
    name: models.embeddings
    model: {
      format: 'OpenAI'
      name: models.embeddings
      version: embeddingModelVersion
    }
    sku: {
      name: models.deployment_type
      capacity: embeddingTpmCapThousands
    }
  }
]

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    location: location
    tags: tags
    logAnalyticsName: 'log-livewell-${environmentName}'
    appInsightsName: 'appi-livewell-${environmentName}'
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    tags: tags
    name: 'stlivewell${environmentName}${token}'
    containerName: n.knowledgeContainer
    searchServiceId: search.outputs.id
    policyOptOutTag: storagePolicyOptOutTag
    networkDefaultAction: storageNetworkDefaultAction
  }
}

module search 'modules/search.bicep' = {
  name: 'search'
  params: {
    location: empty(searchLocation) ? location : searchLocation
    tags: tags
    name: n.search
    sku: searchSku
  }
}

module containers 'modules/containerapps.bicep' = {
  name: 'containers'
  params: {
    location: location
    tags: tags
    acrName: 'crlivewell${environmentName}${token}'
    identityName: 'id-livewell-${environmentName}'
    environmentName: 'cae-livewell-${environmentName}'
    mcpAppName: n.mcpApp
    logAnalyticsId: monitoring.outputs.logAnalyticsId
    mcpMinReplicas: mcpMinReplicas
    mcpImage: mcpImage
  }
}

module foundry 'modules/foundry.bicep' = {
  name: 'foundry'
  params: {
    location: location
    tags: tags
    accountName: n.foundryAccount
    projectName: n.foundryProject
    deployments: deployments
    appInsightsId: monitoring.outputs.appInsightsId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    searchId: search.outputs.id
    searchEndpoint: search.outputs.endpoint
    storageId: storage.outputs.id
    storageBlobEndpoint: storage.outputs.blobEndpoint
    acrId: containers.outputs.acrId
    acrLoginServer: containers.outputs.acrLoginServer
    searchConnectionName: n.searchConnection
    storageConnectionName: n.storageConnection
    acrConnectionName: n.acrConnection
    appInsightsConnectionName: n.appInsightsConnection
    linkBlocklist: guardrailLinkBlocklist
  }
}

module rbac 'modules/rbac.bicep' = {
  name: 'rbac'
  params: {
    accountName: foundry.outputs.accountName
    projectName: foundry.outputs.projectName
    searchName: search.outputs.name
    storageName: storage.outputs.name
    acrName: containers.outputs.acrName
    facilitatorPrincipalIds: facilitators
    facilitatorPrincipalType: principalType
    projectPrincipalId: foundry.outputs.projectPrincipalId
    searchPrincipalId: search.outputs.principalId
  }
}

// After foundry: the DevUI needs the project endpoint and Foundry User on the project (containers comes first
// because foundry takes the ACR from it).
module devui 'modules/devui.bicep' = if (deployDevUi) {
  name: 'devui'
  params: {
    location: location
    tags: tags
    name: n.devuiApp
    identityName: 'id-livewell-devui-${environmentName}'
    environmentId: containers.outputs.environmentId
    acrName: containers.outputs.acrName
    accountName: foundry.outputs.accountName
    projectName: foundry.outputs.projectName
    projectEndpoint: foundry.outputs.projectEndpoint
    authToken: devuiToken
    image: devuiImage
    minReplicas: devuiMinReplicas
    seats: devuiSeats
  }
}

module fabric 'modules/fabric.bicep' = if (fabricBridge) {
  name: 'fabric'
  params: {
    location: location
    tags: tags
    name: n.fabricCapacity
    adminMembers: fabricAdminMembers
    skuName: fabricSku
  }
}

module budget 'modules/budget.bicep' = {
  name: 'budget'
  params: {
    name: n.budget
    amount: budgetAmountUsd
    alertThresholdsUsd: budgetAlertThresholdsUsd
    contactEmails: budgetContactEmails
    startDate: empty(budgetStartDate) ? currentMonthStart : budgetStartDate
  }
}

// --- Outputs → .azure/<env>/.env (single source of truth, SPEC.md §8.1) ----------------------------
output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = resourceGroup().name
// MODE and FABRIC_BRIDGE are inputs (azd env set). They are deliberately NOT outputs: azd down deletes
// output keys from .azure/<env>/.env, which would silently reset an override on the next provision.
output LIVEWELL_PROJECT_MODE string = projectMode
output LIVEWELL_FABRIC_BRIDGE string = fabricBridge ? 'true' : 'false'

output AZURE_AI_ACCOUNT_NAME string = foundry.outputs.accountName
output AZURE_AI_PROJECT_NAME string = foundry.outputs.projectName
output AZURE_AI_PROJECT_ID string = foundry.outputs.projectId
output AZURE_AI_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
output FOUNDRY_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
output AZURE_OPENAI_ENDPOINT string = foundry.outputs.openAiEndpoint
output AZURE_AI_MODEL_DEPLOYMENT_NAME string = models.default
output AZURE_AI_TOOLS_DEPLOYMENT_NAME string = models.tools
output AZURE_AI_EMBEDDING_DEPLOYMENT_NAME string = models.embeddings

output AZURE_SEARCH_SERVICE_NAME string = search.outputs.name
output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_SEARCH_LOCATION string = empty(searchLocation) ? location : searchLocation
output AZURE_SEARCH_CONNECTION_NAME string = n.searchConnection
output AZURE_SEARCH_CONNECTION_ID string = foundry.outputs.searchConnectionId
output LIVEWELL_RAI_POLICY_NAME string = foundry.outputs.raiPolicyName
output LIVEWELL_RAI_POLICY_ID string = foundry.outputs.raiPolicyId
output AZURE_STORAGE_ACCOUNT_NAME string = storage.outputs.name
output AZURE_STORAGE_BLOB_ENDPOINT string = storage.outputs.blobEndpoint
output KNOWLEDGE_CONTAINER string = n.knowledgeContainer

output APPLICATIONINSIGHTS_NAME string = monitoring.outputs.appInsightsName
output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.appInsightsConnectionString

output AZURE_CONTAINER_REGISTRY_NAME string = containers.outputs.acrName
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containers.outputs.acrLoginServer
output AZURE_CONTAINER_APPS_ENVIRONMENT_NAME string = containers.outputs.environmentName
output AZURE_CONTAINER_APPS_ENVIRONMENT_ID string = containers.outputs.environmentId
output AZURE_USER_ASSIGNED_IDENTITY_CLIENT_ID string = containers.outputs.identityClientId
output MCP_APP_NAME string = containers.outputs.mcpAppName
output MCP_URL string = 'https://${containers.outputs.mcpAppFqdn}/mcp'
output LAB4_DEVUI_APP_NAME string = deployDevUi ? devui!.outputs.name : ''
output LAB4_DEVUI_URL string = deployDevUi ? 'https://${devui!.outputs.fqdn}' : ''

output FABRIC_CAPACITY_NAME string = fabricBridge ? fabric!.outputs.name : ''
output FABRIC_CAPACITY_ID string = fabricBridge ? fabric!.outputs.id : ''
output BUDGET_NAME string = budget.outputs.name
