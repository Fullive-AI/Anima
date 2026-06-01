# Contributing to Anima

Thank you for your interest in contributing to Anima! We welcome contributions from the community.

## Getting Started

1. Fork the repository
2. Clone your fork and create a branch:

```bash
git clone https://github.com/<your-username>/Anima.git
cd Anima
git checkout -b feat/your-feature
```

3. Install dependencies:

```bash
pnpm install
cp .env.example .env  # fill in ANIMA_LLM_API_KEY
```

4. Run the development server:

```bash
pnpm dev
```

## Development Setup

### Prerequisites

- [Node.js](https://nodejs.org/) >= 18 + [pnpm](https://pnpm.io/) >= 8
- [Python](https://www.python.org/) >= 3.11
- [uv](https://docs.astral.sh/uv/) (install first — `pnpm install` runs `uv sync` automatically)

### Running Tests

```bash
uv run pytest tests/ -v
```

### Code Style

- **Python**: We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting. Pre-commit hooks are configured.
- **TypeScript/React**: ESLint is configured in the `dashboard/` workspace.

Install pre-commit hooks:

```bash
uv run pre-commit install
```

## Ways to Contribute

### Write a Skill

The easiest way to contribute is to write a new Skill:

1. Copy the template: `cp -r skills/custom/_template skills/custom/your-skill`
2. Edit `SKILL.md` with your skill's knowledge
3. Add reference documents in `references/`
4. Optionally add action scripts in `scripts/`

See the [Skill System documentation](./README.md#skill-system) for details.

### Write an Adapter

Add support for a new device protocol:

1. Create a new directory under `adapters/`
2. Implement the `BaseAdapter` interface (3 methods: `discover()`, `subscribe()`, `execute()`)
3. Register it in `core/main.py`

### Report Bugs

- Use [GitHub Issues](https://github.com/fulai-tech/Anima/issues) to report bugs
- Include steps to reproduce, expected behavior, and actual behavior
- Include your environment details (OS, Python version, Node version)

### Suggest Features

- Open a [GitHub Issue](https://github.com/fulai-tech/Anima/issues)
- Describe the use case and expected behavior

## Pull Request Guidelines

1. Keep PRs focused on a single change
2. Write clear commit messages
3. Update documentation if your change affects usage
4. Add tests for new features when practical
5. Ensure all checks pass before requesting review

## Code of Conduct

Please be respectful and constructive in all interactions. We are committed to providing a welcoming and inclusive experience for everyone.

## License

By contributing to Anima, you agree that your contributions will be licensed under the [Apache License 2.0](./LICENSE).
