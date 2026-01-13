# WABotII - WhatsApp Video Downloader Bot

A modern, production-ready WhatsApp video downloader bot built with FastAPI and WAHA (WhatsApp HTTP API). Download videos from YouTube and Facebook directly via WhatsApp with automatic Cloudinary cloud storage integration.

## Features

- 🎥 **Download from Multiple Platforms**: YouTube, Facebook, and more via yt-dlp
- 📱 **WhatsApp Integration**: WAHA-based for reliable, stable connections
- ☁️ **Cloud Storage**: Automatic Cloudinary integration for videos >16MB
- 📊 **Download Tracking**: SQLite database for user and download history
- 📝 **Structured Logging**: JSON-based logging for production monitoring
- 🔒 **Security**: HTTPS-ready, security headers, input validation
- 🐳 **Docker Ready**: Docker and docker-compose for easy deployment
- 🚀 **CI/CD Pipeline**: GitHub Actions with DockerHub and Oracle Cloud deployment
- 💾 **Async Processing**: Async/await throughout for high performance

## Architecture

```
FastAPI Server (Port 8000)
    ↓
WAHA Service (Port 3000 - WhatsApp Protocol Handler)
    ↓
Services Layer:
    - Video: yt-dlp for downloads
    - Cloud: Cloudinary uploads
    - Database: SQLite tracking
    - WAHA: WhatsApp messaging
    ↓
WhatsApp Servers
```

## Quick Start

### Prerequisites

- Docker and docker-compose installed
- `.env` file configured (see `.env.example`)
- WhatsApp Business Account connected to WAHA

### Local Development

1. **Copy environment file**:
   ```bash
   cp .env.example .env
   ```

2. **Start services**:
   ```bash
   docker-compose up -d
   ```

3. **Access WAHA admin panel** (to scan QR code):
   - Navigate to `http://localhost:3000` in your browser
   - Scan the QR code with WhatsApp
   - Done! Session is now authenticated

4. **Test the API**:
   ```bash
   # Health check
   curl http://localhost:8000/health
   
   # API documentation
   open http://localhost:8000/docs
   ```

5. **Send a test message** via WhatsApp:
   - Send a WhatsApp message to your bot with a YouTube URL
   - Bot will download and send back the video

### Using with Family

Once authenticated:
1. Family members can send WhatsApp messages with video URLs
2. Bot automatically downloads and responds with:
   - Direct video (if <16MB)
   - Cloudinary shareable link (always)
3. Videos auto-cleanup after 24 hours

## Configuration

### Environment Variables

```bash
# Application
APP_NAME=WABotII
DEV_MODE=false              # Set to true for Swagger docs + test endpoints
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR
PORT=8000

# WAHA Service
WAHA_BASE_URL=http://waha:3000
VERIFY_TOKEN=your_token     # Webhook verification token

# Database
DATABASE_URL=sqlite:///./wabotii.db

# Cloudinary (for cloud storage)
CLOUDINARY_CLOUD_NAME=your_cloud
CLOUDINARY_API_KEY=your_key
CLOUDINARY_API_SECRET=your_secret

# Storage Settings
FILE_RETENTION_HOURS=24     # Delete local files after 24 hours
CLOUDINARY_RETENTION_HOURS=24
MAX_FILE_SIZE_MB=16         # Send directly if smaller
```

See `.env.example` for all available options.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/health` | GET | Detailed health status + WAHA status |
| `/stats` | GET | Download statistics |
| `/webhook` | GET | WhatsApp webhook verification |
| `/webhook` | POST | Receive WhatsApp messages |
| `/privacy` | GET | Privacy policy page |
| `/terms` | GET | Terms and conditions page |
| `/test-download` | POST | Test download (DEV_MODE only) |

### Example: Test Download

```bash
curl -X POST http://localhost:8000/test-download \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

## Development

### Setup Development Environment

1. **Install uv** (modern Python dependency manager):
   ```bash
   pip install uv
   ```

2. **Sync dependencies**:
   ```bash
   uv sync
   ```

3. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

4. **Run locally** (without Docker):
   ```bash
   DEV_MODE=true python main.py
   ```

### Project Structure

