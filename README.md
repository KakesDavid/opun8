# 🦉 Opun8

<div align="center">

**Universal Deployment Platform — One Command. Zero Friction.**

[![PyPI version](https://img.shields.io/pypi/v/opun8.svg)](https://pypi.org/project/opun8/)
[![Python Version](https://img.shields.io/pypi/pyversions/opun8.svg)](https://pypi.org/project/opun8/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/KakesDavid/opun8.svg)](https://github.com/KakesDavid/opun8/stargazers)

Deploy to **Vercel**, **Netlify**, **Render**, and **GitHub** with a single command. Works on Windows, macOS, Linux, and Termux on Android.

[Documentation](https://opun8.dev/docs) · [Report Bug](https://github.com/KakesDavid/opun8/issues) · [Request Feature](https://github.com/KakesDavid/opun8/issues)

</div>

---

## ✨ Why Opun8?

Stop wrestling with different deployment workflows for every hosting provider. Opun8 brings Vercel, Netlify, Render, and GitHub into a single, unified CLI experience.

- 🚀 **One command** — Deploy to any platform with `opun8 deploy vercel`
- 🧠 **Smart detection** — Auto-detects React, Next.js, Vue, Node.js, Python, and static HTML
- 🔐 **Secure auth** — OAuth 2.0 + PKCE with PAT fallback
- 📱 **Works anywhere** — Windows, macOS, Linux, and Termux on Android
- 🏆 **History & badges** — Track every deployment and earn achievements
- 📂 **Native folder picker** — No more typing paths manually

---

## 📦 Installation

### Prerequisites
- Python 3.8 or higher

### Install via pip
```bash
pip install opun8
```

### Verify installation
```bash
opun8 --version
```

---

## 🚀 Quick Start

### 1. Navigate to your project
```bash
cd my-project
```

### 2. Detect your project
```bash
opun8 detect
```
```
✅ Detected: Next.js project
📦 Package manager: npm
🛠️ Build command: npm run build
📁 Output directory: .next
```

### 3. Authenticate with your provider
```bash
opun8 vercel
```

### 4. Deploy!
```bash
opun8 deploy vercel
```
```
🚀 Deploying to Vercel...
✅ Deployment complete!
🌐 Live at: https://my-project.vercel.app
```

---

## 📚 Commands

| Command | Description |
|---------|-------------|
| `opun8` | Show welcome screen |
| `opun8 --version` | Show version |
| `opun8 doctor` | Check environment |
| `opun8 detect` | Detect project type |
| `opun8 deploy vercel` | Deploy to Vercel |
| `opun8 deploy netlify` | Deploy to Netlify *(Coming soon)* |
| `opun8 deploy render` | Deploy to Render *(Coming soon)* |
| `opun8 github` | Connect to GitHub |
| `opun8 vercel` | Connect to Vercel |
| `opun8 history` | View deployment history |
| `opun8 badges` | View badge progress |
| `opun8 logout` | Logout from all services |
| `opun8 help` | Show all commands |

---

## 🎖️ Badge System

| Level | Badge | Name | Deployments |
|-------|-------|------|-------------|
| 1 | 🥉 | First Launch | 1 |
| 2 | 🥉 | Apprentice | 3 |
| 3 | 🥈 | Builder | 5 |
| 4 | 🥈 | Ship Captain | 10 |
| 5 | 🥇 | Deployment Master | 25 |
| 6 | 🥇 | Shipping Machine | 50 |
| 7 | 🏆 | Opun8 Legend | 100 |

---

## 🔧 Development

### Clone the repository
```bash
git clone https://github.com/KakesDavid/opun8.git
cd opun8
```

### Create a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### Install in editable mode
```bash
pip install -e .
```

### Run tests
```bash
pytest
```

---

## 🤝 Contributing

We welcome contributions! Here's how you can help:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

### Areas we need help with:
- Adding Render, Netlify, and Railway providers
- Improving documentation
- Writing tests
- Bug fixes

---

## 💖 Sponsors

Support Opun8 and help us build the future of universal deployment.

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-181717?logo=github)](https://github.com/sponsors/KakesDavid)
[![Open Collective](https://img.shields.io/badge/Sponsor-Open%20Collective-7B16FF?logo=opencollective)](https://opencollective.com/opun8)

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

Built with ❤️ by [Kakes David](https://github.com/KakesDavid) and the Opun8 community.

<div align="center">
  
**Star us on GitHub ★ — It helps more developers discover Opun8**

[![GitHub stars](https://img.shields.io/github/stars/KakesDavid/opun8.svg?style=social)](https://github.com/KakesDavid/opun8/stargazers)

</div>