# Contributing to Hampstead Renovations Voice AI Agent

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Workflow](#development-workflow)
4. [Coding Standards](#coding-standards)
5. [Testing Guidelines](#testing-guidelines)
6. [Pull Request Process](#pull-request-process)
7. [Security](#security)

---

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Collaborate openly and transparently
- Prioritize security and privacy

---

## Getting Started

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Git

### Local Setup

```bash
# Clone the repository
git clone https://github.com/rockmrack/hampstead-renovations-voice-ai-agent.git
cd hampstead-renovations-voice-ai-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r api/requirements.txt
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Copy environment template
cp .env.example .env
# Edit .env with your API keys

# Start services
docker compose up -d postgres redis

# Run the API
cd api && uvicorn app:app --reload
```

---

## Development Workflow

### Branch Naming

```
feature/   - New features (feature/add-voice-analytics)
fix/       - Bug fixes (fix/whatsapp-timeout)
refactor/  - Code refactoring (refactor/services-structure)
docs/      - Documentation (docs/api-reference)
test/      - Testing improvements (test/integration-coverage)
chore/     - Maintenance (chore/update-dependencies)
```

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Code style (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Tests
- `chore`: Maintenance

Examples:
```bash
feat(voice): add real-time transcription streaming
fix(whatsapp): handle message retry on timeout
docs(api): add calendar endpoint documentation
test(services): add claude service unit tests
```

---

## Coding Standards

### Python Style Guide

We use the following tools (configured in `pyproject.toml`):

- **Ruff**: Linting
- **Black**: Formatting
- **isort**: Import sorting
- **mypy**: Type checking

```bash
# Run all linting
ruff check api/
black --check api/
isort --check-only api/
mypy api/

# Auto-fix issues
ruff check api/ --fix
black api/
isort api/
```

### Code Guidelines

1. **Type Hints**: Required for all functions

```python
async def process_message(
    message: str,
    user_id: str,
    context: dict[str, Any] | None = None,
) -> ConversationResponse:
    ...
```

2. **Docstrings**: Use Google style

```python
async def book_appointment(
    customer: Customer,
    slot: TimeSlot,
) -> Booking:
    """Book an appointment for a customer.

    Args:
        customer: The customer booking the appointment.
        slot: The desired time slot.

    Returns:
        The created booking with confirmation details.

    Raises:
        SlotUnavailableError: If the slot is no longer available.
        ValidationError: If customer data is invalid.
    """
    ...
```

3. **Error Handling**: Use custom exceptions

```python
# Good
raise ServiceUnavailableError(
    service="claude",
    message="API timeout after 30s",
    retry_after=60
)

# Avoid
raise Exception("Something went wrong")
```

4. **Logging**: Use structured logging

```python
import structlog

logger = structlog.get_logger()

# Good
logger.info(
    "message_processed",
    message_id=msg.id,
    channel="whatsapp",
    duration_ms=elapsed
)

# Avoid
print(f"Processed message {msg.id}")
```

---

## Testing Guidelines

### Test Structure

```
tests/
├── conftest.py          # Shared fixtures
├── test_services.py     # Service unit tests
├── test_routes.py       # API route tests
├── test_utils.py        # Utility function tests
├── test_middleware.py   # Middleware tests
└── test_integration.py  # End-to-end tests
```

### Writing Tests

1. **Unit Tests**: Test individual functions

```python
@pytest.mark.asyncio
async def test_format_phone_number():
    assert format_phone_number("07777123456") == "+447777123456"
    assert format_phone_number("+447777123456") == "+447777123456"
```

2. **Service Tests**: Mock external dependencies

```python
@pytest.mark.asyncio
async def test_claude_service_generate(mock_anthropic_client):
    service = ClaudeService()
    
    mock_anthropic_client.messages.create.return_value = MockResponse(
        content=[{"text": "Hello!"}]
    )
    
    result = await service.generate("Hi there")
    
    assert result == "Hello!"
    mock_anthropic_client.messages.create.assert_called_once()
```

3. **Integration Tests**: Test full flows

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_whatsapp_message_flow(test_client, mock_services):
    response = await test_client.post(
        "/whatsapp/webhook",
        json=SAMPLE_WHATSAPP_MESSAGE,
        headers={"X-Hub-Signature-256": valid_signature}
    )
    
    assert response.status_code == 200
    assert mock_services["claude"].generate.called
    assert mock_services["whatsapp"].send_message.called
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=api --cov-report=html

# Run specific test file
pytest tests/test_services.py

# Run tests matching pattern
pytest -k "test_claude"

# Run only fast tests
pytest -m "not slow"

# Run in parallel
pytest -n auto
```

---

## Pull Request Process

### Before Submitting

1. **Update from main**:
   ```bash
   git checkout main
   git pull
   git checkout your-branch
   git rebase main
   ```

2. **Run all checks**:
   ```bash
   # Linting
   ruff check api/
   black --check api/
   
   # Tests
   pytest
   
   # Type checking
   mypy api/
   ```

3. **Update documentation** if needed

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No new warnings
```

### Review Process

1. Create PR against `develop` branch
2. Automated checks must pass (CI/CD)
3. At least one approval required
4. Squash and merge preferred

---

## Security

### Reporting Vulnerabilities

**DO NOT** open public issues for security vulnerabilities.

Email: security@hampsteadrenovations.com

Include:
- Description of vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Security Practices

1. Never commit secrets or API keys
2. Use environment variables for configuration
3. Validate all user inputs
4. Follow OWASP guidelines
5. Run Snyk scans before committing

```bash
# Run security scan
snyk code test api/
snyk test --file=api/requirements.txt
```

---

## Questions?

- Open a discussion on GitHub
- Contact: dev@hampsteadrenovations.com

Thank you for contributing! 🚀
