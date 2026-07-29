## 📝 **Full Updated Content for `README.md`:**

```markdown
# 🦉 Opun8

<div align="center">

**Universal Deployment Platform — One Command. Zero Friction.**

[![PyPI version](https://img.shields.io/pypi/v/opun8.svg)](https://pypi.org/project/opun8/)
[![Python Version](https://img.shields.io/pypi/pyversions/opun8.svg)](https://pypi.org/project/opun8/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/KakesDavid/opun8.svg)](https://github.com/KakesDavid/opun8/stargazers)

Deploy to **Vercel**, **Netlify**, **Render**, and **GitHub** with a single command. Works on Windows, macOS, Linux, and Termux on Android.

[📖 Documentation](https://opun8.dev/docs) · [🐛 Report Bug](https://github.com/KakesDavid/opun8/issues) · [💡 Request Feature](https://github.com/KakesDavid/opun8/issues)

</div>

---

## ✨ Why Opun8?

Stop wrestling with different deployment workflows for every hosting provider. Opun8 brings Vercel, Render, Netlify, and GitHub into a single, unified CLI experience.

| Feature | Description |
|---------|-------------|
| 🚀 **One command** | Deploy with `opun8 deploy vercel`, `netlify`, or `render` — same shape every time |
| 🧠 **Smart detection** | Auto-detects React, Next.js, Vue, Node.js, Python, and static HTML projects |
| 🔐 **Secure auth** | OAuth 2.0 + PKCE by default, with personal access token fallback for CI |
| 💰 **Cost estimator** | See what a deployment will cost before you commit to it |
| 📱 **Works anywhere** | Windows, macOS, Linux, and Termux on Android — same binary, same commands |
| 🏅 **History & badges** | Every deployment is logged. Ship enough of them and you'll earn it |
| 📂 **Native folder picker** | A real file browser dialog — no more typing paths by hand |
| 🔑 **Interactive env vars** | Scans your source, detects required variables, prompts you for values |

---

## 📦 Installation

### Prerequisites
- Python 3.8 or higher

### Install via pip
```bash
pip install opun8
```

### Install with extras
```bash
# For clipboard support
pip install opun8[clipboard]

# For all features
pip install opun8[all]
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
# For Vercel
opun8 vercel

# For Netlify
opun8 netlify

# For Render
opun8 render

# For GitHub (needed for Render deployments)
opun8 github
```

### 4. Deploy!
```bash
# Deploy to Vercel
opun8 deploy vercel

# Deploy to Netlify
opun8 deploy netlify

# Deploy to Render
opun8 deploy render
```
```
🚀 Deploying...
✅ Deployment complete!
🌐 Live at: https://my-project.vercel.app
```

---

## 🔑 Interactive Environment Variables

Opun8 scans your source code to detect environment variables your project needs.

```bash
opun8 deploy netlify
```
```
🔐 Environment Variables Detected

Select variables to include:
  [x] DATABASE_URL     → used in app/config.py:15, models/db.py:22
  [x] API_KEY          → used in services/api.py:42
  [ ] SECRET_KEY       → used in app/settings.py:8

Commands:
  <number>  Toggle selection
  a         Select all
  n         Select none
  d         Done — proceed with selected
  q         Cancel

Enter value for DATABASE_URL: postgres://...
Enter value for API_KEY: ********

