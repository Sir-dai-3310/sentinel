# Contributing to Sentinel

Thank you for your interest in contributing to Sentinel! 🎉

## Getting Started

1. **Fork** the repository
2. **Clone** your fork
3. **Create a branch** for your feature/fix
4. **Make your changes**
5. **Write tests** (aim for 90%+ coverage)
6. **Run tests** locally
7. **Submit a Pull Request**

## Development Setup

### Prerequisites

- Rust 1.70+ (`curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`)
- Python 3.11+ (`pyenv install 3.11`)
- Node.js 20+ (`nvm install 20`)
- Docker (`https://docs.docker.com/get-docker/`)

### Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/sentinel.git
cd sentinel

# Install Rust core
cd sentinel-core && cargo build

# Install Python agents
cd ../sentinel-agents && pip install -e .[dev]

# Install API
cd ../sentinel-api && pip install -e .[dev]

# Install Web UI
cd ../sentinel-web && npm install
```

## Code Style

### Rust

```bash
cargo fmt
cargo clippy
```

### Python

```bash
black .
ruff check .
mypy .
```

### TypeScript

```bash
npm run lint
npm run type-check
```

## Testing

```bash
# Rust
cargo test

# Python
pytest

# API
pytest

# Web
npm test
```

## Pull Request Process

1. **Update documentation** if you changed APIs
2. **Add tests** for new features
3. **Ensure all tests pass** (`cargo test && pytest && npm test`)
4. **Update CHANGELOG.md** with your changes
5. **Request review** from maintainers

## Code Review

We aim to review PRs within 48 hours. Please be patient.

## Community

- **Discord**: https://discord.gg/sentinel
- **Discussions**: https://github.com/yourusername/sentinel/discussions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
