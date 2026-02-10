# GitHub Actions CI/CD Workflows

This directory contains the CI/CD workflows for Arboric.

## Workflows

### 🧪 [test.yml](.github/workflows/test.yml)
**Triggers:** Push to main/develop, Pull Requests

Comprehensive testing workflow that runs on every push and PR:

- **Multi-Python Testing**: Tests on Python 3.10, 3.11, and 3.12
- **Linting**: Runs `ruff check` to catch code quality issues
- **Formatting**: Checks code formatting with `ruff format`
- **Type Checking**: Runs `mypy` for static type analysis
- **Unit Tests**: Executes pytest with coverage reporting
- **API Tests**: Separate job for API integration tests
- **Package Build**: Verifies the package can be built
- **Coverage Upload**: Uploads coverage to Codecov (Python 3.11 only)

**Jobs:**
1. `test` - Main test matrix (3.10, 3.11, 3.12)
2. `api-test` - API-specific integration tests
3. `build` - Package build verification

### 🎨 [lint.yml](.github/workflows/lint.yml)
**Triggers:** Push to main/develop, All Pull Requests

Fast linting checks:

- **Ruff Linting**: Code quality checks
- **Ruff Formatting**: Code style validation

This workflow runs quickly to provide fast feedback on code quality.

### 📦 [publish.yml](.github/workflows/publish.yml)
**Triggers:** GitHub Release published

Automated PyPI publishing:

- **Build Package**: Creates source and wheel distributions
- **Validate Package**: Checks package metadata with twine
- **Publish to PyPI**: Uses trusted publishing (OIDC)

**Setup Required:**
1. Configure PyPI trusted publishing for your repository
2. Go to https://pypi.org/manage/account/publishing/
3. Add your GitHub repository

## Status Badges

The following badges are displayed in the README:

```markdown
[![Tests](https://github.com/arboric/arboric/actions/workflows/test.yml/badge.svg)](https://github.com/arboric/arboric/actions/workflows/test.yml)
[![Lint](https://github.com/arboric/arboric/actions/workflows/lint.yml/badge.svg)](https://github.com/arboric/arboric/actions/workflows/lint.yml)
```

## Local Development

To run the same checks locally before pushing:

```bash
# Linting
ruff check arboric tests

# Formatting
ruff format arboric tests

# Type checking
mypy arboric

# Tests
pytest tests/ -v

# Tests with coverage
pytest tests/ --cov=arboric --cov-report=term-missing

# API tests specifically
pytest tests/test_api/ -v
```

## Workflow Diagram

```
┌─────────────┐
│   Push/PR   │
└──────┬──────┘
       │
       ├──────────────┐
       │              │
       ▼              ▼
   ┌───────┐    ┌─────────┐
   │ Lint  │    │  Test   │
   │ (Fast)│    │(Matrix) │
   └───────┘    └────┬────┘
                     │
                ┌────┼────┐
                │    │    │
                ▼    ▼    ▼
              3.10 3.11 3.12
                │    │    │
                └────┼────┘
                     │
                     ▼
              ┌──────────┐
              │API Tests │
              └──────────┘
                     │
                     ▼
              ┌──────────┐
              │  Build   │
              └──────────┘

┌──────────┐
│ Release  │
└────┬─────┘
     │
     ▼
┌─────────┐
│ Publish │
│  PyPI   │
└─────────┘
```

## Tips

1. **Fast Feedback**: The lint workflow runs quickly to catch style issues early
2. **Full Coverage**: The test workflow ensures compatibility across Python versions
3. **Auto-Deploy**: Creating a GitHub release automatically publishes to PyPI
4. **Branch Protection**: Consider requiring these workflows to pass before merging PRs

## Troubleshooting

### Tests failing on CI but passing locally?

- Ensure you're using the same Python version
- Check if dependencies are pinned correctly
- Review the workflow logs for environment differences

### Codecov not uploading?

- Ensure the `CODECOV_TOKEN` secret is set (if private repo)
- Check the upload step logs for errors
- Verify coverage.xml is being generated

### PyPI publish failing?

- Ensure trusted publishing is configured on PyPI
- Check that the release tag matches the package version
- Review the build artifacts in the workflow logs
