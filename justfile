# safaribookshelf — task runner (https://github.com/casey/just)

# List available recipes
default:
    @just --list

# Install the virtual environment and the pre-commit hooks
install:
    @echo "🚀 Creating virtual environment using uv"
    @uv sync
    @echo "🚀 Installing pre-commit hooks (pre-commit + commit-msg)"
    @uv run pre-commit install --install-hooks

# Run code quality tools
check:
    @echo "🚀 Checking lock file consistency with 'pyproject.toml'"
    @uv lock --locked
    @echo "🚀 Linting code: Running pre-commit"
    @uv run pre-commit run -a
    @echo "🚀 Static type checking: Running mypy"
    @uv run mypy
    @echo "🚀 Checking for obsolete dependencies: Running deptry"
    @uv run deptry .

# Test the code with pytest
test:
    @echo "🚀 Testing code: Running pytest"
    @uv run python -m pytest --doctest-modules

# Build sdist and wheel
build: clean-build
    @echo "🚀 Building sdist and wheel"
    @uv build

# Remove build artifacts
clean-build:
    @echo "🚀 Removing build artifacts"
    @rm -rf dist
