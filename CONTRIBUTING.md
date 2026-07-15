# Contributing to LifeInAdventure-Tools

Thank you for your interest in contributing! 🎮

---

## How to Contribute

### 1. Reporting Bugs

- Check if the bug is already reported in [GitHub Issues](https://github.com/yourusername/LifeInAdventure-Tools/issues)
- Open a new issue with:
  - Clear title describing the bug
  - Steps to reproduce
  - Expected vs actual behavior
  - Your environment (OS, Python version, emulator)
  - Screenshot if applicable

### 2. Submitting Knowledge Base Data

The most valuable contribution is **quest/outcome data**:

- **Format**: JSON matching `docs/data/DATA_SCHEMA.md`
- **Process**: Submit via GitHub PR or open a Discussion
- **Verification**: Data will be validated against schema before merge
- **Credit**: Contributors will be credited in the KB changelog

Example contribution:
```json
{
  "quest_id": "q_custom_001",
  "title": "Your Quest Title",
  "type": "side",
  "events": [
    {
      "id": "evt_custom_01",
      "text": "Quest description...",
      "choices": [
        {
          "id": "ch_custom_01_a",
          "text": "Choice A",
          "stat_check": { "stat": "CHA", "threshold": 5 },
          "outcomes": [...]
        }
      ]
    }
  ]
}
```

### 3. Improving Documentation

- Fix typos, clarify explanations
- Add examples and screenshots
- Translate to other languages
- Improve OCR accuracy by contributing sample screenshots

### 4. Code Contributions

1. **Fork** the repository
2. **Create a branch**: `git checkout -b feature/my-feature`
3. **Write tests** for new functionality
4. **Follow** existing code style (PEP 8)
5. **Commit** with clear messages
6. **Push** and open a Pull Request

---

## Development Setup

```bash
# Clone
git clone https://github.com/yourusername/LifeInAdventure-Tools.git
cd LifeInAdventure-Tools

# Virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dev dependencies
pip install -r requirements.txt
pip install pytest pytest-cov

# Run tests
pytest

# Run with dev config
cp configs/default_config.yaml configs/dev_config.yaml
# Edit dev_config.yaml with your settings
LIA_CONFIG_PATH=configs/dev_config.yaml python src/main.py
```

---

## Code Style

- **Python**: PEP 8 (enforced via `ruff` or `black`)
- **Type hints**: Required for all function signatures
- **Docstrings**: Google style
- **Naming**:
  - Classes: `PascalCase`
  - Functions/variables: `snake_case`
  - Constants: `SCREAMING_SNAKE_CASE`
  - Private: prefix with `_`

---

## Commit Message Convention

```
type(scope): short description

[body]

[footer]
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `data`

Examples:
```
feat(ocr): add Korean language support for EasyOCR
fix(ui): prevent overlay from going off-screen
docs(kb): add 15 new quest entries from community data
data(quests): add Haunted Manor quest chain outcomes
```

---

## Questions?

- **Issues**: [GitHub Issues](https://github.com/yourusername/LifeInAdventure-Tools/issues)
- **Discussion**: [GitHub Discussions](https://github.com/yourusername/LifeInAdventure-Tools/discussions)
- **Discord**: [Life in Adventure Community](https://discord.gg/9JdYkGm2T3)
