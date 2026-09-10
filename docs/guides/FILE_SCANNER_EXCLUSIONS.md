# File Scanner Exclusions

Patterns to exclude from RIM analysis — build artifacts, dependencies, and generated files that don't represent source code.

---

## Python Projects

### Package Management
```
venv/
env/
.venv/
ENV/
.env.local
.env.*.local
*.egg-info/
dist/
build/
*.whl
*.egg
.eggs/
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
pip-log.txt
pip-delete-this-directory.txt
```

### Testing & Coverage
```
.pytest_cache/
.coverage
htmlcov/
.tox/
.hypothesis/
*.cover
.mypy_cache/
.dmypy.json
dmypy.json
.pyre/
.pytype/
```

### IDE & Editors
```
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store
.sublime-*
.vim/
.netrwhist
tags
.tags
```

### Virtual Environments & Compiled
```
site-packages/
easy-install.pth
*.so
*.o
*.a
*.la
*.lib
*.dll
*.dylib
```

### Development
```
.pytest_cache/
.coverage
htmlcov/
.tox/
.nox/
.hypothesis/
*.egg
*.egg-info/
.ruff_cache/
.pre-commit-config.yaml
.pre-commit-hooks.yaml
```

### Database & Logs
```
*.db
*.sqlite
*.sqlite3
*.log
*.logs
```

---

## JavaScript/TypeScript Projects

### Node Modules & Package Management
```
node_modules/
package-lock.json (read-only, don't analyze content)
yarn.lock (read-only)
pnpm-lock.yaml (read-only)
npm-debug.log
yarn-error.log
lerna-debug.log
```

### Build Output
```
.next/
dist/
build/
out/
.nuxt/
.vuepress/dist/
.docusaurus/
.cache/
.parcel-cache/
coverage/
.nyc_output/
```

### Development & Build Tools
```
.turbopack/
.webpack/
.babel-cache/
.eslintcache
.stylelintcache
.parcel-cache/
.grunt/
.rollup.cache/
.rts2_cache_*
.tsdist/
```

### Testing & Coverage
```
.nyc_output/
coverage/
jest/
.jest/
.vitest/
.mocha/
test-results/
junit.xml
coverage/
```

### IDE & Editors
```
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store
.sublime-*
.vim/
.netrwhist
tags
.tags
.editorconfig (config file, could be included)
.prettierignore (config, could be included)
```

### Environment & Secrets
```
.env.local
.env.*.local
.env.production.local
.env.development.local
.env.test.local
.env.example (keep for reference)
.env.sample (keep for reference)
```

### OS-Specific
```
.DS_Store
Thumbs.db
.directory
.~*
*.tmp
```

### Playwright & Testing
```
playwright-report/
.playwright/
test-results/
blob-report/
```

---

## Monorepo/Workspace
```
.lerna/
.turbo/
dist/
build/
out/
```

---

## Documentation & Artifacts
```
docs/.docusaurus/
docs/build/
site/
_book/
_site/
```

---

## Version Control & Git
```
.git/
.github/workflows/ (workflows usually contain CI/CD, could include or exclude based on needs)
.gitignore (config, could be included)
.gitattributes (config, could be included)
.gitmodules (config, could be included)
```

---

## Docker
```
.dockerignore
Dockerfile (include - config)
docker-compose.yml (include - config)
```

---

## CI/CD (Usually safe to skip actual logs)
```
.github/
.gitlab-ci.yml (include - config)
.circleci/
.travis.yml (include - config)
Jenkinsfile (include - config)
azure-pipelines.yml (include - config)
.github/workflows/ (include for understanding, but logs skip)
```

---

## Full Unified Exclusion List

### Directories (recursive exclude)
```
node_modules/
venv/
.venv/
env/
build/
dist/
.next/
.nuxt/
coverage/
.pytest_cache/
.tox/
.nox/
.hypothesis/
__pycache__/
.mypy_cache/
.ruff_cache/
.pytest_cache/
.turbopack/
.webpack/
.cache/
.parcel-cache/
.nyc_output/
.git/
.vscode/
.idea/
.turbo/
htmlcov/
.lerna/
site-packages/
.eslintcache
.stylelintcache
.babel-cache/
.rollup.cache/
.rts2_cache_*
.tsdist/
jest/
.jest/
.vitest/
.mocha/
playwright-report/
blob-report/
```

### Files (specific patterns)
```
*.pyc
*.pyo
*.pyd
*.so
*.o
*.a
*.egg
*.egg-info
*.whl
*.jar
*.class
*.pyc
*.log
*.logs
npm-debug.log
yarn-error.log
lerna-debug.log
.DS_Store
Thumbs.db
.directory
.~*
*.tmp
*.swp
*.swo
*~
package-lock.json (optional - read if tracking deps is needed)
yarn.lock (optional)
pnpm-lock.yaml (optional)
.env.local
.env.*.local
.env.production.local
.env.development.local
.env.test.local
.coverage
.rts2_cache_*
.turbo/
```