```
WABotII/
├── src/wabotii/
│   ├── config/          # Settings and configuration
│   ├── services/        # Business logic (WAHA, Video, Cloud, DB)
│   ├── api/             # FastAPI routes and schemas
│   ├── utils/           # Utilities (logging, helpers)
│   └── __main__.py      # FastAPI app initialization
├── tests/               # Test suite (pytest)
├── downloads/           # Local video cache
├── legal/               # Terms and privacy pages
├── main.py             # Entry point
├── pyproject.toml      # Dependencies and config
├── Dockerfile          # Container image
├── docker-compose.yml  # Multi-container orchestration
├── .env.example        # Environment template
├── .pre-commit-config.yaml  # Pre-commit hooks
└── .github/workflows/deploy.yaml  # CI/CD pipeline
```

### Key Services

#### WAHA Service (`services/waha.py`)
Wrapper around WAHA HTTP API for sending/receiving WhatsApp messages.

#### Video Service (`services/video.py`)
Downloads videos using yt-dlp with support for:
- YouTube (with cookie authentication)
- Facebook (with checkpoint detection)
- Format selection and quality optimization

#### Cloud Service (`services/cloud.py`)
Uploads videos to Cloudinary and manages cleanup.

#### Database Service (`services/database.py`)
Tracks users and downloads for analytics:
- User: phone_number, created_at
- Download: url, title, size, status, created_at

## Deployment

### Deploy to Oracle Cloud

1. **Set GitHub Secrets**:
   ```
   DOCKERHUB_USERNAME      # Docker Hub username
   DOCKERHUB_TOKEN         # Docker Hub access token
   DOCKERHUB_REPO          # Repository name (e.g., "wabotii")
   ORACLE_VM_IP            # Oracle VM public IP
   ORACLE_VM_USERNAME      # SSH username
   ORACLE_VM_SSH_KEY       # SSH private key
   ENV_FILE                # Production .env contents
   ```

2. **Push to main branch**:
   ```bash
   git add .
   git commit -m "Deploy to production"
   git push origin main
   ```

3. **GitHub Actions will**:
   - Run linting and tests
   - Build Docker image
   - Push to DockerHub
   - SSH into Oracle VM
   - Pull latest image and restart services

### Docker Production

```bash
# On Oracle VM
docker login -u $DOCKERHUB_USERNAME -p $DOCKERHUB_TOKEN
docker pull $DOCKERHUB_USERNAME/$DOCKERHUB_REPO:latest
echo "$ENV_FILE" > .env
docker-compose up -d
```

## WAHA Session Management

WAHA requires a WhatsApp session to be authenticated:

1. **Initial Setup** (first deployment):
   - Access WAHA admin: `http://your-server:3000`
   - Scan QR code with WhatsApp
   - Session is saved and persists across restarts

2. **Session Persistence**:
   - Session data stored in `waha-data/` volume
   - Survives container restarts

3. **Re-authenticate**:
   ```bash
   docker-compose down
   docker-compose up -d waha
   # Access http://localhost:3000 and rescan QR code
   docker-compose up -d
   ```

## Security Considerations

### Unofficial WhatsApp API
WAHA uses reverse-engineered WhatsApp Web protocol:
- ✅ **Advantages**: Full feature set, fast, no official API costs
- ⚠️ **Risks**: Account bans possible (rare, but possible), protocol changes
- **Recommendation**: For production, consider Meta Cloud API as backup

### Data Privacy
- **No storage** of message contents (only URL logged)
- **No tracking** of user conversations
- **Auto-delete** of downloaded files after 24 hours
- See [Privacy Policy](legal/privacy.html)

## Troubleshooting

### WAHA not connecting
```bash
# Check WAHA logs
docker-compose logs waha

# Restart WAHA
docker-compose restart waha
```

### Downloads failing
- Check Facebook checkpoint: bot warns if security checkpoint detected
- Check yt-dlp logs: `DEV_MODE=true` for verbose output
- Ensure cookies are set if authentication required

### Cloudinary errors
- Verify `CLOUDINARY_API_KEY` and `CLOUDINARY_API_SECRET`
- Check Cloudinary account has API enabled

### Health check failing
```bash
curl http://localhost:8000/health
# Should return: {"status": "healthy", "version": "0.1.0", "waha_healthy": true}
```

## Testing

```bash
# Run tests
pytest tests/

# With coverage
pytest --cov=src tests/

# Watch mode
pytest-watch
```

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## License

MIT License - See LICENSE file for details

## Support

For issues and questions:
- 📧 Email: donfolayan@yahoo.com
- 🐛 GitHub Issues: [WABotII Issues](https://github.com/donfolayan/WABotII/issues)

## Acknowledgments

- [WAHA](https://github.com/devlikeapro/waha) - WhatsApp HTTP API
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Video downloader
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Cloudinary](https://cloudinary.com/) - Cloud storage
