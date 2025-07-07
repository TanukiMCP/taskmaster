# Smithery Deployment Guide

## 🚀 Taskmaster MCP Server - Smithery Deployment

This guide covers deploying the Taskmaster MCP Server to Smithery.ai for production use.

### Prerequisites

- GitHub repository with the Taskmaster MCP Server code
- Smithery.ai account
- Docker container registry access (GitHub Container Registry is configured)

### Deployment Configuration

#### 1. Smithery Configuration (`smithery.yaml`)

The project includes a pre-configured `smithery.yaml` file optimized for Smithery deployment:

```yaml
runtime: "container"
build:
  dockerfile: "Dockerfile"
  dockerBuildPath: "."
startCommand:
  type: "http"
  configSchema:
    type: "object"
    properties:
      apiKey:
        type: "string"
        title: "API Key"
        description: "Optional API key for enhanced authentication and rate limiting"
      debug:
        type: "boolean"
        title: "Debug Mode"
        description: "Enable debug logging for troubleshooting"
        default: false
      sessionTimeout:
        type: "integer"
        title: "Session Timeout"
        description: "Session timeout in minutes"
        default: 30
        minimum: 5
        maximum: 120
    required: []
  exampleConfig:
    apiKey: "optional-api-key-123"
    debug: false
    sessionTimeout: 30
```

#### 2. Container Configuration (`Dockerfile`)

The Dockerfile is optimized for Smithery deployment with:
- Python 3.11 slim base image
- Streamable HTTP transport support
- Production-ready environment variables
- Health check endpoints

#### 3. Server Configuration

The server includes Smithery-specific features:
- **Streamable HTTP Transport**: Native support for Smithery's communication protocol
- **Configuration Endpoints**: `/config` endpoint for Smithery integration
- **Health Monitoring**: `/health` endpoint for deployment monitoring
- **CORS Configuration**: Properly configured for Smithery's requirements

### Deployment Steps

#### Step 1: Repository Setup

1. Ensure your code is in a GitHub repository
2. Verify all files are committed:
   - `smithery.yaml`
   - `Dockerfile`
   - `server.py`
   - `requirements.txt`

#### Step 2: GitHub Actions (Automated)

The repository includes a GitHub Actions workflow (`.github/workflows/deploy-smithery.yml`) that:
- ✅ Tests the server startup
- ✅ Builds and pushes Docker images to GitHub Container Registry
- ✅ Validates Smithery configuration
- ✅ Provides deployment readiness summary

#### Step 3: Smithery Deployment

1. **Connect Repository to Smithery**:
   - Log into Smithery.ai
   - Navigate to "Deploy" section
   - Connect your GitHub repository
   - Select the repository containing the Taskmaster MCP Server

2. **Configure Deployment**:
   - Smithery will automatically detect the `smithery.yaml` configuration
   - Review the configuration schema
   - Set any required environment variables

3. **Deploy**:
   - Click "Deploy" in the Smithery UI
   - Monitor the deployment progress
   - Verify the deployment is successful

### Server Endpoints

Once deployed, your server will expose:

- **MCP Endpoint**: `/mcp` - Main MCP protocol endpoint
- **Health Check**: `/health` - Server health and status
- **Configuration**: `/config` - Server capabilities and schema
- **Documentation**: `/docs` - API documentation
- **Root**: `/` - Server information

### Configuration Options

The server supports the following configuration parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `apiKey` | string | - | Optional API key for enhanced authentication |
| `debug` | boolean | false | Enable debug logging |
| `sessionTimeout` | integer | 30 | Session timeout in minutes (5-120) |

### Environment Variables

The server recognizes these environment variables:

- `PORT`: Server port (default: 8080)
- `SMITHERY_DEPLOY`: Set to "true" for Smithery deployment mode

### Verification

After deployment, verify your server is working:

1. **Health Check**: Visit `https://your-deployment-url/health`
2. **Configuration**: Visit `https://your-deployment-url/config`
3. **MCP Protocol**: Test the `/mcp` endpoint with MCP clients

### Troubleshooting

#### Common Issues

1. **Build Failures**:
   - Check GitHub Actions logs
   - Verify all dependencies in `requirements.txt`
   - Ensure Dockerfile syntax is correct

2. **Deployment Failures**:
   - Verify `smithery.yaml` configuration
   - Check Smithery deployment logs
   - Ensure container registry is accessible

3. **Runtime Issues**:
   - Check server health endpoint
   - Review application logs in Smithery dashboard
   - Verify environment variables

#### Support

- **GitHub Issues**: Report issues in the repository
- **Smithery Support**: Contact Smithery.ai support for deployment issues
- **Documentation**: Refer to Smithery.ai documentation for platform-specific help

### Production Considerations

- **Monitoring**: Use the `/health` endpoint for monitoring
- **Scaling**: Smithery handles automatic scaling
- **Updates**: Push code changes to trigger automatic redeployment
- **Configuration**: Update configuration through Smithery UI

---

**Deployment Date**: July 7, 2025  
**Server Version**: Taskmaster MCP v3.0  
**Smithery Compatible**: ✅ Yes  
**Transport Protocol**: Streamable HTTP 