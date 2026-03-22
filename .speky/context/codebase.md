# Codebase Structure

## Project Type
Python package/library focused on AI-assisted software engineering features (SPEKY) with extensive documentation and testing infrastructure.

## Key Directories
- `speky.egg-info/` - Python package metadata and distribution files
- `docs/` - Product requirements and analysis documentation
- `project_ops/` - Project management and operational documentation
- `image/` - Screenshots and visual documentation assets

## Key Files
- `speky.py` - Main module implementation
- `speky_testing.py` - Test suite for the main module
- `setup.py` - Package installation and distribution configuration
- `requirements.txt` - Python dependencies
- `README.md` - Project overview and setup instructions
- `QUICKSTART.md` - Getting started guide

## Patterns Observed
- **Documentation-heavy**: Extensive markdown files for features, testing, and processes
- **Feature-driven development**: Multiple feature specification files (IMPORT_FEATURE.md, EPIC_FEATURE.md, etc.)
- **Testing-focused**: Multiple testing-related documents and dedicated test files
- **Process documentation**: Workflow files for commits, sequencing, and development processes
- **Standard Python package structure**: Follows Python packaging conventions

## Notes for AI Assistants
- This is an active development project with emphasis on AI-assisted engineering
- Heavy focus on testing and documentation suggests quality-first approach
- Multiple PRD (Product Requirements Document) files indicate feature planning stage
- The `.windsurfrules` file likely contains project-specific AI assistant guidelines
- Environment file (`.env`) present - check for configuration requirements