---

## Files TO KEEP (Source & Config)

### Python Source
```
*.py (all Python files)
setup.py
setup.cfg
pyproject.toml
Pipfile
requirements.txt
requirements-*.txt
tox.ini
pytest.ini
```

### Python Config
```
.flake8
.pylintrc
mypy.ini
black.toml
isort.cfg
poetry.lock (metadata about dependencies)
```

### JavaScript/TypeScript Source
```
*.js
*.jsx
*.ts
*.tsx
*.mjs
*.mts
*.cjs
*.json (keep most, exclude lock files)
*.html
*.css
*.scss
*.sass
*.less
```

### JavaScript/TypeScript Config
```
package.json
tsconfig.json
tsconfig.*.json
jest.config.js
vitest.config.js
eslint.config.js
.eslintrc*
.prettierrc*
babel.config.js
webpack.config.js
rollup.config.js
vite.config.js
next.config.js
nuxt.config.js
```

### Documentation & Config (Keep)
```
README.md
CHANGELOG.md
LICENSE
.gitignore
.gitattributes
Dockerfile
docker-compose.yml
.github/workflows/*.yml (CI configs)
.gitlab-ci.yml
.circleci/config.yml
Jenkinsfile
```

---

## Implementation

### For Python/Backend
```python
# File scanner exclusions
EXCLUDE_PATTERNS = [
    # Directories
    r'.*/__pycache__',
    r'.*/\.venv',
    r'.*/venv',
    r'.*/\.next',
    r'.*/build',
    r'.*/dist',
    r'.*/\.pytest_cache',
    r'.*/\.tox',
    r'.*/.mypy_cache',
    r'.*/\.ruff_cache',
    r'.*/htmlcov',
    r'.*/site-packages',
    
    # Files
    r'.*\.pyc$',
    r'.*\.pyo$',
    r'.*\.egg-info',
    r'.*\.log$',
    r'.*\.coverage$',
    
    # OS
    r'.*\.DS_Store$',
    r'.*Thumbs\.db$',
]

INCLUDE_PATTERNS = [
    r'.*\.py$',          # Python source
    r'.*\.md$',          # Documentation
    r'.*\.yml$',         # Config
    r'.*\.yaml$',        # Config
    r'.*\.toml$',        # Config
    r'.*\.json$',        # Config
    r'.*\.txt$',         # Text files
]
```

### For JavaScript/TypeScript Frontend
```javascript
// File scanner exclusions
const EXCLUDE_PATTERNS = [
    // Directories
    /.*\/node_modules/,
    /.*\/.next/,
    /.*\/dist/,
    /.*\/build/,
    /.*\/coverage/,
    /.*\/.turbo/,
    /.*\/.turbopack/,
    /.*\/.webpack/,
    /.*\/\.parcel-cache/,
    /.*\/.cache/,
    /.*\/\.nyc_output/,
    /.*\/\.vscode/,
    /.*\/\.idea/,
    /.*\/playwright-report/,
    /.*\/blob-report/,
    
    // Files
    /.*\.log$/,
    /.*\.swp$/,
    /.*\.swo$/,
    /.*~$/,
    /.*\.DS_Store$/,
    /.*Thumbs\.db$/,
    /.*\.env\.local$/,
    /.*\.env\..*\.local$/,
];

const INCLUDE_PATTERNS = [
    /.*\.(js|jsx|ts|tsx|mjs|mts|cjs)$/,  // Source
    /.*\.(json|yaml|yml|toml)$/,          // Config
    /.*\.(md|txt)$/,                       // Docs
    /.*\.html$/,                           // Templates
];
```

---

## Size & Impact Estimates

### Without Exclusions
- GitOnboard: ~2,495 files scanned
- Includes: node_modules, .next, __pycache__, build artifacts
- Unnecessary entities: ~5,000-10,000
- Unnecessary relationships: ~20,000-50,000
- Analysis time: ~100+ seconds

### With Exclusions  
- GitOnboard: ~1,200-1,500 files scanned
- Source only: Python + JS/TS files + configs
- Cleaner entities: ~27,000-28,000
- Relevant relationships: ~100,000-110,000
- Analysis time: ~60-80 seconds (faster + cleaner)

---

## Recommended Configuration

### Tier 1: Essential Excludes (Do this first)
```
node_modules/
.venv/
venv/
__pycache__/
.next/
build/
dist/
coverage/
.git/
.mypy_cache/
.pytest_cache/
.ruff_cache/
.turbo/
```

### Tier 2: IDE & OS Files
```
.vscode/
.idea/
.DS_Store
Thumbs.db
*.swp
*.swo
*~
```

### Tier 3: Logs & Temp
```
*.log
*.tmp
.env.local
```

---

**Note:** Adjust based on your specific project needs. Security scanning vs. architecture analysis may have different requirements.