✅ Selected 2 environment variable(s) for deployment
🔒 1 sensitive value(s) hidden from display
```

---

## 📚 Commands

### Core Commands
| Command | Description |
|---------|-------------|
| `opun8` | Show welcome screen |
| `opun8 --version` | Show version |
| `opun8 doctor` | Check environment |
| `opun8 detect` | Detect project type |
| `opun8 deploy` | Deploy your project |
| `opun8 help` | Show all commands |

### Platform Commands
| Command | Description |
|---------|-------------|
| `opun8 github` | Connect to GitHub |
| `opun8 vercel` | Connect to Vercel |
| `opun8 netlify` | Connect to Netlify |
| `opun8 render` | Connect to Render |
| `opun8 vercel --logout` | Disconnect from Vercel |
| `opun8 netlify --logout` | Disconnect from Netlify |
| `opun8 render --logout` | Disconnect from Render |

### Deployment Commands
| Command | Description |
|---------|-------------|
| `opun8 deploy vercel` | Deploy to Vercel |
| `opun8 deploy netlify` | Deploy to Netlify |
| `opun8 deploy render` | Deploy to Render |

### Account Commands
| Command | Description |
|---------|-------------|
| `opun8 register` | Create an OPUN8 account |
| `opun8 login` | Log in to your account |
| `opun8 verify` | Verify email with OTP |
| `opun8 resend-otp` | Resend verification code |
| `opun8 status` | Check account status |
| `opun8 upgrade` | Upgrade subscription plan |
| `opun8 logout` | Logout from all services |

### Advanced Commands
| Command | Description |
|---------|-------------|
| `opun8 clone` | Clone any website |
| `opun8 history` | View deployment history |
| `opun8 badges` | View badge progress |

---

## 🎖️ Badge System

| Level | Badge | Name | Deployments |
|-------|-------|------|-------------|
| 1 | 🌱 | First Clone | 1 |
| 2 | 🔍 | Curious Explorer | 3 |
| 3 | 🧩 | Pattern Finder | 5 |
| 4 | 📚 | Archivist | 10 |
| 5 | 🚀 | Speed Runner | 25 |
| 6 | 🏆 | Master Archiver | 50 |
| 7 | 👑 | Clone King | 100 |

---

## ☁️ Provider Support

### ▲ Vercel
- OAuth 2.0 + PKCE authentication
- Project creation and management
- File upload and deployment
- Environment variable management
- Cost estimation
- URL renaming

### 📦 Netlify *(NEW in v0.1.5)*
- OAuth 2.0 authentication
- Site creation and management
- File upload and deployment
- Environment variable management
- Credit-based cost estimation
- Interactive name conflict resolution
- Personal Access Token support

### ☁️ Render
- GitHub repository deployment
- Service creation and management
- Environment variable management
- Deployment status polling
- Interactive name conflict resolution

### 🐙 GitHub
- Repository listing
- Repository cloning
- Push to GitHub

---

## 💰 Cost Estimator

Opun8 shows you deployment costs before you deploy.

### Vercel
```
┌──────────────────────────────────────────────────────────┐
│ ▲ Vercel Cost Estimate                                  │
│ Plan: Pro                                               │
│                                                          │
│ Seats           $20.00                                  │
│ Bandwidth       $0.00                                   │
│ Build Minutes   $0.00                                   │
│ Functions       $0.00                                   │
│ ─────────────────────────────────────────────────────── │
│ Total           $20.00/month                           │
└──────────────────────────────────────────────────────────┘
```

### Netlify
```
┌──────────────────────────────────────────────────────────┐
│ 📦 Netlify Cost Estimate                                │
│ Plan: Pro                                               │
│ Credit-based pricing                                    │
│                                                          │
│ Plan               $20.00                               │
│ ─────────────────────────────────────────────────────── │
│ Bandwidth          300 credits                          │
│ Compute            300 credits                          │
│ Web Requests       20 credits                           │
│ Production Deploys 75 credits                           │
│ ─────────────────────────────────────────────────────── │
│ Total Credits Used 695 credits                          │
│ Plan Credits       3,000 credits                        │
│ ─────────────────────────────────────────────────────── │
│ Total              $20.00/month                        │
│ 23% of plan credits used                                │
└──────────────────────────────────────────────────────────┘
```

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
- Adding Railway provider
- Improving documentation
- Writing tests
- Bug fixes
- UI/UX improvements

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
```

---

## 📋 **Summary:**

| Section | Content |
|---------|---------|
| **Badges** | PyPI, Python, License, Stars |
| **Why Opun8** | Feature table with emojis |
| **Installation** | pip, extras, verification |
| **Quick Start** | 4 steps with examples |
| **Interactive Env Vars** | Full UI example |
| **Commands** | Tables organized by category |
| **Badge System** | All 7 levels with emojis |
| **Provider Support** | Vercel, Netlify, Render, GitHub |
| **Cost Estimator** | Vercel + Netlify examples |
| **Development** | Clone, setup, tests |
| **Contributing** | PR process + help areas |